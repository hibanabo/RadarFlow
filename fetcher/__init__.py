"""Fetcher 层公共出口。"""

from .aggregator import collect_news
from .base_fetcher import BaseNewsFetcher, NewsRecord
from .thepaper_handpick import ThePaperHandpickFetcher
from .zaobao_realtime import ZaobaoRealtimeFetcher
from .bbc_news import BBCNewsFetcher
from .asahi import AsahiNewsFetcher
from .voachinese import VOAChineseNewsFetcher
from .rfi import RFINewsFetcher
from .yna import YNAFetcher
from .cna import CNAFetcher
from .ltn import LTNFetcher

__all__ = [
    "BaseNewsFetcher",
    "NewsRecord",
    "ThePaperHandpickFetcher",
    "ZaobaoRealtimeFetcher",
    "BBCNewsFetcher",
    "AsahiNewsFetcher",
    "VOAChineseNewsFetcher",
    "RFINewsFetcher",
    "YNAFetcher",
    "CNAFetcher",
    "LTNFetcher",
    "collect_news",
]
