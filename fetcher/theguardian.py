"""The Guardian 多频道抓取器。"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from .base_fetcher import BaseNewsFetcher, NewsRecord

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9",
}


class TheGuardianNewsFetcher(BaseNewsFetcher):
    """抓取英国卫报国际站与各区域频道。"""

    name = "英国卫报"
    base_url = "https://www.theguardian.com"
    listing_paths: List[str] = [
        "/international",
        "/world",
        "/world/europe-news",
        "/us-news",
        "/world/americas",
        "/world/asia",
        "/australia-news",
        "/world/middleeast",
        "/world/africa",
        "/inequality",
        "/global-development",
    ]

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def get_news_list(self) -> List[NewsRecord]:
        seen: set[str] = set()
        all_records: List[NewsRecord] = []
        for path in self.listing_paths:
            url = self._absolute_url(path)
            try:
                resp = self.session.get(url, timeout=20)
                resp.raise_for_status()
            except requests.RequestException as exc:  # noqa: BLE001
                logger.warning("抓取 Guardian 頁面失敗 (%s): %s", url, exc)
                continue
            records = self._parse_listing(resp.text, seen)
            all_records.extend(records)
        return all_records

    def get_news_detail(self, record: NewsRecord) -> NewsRecord:
        if not record.url:
            return record
        try:
            resp = self.session.get(record.url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 Guardian 详情失败 (%s): %s", record.url, exc)
            return record
        return self._parse_detail(resp.text, record)

    def _parse_listing(self, html: str, seen: set[str]) -> List[NewsRecord]:
        soup = BeautifulSoup(html, "html.parser")
        records: List[NewsRecord] = []
        for anchor in soup.select('a[data-link-name="article"]'):
            href = anchor.get("href")
            if not href:
                continue
            url = self._absolute_url(href)
            if url in seen:
                continue
            title = self._extract_title(anchor)
            if not title:
                continue
            summary = self._extract_summary(anchor)
            image = self._extract_image(anchor)
            section = self._infer_section(url)
            record = NewsRecord(
                source=self.name,
                title=title,
                url=url,
                summary=summary,
                raw={
                    "section": section,
                    "image": image,
                },
            )
            records.append(record)
            seen.add(url)
        return records

    def _parse_detail(self, html: str, record: NewsRecord) -> NewsRecord:
        soup = BeautifulSoup(html, "html.parser")
        schema = self._extract_schema(soup)
        if schema:
            if schema.get("headline"):
                record.title = schema["headline"].strip()
            if schema.get("description"):
                record.summary = schema["description"].strip()
            published = schema.get("datePublished")
            if published:
                normalized = self._normalize_datetime(published)
                if normalized:
                    record.published_at = normalized
            modified = schema.get("dateModified")
            if modified:
                normalized_mod = self._normalize_datetime(modified)
                if normalized_mod:
                    record.raw["updated_at"] = normalized_mod
            schema_authors = self._authors_from_schema(schema.get("author"))
        else:
            schema_authors = []

        meta_desc = self._meta_content(soup, "description")
        if meta_desc and not record.summary:
            record.summary = meta_desc

        title_dom = soup.select_one("h1")
        if title_dom:
            record.title = title_dom.get_text(" ", strip=True)

        authors = self._extract_dom_authors(soup) or schema_authors
        if authors:
            record.authors = authors

        if not record.published_at:
            published_meta = self._meta_content(soup, "article:published_time")
            if published_meta:
                normalized = self._normalize_datetime(published_meta)
                if normalized:
                    record.published_at = normalized

        if "updated_at" not in record.raw:
            updated_meta = self._meta_content(soup, "article:modified_time")
            if updated_meta:
                normalized = self._normalize_datetime(updated_meta)
                if normalized:
                    record.raw["updated_at"] = normalized

        body = self._extract_body(soup)
        if body:
            record.raw["content_text"] = body
            if not record.summary:
                record.summary = body.split("\n\n", 1)[0][:200]

        keywords = self._meta_keywords(soup)
        if keywords:
            record.raw["keywords"] = keywords
        return record

    def _absolute_url(self, href: str) -> str:
        if href.startswith("http"):
            return href
        return urljoin(self.base_url, href)

    def _extract_title(self, anchor: Tag) -> Optional[str]:
        text = anchor.get_text(" ", strip=True)
        if text:
            return text
        container = anchor.find_parent(["li", "div", "section"]) or anchor
        for selector in ("h1 span", "h2 span", "h3 span", "h4 span", "h5 span", "span"):
            node = container.select_one(selector)
            if node:
                text = node.get_text(" ", strip=True)
                if text:
                    return text
        return None

    def _extract_summary(self, anchor: Tag) -> Optional[str]:
        container = anchor.find_parent(["li", "div", "section"]) or anchor
        for selector in ("p",):
            node = container.select_one(selector)
            if node:
                text = node.get_text(" ", strip=True)
                cleaned = self._clean_text(text)
                if cleaned:
                    return cleaned
        return None

    def _extract_image(self, anchor: Tag) -> Optional[str]:
        container = anchor.find_parent(["li", "div", "figure"]) or anchor
        img = container.find("img")
        if img and img.get("src"):
            src = img["src"]
            return self._absolute_url(src) if src.startswith("/") else src
        return None

    def _infer_section(self, url: str) -> Optional[str]:
        path = urlparse(url).path.strip("/")
        if not path:
            return None
        parts = path.split("/")
        return parts[0] if parts else None

    def _extract_schema(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
            except json.JSONDecodeError:
                continue
            # 页面使用列表包装
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and entry.get("@type") == "NewsArticle":
                        return entry
            elif isinstance(data, dict) and data.get("@type") == "NewsArticle":
                return data
        return None

    def _authors_from_schema(self, data: Any) -> List[str]:
        names: List[str] = []
        if isinstance(data, dict):
            name = data.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
        elif isinstance(data, list):
            for entry in data:
                names.extend(self._authors_from_schema(entry))
        elif isinstance(data, str) and data.strip():
            names.append(data.strip())
        return names

    def _extract_dom_authors(self, soup: BeautifulSoup) -> List[str]:
        authors: List[str] = []
        for node in soup.select('[rel="author"]'):
            text = node.get_text(" ", strip=True)
            if text:
                authors.append(text)
        return list(dict.fromkeys(authors))

    def _extract_body(self, soup: BeautifulSoup) -> Optional[str]:
        container = soup.select_one(".article-body-commercial-selector")
        if not container:
            return None
        texts: List[str] = []
        for node in container.find_all(["p", "li"]):
            text = node.get_text(" ", strip=True)
            cleaned = self._clean_text(text)
            if cleaned:
                texts.append(cleaned)
        return "\n\n".join(texts).strip() if texts else None

    def _normalize_datetime(self, value: str) -> Optional[str]:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt.isoformat()

    def _meta_content(self, soup: BeautifulSoup, name: str) -> Optional[str]:
        meta = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
        if meta and meta.get("content"):
            return meta["content"].strip()
        return None

    def _meta_keywords(self, soup: BeautifulSoup) -> List[str]:
        keywords = self._meta_content(soup, "keywords")
        if not keywords:
            return []
        return [token.strip() for token in keywords.split(",") if token.strip()]

    def _clean_text(self, text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        cleaned = " ".join(text.split())
        return cleaned or None
