"""Fetcher 层公共出口。"""

from .aggregator import collect_news
from .base_fetcher import BaseNewsFetcher, NewsRecord
from .thepaper_handpick import ThePaperHandpickFetcher
from .zaobao_realtime import ZaobaoRealtimeFetcher
from .bbc_news import BBCNewsFetcher

__all__ = [
    "BaseNewsFetcher",
    "NewsRecord",
    "ThePaperHandpickFetcher",
    "ZaobaoRealtimeFetcher",
    "BBCNewsFetcher",
    "collect_news",
]
