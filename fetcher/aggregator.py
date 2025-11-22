"""简单的新闻聚合器，串联多个抓取器。"""
from __future__ import annotations

import logging
from typing import Iterable, List, Sequence, Type
from .base_fetcher import BaseNewsFetcher, NewsRecord

from .zaobao_realtime import ZaobaoRealtimeFetcher
from .thepaper_handpick import ThePaperHandpickFetcher

logger = logging.getLogger(__name__)

# 默认启用的抓取器列表，后续想扩展只需添加新类
DEFAULT_FETCHER_CLASSES: Sequence[Type[BaseNewsFetcher]] = [
    ThePaperHandpickFetcher,
    ZaobaoRealtimeFetcher,
    # BBCNewsFetcher,
]


def collect_news(fetcher_classes: Iterable[Type[BaseNewsFetcher]] = DEFAULT_FETCHER_CLASSES) -> List[NewsRecord]:
    """依次调用各个抓取器，合并为统一的新闻列表。"""

    news: List[NewsRecord] = []
    for fetcher_cls in fetcher_classes:
        fetcher = fetcher_cls()
        try:
            logger.info("开始抓取 %s", fetcher_cls.__name__)
            records = fetcher.get_news_list()
            logger.info("%s 返回 %d 条记录", fetcher_cls.__name__, len(records))
        except Exception as exc:  # noqa: BLE001
            logger.exception("抓取器 %s 执行失败: %s", fetcher_cls.__name__, exc)
            continue
        for record in records:
            try:
                enriched = fetcher.get_news_detail(record)
                if enriched.raw.get("content_text"):
                    logger.debug("%s 详情解析成功: %s", fetcher_cls.__name__, record.title)
            except Exception as detail_exc:  # noqa: BLE001
                logger.exception("抓取器 %s 解析详情失败: %s", fetcher_cls.__name__, detail_exc)
                enriched = record
            news.append(enriched)
    return news
