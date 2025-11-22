"""多渠道通知发送工具。"""
from __future__ import annotations

import html
import json
import os
import re
import smtplib
import logging
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from ai import AISummary
from fetcher.base_fetcher import NewsRecord
from utils.config_loader import DEFAULT_CONFIG_PATH as GLOBAL_CONFIG_PATH, load_settings
from utils.time_utils import get_timezone_helper

try:  # pragma: no cover - optional dependency
    from jieba import analyse as jieba_analyse
except ImportError:  # pragma: no cover
    jieba_analyse = None

DEFAULT_CONFIG_PATH = GLOBAL_CONFIG_PATH


class NotificationClient:
    """负责加载配置并将新闻发送到各通知渠道。"""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.config = self._load_config()
        self.enabled = self.config.get("enable", False)
        self.feishu = self.config.get("feishu", {})
        self.dingtalk = self.config.get("dingtalk", {})
        self.wechat_work = self.config.get("wechat_work", {})
        self.telegram = self.config.get("telegram", {})
        self.email = self.config.get("email", {})
        self.display_summary = bool(self.config.get("display_summary", True))
        self.tz_helper = get_timezone_helper(self.config_path)

    def _load_config(self) -> Dict[str, any]:  # type: ignore[override]
        settings = load_settings(self.config_path)
        cfg = settings.get("notification", {}) or {}
        # 兼容配置既能放在 notification 内，也能放在顶层
        cfg.setdefault("feishu", settings.get("feishu", {}))
        cfg.setdefault("dingtalk", settings.get("dingtalk", {}))
        cfg.setdefault("wechat_work", settings.get("wechat_work", {}))
        cfg.setdefault("telegram", settings.get("telegram", {}))
        cfg.setdefault("email", settings.get("email", {}))

        env_map = {
            ("feishu", "webhook_url"): os.environ.get("FEISHU_WEBHOOK", "").strip(),
            ("dingtalk", "webhook_url"): os.environ.get("DINGTALK_WEBHOOK", "").strip(),
            ("wechat_work", "webhook_url"): os.environ.get("WEWORK_WEBHOOK", "").strip(),
            ("telegram", "bot_token"): os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
            ("telegram", "chat_id"): os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
            ("email", "from"): os.environ.get("EMAIL_FROM", "").strip(),
            ("email", "password"): os.environ.get("EMAIL_PASSWORD", "").strip(),
            ("email", "to"): os.environ.get("EMAIL_TO", "").strip(),
            ("email", "smtp_server"): os.environ.get("EMAIL_SMTP_SERVER", "").strip(),
            ("email", "smtp_port"): os.environ.get("EMAIL_SMTP_PORT", "").strip(),
        }
        for (section, key), value in env_map.items():
            if value:
                cfg[section][key] = value
        return cfg

    def send(
        self,
        news: Iterable[NewsRecord],
        summaries: Optional[Dict[str, AISummary]] = None,
    ) -> Dict[str, bool]:
        records = list(news)
        results: Dict[str, bool] = {}
        if not self.enabled or not records:
            return results
        default_messages = self._format_messages(records, summaries or {})
        title = self.config.get("title", "News Digest")

        if self.feishu.get("webhook_url"):
            results["feishu"] = self._send_messages(
                default_messages,
                lambda text: self._send_feishu(self.feishu["webhook_url"], text),
            )
        if self.dingtalk.get("webhook_url"):
            results["dingtalk"] = self._send_messages(
                default_messages,
                lambda text: self._send_dingtalk(self.dingtalk["webhook_url"], text),
            )
        if self.wechat_work.get("webhook_url"):
            msgtype = self.wechat_work.get("msgtype", "text").lower()
            wechat_style = "markdown" if msgtype == "markdown" else "text"
            wechat_messages = default_messages if wechat_style == "text" else self._format_messages(records, summaries or {}, style=wechat_style)

            def _wechat_sender(text: str) -> bool:
                return self._send_wework(self.wechat_work["webhook_url"], text, msgtype)

            results["wechat_work"] = self._send_messages(wechat_messages, _wechat_sender)
        if self.telegram.get("bot_token") and self.telegram.get("chat_id"):
            telegram_messages = self._format_messages(records, summaries or {}, style="telegram")
            results["telegram"] = self._send_messages(
                telegram_messages,
                lambda text: self._send_telegram(
                    self.telegram["bot_token"],
                    self.telegram["chat_id"],
                    text,
                ),
            )
        if self.email.get("from") and self.email.get("to"):
            results["email"] = self._send_messages(
                default_messages,
                lambda text: self._send_email(title, text),
            )
        return results

    def _send_messages(self, messages: List[str], sender) -> bool:
        success = False
        for idx, text in enumerate(messages, start=1):
            if not text:
                continue
            try:
                delivery = sender(text)
                success = delivery or success
                logging.info("通知消息(%d/%d)发送结果: %s", idx, len(messages), "成功" if delivery else "失败")
            except Exception as exc:  # noqa: BLE001
                logging.warning("通知消息(%d/%d)发送异常: %s", idx, len(messages), exc)
        return success

    def _format_messages(
        self,
        news: List[NewsRecord],
        summaries: Dict[str, AISummary],
        *,
        style: str = "text",
    ) -> List[str]:
        if not news:
            return []
        batch_size = max(1, int(self.config.get("items_per_message", 3)))
        batches: List[str] = []
        current: List[str] = []
        count = 0
        sorted_news = self._sort_records_by_rule(news)
        last_group: Optional[Tuple[int, str]] = None
        separator = "\n\n\n" if style in {"text", "markdown"} else "\n\n"
        for item in sorted_news:
            summary = self._lookup_summary(summaries, item)
            group_key = self._group_key(item)
            header = ""
            if group_key != last_group:
                header = self._format_group_header(group_key, style=style)
            block = self._render_block(item, summary, style=style, show_category_line=False)
            if header:
                block = f"{header}\n\n{block}" if block else header
            last_group = group_key
            current.append(block)
            count += 1
            if count >= batch_size:
                batches.append(separator.join(current))
                current = []
                count = 0
        if current:
            batches.append(separator.join(current))
        return batches

    def _group_key(self, record: NewsRecord) -> Tuple[int, str]:
        raw = record.raw if isinstance(record.raw, dict) else {}
        idx = raw.get("_matched_rule_index")
        name = raw.get("_matched_rule") or "未分类"
        rank = idx if isinstance(idx, int) else 10**6
        return rank, name

    def _sort_records_by_rule(self, records: List[NewsRecord]) -> List[NewsRecord]:
        indexed = list(enumerate(records))
        indexed.sort(key=lambda pair: (self._group_key(pair[1])[0], pair[0]))
        return [record for _, record in indexed]

    def _format_group_header(self, group_key: Tuple[int, str], *, style: str) -> str:
        _, name = group_key
        display = name or "未分类"
        if style == "telegram":
            return f"<b>[{html.escape(display)}]</b>"
        if style == "markdown":
            return f"**[{display}]**"
        return f"[{display}]"

    def _render_block(
        self,
        item: NewsRecord,
        summary: AISummary,
        *,
        style: str = "text",
        show_category_line: bool = True,
    ) -> str:
        category = None
        if isinstance(item.raw, dict):
            category = item.raw.get("_matched_rule")
        summary_text = self._trim_summary(self._prepare_summary_text(summary, item))
        keywords = summary.keywords or summary.key_points
        if not keywords and isinstance(item.raw, dict):
            tags = item.raw.get("tags")
            if isinstance(tags, list):
                keywords = [tag.get("tag") if isinstance(tag, dict) else tag for tag in tags]
        keywords_text = ", ".join(filter(None, keywords or []))
        if not keywords_text:
            fallback_keywords = self._fallback_keywords(item, summary_text)
            if fallback_keywords:
                keywords_text = ", ".join(fallback_keywords)
        meta = summary.meta or {}
        publish_time = meta.get("publish_time")
        if not publish_time:
            publish_time = getattr(item, "published_at", None)
        if not publish_time and isinstance(item.raw, dict):
            publish_time = item.raw.get("published_at") or item.raw.get("timestamp")
        publish_time_display = self.tz_helper.to_display(publish_time)
        source = meta.get("source") or item.source or "Unknown"
        has_ai = self._has_ai_payload(summary)
        sentiment = self._extract_sentiment(summary) if has_ai else None
        sentiment_line = self._format_sentiment_line(sentiment)
        entity_items = self._collect_entity_strings(summary) if has_ai else []
        if style == "telegram":
            return self._render_block_telegram(
                item=item,
                category=category,
                keywords_text=keywords_text,
                publish_time=publish_time_display,
                source=source,
                sentiment_line=sentiment_line,
                entity_items=entity_items,
                summary_text=summary_text,
                show_category_line=show_category_line,
            )

        block: List[str] = []
        if show_category_line and category:
            block.append(f"[{category}]")
        title_line = self._render_plain_title_with_link(item)
        block.extend(
            [
                title_line,
                f"🌍 关键词：{keywords_text or '未标注'}",
                f"🕒 {publish_time_display or '未知时间'} | 🏷 {source}",
            ]
        )
        if self.display_summary:
            block.extend(["", "摘要：", summary_text])
        block.extend(
            [
                "",
                sentiment_line or "",
                f"*实体*: {'、'.join(entity_items)}" if entity_items else "",
            ]
        )
        block_lines = [line for line in block if line]
        block_lines.append("")  # 空行分隔
        return "\n".join(block_lines)

    def _lookup_summary(self, summaries: Dict[str, AISummary], record: NewsRecord) -> AISummary:
        key = record.url or f"{record.source}-{record.title}"
        summary = summaries.get(key)
        if summary:
            return summary
        return AISummary(
            source=record.source,
            title=record.title or "",
            url=record.url,
            summary=record.summary or "",
            sentiment=None,
        )

    def _trim_summary(self, text: str, max_lines: int = 3, max_chars: int = 300) -> str:
        if not text:
            return "暂无摘要"
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return text[:max_chars] + ("…" if len(text) > max_chars else "")
        trimmed = " ".join(lines[:max_lines])
        truncated = trimmed[:max_chars].rstrip()
        if len(lines) > max_lines or len(trimmed) > max_chars:
            truncated += " …"
        return truncated

    def _send_feishu(self, webhook: str, text: str) -> bool:
        payload = {"msg_type": "text", "content": {"text": text}}
        return self._post_json(webhook, payload)

    def _send_dingtalk(self, webhook: str, text: str) -> bool:
        payload = {"msgtype": "text", "text": {"content": text}}
        return self._post_json(webhook, payload)

    def _send_wework(self, webhook: str, text: str, msgtype: str = "text") -> bool:
        msgtype = msgtype.lower()
        if msgtype == "markdown":
            payload = {"msgtype": "markdown", "markdown": {"content": text}}
        else:
            payload = {"msgtype": "text", "text": {"content": text}}
        return self._post_json(webhook, payload)

    def _render_block_telegram(
        self,
        *,
        item: NewsRecord,
        category: Optional[str],
        keywords_text: str,
        publish_time: Optional[str],
        source: str,
        sentiment_line: Optional[str],
        entity_items: List[str],
        summary_text: str,
        show_category_line: bool,
    ) -> str:
        def esc(value: Optional[str]) -> str:
            return html.escape(value or "")

        lines: List[str] = []
        if show_category_line and category:
            lines.append(f"[{esc(category)}]")
        lines.extend(
            [
                self._render_title_with_link(item, esc),
                f"🌍 关键词：{esc(keywords_text) or '未标注'}",
                f"🕒 {esc(publish_time or '未知时间')} | 🏷 {esc(source)}",
            ]
        )
        if self.display_summary:
            lines.extend(["", "<b>摘要：</b>", esc(summary_text)])
        lines.extend(
            [
                "",
                sentiment_line or "",
                f"<b>实体</b>: {'、'.join(esc(item) for item in entity_items)}" if entity_items else "",
            ]
        )
        return "\n".join(filter(None, lines))

    def _render_title_with_link(self, item: NewsRecord, esc) -> str:
        if item.url:
            return f"📰 <a href=\"{esc(item.url)}\">{esc(item.title or '未命名')}</a>"
        return f"📰 {esc(item.title or '未命名')}"

    def _render_plain_title_with_link(self, item: NewsRecord) -> str:
        if item.url:
            return f"📰 [{item.title or '未命名'}]({item.url})"
        return f"📰 {item.title or '未命名'}"

    def _has_ai_payload(self, summary: AISummary) -> bool:
        if getattr(summary, "is_ai", False):
            return True
        return bool(summary.raw_response)

    def _extract_sentiment(self, summary: AISummary) -> Optional[Dict[str, Any]]:
        raw = summary.sentiment
        if not raw:
            return None
        defaults = {"label": "neutral", "reason": "", "level": "中", "score": 0}
        if isinstance(raw, dict):
            merged = {**defaults, **raw}
        elif isinstance(raw, str):
            merged = {**defaults, "label": raw}
        else:
            return None
        merged["label"] = str(merged.get("label") or defaults["label"]).lower()
        merged["reason"] = str(merged.get("reason") or "")
        merged["level"] = self._normalize_level(merged.get("level"))
        merged["score"] = self._safe_sentiment_score(merged.get("score"))
        return merged

    def _format_sentiment_line(self, sentiment: Optional[Dict[str, Any]]) -> Optional[str]:
        if not sentiment:
            return None
        label_map = {
            "positive": ("积极", "🟩"),
            "negative": ("消极", "🟥"),
            "neutral": ("中性", "🟨"),
        }
        label_cn, icon = label_map.get(sentiment.get("label"), ("未知", "⚪️"))
        level = sentiment.get("level") or "中"
        score = sentiment.get("score") if isinstance(sentiment.get("score"), int) else 0
        return f"情绪：{label_cn}{icon}｜等级：{level}｜指数：{score}"

    def _collect_entity_strings(self, summary: AISummary, limit: int = 3) -> List[str]:
        entities = summary.entities if isinstance(summary.entities, list) else []
        formatted: List[str] = []
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            text = str(entity.get("text") or "").strip()
            if not text:
                continue
            entity_type = str(entity.get("type") or "").strip()
            if entity_type:
                formatted.append(f"{text}({entity_type})")
            else:
                formatted.append(text)
            if len(formatted) >= limit:
                break
        return formatted

    def _fallback_keywords(self, item: NewsRecord, summary_text: str, max_keywords: int = 5) -> List[str]:
        title = item.title or ""
        raw_content = ""
        if isinstance(item.raw, dict):
            detail = item.raw.get("detail") if isinstance(item.raw.get("detail"), dict) else {}
            raw_content = str(item.raw.get("content_text") or detail.get("summary") or "")
        text = "\n".join(part for part in [title, summary_text or "", raw_content] if part)
        text = text.strip()
        if not text:
            return []
        keywords: List[str] = []
        if jieba_analyse is not None:
            try:
                keywords = [kw for kw in jieba_analyse.extract_tags(text, topK=max_keywords) if kw]
            except Exception:  # pragma: no cover
                keywords = []
        if keywords:
            return keywords
        tokens = [token.strip() for token in re.split(r"[\s,，。！？；:、|]+", text) if token.strip()]
        return tokens[:max_keywords]

    def _normalize_level(self, level: Any) -> str:
        if isinstance(level, str):
            text = level.strip()
        else:
            text = ""
        if not text:
            return "中"
        lowered = text.lower()
        mapping = {"low": "低", "medium": "中", "mid": "中", "high": "高"}
        return mapping.get(lowered, text)

    def _safe_sentiment_score(self, score: Any) -> int:
        try:
            return int(round(float(score)))
        except (TypeError, ValueError):
            return 0

    def _send_telegram(self, token: str, chat_id: str, text: str) -> bool:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            response = requests.post(url, data=data, timeout=15)
            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            logging.warning("通知 webhook(%s) 请求失败: %s", url, exc)
            return False

    def _send_email(self, subject: str, body: str) -> bool:
        smtp_server = self.email.get("smtp_server") or "smtp.qq.com"
        smtp_port = int(self.email.get("smtp_port") or 465)
        sender = self.email.get("from")
        password = self.email.get("password")
        recipients = [addr.strip() for addr in self.email.get("to", "").split(",") if addr.strip()]
        if not sender or not password or not recipients:
            return False
        message = MIMEText(body, "plain", "utf-8")
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = ", ".join(recipients)
        try:
            if smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
            with server:
                server.login(sender, password)
                server.sendmail(sender, recipients, message.as_string())
            return True
        except Exception:
            return False

    def _post_json(self, url: str, payload: dict) -> bool:
        try:
            response = requests.post(url, json=payload, timeout=15)
            response.raise_for_status()
            content = {}
            try:
                content = response.json()
            except ValueError:
                content = {"text": response.text}
            logging.info("通知 webhook(%s) 返回: %s", url, content)
            if isinstance(content, dict):
                err_code = content.get("errcode")
                if err_code not in (None, 0):
                    logging.warning("通知 webhook(%s) errcode=%s errmsg=%s", url, err_code, content.get("errmsg"))
                    return False
            return True
        except requests.RequestException:
            return False

    def _prepare_summary_text(self, summary: AISummary, item: NewsRecord) -> str:
        candidate: Optional[str] = summary.summary or item.summary
        if isinstance(candidate, dict):
            candidate = candidate.get("summary") or candidate.get("content") or json.dumps(candidate, ensure_ascii=False)
        if not candidate and isinstance(item.raw, dict):
            candidate = item.raw.get("detail", {}).get("teaser") if isinstance(item.raw.get("detail"), dict) else None
        text = str(candidate or "暂无摘要")
        stripped = text.strip()
        if not stripped:
            return "暂无摘要"
        parsed = self._extract_json_summary(stripped)
        return parsed or text

    def _extract_json_summary(self, text: str) -> Optional[str]:
        lower = text.lower()
        raw_json = None
        if lower.startswith("json"):
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                raw_json = text[start : end + 1]
        elif text.startswith("{") and text.endswith("}"):
            raw_json = text
        if not raw_json:
            return None
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            return None
        if isinstance(data, dict):
            return data.get("summary") or data.get("content") or data.get("text")
        return None
