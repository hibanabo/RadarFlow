"""Utility to drop news rows that missed AI summaries."""
from __future__ import annotations

import argparse
import hashlib
import sqlite3
from pathlib import Path


def compute_news_id(source: str | None, title: str | None, url: str | None) -> str:
    """Mirror deduper hashing logic so processed_articles can be cleaned."""
    base = (url or "").strip()
    if not base:
        base = f"{(source or '').strip()}-{(title or '').strip()}"
    if not base:
        base = repr((source, title, url))
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def cleanup(db_path: Path) -> tuple[int, int]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT id, source, title, url
        FROM news_records
        WHERE ai_summary IS NULL OR TRIM(ai_summary) = ''
        """
    )
    rows = cur.fetchall()
    removed_news = 0
    removed_deduper = 0
    with conn:
        for row in rows:
            news_id = compute_news_id(row["source"], row["title"], row["url"])
            cur = conn.execute("DELETE FROM processed_articles WHERE news_id = ?", (news_id,))
            removed_deduper += cur.rowcount if cur.rowcount is not None else 0
            conn.execute("DELETE FROM news_records WHERE id = ?", (row["id"],))
            removed_news += 1
    conn.close()
    return removed_news, removed_deduper


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove news rows with empty ai_summary.")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("state") / "news.db",
        help="Path to SQLite database (default: state/news.db)",
    )
    args = parser.parse_args()
    removed_news, removed_deduper = cleanup(args.db)
    print(f"Removed {removed_news} news_records rows")
    print(f"Removed {removed_deduper} processed_articles rows")


if __name__ == "__main__":
    main()
