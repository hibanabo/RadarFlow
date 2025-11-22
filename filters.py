"""关键词过滤器，支持多条规则与 AND/OR 组合。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from fetcher.base_fetcher import NewsRecord
from utils.config_loader import DEFAULT_CONFIG_PATH, load_settings

logger = logging.getLogger(__name__)

DEFAULT_FILTER_PATH = DEFAULT_CONFIG_PATH


@dataclass
class FilterRule:
    name: str
    action: str = "allow"  # allow or deny
    all_of: List[str] = field(default_factory=list)
    any_of: List[str] = field(default_factory=list)
    none_of: List[str] = field(default_factory=list)
    enabled: bool = True

    def matches(self, text: str) -> bool:
        if not self.enabled:
            return False
        lowered = text.lower()
        if self.all_of and any(keyword.lower() not in lowered for keyword in self.all_of):
            return False
        if self.any_of and not any(keyword.lower() in lowered for keyword in self.any_of):
            return False
        if self.none_of and any(keyword.lower() in lowered for keyword in self.none_of):
            return False
        return True


class FilterSet:
    """根据配置文件过滤新闻。"""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or DEFAULT_FILTER_PATH
        self.enabled = False
        self.default_action = "allow"
        self.rules: List[FilterRule] = []
        self._load()

    def _load(self) -> None:
        settings = load_settings(self.path)
        config = settings.get("filters", {})
        if not config:
            logger.info("未在 %s 中找到 filters 配置，默认不过滤", self.path)
            return
        self.enabled = config.get("enabled", False)
        self.default_action = config.get("default_action", "allow")
        for rule_cfg in config.get("rules", []):
            rule = FilterRule(
                name=rule_cfg.get("name", "unnamed"),
                action=rule_cfg.get("action", "allow"),
                all_of=rule_cfg.get("all_of", []) or [],
                any_of=rule_cfg.get("any_of", []) or [],
                none_of=rule_cfg.get("none_of", []) or [],
                enabled=rule_cfg.get("enabled", True),
            )
            self.rules.append(rule)

    def apply(self, records: Iterable[NewsRecord]) -> List[NewsRecord]:
        if not self.enabled or not self.rules:
            return list(records)
        allowed: List[NewsRecord] = []
        for record in records:
            text = self._combine_text(record)
            action, rule_name, rule_index = self._evaluate(text)
            if action == "allow":
                if isinstance(record.raw, dict):
                    if rule_name:
                        record.raw["_matched_rule"] = rule_name
                    if rule_index is not None:
                        record.raw["_matched_rule_index"] = rule_index
                allowed.append(record)
            else:
                logger.debug("新闻被过滤: %s - %s", record.source, record.title)
        logger.info("过滤后剩余 %d 条新闻", len(allowed))
        return allowed

    def _evaluate(self, text: str) -> Tuple[str, Optional[str], Optional[int]]:
        for idx, rule in enumerate(self.rules):
            if rule.matches(text):
                return rule.action, rule.name, idx
        return self.default_action, None, None

    def _combine_text(self, record: NewsRecord) -> str:
        parts = [
            record.title or "",
            record.summary or "",
            record.raw.get("content_text", "") if isinstance(record.raw, dict) else "",
        ]
        return "\n".join(parts)
