"""VOA 中文网美国频道抓取器。"""
from __future__ import annotations

import logging
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from .base_fetcher import BaseNewsFetcher, NewsRecord

logger = logging.getLogger(__name__)


class VOAChineseNewsFetcher(BaseNewsFetcher):
    """抓取 VOA 中文网美国频道新闻。"""

    name = "美国之音中文网"
    base_url = "https://www.voachinese.com"
    listing_path = "/US"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()

    def get_news_list(self) -> List[NewsRecord]:
        try:
            resp = self.session.get(f"{self.base_url}{self.listing_path}", timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 VOA 中文网列表失败: %s", exc)
            return []
        html = self._ensure_utf8(resp)
        return self._parse_listing(html)

    def get_news_detail(self, record: NewsRecord) -> NewsRecord:
        if not record.url:
            return record
        try:
            resp = self.session.get(record.url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 VOA 中文网详情失败 (%s): %s", record.url, exc)
            return record
        html = self._ensure_utf8(resp)
        return self._parse_detail(html, record)

    def _parse_listing(self, html: str) -> List[NewsRecord]:
        soup = BeautifulSoup(html, "html.parser")
        records: List[NewsRecord] = []
        seen: set[str] = set()
        for block in soup.select("div.media-block"):
            content_link = block.select_one("div.media-block__content a[href]")
            if not content_link:
                continue
            href = content_link.get("href")
            if not href:
                continue
            url = urljoin(self.base_url, href)
            if url in seen:
                continue
            title = self._normalize_text(content_link.get_text(" ", strip=True))
            if not title:
                continue
            summary = self._extract_summary(block)
            section = self._extract_section(block)
            thumb_alt = None
            thumb = block.select_one("a img[alt]")
            if thumb and thumb.get("alt"):
                thumb_alt = self._normalize_text(thumb["alt"])
            raw = {
                "path": href,
                "section": section,
                "image_alt": thumb_alt,
            }
            record = NewsRecord(
                source=self.name,
                title=title,
                url=url,
                summary=summary,
                raw=raw,
            )
            records.append(record)
            seen.add(url)
        return records

    def _parse_detail(self, html: str, record: NewsRecord) -> NewsRecord:
        soup = BeautifulSoup(html, "html.parser")
        published = self._extract_published_at(soup)
        if published:
            record.published_at = published
        authors = self._extract_authors(soup)
        if authors:
            record.authors = authors
        content_text = self._extract_article_body(soup)
        if content_text:
            record.raw["content_text"] = content_text
            if not record.summary:
                first_paragraph = content_text.split("\n\n", 1)[0]
                record.summary = first_paragraph[:200]
        keywords = self._extract_keywords(soup)
        if keywords:
            record.raw["keywords"] = keywords
        record.raw.setdefault("detail_path", record.raw.get("path"))
        return record

    def _extract_summary(self, block: Tag) -> Optional[str]:
        desc = block.select_one(".media-block__desc")
        if desc:
            return self._normalize_text(desc.get_text(" ", strip=True))
        return None

    def _extract_section(self, block: Tag) -> Optional[str]:
        wrapper = block.find_parent(attrs={"data-area-id": True})
        if wrapper and wrapper.get("data-area-id"):
            return wrapper["data-area-id"]
        heading = block.find_previous("h2", class_="section-head")
        if heading:
            return self._normalize_text(heading.get_text(" ", strip=True))
        return None

    def _extract_published_at(self, soup: BeautifulSoup) -> Optional[str]:
        time_el = soup.find("time", attrs={"datetime": True})
        if time_el and time_el.get("datetime"):
            return time_el["datetime"].strip()
        meta = soup.find("meta", attrs={"property": "article:published_time"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        return None

    def _extract_article_body(self, soup: BeautifulSoup) -> Optional[str]:
        container = soup.select_one("#article-content .wsw") or soup.select_one(".wsw")
        if not container:
            return None
        paragraphs: List[str] = []
        for node in container.find_all(["p", "li", "span"], recursive=True):
            if isinstance(node, Tag):
                text = self._normalize_text(node.get_text(" ", strip=True))
                if text:
                    paragraphs.append(text)
        filtered: List[str] = []
        for text in paragraphs:
            if text.lower() == "华盛顿 —":
                continue
            filtered.append(text)
        if not filtered:
            filtered = paragraphs
        return "\n\n".join(filtered).strip() if filtered else None

    def _extract_keywords(self, soup: BeautifulSoup) -> List[str]:
        meta = soup.find("meta", attrs={"name": "keywords"})
        if not meta or not meta.get("content"):
            return []
        keywords = [self._normalize_text(part) for part in meta["content"].split(",")]
        return [token for token in keywords if token]

    def _extract_authors(self, soup: BeautifulSoup) -> List[str]:
        meta = soup.find("meta", attrs={"name": "Author"})
        if meta and meta.get("content"):
            author = self._normalize_text(meta["content"])
            if author:
                return [author]
        byline = soup.select_one(".author-name")
        if byline:
            text = self._normalize_text(byline.get_text(" ", strip=True))
            if text:
                return [text]
        return []

    def _normalize_text(self, text: Optional[str]) -> str:
        if not text:
            return ""
        return " ".join(text.replace("\xa0", " ").split())

    def _ensure_utf8(self, resp: requests.Response) -> str:
        try:
            return resp.content.decode("utf-8")
        except UnicodeDecodeError:
            encoding = resp.apparent_encoding or resp.encoding or "utf-8"
            resp.encoding = encoding
            try:
                return resp.text
            except UnicodeDecodeError:
                return resp.content.decode("utf-8", errors="ignore")
