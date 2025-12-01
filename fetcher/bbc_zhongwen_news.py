"""BBC 中文新闻抓取器。"""
from __future__ import annotations

import logging
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .base_fetcher import BaseNewsFetcher, NewsRecord
from .bbc_base import extract_schema_data, extract_body_from_next_data

logger = logging.getLogger(__name__)


class BBCZhongwenNewsFetcher(BaseNewsFetcher):
    """BBC 中文网抓取器。"""

    name = "BBC 中文"
    base_url = "https://www.bbc.com"
    default_section_urls = [
        "https://www.bbc.com/zhongwen/simp",
        "https://www.bbc.com/zhongwen/topics/c83plve5vmjt/trad",
        "https://www.bbc.com/zhongwen/topics/ckr7mn6r003t/trad",
        "https://www.bbc.com/zhongwen/topics/cezw73jk755t/trad",
        "https://www.bbc.com/zhongwen/topics/cd6qem06z92t/trad",
        "https://www.bbc.com/zhongwen/topics/c1ez1k4emn0t/trad",
        "https://www.bbc.com/zhongwen/topics/cq8nqywy37yt/trad",
        "https://www.bbc.com/zhongwen/topics/cgvl47l38e1t/trad",
    ]

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        section_urls: Optional[List[str]] = None,
    ) -> None:
        self.session = session or requests.Session()
        self.section_urls = section_urls or list(self.default_section_urls)

    def get_news_list(self) -> List[NewsRecord]:
        records: List[NewsRecord] = []
        seen: set[str] = set()
        for url in self.section_urls:
            html = self._fetch_listing(url)
            if not html:
                continue
            parsed = self._parse_listing(html)
            for record in parsed:
                if record.url in seen:
                    continue
                records.append(record)
                seen.add(record.url)
        return records

    def _fetch_listing(self, url: str) -> Optional[str]:
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 BBC 中文列表页失败 (%s): %s", url, exc)
            return None

    def _parse_listing(self, html: str) -> List[NewsRecord]:
        soup = BeautifulSoup(html, "html.parser")
        records: List[NewsRecord] = []
        for promo in soup.select("div.promo-text"):
            link = promo.find("a", href=True)
            if not link:
                continue
            title = link.get_text(strip=True)
            if not title:
                continue
            url = self._absolute_url(link["href"])
            summary_node = promo.find("p")
            time_node = promo.find("time")
            published = None
            if time_node and time_node.get("datetime"):
                published = time_node["datetime"]
            elif time_node:
                published = time_node.get_text(strip=True)
            summary = summary_node.get_text(strip=True) if summary_node else None
            record = NewsRecord(
                source=self.name,
                title=title,
                url=url,
                summary=summary,
                published_at=published,
                raw={"lang": "zh"},
            )
            records.append(record)
        return records

    def _absolute_url(self, href: str) -> str:
        return href if href.startswith("http") else urljoin(self.base_url, href)

    def get_news_detail(self, record: NewsRecord) -> NewsRecord:
        if not record.url:
            return record
        try:
            resp = self.session.get(record.url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 BBC 中文详情失败 (%s): %s", record.url, exc)
            return record

        soup = BeautifulSoup(resp.text, "html.parser")
        schema = extract_schema_data(soup)
        if schema:
            body = schema.get("articleBody")
            if body:
                record.raw["content_text"] = body.strip()
                if not record.summary:
                    record.summary = schema.get("description") or body[:120]
            if not record.published_at:
                record.published_at = schema.get("datePublished")
            record.raw["schema"] = schema
        body_from_next = extract_body_from_next_data(soup)
        if body_from_next:
            record.raw["content_text"] = body_from_next
            if not record.summary:
                record.summary = body_from_next[:120]
        if "content_text" not in record.raw:
            record.raw.setdefault("detail_html", resp.text)
        return record
