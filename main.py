"""演示如何通过统一接口抓取多来源新闻，并输出 JSON。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterable, List

from ai import AIClient, AISummary, AISummaryFilter, AIPreFilter
from deduper import SQLiteDeduper
from fetcher import collect_news
from filters import FilterSet
from notifications import NotificationClient
from utils.storage import SQLiteStorage
from utils.time_utils import get_timezone_helper

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", force=True)


def log_section(title: str) -> None:
    logging.info("%s %s %s", "=" * 12, title, "=" * 12)


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
    ai_prefilter = AIPreFilter()
    ai_filter = AISummaryFilter()
    try:
        log_section("去重")
        fresh_news = deduper.filter_new(news)
        logging.info("去重后新增 %d/%d 条新闻", len(fresh_news), len(news))

        has_active_rules = any(rule.enabled for rule in filter_set.rules)
        log_section("AI 预过滤")
        prefilter_active = (
            ai_prefilter.enabled
            and bool(ai_prefilter.api_key)
            and filter_set.enabled
            and has_active_rules
        )
        if prefilter_active:
            logging.info("AI 预过滤输入 %d 条新闻", len(fresh_news))
            prefiltered_news = ai_prefilter.apply(fresh_news, filter_set.rules, filter_set.enabled)
            logging.info("AI 预过滤输出 %d 条新闻", len(prefiltered_news))
        else:
            logging.info("AI 预过滤未启用或缺少必要配置，跳过。")
            prefiltered_news = list(fresh_news)

        log_section("关键词过滤")
        logging.info("关键词过滤输入 %d 条新闻", len(prefiltered_news))
        filtered_news = filter_set.apply(prefiltered_news)

        ai_client = AIClient()
        summaries: List[AISummary] = []
        log_section("AI 摘要")
        if ai_client.enabled and filtered_news:
            max_items = getattr(ai_client, "max_items", len(filtered_news)) or len(filtered_news)
            if max_items <= 0:
                target_count = len(filtered_news)
            else:
                target_count = min(max_items, len(filtered_news))
            ai_targets = filtered_news[:target_count]
            logging.info("AI 将处理 %d 条新闻", len(ai_targets))
            summaries = ai_client.summarize_news(ai_targets)
        else:
            logging.info("AI 摘要未启用或无可处理新闻，跳过。")

        blocked_by_ai = [
            record
            for record in filtered_news
            if isinstance(record.raw, dict) and record.raw.get("_ai_summary_blocked")
        ]
        if blocked_by_ai:
            filtered_news = [
                record
                for record in filtered_news
                if not (isinstance(record.raw, dict) and record.raw.get("_ai_summary_blocked"))
            ]
            logging.warning("AI 摘要阶段拦截 %d 条新闻，已跳过后续流程。", len(blocked_by_ai))

        summary_map = {
            (summary.url or f"{summary.source}-{summary.title}"): summary
            for summary in (summaries or [])
        }
        log_section("AI 后置过滤")
        logging.info("AI 后置过滤输入 %d 条新闻", len(filtered_news))
        post_filtered_news, post_filtered_summary_map = ai_filter.apply(filtered_news, summary_map)
        logging.info("AI 后置过滤输出 %d 条新闻", len(post_filtered_news))

        storage = SQLiteStorage(db_path)
        try:
            storage.save_news(filtered_news, summary_map)
        finally:
            storage.close()

        notifier = NotificationClient()
        log_section("通知推送")
        logging.info("将推送 %d 条新闻", len(post_filtered_news))
        results = notifier.send(post_filtered_news, post_filtered_summary_map)
        if results:
            logging.info("通知发送结果: %s", results)

        for item in fresh_news:
            deduper.mark(item)
    finally:
        deduper.close()


if __name__ == "__main__":
    main()
