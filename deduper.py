"""简单的 SQLite 去重器."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from fetcher.base_fetcher import NewsRecord


class SQLiteDeduper:
    """记录已处理过的新闻，避免重复推送/调用 AI."""

    def __init__(self, db_path: Path, retention_days: int = 3) -> None:
        self.db_path = db_path
        self.retention_days = retention_days
        if not db_path.parent.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_articles (
                news_id TEXT PRIMARY KEY,
                source TEXT,
                title TEXT,
                url TEXT,
                processed_at TEXT
            )
            """
        )
        self.conn.commit()
        self.prune()

    def close(self) -> None:
        self.conn.close()

    def _make_news_id(self, record: NewsRecord) -> str:
        base = record.url or f"{record.source}-{record.title}" or repr(record)
        return hashlib.sha1(base.encode("utf-8")).hexdigest()

    def is_seen(self, record: NewsRecord) -> bool:
        news_id = self._make_news_id(record)
        cur = self.conn.execute(
            "SELECT 1 FROM processed_articles WHERE news_id = ?", (news_id,)
        )
        return cur.fetchone() is not None

    def mark(self, record: NewsRecord) -> None:
        news_id = self._make_news_id(record)
        self.conn.execute(
            "INSERT OR REPLACE INTO processed_articles (news_id, source, title, url, processed_at) VALUES (?, ?, ?, ?, ?)",
            (
                news_id,
                record.source,
                record.title,
                record.url,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()

    def filter_new(self, records: Iterable[NewsRecord]) -> List[NewsRecord]:
        fresh: List[NewsRecord] = []
        for record in records:
            if not self.is_seen(record):
                fresh.append(record)
        return fresh

    def prune(self) -> None:
        if self.retention_days <= 0:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        self.conn.execute(
            "DELETE FROM processed_articles WHERE processed_at < ?",
            (cutoff.isoformat(),),
        )
        self.conn.commit()
