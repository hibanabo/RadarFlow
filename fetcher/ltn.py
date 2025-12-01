"""台灣自由時報抓取器。"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import requests
from bs4 import BeautifulSoup

from .base_fetcher import BaseNewsFetcher, NewsRecord

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}


class LTNFetcher(BaseNewsFetcher):
    """抓取自由時報首頁與新聞詳情。"""

    name = "台灣自由時報"
    base_url = "https://www.ltn.com.tw"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def get_news_list(self) -> List[NewsRecord]:
        try:
            resp = self.session.get(self.base_url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取自由時報首頁失敗: %s", exc)
            return []
        html = resp.text
        return self._parse_listing(html)

    def get_news_detail(self, record: NewsRecord) -> NewsRecord:
        if not record.url:
            return record
        try:
            resp = self.session.get(record.url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取自由時報詳情失敗 (%s): %s", record.url, exc)
            return record
        html = resp.text
        return self._parse_detail(html, record)

    def _parse_listing(self, html: str) -> List[NewsRecord]:
        soup = BeautifulSoup(html, "html.parser")
        anchors = soup.select("a[href^='https://news.ltn.com.tw/news']")
        records: List[NewsRecord] = []
        seen: set[str] = set()
        for anchor in anchors:
            href = anchor.get("href") or ""
            if not href.startswith("https://news.ltn.com.tw/news"):
                continue
            title = anchor.get_text(" ", strip=True)
            if not title:
                continue
            url = href
            if url in seen:
                continue
            summary = self._extract_summary(anchor)
            record = NewsRecord(
                source=self.name,
                title=title,
                url=url,
                summary=summary,
            )
            records.append(record)
            seen.add(url)
        return records

    def _parse_detail(self, html: str, record: NewsRecord) -> NewsRecord:
        soup = BeautifulSoup(html, "html.parser")
        published = self._extract_article_time(soup) or self._meta_content(soup, "article:published_time")
        if published:
            record.published_at = published
        title_el = soup.select_one("h1")
        if title_el:
            record.title = title_el.get_text(" ", strip=True)
        summary = self._extract_body_text(soup, record)
        desc = self._meta_content(soup, "description")
        if desc:
            record.raw["description"] = desc
            if not summary:
                summary = desc[:200]
        edit_text = soup.select_one(".article_edit")
        author = None
        if edit_text:
            author = self._extract_author(edit_text.get_text(" ", strip=True))
        if not author:
            author = self._extract_author(summary or desc or "")
        if author:
            record.authors = [author]
        keywords = self._meta_content(soup, "news_keywords")
        if keywords:
            record.raw["keywords"] = [kw.strip() for kw in keywords.split(",") if kw.strip()]
        if summary:
            record.summary = summary
        return record

    def _meta_content(self, soup: BeautifulSoup, name: str) -> Optional[str]:
        meta = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if meta and meta.get("content"):
            return meta["content"].strip()
        return None

    def _extract_summary(self, anchor) -> Optional[str]:
        parent = anchor.find_parent("div", class_="articleBox")
        if parent:
            desc = parent.select_one("p")
            if desc:
                text = desc.get_text(" ", strip=True)
                if text:
                    return text
        return None

    def _extract_author(self, text: str) -> Optional[str]:
        if not text:
            return None
        match = re.search(r"記者([\u4e00-\u9fa5]+)", text)
        if match:
            return match.group(1)
        return None

    def _extract_body_text(self, soup: BeautifulSoup, record: NewsRecord) -> Optional[str]:
        container = soup.select_one(".text") or soup.find("article")
        paragraphs: List[str] = []
        if container:
            for node in container.find_all("p"):
                text = node.get_text(" ", strip=True)
                if text:
                    paragraphs.append(text)
        if paragraphs:
            body = "\n\n".join(paragraphs)
            record.raw["content_text"] = body
            return paragraphs[0][:200]
        desc = self._meta_content(soup, "description")
        if desc:
            record.raw["content_text"] = desc
            return desc[:200]
        return None

    def _extract_article_time(self, soup: BeautifulSoup) -> Optional[str]:
        time_el = soup.select_one(".article_time") or soup.select_one(".text span.date")
        if not time_el:
            return None
        text = time_el.get_text(" ", strip=True)
        match = re.search(r"(\d{4}/\d{1,2}/\d{1,2})(?:\s+(\d{1,2}:\d{2}))?", text)
        if not match:
            return None
        date_part = match.group(1).replace("/", "-")
        time_part = match.group(2) or "00:00"
        try:
            dt = datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M")
            dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
            return dt.isoformat()
        except ValueError:
            return None
