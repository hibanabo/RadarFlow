"""8world 世界频道抓取器。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from html import unescape
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from .base_fetcher import BaseNewsFetcher, NewsRecord

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

SG_TZ = timezone(timedelta(hours=8))


class EightWorldNewsFetcher(BaseNewsFetcher):
    """抓取 https://www.8world.com/world 的新闻。"""

    name = "8视界世界"
    base_url = "https://www.8world.com"
    default_section_urls: List[str] = [
        "https://www.8world.com/world",
        "https://www.8world.com/greater-china",
        "https://www.8world.com/southeast-asia",
        "https://www.8world.com/singapore",
        "https://www.8world.com/realtime",
    ]
    default_max_pages = 3

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        section_urls: Optional[List[str]] = None,
        max_pages: int = default_max_pages,
    ) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        urls = section_urls or self.default_section_urls
        self.section_urls = list(dict.fromkeys(urls))  # preserve order, remove dup
        self.max_pages = max(1, max_pages)

    def get_news_list(self) -> List[NewsRecord]:
        records: List[NewsRecord] = []
        seen: set[str] = set()
        for base_url in self.section_urls:
            for page in range(self.max_pages):
                page_url = self._build_page_url(base_url, page)
                page_records = self._fetch_listing_page(page_url)
                for record in page_records:
                    if record.url in seen:
                        continue
                    records.append(record)
                    seen.add(record.url)
        return records

    def get_news_detail(self, record: NewsRecord) -> NewsRecord:
        if not record.url:
            return record
        try:
            resp = self.session.get(record.url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 8world 文章失败 (%s): %s", record.url, exc)
            return record
        return self._parse_detail(resp.text, record)

    def _fetch_listing_page(self, url: str) -> List[NewsRecord]:
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 8world 列表页失败 (%s): %s", url, exc)
            return []
        return self._parse_listing(resp.text)

    def _parse_listing(self, html: str) -> List[NewsRecord]:
        soup = BeautifulSoup(html, "html.parser")
        container = soup.select_one(".category__listing")
        if not container:
            logger.warning("8world 列表页缺少 category__listing 模块")
            return []
        records: List[NewsRecord] = []
        for article in container.select("article.article"):
            link = article.select_one("a.article-link")
            title_span = article.select_one("h3.article-title span")
            if not link or not link.get("href") or not title_span:
                continue
            url = self._absolute_url(link["href"])
            published = self._parse_datetime(
                article.select_one(".article-time time"),
                fallback_text=article.select_one(".article-time"),
            )
            summary = None
            record = NewsRecord(
                source=self.name,
                title=title_span.get_text(strip=True),
                url=url,
                summary=summary,
            )
            if published:
                record.published_at = published
            record.raw = {
                "category": self._clean_text(article.select_one(".article-meta .category span")),
                "thumbnail": self._image_src(article),
            }
            records.append(record)
        return records

    def _parse_detail(self, html: str, record: NewsRecord) -> NewsRecord:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.select_one("h1.h1 span")
        if title:
            record.title = title.get_text(strip=True)
        summary_meta = soup.find("meta", attrs={"name": "description"})
        if summary_meta and summary_meta.get("content"):
            record.summary = summary_meta["content"].strip()
        published = self._extract_detail_published(soup)
        if published:
            record.published_at = published
        keywords_meta = soup.find("meta", attrs={"name": "keywords"})
        if keywords_meta and keywords_meta.get("content"):
            keywords = [kw.strip() for kw in keywords_meta["content"].split(",") if kw.strip()]
            if keywords:
                record.raw["keywords"] = keywords
        body_section = soup.select_one("div.article-content section.block-field-blocknodearticlefield-content")
        if body_section:
            body_text = self._normalize_body_text(body_section.get_text("\n", strip=True))
            if body_text:
                record.raw["content_text"] = body_text
                if not record.summary:
                    record.summary = body_text.split("\n\n", 1)[0][:200]
        hero_image = soup.select_one(".article-media .article-image")
        if hero_image and hero_image.get("style"):
            record.raw["hero_image"] = self._extract_background_url(hero_image["style"])
        time_meta = soup.find("meta", attrs={"property": "article:published_time"})
        if time_meta and time_meta.get("content"):
            record.raw["published_time_meta"] = time_meta["content"]
        return record

    def _parse_datetime(self, time_tag: Optional[Tag], fallback_text: Optional[Tag] = None) -> Optional[str]:
        candidates: List[str] = []
        if time_tag and time_tag.get("datetime"):
            candidates.append(time_tag["datetime"])
        if fallback_text:
            candidates.append(fallback_text.get_text(strip=True))
        for text in candidates:
            parsed = self._parse_known_formats(text)
            if parsed:
                return parsed
        return None

    def _parse_known_formats(self, value: str) -> Optional[str]:
        cleaned = value.strip()
        for fmt in ("%d/%m/%Y %H:%M", "%d %b %Y %H:%M"):
            try:
                dt = datetime.strptime(cleaned, fmt)
                return dt.replace(tzinfo=SG_TZ).isoformat()
            except ValueError:
                continue
        return None

    def _extract_detail_published(self, soup: BeautifulSoup) -> Optional[str]:
        publish_li = soup.select_one(".article-info .publishing .publish")
        if publish_li:
            text = publish_li.get_text(strip=True).replace("发布", "").replace(":", "").strip()
            parsed = self._parse_known_formats(text)
            if parsed:
                return parsed
        time_tag = soup.select_one(".article-header time")
        if time_tag:
            return self._parse_datetime(time_tag)
        return None

    def _normalize_body_text(self, text: str) -> str:
        parts = [line.strip() for line in text.splitlines()]
        cleaned = [line for line in parts if line]
        return "\n\n".join(cleaned)

    def _extract_background_url(self, style_value: str) -> Optional[str]:
        marker = "url('"
        if marker in style_value:
            start = style_value.find(marker) + len(marker)
            end = style_value.find("')", start)
            if end > start:
                return style_value[start:end]
        return None

    def _image_src(self, article: Tag) -> Optional[str]:
        img = article.select_one("figure img")
        if img and img.get("src"):
            return img["src"]
        return None

    def _clean_text(self, node: Optional[Tag]) -> Optional[str]:
        if not node:
            return None
        text = node.get_text(strip=True)
        return unescape(text) if text else None

    def _absolute_url(self, href: str) -> str:
        return urljoin(self.base_url, href)

    def _build_page_url(self, base_url: str, page: int) -> str:
        if page <= 0:
            return base_url
        joiner = "&" if "?" in base_url else "?"
        return f"{base_url}{joiner}page={page}"
