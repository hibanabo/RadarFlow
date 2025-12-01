"""简单测试：抓取朝日新聞首页并打印列表。"""
from __future__ import annotations

from fetcher.asahi import AsahiNewsFetcher


def main() -> None:
    fetcher = AsahiNewsFetcher()
    records = fetcher.get_news_list()
    print(f"共抓取 {len(records)} 条朝日新聞速報：")
    for idx, record in enumerate(records, start=1):
        rel_time = record.raw.get("relative_time") if isinstance(record.raw, dict) else None
        time_part = f"[{rel_time}]" if rel_time else ""
        print(f"{idx:02d}. {time_part} {record.title} -> {record.url}")


if __name__ == "__main__":
    main()
