"""Al Jazeera 首页与文章抓取器。"""
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
    "Accept-Language": "en-US,en;q=0.9",
}


class AlJazeeraNewsFetcher(BaseNewsFetcher):
    """抓取 https://www.aljazeera.com 首頁最新新聞。"""

    name = "半岛电视台"
    base_url = "https://www.aljazeera.com"
    listing_paths: List[str] = [
        "/",
        "/asia/",
        "/africa/",
        "/us-canada/",
        "/latin-america/",
        "/europe/",
        "/asia-pacific/",
        "/middle-east/",
    ]

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def get_news_list(self) -> List[NewsRecord]:
        seen: set[str] = set()
        all_records: List[NewsRecord] = []
        paths = self.listing_paths or ["/"]
        for path in paths:
            url = urljoin(self.base_url, path)
            try:
                resp = self.session.get(url, timeout=20)
                resp.raise_for_status()
            except requests.RequestException as exc:  # noqa: BLE001
                logger.warning("抓取 Al Jazeera 頁面失敗 (%s): %s", url, exc)
                continue
            records = self._parse_listing(resp.text, seen=seen)
            all_records.extend(records)
        return all_records

    def get_news_detail(self, record: NewsRecord) -> NewsRecord:
        if not record.url:
            return record
        try:
            resp = self.session.get(record.url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 Al Jazeera 文章失敗 (%s): %s", record.url, exc)
            return record
        return self._parse_detail(resp.text, record)

    def _parse_listing(self, html: str, *, seen: Optional[set[str]] = None) -> List[NewsRecord]:
        soup = BeautifulSoup(html, "html.parser")
        records: List[NewsRecord] = []
        seen_urls = seen if seen is not None else set()
        for card in soup.select("article"):
            link = card.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            if not self._is_valid_path(href):
                continue
            title_node = card.select_one(".article-card__title span")
            title = self._clean_text(title_node.get_text(" ", strip=True) if title_node else link.get_text(" ", strip=True))
            if not title:
                continue
            url = self._absolute_url(href)
            if url in seen_urls:
                continue
            summary_node = card.select_one(".article-card__excerpt")
            summary = self._clean_text(summary_node.get_text(" ", strip=True)) if summary_node else None
            tag = self._clean_text(self._text_or_none(card.select_one(".post-label__text")))
            image = self._extract_image(card)
            record = NewsRecord(
                source=self.name,
                title=title,
                url=url,
                summary=summary,
                raw={
                    "tag": tag,
                    "image": image,
                },
            )
            records.append(record)
            seen_urls.add(url)
        return records

    def _parse_detail(self, html: str, record: NewsRecord) -> NewsRecord:
        soup = BeautifulSoup(html, "html.parser")
        schema = self._extract_schema(soup)
        if schema:
            record.raw["schema"] = schema
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
                normalized_modified = self._normalize_datetime(modified)
                if normalized_modified:
                    record.raw["updated_at"] = normalized_modified
            authors_from_schema = self._authors_from_schema(schema.get("author"))
        else:
            authors_from_schema = []

        title = self._clean_text(self._text_or_none(soup.select_one("main h1")))
        if title:
            record.title = title
        subhead = self._clean_text(self._text_or_none(soup.select_one("p.article__subhead")))
        if subhead:
            record.raw["subhead"] = subhead
            if not record.summary:
                record.summary = subhead

        authors_dom = self._extract_dom_authors(soup)
        authors = authors_dom or authors_from_schema
        if authors:
            record.authors = authors

        published_dom = self._extract_dom_timestamp(soup, ".article-timestamp-published time")
        if published_dom:
            record.published_at = published_dom
        if "updated_at" not in record.raw:
            updated_dom = self._extract_dom_timestamp(soup, ".article-timestamp-updated time")
            if updated_dom:
                record.raw["updated_at"] = updated_dom

        breadcrumbs = [link.get_text(" ", strip=True) for link in soup.select(".breadcrumbs a")]
        if breadcrumbs:
            record.raw["breadcrumbs"] = breadcrumbs

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

    def _is_valid_path(self, href: str) -> bool:
        if not href:
            return False
        parsed = urlparse(self._absolute_url(href))
        return parsed.path.startswith("/news/")

    def _extract_image(self, card: Tag) -> Optional[str]:
        img = card.find("img")
        if img and img.get("src"):
            return self._absolute_url(img["src"]) if img["src"].startswith("/") else img["src"]
        return None

    def _extract_schema(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("@type") in {"NewsArticle", "LiveBlogPosting"}:
                return data
        return None

    def _authors_from_schema(self, data: Any) -> List[str]:
        if not data:
            return []
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
        container = soup.select_one(".contributors-list")
        if not container:
            return []
        names: List[str] = []
        for element in container.children:
            if isinstance(element, str):
                text = element.strip()
                if not text:
                    continue
                if text.lower() in {"by", "and"}:
                    continue
                for piece in (token.strip() for token in text.split(" and ")):
                    if piece:
                        names.append(piece)
            elif getattr(element, "name", "") == "a":
                text = element.get_text(" ", strip=True)
                if text:
                    names.append(text)
        return list(dict.fromkeys(names))

    def _extract_dom_timestamp(self, soup: BeautifulSoup, selector: str) -> Optional[str]:
        node = soup.select_one(selector)
        if not node or not node.get("datetime"):
            return None
        return self._normalize_datetime(node["datetime"])

    def _extract_body(self, soup: BeautifulSoup) -> Optional[str]:
        main = soup.select_one("#main-content-area")
        if not main:
            return None
        paragraphs: List[str] = []
        for node in main.find_all("p"):
            if node.find_parent(class_="article-info"):
                continue
            classes = node.get("class", [])
            if "article__subhead" in classes:
                continue
            text = self._clean_text(node.get_text(" ", strip=True))
            if not text:
                continue
            lowered = text.lower()
            if lowered in {"share", "save"}:
                continue
            paragraphs.append(text)
        return "\n\n".join(paragraphs).strip() if paragraphs else None

    def _meta_keywords(self, soup: BeautifulSoup) -> List[str]:
        keywords = self._meta_content(soup, "keywords")
        if not keywords:
            return []
        return [token.strip() for token in keywords.split(",") if token.strip()]

    def _meta_content(self, soup: BeautifulSoup, name: str) -> Optional[str]:
        meta = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
        if meta and meta.get("content"):
            return meta["content"].strip()
        return None

    def _normalize_datetime(self, value: str) -> Optional[str]:
        if not value:
            return None
        normalized = value.strip().replace("Z", "+00:00") if value.endswith("Z") else value.strip()
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return dt.isoformat()

    def _text_or_none(self, node: Optional[Tag]) -> Optional[str]:
        if not node:
            return None
        text = node.get_text(" ", strip=True)
        return text or None

    def _clean_text(self, text: Optional[str]) -> Optional[str]:
        if text is None:
            return None
        cleaned = " ".join(text.split())
        return cleaned or None
