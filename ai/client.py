"""通用的 OpenAI 风格接口封装。"""
from __future__ import annotations

import json
import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from .types import AISummary
from fetcher.base_fetcher import NewsRecord
from utils.config_loader import DEFAULT_CONFIG_PATH, load_settings
from utils.time_utils import get_timezone_helper

DEFAULT_PROMPT_FILE = Path("prompts/news_summary.md")


logger = logging.getLogger(__name__)


class AIClient:
    """读取配置并调用 OpenAI 兼容接口生成摘要。"""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.config = self._load_config()
        self.enabled = self.config.get("enabled", False)
        self.base_url = self.config.get("base_url", "https://api.openai.com/v1")
        self.model = self.config.get("model", "gpt-4o-mini")
        self.api_key = (
            os.environ.get("ARK_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or self.config.get("api_key", "")
        )
        prompt_file = self.config.get("prompt_file") or str(DEFAULT_PROMPT_FILE)
        self.prompt_template = Path(prompt_file).read_text(encoding="utf-8") if Path(prompt_file).exists() else ""
        self.system_prompt = self.config.get("system_prompt", "你是一名严谨的中文财经记者，请根据指定信息生成摘要。")
        self.reasoning_effort = self.config.get("reasoning_effort")
        self.temperature = self.config.get("temperature")
        self.timeout = int(self.config.get("timeout_sec", 30))
        self.max_items = int(self.config.get("max_items", 5))
        max_workers = self.config.get("max_workers")
        try:
            self.max_workers = max(1, int(max_workers)) if max_workers is not None else 3
        except (TypeError, ValueError):
            self.max_workers = 3
        self.use_article_body = bool(self.config.get("use_article_body", True))
        self.identity_hint = self.config.get("identity_hint") or "保持专业中立、关注风险敞口的分析视角"
        self.fail_open_on_error = bool(self.config.get("fail_open_on_error", True))
        self.tz_helper = get_timezone_helper(self.config_path)

    def _load_config(self) -> Dict[str, any]:  # type: ignore[override]
        settings = load_settings(self.config_path)
        return settings.get("ai", {})

    def summarize_news(self, records: Iterable[NewsRecord]) -> List[AISummary]:
        record_list = list(records)
        summaries: List[Tuple[int, AISummary]] = []
        if not self.enabled or not self.api_key or not record_list:
            return []
        if len(record_list) == 1 or self.max_workers <= 1:
            for idx, record in enumerate(record_list):
                summary = self._summarize_single(record)
                if summary:
                    summaries.append((idx, summary))
                    logger.info("[AI]%s -> %s", record.title or record.source, summary.summary)
            return [summary for _, summary in summaries]
        max_workers = min(self.max_workers, len(record_list))
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ai-summary") as executor:
            future_map = {
                executor.submit(self._summarize_single, record): (idx, record)
                for idx, record in enumerate(record_list)
            }
            for future in as_completed(future_map):
                idx, record = future_map[future]
                try:
                    summary = future.result()
                except Exception as exc:  # noqa: BLE001
                    logger.exception("AI 摘要单条调用失败: %s", exc)
                    summary = None
                if summary:
                    summaries.append((idx, summary))
                    logger.info("[AI]%s -> %s", record.title or record.source, summary.summary)
        summaries.sort(key=lambda pair: pair[0])
        return [summary for _, summary in summaries]

    def _summarize_single(self, record: NewsRecord) -> Optional[AISummary]:
        prompt = self._render_prompt(record)
        logger.debug("AI prompt:\n%s", prompt)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            error_text = ""
            if exc.response is not None:
                try:
                    error_text = exc.response.text[:1000]
                except Exception:
                    error_text = "<无法读取响应>"
            logger.warning("AI 请求失败: %s | payload=%s | response=%s", exc, payload, error_text)
            return self._handle_summary_failure(record, "request_error")
        try:
            data = response.json()
        except ValueError as exc:  # noqa: B007
            logger.warning("AI 响应解析失败: %s", exc)
            return self._handle_summary_failure(record, "invalid_json")
        usage = data.get("usage")
        self._log_usage(usage, record.title, stage="AI 摘要")
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if not content:
            logger.warning("AI 摘要返回空内容: %s", record.title)
            return self._handle_summary_failure(record, "empty_content")
        structured = self._ensure_schema(self._parse_ai_output(content), record)
        summary_text = structured.get("summary") or ""
        if self._is_refusal_summary(summary_text, usage):
            logger.warning("AI 摘要疑似拒答或无效输出，改用原始信息: %s", record.title)
            return self._handle_summary_failure(record, "ai_refusal")
        logger.debug("AI 返回: %s", structured)
        meta = structured.get("meta") if isinstance(structured.get("meta"), dict) else None
        keywords = structured.get("keywords")
        key_points = structured.get("key_points")
        entities = structured.get("entities")
        events = structured.get("events")
        topics = structured.get("topics")
        if not isinstance(keywords, list):
            keywords = []
        if not isinstance(key_points, list):
            key_points = []
        if not isinstance(entities, list):
            entities = []
        if not isinstance(events, list):
            events = []
        if not isinstance(topics, list):
            topics = []
        else:
            normalized_topics = []
            for topic in topics:
                text = str(topic or "").strip()
                if text:
                    normalized_topics.append(text)
            topics = normalized_topics
        sentiment_data = self._normalize_sentiment(structured.get("sentiment"))
        ai_title = (
            (meta.get("title") if meta else None)
            or structured.get("title")
            or record.title
            or ""
        )
        return AISummary(
            source=record.source,
            title=str(ai_title or "").strip() or (record.title or ""),
            url=record.url,
            summary=structured.get("summary") or content,
            sentiment=sentiment_data,
            keywords=keywords,
            key_points=key_points,
            entities=entities,
            events=events,
            topics=topics,
            meta=meta,
            raw_response=data,
            is_ai=True,
        )

    def _render_prompt(self, record: NewsRecord) -> str:
        template = self.prompt_template or "请总结以下新闻：\n标题：{title}\n来源：{source}\n内容：{content}\n链接：{url}"
        values = {
            "title": record.title or "",
            "source": record.source or "",
            "summary": record.summary or "",
            "url": record.url or "",
            "content": self._select_content(record),
            "identity_hint": self.identity_hint,
            "current_time": self._current_time_text(),
            "publish_time": self._record_publish_time(record),
        }
        rendered = template
        for key, val in values.items():
            safe_val = str(val or "")
            rendered = rendered.replace(f"{{{key}}}", safe_val)
        return rendered

    def _parse_ai_output(self, content: str) -> Dict[str, any]:  # type: ignore[override]
        """尝试解析 JSON，如果失败则回退到纯文本摘要。"""
        cleaned = self._clean_ai_content(content)
        parsed = self._try_decode_json(cleaned)
        if isinstance(parsed, dict):
            return parsed
        return {"summary": cleaned}

    def _ensure_schema(self, data: Dict[str, any], record: NewsRecord) -> Dict[str, any]:
        publish_time = None
        if isinstance(record.raw, dict):
            publish_time = record.raw.get("published_at") or record.raw.get("published")
        publish_time = publish_time or getattr(record, "published_at", None)
        meta_default = {
            "title": record.title or "",
            "publish_time": publish_time or "",
            "source": record.source or "",
        }
        sentiment_default = self._sentiment_defaults()
        impact_default = {"risks": [], "market_impact": "", "industry_impact": "", "company_impact": ""}

        data.setdefault("summary", "")
        data.setdefault("keywords", [])
        data.setdefault("key_points", [])
        data.setdefault("entities", [])
        data.setdefault("events", [])
        data.setdefault("topics", [])
        data.setdefault("meta", meta_default)
        data.setdefault("impact", impact_default)
        data["meta"] = {**meta_default, **data.get("meta", {})}
        data["impact"] = {**impact_default, **data.get("impact", {})}
        sentiment_value = data.get("sentiment")
        data["sentiment"] = self._normalize_sentiment(sentiment_value) or sentiment_default
        return data

    def _fallback_summary(self, record: NewsRecord, reason: str) -> AISummary:
        snippet = self._build_fallback_snippet(record)
        note = "（AI 摘要失败，展示原文片段）"
        summary_text = f"{snippet}\n\n{note}" if snippet else note
        publish_time = getattr(record, "published_at", None)
        if isinstance(record.raw, dict):
            publish_time = record.raw.get("published_at") or publish_time
        meta = {
            "title": record.title or "",
            "publish_time": publish_time or "",
            "source": record.source or "",
            "_fallback_no_ai": True,
            "_fallback_reason": reason,
        }
        sentiment = {"label": "unknown", "score": None}
        return AISummary(
            source=record.source,
            title=record.title or "",
            url=record.url,
            summary=summary_text,
            sentiment=sentiment,
            keywords=[],
            key_points=[],
            entities=[],
            events=[],
            topics=[],
            meta=meta,
            raw_response=None,
            is_ai=False,
        )

    def _handle_summary_failure(self, record: NewsRecord, reason: str) -> Optional[AISummary]:
        if self.fail_open_on_error:
            return self._fallback_summary(record, reason)
        self._mark_summary_block(record, reason)
        return None

    def _mark_summary_block(self, record: NewsRecord, reason: str) -> None:
        if not isinstance(record.raw, dict):
            record.raw = {}
        record.raw["_ai_summary_blocked"] = True
        record.raw["_ai_summary_error"] = reason

    def _build_fallback_snippet(self, record: NewsRecord) -> str:
        candidates: List[str] = []
        if record.summary:
            candidates.append(str(record.summary))
        if isinstance(record.raw, dict):
            for key in ("content_text", "description"):
                value = record.raw.get(key)
                if value:
                    candidates.append(str(value))
        candidates.append(record.title or "")
        for text in candidates:
            snippet = str(text or "").strip()
            if not snippet:
                continue
            max_chars = 400
            return snippet[:max_chars].rstrip() + ("..." if len(snippet) > max_chars else "")
        return "该新闻暂无法生成 AI 摘要，请查看原文链接。"

    def _is_refusal_summary(self, summary_text: str, usage: Any) -> bool:
        text = (summary_text or "").strip()
        prompt_tokens, completion_tokens, total_tokens = self._usage_token_tuple(usage)
        if not text:
            return True
        lowered = text.lower()
        head = lowered[:60]
        refusal_prefixes = [
            "抱歉",
            "很抱歉",
            "十分抱歉",
            "我无法",
            "我不能",
            "无法满足",
            "无法提供",
            "不支持",
            "不能满足",
            "未找到相关",
            "无权回答",
            "抱歉，这个问题",
            "抱歉，未找到",
            "i'm sorry",
            "i am sorry",
            "sorry,",
            "i cannot",
            "i can’t",
            "cannot comply",
            "not able to",
            "sensitive content",
            "no relevant result",
            "this request is not",
        ]
        if any(head.startswith(marker) for marker in refusal_prefixes):
            return True
        # 某些兼容 API 在未统计 tokens 时会返回 0，此时不应直接视为拒答
        # 仅在文本为空或命中上面的拒答短语时才回退
        return False

    def _usage_token_tuple(self, usage: Any) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        if not isinstance(usage, dict):
            return None, None, None
        return (
            self._safe_int(usage.get("prompt_tokens")),
            self._safe_int(usage.get("completion_tokens")),
            self._safe_int(usage.get("total_tokens")),
        )

    def _safe_int(self, value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _select_content(self, record: NewsRecord) -> str:
        if self.use_article_body and isinstance(record.raw, dict):
            content = record.raw.get("content_text")
            if content:
                return str(content)
        if record.summary:
            return str(record.summary)
        if isinstance(record.raw, dict):
            for key in ("description", "content_text"):
                value = record.raw.get(key)
                if value:
                    return str(value)
        return record.title or ""

    def _current_time_text(self) -> str:
        tz = getattr(self.tz_helper, "tzinfo", None)
        now = datetime.now(tz) if tz else datetime.now()
        return now.strftime("%Y-%m-%d %H:%M")

    def _record_publish_time(self, record: NewsRecord) -> str:
        publish_time = None
        if isinstance(record.raw, dict):
            publish_time = record.raw.get("published_at") or record.raw.get("published")
        publish_time = publish_time or getattr(record, "published_at", None)
        return str(publish_time or "")

    def _clean_ai_content(self, content: str) -> str:
        text = content.strip()
        text = self._strip_code_block(text)
        text = self._strip_json_prefix(text)
        return text.strip()

    def _strip_code_block(self, text: str) -> str:
        if not text.startswith("```"):
            return text
        without_open = text[3:]
        closing_index = without_open.rfind("```")
        if closing_index != -1:
            return without_open[:closing_index].strip()
        return text

    def _strip_json_prefix(self, text: str) -> str:
        stripped = text.lstrip()
        lowered = stripped.lower()
        if lowered.startswith("json"):
            remainder = stripped[4:]
            return remainder.lstrip(" :\n")
        return text

    def _try_decode_json(self, text: str) -> Optional[Any]:
        if not text:
            return None
        decoder = json.JSONDecoder()
        try:
            return decoder.decode(text)
        except json.JSONDecodeError:
            pass
        for idx, ch in enumerate(text):
            if ch in "{[":
                try:
                    parsed, _ = decoder.raw_decode(text[idx:])
                    return parsed
                except json.JSONDecodeError:
                    continue
        return None

    def _sentiment_defaults(self) -> Dict[str, Any]:
        return {"label": "neutral", "reason": "", "level": "中", "score": 0}

    def _normalize_sentiment(self, value: Any) -> Optional[Dict[str, Any]]:
        defaults = self._sentiment_defaults()
        if isinstance(value, dict):
            merged = {**defaults, **value}
        elif isinstance(value, str):
            merged = {**defaults, "label": value}
        else:
            return None
        merged["label"] = str(merged.get("label") or defaults["label"]).lower()
        merged["reason"] = str(merged.get("reason") or "")
        merged["level"] = str(merged.get("level") or defaults["level"])
        merged["score"] = self._safe_sentiment_score(merged.get("score"))
        return merged

    def _safe_sentiment_score(self, value: Any) -> int:
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return 0

    def _log_usage(self, usage: Any, title: Optional[str], stage: str) -> None:
        if not isinstance(usage, dict):
            return
        def _to_int(val: Any) -> Optional[int]:
            try:
                return int(val)
            except (TypeError, ValueError):
                return None

        prompt = _to_int(usage.get("prompt_tokens"))
        completion = _to_int(usage.get("completion_tokens"))
        total = _to_int(usage.get("total_tokens"))
        if total is None and prompt is not None and completion is not None:
            total = prompt + completion
        if all(v is None for v in (prompt, completion, total)):
            return
        safe_title = (title or "").strip() or "未知标题"
        try:
            raw_usage = json.dumps(usage, ensure_ascii=False)
        except TypeError:
            raw_usage = str(usage)
        logger.info(
            "[AI tokens] %s | %s | prompt=%s completion=%s total=%s",
            stage,
            safe_title,
            prompt if prompt is not None else "-",
            completion if completion is not None else "-",
            total if total is not None else "-",
        )
        if prompt == completion == total == 0:
            logger.info("[AI usage raw] %s | %s | %s", stage, safe_title, raw_usage)
