"""BBC News 列表与详情抓取。"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from .base_fetcher import BaseNewsFetcher, NewsRecord

logger = logging.getLogger(__name__)


class BBCNewsFetcher(BaseNewsFetcher):
    """BBC 新闻频道抓取器。"""

    name = "BBC News"
    base_url = "https://www.bbc.com"
    listing_path = "/news"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()

    def get_news_list(self) -> List[NewsRecord]:
        resp = self.session.get(self.base_url + self.listing_path, timeout=15)
        resp.raise_for_status()
        return self._parse_listing(resp.text)

    def _parse_listing(self, html: str) -> List[NewsRecord]:
        soup = BeautifulSoup(html, "html.parser")
        records: List[NewsRecord] = []
        for anchor in soup.select('a[data-testid="internal-link"]'):
            headline = anchor.select_one('[data-testid="card-headline"]')
            if not headline:
                continue
            href = anchor.get("href", "")
            url = self._absolute_url(href)
            summary_el = anchor.select_one('[data-testid="card-description"]')
            timestamp_el = anchor.select_one('[data-testid="card-metadata-lastupdated"]')
            tag_el = anchor.select_one('[data-testid="card-metadata-tag"]')
            record = NewsRecord(
                source=self.name,
                title=headline.get_text(strip=True),
                url=url,
                summary=summary_el.get_text(strip=True) if summary_el else None,
                published_at=timestamp_el.get_text(strip=True) if timestamp_el else None,
                raw={
                    "tag": tag_el.get_text(strip=True) if tag_el else None,
                    "path": href,
                },
            )
            records.append(record)
        return records

    def _absolute_url(self, href: str) -> str:
        if href.startswith("http"):
            return href
        return f"{self.base_url}{href}" if href else ""

    def get_news_detail(self, record: NewsRecord) -> NewsRecord:
        if not record.url:
            return record
        try:
            resp = self.session.get(record.url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 BBC 详情失败 (%s): %s", record.url, exc)
            return record

        soup = BeautifulSoup(resp.text, "html.parser")
        article_schema = self._extract_schema(soup)
        if article_schema:
            body = article_schema.get("articleBody")
            if body:
                record.raw["content_text"] = body.strip()
                if not record.summary:
                    record.summary = article_schema.get("description") or body[:120]
            if not record.published_at:
                record.published_at = article_schema.get("datePublished")
            record.raw["schema"] = article_schema
        body_from_next = self._extract_body_from_next_data(soup)
        if body_from_next:
            record.raw["content_text"] = body_from_next
            if not record.summary:
                record.summary = body_from_next[:120]
        if not record.published_at:
            record.published_at = article_schema.get("datePublished") if article_schema else record.published_at
        if "content_text" not in record.raw:
            record.raw.setdefault("detail_html", resp.text)
        return record

    def _extract_schema(self, soup: BeautifulSoup) -> Optional[dict]:
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("@type") in {"NewsArticle", "Article", "ReportageNewsArticle"}:
                return data
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") in {"NewsArticle", "Article", "ReportageNewsArticle"}:
                        return item
        return None

    def _extract_body_from_next_data(self, soup: BeautifulSoup) -> Optional[str]:
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return None
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            return None
        page = data.get("props", {}).get("pageProps", {}).get("page")
        if not isinstance(page, dict):
            return None
        page_obj = next(iter(page.values()), None)
        if not isinstance(page_obj, dict):
            return None
        contents = page_obj.get("contents", [])
        paragraphs: List[str] = []
        for block in contents:
            if block.get("type") != "text":
                continue
            for sub in block.get("model", {}).get("blocks", []):
                if sub.get("type") == "paragraph":
                    text = sub.get("model", {}).get("text")
                    if text:
                        paragraphs.append(text.strip())
        return "\n\n".join(paragraphs) if paragraphs else None
