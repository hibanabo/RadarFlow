"""ABS-CBN 新闻抓取器。"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from .base_fetcher import BaseNewsFetcher, NewsRecord

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

IMAGE_BASE = "https://od2-image-api.abs-cbn.com/prod/"


class AbsCbnNewsFetcher(BaseNewsFetcher):
    """抓取 ABS-CBN 多个频道的新闻列表与详情。"""

    name = "菲律宾ABS-CBN"
    base_url = "https://www.abs-cbn.com"
    listing_paths: List[str] = [
        "/news/world",
        "/news/nation",
        "/news/regions",
    ]

    api_paths: List[str] = [
        "world",
        "nation",
        "regions",
    ]

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def get_news_list(self) -> List[NewsRecord]:
        seen: set[str] = set()
        records: List[NewsRecord] = []
        for path in self.listing_paths:
            url = urljoin(self.base_url, path)
            try:
                resp = self.session.get(url, timeout=20)
                resp.raise_for_status()
            except requests.RequestException as exc:  # noqa: BLE001
                logger.warning("抓取 ABS-CBN 列表失败 (%s): %s", url, exc)
                continue
            records.extend(self._parse_listing(resp.text, seen))
        for section in self.api_paths:
            records.extend(self._fetch_api_listing(section, seen))
        return records

    def get_news_detail(self, record: NewsRecord) -> NewsRecord:
        if not record.url:
            return record
        try:
            resp = self.session.get(record.url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 ABS-CBN 详情失败 (%s): %s", record.url, exc)
            return record
        return self._parse_detail(resp.text, record)

    def _parse_listing(self, html: str, seen: set[str]) -> List[NewsRecord]:
        data = self._load_next_data(html)
        items = list(self._iter_listing_items(data))
        records: List[NewsRecord] = []
        for item in items:
            slug_path = item.get("slugline_url")
            if not slug_path:
                continue
            url = urljoin(self.base_url, slug_path.lstrip("/"))
            if url in seen:
                continue
            title = item.get("title") or item.get("slugline")
            if not title:
                continue
            summary = item.get("abstract") or item.get("description_text")
            summary = self._clean_text(summary)
            image = self._normalize_image(item.get("deskUrl") or item.get("image"))
            published = item.get("createdDateFull") or item.get("updatedDateFull")
            record = NewsRecord(
                source=self.name,
                title=title.strip(),
                url=url,
                summary=summary,
                published_at=self._normalize_datetime(published) if published else None,
                raw={
                    "category": item.get("category"),
                    "image": image,
                },
            )
            records.append(record)
            seen.add(url)
        return records

    def _fetch_api_listing(self, section: str, seen: set[str]) -> List[NewsRecord]:
        records: List[NewsRecord] = []
        base_api = "https://od2-content-api.abs-cbn.com/prod/latest"
        limit = 12
        for page in range(2):  # fetch two pages by default
            params = {
                "sectionId": section,
                "brand": "OD",
                "partner": "imp-01",
                "limit": str(limit),
                "offset": str(page * limit),
            }
            try:
                resp = self.session.get(base_api, params=params, timeout=15)
                resp.raise_for_status()
            except requests.RequestException as exc:  # noqa: BLE001
                logger.warning("ABS-CBN API 拉取失败(%s/%s): %s", section, page, exc)
                break
            data = resp.json()
            items = data.get("listItem") if isinstance(data, dict) else None
            if not items:
                break
            for item in items:
                slug_path = item.get("slugline_url")
                if not slug_path:
                    continue
                url = urljoin(self.base_url, slug_path.lstrip("/"))
                if url in seen:
                    continue
                title = item.get("title") or item.get("slugline")
                if not title:
                    continue
                summary = self._clean_text(item.get("abstract"))
                published = item.get("createdDateFull") or item.get("updatedDateFull")
                image = self._normalize_image(item.get("deskUrl") or item.get("image"))
                record = NewsRecord(
                    source=self.name,
                    title=title.strip(),
                    url=url,
                    summary=summary,
                    published_at=self._normalize_datetime(published) if published else None,
                    raw={
                        "category": item.get("category"),
                        "image": image,
                        "_api": True,
                    },
                )
                records.append(record)
                seen.add(url)
        return records

    def _parse_detail(self, html: str, record: NewsRecord) -> NewsRecord:
        data = self._load_next_data(html)
        article = self._find_article(data)
        if not article:
            record.raw.setdefault("detail_html", html)
            return record
        title = article.get("headline") or article.get("slugline")
        if title:
            record.title = title.strip()
        summary = article.get("description_text") or article.get("description_html")
        if summary:
            record.summary = self._clean_text(summary)
        body_html = article.get("body_html")
        body_text = self._render_body(body_html)
        if body_text:
            record.raw["content_text"] = body_text
            if not record.summary:
                record.summary = body_text.split("\n\n", 1)[0][:200]
        published = article.get("firstpublished") or article.get("firstcreated")
        if published:
            record.published_at = self._normalize_datetime(published)
        updated = article.get("versioncreated") or article.get("_updated")
        if updated:
            record.raw["updated_at"] = self._normalize_datetime(updated)
        authors = self._extract_authors(article.get("authors", []))
        if authors:
            record.authors = authors
        tags = self._extract_tags(article)
        if tags:
            record.raw["keywords"] = tags
        hero = self._normalize_image(self._extract_hero_image(article))
        if hero:
            record.raw["image"] = hero
        return record

    def _load_next_data(self, html: str) -> Any:
        soup = BeautifulSoup(html, "html.parser")
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return {}
        try:
            raw = json.loads(script.string)
            data_str = raw.get("props", {}).get("pageProps", {}).get("dataStr")
            return json.loads(data_str) if data_str else {}
        except json.JSONDecodeError as exc:  # noqa: BLE001
            logger.warning("解析 ABS-CBN JSON 失败: %s", exc)
            return {}

    def _iter_listing_items(self, data: Any) -> Iterable[Dict[str, Any]]:
        if isinstance(data, dict):
            if "slugline_url" in data:
                yield data
            for value in data.values():
                yield from self._iter_listing_items(value)
        elif isinstance(data, list):
            for item in data:
                yield from self._iter_listing_items(item)

    def _find_article(self, data: Any) -> Optional[Dict[str, Any]]:
        if isinstance(data, dict):
            if data.get("name") == "articleContentOd":
                if "article" in data:
                    return data["article"]
                props = data.get("articleProps")
                if isinstance(props, dict) and "article" in props:
                    return props["article"]
            for value in data.values():
                found = self._find_article(value)
                if found:
                    return found
        elif isinstance(data, list):
            for item in data:
                found = self._find_article(item)
                if found:
                    return found
        return None

    def _extract_authors(self, authors: Any) -> List[str]:
        names: List[str] = []
        for entry in authors or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name") or entry.get("byline")
            if name:
                names.append(name.strip())
        return names

    def _extract_tags(self, article: Dict[str, Any]) -> List[str]:
        tags: List[str] = []
        extra = article.get("extra", {})
        tags_str = extra.get("tags") if isinstance(extra, dict) else None
        if isinstance(tags_str, str):
            tags.extend([token.strip() for token in tags_str.split(",") if token.strip()])
        for subject in article.get("subject", []) or []:
            name = subject.get("name") if isinstance(subject, dict) else None
            if name:
                tags.append(name.strip())
        return list(dict.fromkeys(tags))

    def _extract_hero_image(self, article: Dict[str, Any]) -> Optional[str]:
        associations = article.get("associations") or {}
        thumb = associations.get("Thumbnail") if isinstance(associations, dict) else None
        if isinstance(thumb, dict):
            for key in ("image", "image_url", "coverImage"):
                value = thumb.get(key)
                if value:
                    return value
        return None

    def _render_body(self, html: Optional[str]) -> Optional[str]:
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        parts: List[str] = []
        for node in soup.find_all(["p", "li"]):
            text = node.get_text(" ", strip=True)
            cleaned = self._clean_text(text)
            if cleaned:
                parts.append(cleaned)
        return "\n\n".join(parts).strip() if parts else None

    def _normalize_image(self, image: Optional[str]) -> Optional[str]:
        if not image:
            return None
        if image.startswith("http"):
            return image
        return urljoin(IMAGE_BASE, image.lstrip("/"))

    def _normalize_datetime(self, value: str) -> Optional[str]:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt.isoformat()

    def _clean_text(self, text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        cleaned = " ".join(text.split())
        return cleaned or None
