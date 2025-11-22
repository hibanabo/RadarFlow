"""通用的 OpenAI 风格接口封装。"""
from __future__ import annotations

import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

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
        self.use_article_body = bool(self.config.get("use_article_body", True))
        self.identity_hint = self.config.get("identity_hint") or "保持专业中立、关注风险敞口的分析视角"
        self.tz_helper = get_timezone_helper(self.config_path)

    def _load_config(self) -> Dict[str, any]:  # type: ignore[override]
        settings = load_settings(self.config_path)
        return settings.get("ai", {})

    def summarize_news(self, records: Iterable[NewsRecord]) -> List[AISummary]:
        summaries: List[AISummary] = []
        if not self.enabled or not self.api_key:
            return summaries
        for record in records:
            summary = self._summarize_single(record)
            if summary:
                summaries.append(summary)
                logger.info("[AI]%s -> %s", record.title or record.source, summary.summary)
        return summaries

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
            logger.warning("AI 请求失败: %s", exc)
            return None
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        structured = self._ensure_schema(self._parse_ai_output(content), record)
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
        return AISummary(
            source=record.source,
            title=record.title or "",
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

    def _select_content(self, record: NewsRecord) -> str:
        if self.use_article_body and isinstance(record.raw, dict):
            content = record.raw.get("content_text")
            if content:
                return str(content)
        return record.summary or ""

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
