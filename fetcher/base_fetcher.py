"""定义统一的新闻抓取抽象。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional


@dataclass
class NewsRecord:
    """标准化的新闻实体。"""

    source: str
    title: str
    url: str
    summary: Optional[str] = None
    published_at: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.raw is None:
            self.raw = {}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BaseNewsFetcher(ABC):
    """每个新闻接口需要实现的标准模板。"""

    name: str = "unknown-source"

    @abstractmethod
    def get_news_list(self) -> List[NewsRecord]:
        """调用远端接口并返回标准化新闻列表。"""

    def get_news_detail(self, record: NewsRecord) -> NewsRecord:
        """如需补充正文，可在子类覆写；默认直接返回。"""

        return record
