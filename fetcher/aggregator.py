"""简单的新闻聚合器，串联多个抓取器。"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, List, Sequence, Type

from .rfi import RFINewsFetcher
from .base_fetcher import BaseNewsFetcher, NewsRecord
from .yahoo_news import YahooNewsFetcher
from .huanqiu import HuanqiuNewsFetcher
from .dailymail import DailyMailNewsFetcher

from .zaobao_realtime import ZaobaoRealtimeFetcher
from .thepaper_handpick import ThePaperHandpickFetcher
from .bbc_news import BBCNewsFetcher
from .bbc_zhongwen_news import BBCZhongwenNewsFetcher
from .asahi import AsahiNewsFetcher
from .voachinese import VOAChineseNewsFetcher
from .yna import YNAFetcher
from .cna import CNAFetcher
from .ltn import LTNFetcher
from .aljazeera import AlJazeeraNewsFetcher
from .theguardian import TheGuardianNewsFetcher
from .abs_cbn import AbsCbnNewsFetcher
from .vnexpress import VnExpressNewsFetcher
from .scmp import SCMPNewsFetcher
from .eightworld import EightWorldNewsFetcher


logger = logging.getLogger(__name__)

DEFAULT_MAX_WORKERS = 6

# 默认启用的抓取器列表，后续想扩展只需添加新类
DEFAULT_FETCHER_CLASSES: Sequence[Type[BaseNewsFetcher]] = [
    # # 澎湃新闻
    # ThePaperHandpickFetcher,
    #
    # # 联合早报
    # ZaobaoRealtimeFetcher,

    # BBC
    BBCNewsFetcher,

    # BBC 中文
    BBCZhongwenNewsFetcher,

    # # 朝日新闻
    # AsahiNewsFetcher,
    #
    # # 美国之音（中文）
    # VOAChineseNewsFetcher,
    #
    # # 韩联社
    # YNAFetcher,
    #
    # # 台湾中央社
    # CNAFetcher,
    #
    # # 台灣自由時報
    # LTNFetcher,
    #
    # # 环球网
    # HuanqiuNewsFetcher,
    #
    # # 英国每日邮报
    # DailyMailNewsFetcher,
    #
    # # 半岛电视台
    # AlJazeeraNewsFetcher,
    #
    # # 英国卫报
    # TheGuardianNewsFetcher,
    #
    # # ABS-CBN
    # AbsCbnNewsFetcher,
    #
    # # 越南 VnExpress
    # VnExpressNewsFetcher,
    #
    # # 8视界世界
    # EightWorldNewsFetcher,
    #
    # # 法国国家电视台
    # RFINewsFetcher,
    #
    # # 南华早报
    # SCMPNewsFetcher,

]


def collect_news(
    fetcher_classes: Iterable[Type[BaseNewsFetcher]] = DEFAULT_FETCHER_CLASSES,
    max_workers: int | None = None,
) -> List[NewsRecord]:
    """并发调用各个抓取器，合并为统一的新闻列表。"""

    fetcher_list = list(fetcher_classes)
    if not fetcher_list:
        return []
    worker_count = max_workers or min(DEFAULT_MAX_WORKERS, len(fetcher_list))

    news: List[NewsRecord] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {executor.submit(_run_fetcher_task, fetcher_cls): fetcher_cls for fetcher_cls in fetcher_list}
        for future in as_completed(future_map):
            fetcher_cls = future_map[future]
            try:
                records = future.result()
            except Exception as exc:  # noqa: BLE001
                logger.exception("聚合线程 %s 失败: %s", fetcher_cls.__name__, exc)
                continue
            news.extend(records)
    return news


def _run_fetcher_task(fetcher_cls: Type[BaseNewsFetcher]) -> List[NewsRecord]:
    """在线程池中运行单个抓取器，返回该抓取器的全部新闻记录。"""

    fetcher = fetcher_cls()
    try:
        logger.info("开始抓取 %s", fetcher_cls.__name__)
        records = fetcher.get_news_list()
        logger.info("%s 返回 %d 条记录", fetcher_cls.__name__, len(records))
    except Exception as exc:  # noqa: BLE001
        logger.exception("抓取器 %s 执行失败: %s", fetcher_cls.__name__, exc)
        return []

    enriched: List[NewsRecord] = []
    for record in records:
        try:
            detail = fetcher.get_news_detail(record)
            if detail.raw.get("content_text"):
                logger.debug("%s 详情解析成功: %s", fetcher_cls.__name__, record.title)
        except Exception as detail_exc:  # noqa: BLE001
            logger.exception("抓取器 %s 解析详情失败: %s", fetcher_cls.__name__, detail_exc)
            detail = record
        enriched.append(detail)
    return enriched
