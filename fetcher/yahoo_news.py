"""Yahoo News 首页与文章抓取。"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup, Tag

from .base_fetcher import BaseNewsFetcher, NewsRecord

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

ARTICLE_PATH_SEGMENT = "/news/articles/"


class YahooNewsFetcher(BaseNewsFetcher):
    """抓取 Yahoo News 首页流以及详情。"""

    name = "Yahoo News"
    base_url = "https://news.yahoo.com"
    listing_path = "/"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def get_news_list(self) -> List[NewsRecord]:
        try:
            resp = self.session.get(self.base_url + self.listing_path, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 Yahoo News 首页失败: %s", exc)
            return []
        return self._parse_listing(resp.text)

    def get_news_detail(self, record: NewsRecord) -> NewsRecord:
        if not record.url:
            return record
        try:
            resp = self.session.get(record.url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 Yahoo News 详情失败 (%s): %s", record.url, exc)
            return record
        return self._parse_detail(resp.text, record)

    def _parse_listing(self, html: str) -> List[NewsRecord]:
        soup = BeautifulSoup(html, "html.parser")
        records: List[NewsRecord] = []
        seen: set[str] = set()
        for item in soup.select("li.stream-item"):
            link = item.select_one('h3[data-test-locator="stream-item-title"] a[href]')
            if not link:
                continue
            href = link.get("href") or ""
            if ARTICLE_PATH_SEGMENT not in href:
                continue
            if href in seen:
                continue
            title = link.get_text(" ", strip=True)
            if not title:
                continue
            summary = self._text(item.select_one('[data-test-locator="stream-item-summary"]'))
            category = self._text(item.select_one('[data-test-locator="stream-item-category-label"]'))
            publisher = self._text(item.select_one('[data-test-locator="stream-item-publisher"]'))
            record = NewsRecord(
                source=self.name,
                title=title,
                url=href,
                summary=summary,
                raw={
                    "category": category,
                    "publisher": publisher,
                    "uuid": item.get("data-uuid"),
                },
            )
            records.append(record)
            seen.add(href)
        return records

    def _parse_detail(self, html: str, record: NewsRecord) -> NewsRecord:
        soup = BeautifulSoup(html, "html.parser")
        collected_keywords: List[str] = []
        schema = self._extract_schema(soup)
        if schema:
            headline = schema.get("headline")
            if isinstance(headline, str) and headline.strip():
                record.title = headline.strip()
            published = schema.get("datePublished")
            if isinstance(published, str) and published.strip():
                record.published_at = published.strip()
            description = schema.get("description")
            if isinstance(description, str) and description.strip():
                record.summary = description.strip()
            keywords = self._extract_keywords(schema)
            if keywords:
                collected_keywords.extend(keywords)
            schema_authors = self._author_names(schema.get("author"))
            if schema_authors:
                record.authors = schema_authors
        if not record.published_at:
            time_el = soup.select_one("article time[datetime]") or soup.find("time", attrs={"datetime": True})
            if time_el and time_el.get("datetime"):
                record.published_at = time_el["datetime"].strip()
        if not record.authors:
            header_author = soup.select_one("article header .font-semibold")
            byline = header_author.get_text(" ", strip=True) if header_author else ""
            if byline:
                record.authors = [byline]
        header_text = ""
        header = soup.select_one("article header")
        if header:
            header_text = header.get_text(" ", strip=True)
        reading_time = self._extract_reading_time(header_text)
        if reading_time:
            record.raw["reading_time"] = reading_time
        body = self._extract_body(soup)
        if body:
            record.raw["content_text"] = body
            if not record.summary:
                record.summary = body.split("\n\n", 1)[0][:200]
        meta_keywords = self._meta_keywords(soup)
        if meta_keywords:
            collected_keywords.extend(meta_keywords)
        if collected_keywords:
            record.raw["keywords"] = list(dict.fromkeys(collected_keywords))
        meta_section = self._meta_content(soup, "article:section") or self._meta_content(soup, "section")
        if meta_section:
            record.raw["section"] = meta_section
        return record

    def _extract_body(self, soup: BeautifulSoup) -> Optional[str]:
        container = soup.select_one('[data-article-body="true"]')
        if not container:
            return None
        paragraphs: List[str] = []
        for node in container.find_all(["p", "li"]):
            text = node.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)
        return "\n\n".join(paragraphs).strip() if paragraphs else None

    def _extract_schema(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
            except json.JSONDecodeError:
                continue
            candidate = self._find_news_article(data)
            if candidate:
                return candidate
        return None

    def _find_news_article(self, data: Any) -> Optional[Dict[str, Any]]:
        if isinstance(data, dict):
            if data.get("@type") == "NewsArticle":
                return data
            for value in data.values():
                candidate = self._find_news_article(value)
                if candidate:
                    return candidate
        elif isinstance(data, list):
            for value in data:
                candidate = self._find_news_article(value)
                if candidate:
                    return candidate
        return None

    def _extract_keywords(self, schema: Dict[str, Any]) -> List[str]:
        keywords = schema.get("keywords")
        if isinstance(keywords, list):
            return [kw.strip() for kw in keywords if isinstance(kw, str) and kw.strip()]
        if isinstance(keywords, str):
            return [token.strip() for token in keywords.split(",") if token.strip()]
        return []

    def _meta_keywords(self, soup: BeautifulSoup) -> List[str]:
        keywords_content = self._meta_content(soup, "keywords")
        if not keywords_content:
            return []
        return [token.strip() for token in keywords_content.split(",") if token.strip()]

    def _meta_content(self, soup: BeautifulSoup, name: str) -> Optional[str]:
        meta = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
        if meta and meta.get("content"):
            return meta["content"].strip()
        return None

    def _author_names(self, data: Any) -> List[str]:
        names: List[str] = []
        if isinstance(data, dict):
            value = data.get("name")
            if isinstance(value, str) and value.strip():
                names.append(value.strip())
        elif isinstance(data, list):
            for element in data:
                names.extend(self._author_names(element))
        elif isinstance(data, str) and data.strip():
            names.append(data.strip())
        return names

    def _text(self, node: Optional[Tag]) -> Optional[str]:
        if not node:
            return None
        text = node.get_text(" ", strip=True)
        return text or None

    def _extract_reading_time(self, header_text: str) -> Optional[str]:
        if not header_text:
            return None
        match = re.search(r"\b\d+\s+min read\b", header_text)
        return match.group(0) if match else None
