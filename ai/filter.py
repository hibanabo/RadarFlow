"""AI 摘要的后置过滤器。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from fetcher.base_fetcher import NewsRecord
from utils.config_loader import DEFAULT_CONFIG_PATH, load_settings

from .types import AISummary

logger = logging.getLogger(__name__)


class AISummaryFilter:
    """根据 AI 输出的主题、情绪等维度筛选需要推送的新闻。"""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        settings = load_settings(config_path or DEFAULT_CONFIG_PATH)
        cfg = settings.get("ai_filter", {}) or {}
        self.enabled = bool(cfg.get("enabled", False))
        ai_cfg = settings.get("ai", {}) or {}
        ai_enabled = bool(ai_cfg.get("enabled", False))
        if not ai_enabled:
            self.enabled = False
        category_cfg = self._normalize_section(cfg.get("categories"))
        sentiment_cfg = self._normalize_section(cfg.get("sentiments"))
        self.category_include = self._normalize_values(category_cfg.get("include"))
        self.category_exclude = self._normalize_values(category_cfg.get("exclude"))
        self.sentiment_include = self._normalize_values(sentiment_cfg.get("include"))
        self.sentiment_exclude = self._normalize_values(sentiment_cfg.get("exclude"))

    def apply(
        self,
        records: Sequence[NewsRecord],
        summary_map: Dict[str, AISummary],
    ) -> Tuple[List[NewsRecord], Dict[str, AISummary]]:
        if not self.enabled:
            return list(records), dict(summary_map)
        kept: List[NewsRecord] = []
        filtered_summary_map: Dict[str, AISummary] = {}
        removed = 0
        for record in records:
            raw = record.raw if isinstance(record.raw, dict) else {}
            if raw.get("_ai_summary_blocked"):
                removed += 1
                logger.info("AI 摘要被拦截，跳过: %s - %s", record.source, record.title)
                continue
            key = self._record_key(record)
            summary = summary_map.get(key)
            if self._should_keep(summary):
                kept.append(record)
                if summary:
                    filtered_summary_map[key] = summary
            else:
                removed += 1
                logger.debug("AI 过滤器剔除: %s - %s", record.source, record.title)
        if removed:
            logger.info("AI 过滤器过滤 %d 条新闻，剩余 %d 条。", removed, len(kept))
        return kept, filtered_summary_map

    def _should_keep(self, summary: Optional[AISummary]) -> bool:
        if summary is None:
            return not self._requires_summary_fields()
        if isinstance(summary.meta, dict) and summary.meta.get("_fallback_no_ai"):
            return True
        if not self._match_categories(summary):
            return False
        if not self._match_sentiment(summary):
            return False
        return True

    def _match_categories(self, summary: AISummary) -> bool:
        topics = summary.topics or []
        normalized_topics = {self._normalize_token(topic) for topic in topics if self._normalize_token(topic)}
        if self.category_include and not (normalized_topics & self.category_include):
            return False
        if self.category_exclude and (normalized_topics & self.category_exclude):
            return False
        return True

    def _match_sentiment(self, summary: AISummary) -> bool:
        sentiment = summary.sentiment or {}
        label = self._normalize_token(sentiment.get("label"))
        if self.sentiment_include and (not label or label not in self.sentiment_include):
            return False
        if self.sentiment_exclude and label and label in self.sentiment_exclude:
            return False
        return True

    def _requires_summary_fields(self) -> bool:
        return bool(self.category_include or self.sentiment_include)

    def _normalize_section(self, value: Optional[object]) -> Dict[str, List[str]]:
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            return {"include": value}
        return {}

    def _normalize_values(self, values: Optional[Sequence[object]]) -> set[str]:
        normalized: set[str] = set()
        if not values:
            return normalized
        for item in values:
            token = self._normalize_token(item)
            if token:
                normalized.add(token)
        return normalized

    def _normalize_token(self, value: Optional[object]) -> str:
        if value is None:
            return ""
        return str(value).strip().lower()

    def _record_key(self, record: NewsRecord) -> str:
        return record.url or f"{record.source}-{record.title}"
