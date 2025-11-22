"""演示如何通过统一接口抓取多来源新闻，并输出 JSON。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterable, List

from ai import AIClient, AISummary, AISummaryFilter
from deduper import SQLiteDeduper
from fetcher import collect_news
from filters import FilterSet
from notifications import NotificationClient
from utils.storage import SQLiteStorage
from utils.time_utils import get_timezone_helper

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", force=True)


def main() -> None:
    news = list(collect_news())
    logging.info("共拉取 %d 条新闻", len(news))
    tz_helper = get_timezone_helper()
    for item in news:
        if item.published_at:
            converted = tz_helper.to_iso(item.published_at)
            if converted:
                if isinstance(item.raw, dict):
                    item.raw.setdefault("original_published_at", item.published_at)
                    item.raw["published_at"] = converted
                item.published_at = converted
    for item in news:
        timestamp_raw = item.published_at or (item.raw.get("timestamp") if isinstance(item.raw, dict) else None)
        timestamp = tz_helper.to_display(timestamp_raw) or timestamp_raw or "未知时间"
        authors = ", ".join(item.authors) if getattr(item, "authors", None) else None
        logging.info(
            "%s - %s | 📅 %s | ✍️ %s",
            item.source,
            item.title,
            timestamp,
            authors or "未知作者",
        )

    db_path = Path("state") / "news.db"
    deduper = SQLiteDeduper(db_path, retention_days=3)
    filter_set = FilterSet()
    ai_filter = AISummaryFilter()
    try:
        fresh_news = deduper.filter_new(news)
        logging.info("其中 %d 条为新增新闻", len(fresh_news))
        filtered_news = filter_set.apply(fresh_news)

        ai_client = AIClient()
        summaries: List[AISummary] = []
        if ai_client.enabled and filtered_news:
            target_count = getattr(ai_client, "max_items", len(filtered_news)) or len(filtered_news)
            ai_targets = filtered_news[:target_count]
            logging.info("AI 将处理 %d 条新闻", len(ai_targets))
            summaries = ai_client.summarize_news(ai_targets)

        summary_map = {
            (summary.url or f"{summary.source}-{summary.title}"): summary
            for summary in (summaries or [])
        }
        post_filtered_news, post_filtered_summary_map = ai_filter.apply(filtered_news, summary_map)

        storage = SQLiteStorage(db_path)
        try:
            storage.save_news(filtered_news, summary_map)
        finally:
            storage.close()

        notifier = NotificationClient()
        results = notifier.send(post_filtered_news, post_filtered_summary_map)
        if results:
            logging.info("通知发送结果: %s", results)

        for item in filtered_news:
            deduper.mark(item)
    finally:
        deduper.close()


if __name__ == "__main__":
    main()
