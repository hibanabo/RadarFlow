"""将新闻数据落库至 SQLite，替代 JSON 输出。"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Optional

from ai import AISummary
from fetcher.base_fetcher import NewsRecord


class SQLiteStorage:
    """简单的 SQLite 持久化模块。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        if not db_path.parent.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                title TEXT,
                url TEXT,
                summary TEXT,
                published_at TEXT,
                authors TEXT,
                raw_json TEXT,
                ai_summary TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def save_news(
        self,
        news: Iterable[NewsRecord],
        summary_map: Dict[str, AISummary],
    ) -> None:
        for record in news:
            self._save_single(record, summary_map)
        self.conn.commit()

    def _save_single(self, record: NewsRecord, summary_map: Dict[str, AISummary]) -> None:
        key = record.url or f"{record.source}-{record.title}"
        ai_summary = summary_map.get(key)
        authors = json.dumps(getattr(record, "authors", []), ensure_ascii=False)
        raw_json = json.dumps(record.raw if isinstance(record.raw, dict) else {}, ensure_ascii=False)
        ai_summary_json = json.dumps(ai_summary.to_dict(), ensure_ascii=False) if ai_summary else None
        self.conn.execute(
            """
            INSERT INTO news_records (source, title, url, summary, published_at, authors, raw_json, ai_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.source,
                record.title,
                record.url,
                record.summary,
                getattr(record, "published_at", None),
                authors,
                raw_json,
                ai_summary_json,
            ),
        )
