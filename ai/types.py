"""AI 摘要相关的数据结构。"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class AISummary:
    """记录 AI 对新闻的摘要。"""

    source: str
    title: str
    url: Optional[str]
    summary: str
    sentiment: Optional[Dict[str, Any]] = None
    keywords: Optional[List[str]] = None
    key_points: Optional[List[str]] = None
    entities: Optional[List[Dict[str, Any]]] = None
    events: Optional[List[Dict[str, Any]]] = None
    topics: Optional[List[str]] = None
    meta: Optional[Dict[str, Any]] = None
    raw_response: Optional[Dict[str, Any]] = None
    is_ai: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
