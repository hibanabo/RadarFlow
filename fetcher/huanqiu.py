"""环球网移动站抓取器。"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from html import unescape
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from .base_fetcher import BaseNewsFetcher, NewsRecord

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class HuanqiuNewsFetcher(BaseNewsFetcher):
    """抓取 https://m.huanqiu.com/ 的热点资讯。"""

    name = "环球网"
    base_url = "https://m.huanqiu.com"
    listing_path = "/"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def get_news_list(self) -> List[NewsRecord]:
        try:
            resp = self.session.get(urljoin(self.base_url, self.listing_path), timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取环球网首页失败: %s", exc)
            return []
        return self._parse_listing(resp.text)

    def get_news_detail(self, record: NewsRecord) -> NewsRecord:
        if not record.url:
            return record
        try:
            resp = self.session.get(record.url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取环球网详情失败 (%s): %s", record.url, exc)
            return record
        return self._parse_detail(resp.text, record)

    def _parse_listing(self, html: str) -> List[NewsRecord]:
        soup = BeautifulSoup(html, "html.parser")
        records: List[NewsRecord] = []
        seen: set[str] = set()
        for item in soup.select("div.data-container li.item"):
            href = self._textarea_text(item, "href")
            title = self._textarea_text(item, "title")
            if not href or not title:
                continue
            if not href.startswith("/article/"):
                continue
            url = urljoin(self.base_url, href)
            if url in seen:
                continue
            summary = self._textarea_text(item, "title-highlight")
            record = NewsRecord(
                source=self.name,
                title=title,
                url=url,
                summary=summary,
                raw=self._build_listing_raw(item),
            )
            records.append(record)
            seen.add(url)
        return records

    def _build_listing_raw(self, item: Tag) -> Dict[str, Any]:
        cover = self._textarea_text(item, "cover")
        source_info = self._parse_json_field(self._textarea_text(item, "source"))
        typedata = self._parse_json_field(self._textarea_text(item, "typedata"))
        return {
            "aid": self._textarea_text(item, "aid"),
            "tag": self._textarea_text(item, "tag"),
            "type": self._textarea_text(item, "addltype"),
            "source": source_info,
            "cover": self._normalize_asset_url(cover),
            "typedata": typedata,
            "serious": self._textarea_text(item, "ext-serious"),
        }

    def _parse_detail(self, html: str, record: NewsRecord) -> NewsRecord:
        soup = BeautifulSoup(html, "html.parser")
        title = self._textarea_text(soup, "article-title")
        if title:
            record.title = title
        summary = self._textarea_text(soup, "article-summary")
        if summary:
            record.summary = summary
        published = self._format_timestamp(self._textarea_text(soup, "article-time", preserve_breaks=True))
        if published:
            record.published_at = published
        author = self._strip_label(self._textarea_text(soup, "article-author"))
        if author:
            record.authors = [author]
        editor = self._strip_label(self._textarea_text(soup, "article-editor-name"))
        content = self._textarea_text(soup, "article-content", preserve_breaks=True)
        body = self._normalize_body(content)
        if body:
            record.raw["content_text"] = body
            if not record.summary:
                record.summary = body.split("\n\n", 1)[0][:200]
        source_name = self._textarea_text(soup, "article-source-name")
        if source_name:
            record.raw["source_name"] = source_name
        record.raw["editor"] = editor
        record.raw["article_host"] = self._textarea_text(soup, "article-host")
        record.raw["article_language"] = self._textarea_text(soup, "article-lang")
        record.raw["article_category"] = self._textarea_text(soup, "article-catnode")
        record.raw["article_id"] = self._textarea_text(soup, "article-aid")
        keyboarder = self._parse_json_field(self._textarea_text(soup, "article-keyboarder"))
        if keyboarder:
            record.raw["keyboarder"] = keyboarder
        keywords = self._meta_keywords(soup)
        if keywords:
            record.raw["keywords"] = keywords
        if not record.authors:
            if editor:
                record.authors = [editor]
            elif source_name:
                record.authors = [source_name]
            else:
                record.authors = [self.name]
        return record

    def _textarea_text(self, parent: Tag | BeautifulSoup, class_name: str, *, preserve_breaks: bool = False) -> Optional[str]:
        node = parent.select_one(f"textarea.{class_name}")
        if not node:
            return None
        text = unescape(node.get_text())
        if preserve_breaks:
            cleaned = text.strip()
        else:
            cleaned = " ".join(text.split())
        return cleaned or None

    def _parse_json_field(self, payload: Optional[str]) -> Optional[Any]:
        if not payload:
            return None
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None
        return self._strip_json(data)

    def _strip_json(self, data: Any) -> Any:
        if isinstance(data, dict):
            return {k.strip(): self._strip_json(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._strip_json(item) for item in data]
        if isinstance(data, str):
            return data.strip()
        return data

    def _normalize_asset_url(self, url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        if url.startswith("//"):
            return f"https:{url}"
        if url.startswith("/"):
            return urljoin(self.base_url, url)
        return url

    def _normalize_body(self, text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        paragraphs: List[str] = []
        for line in text.splitlines():
            cleaned = line.strip()
            if cleaned:
                paragraphs.append(cleaned)
        return "\n\n".join(paragraphs).strip() if paragraphs else None

    def _strip_label(self, text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        parts = text.split("：", 1)
        if len(parts) == 2:
            return parts[1].strip() or None
        return text.strip() or None

    def _format_timestamp(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        try:
            timestamp = int(value)
        except ValueError:
            return None
        dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        return dt.isoformat()

    def _meta_keywords(self, soup: BeautifulSoup) -> List[str]:
        meta = soup.find("meta", attrs={"name": "keywords"})
        if not meta or not meta.get("content"):
            return []
        return [token.strip() for token in meta["content"].split(",") if token.strip()]
