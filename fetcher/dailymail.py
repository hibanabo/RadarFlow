"""Daily Mail 首页与文章抓取器。"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from .base_fetcher import BaseNewsFetcher, NewsRecord

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9",
}


class DailyMailNewsFetcher(BaseNewsFetcher):
    """抓取 Daily Mail (UK) 首页新闻。"""

    name = "英国每日邮报"
    base_url = "https://www.dailymail.co.uk"
    listing_path = "/home/index.html"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def get_news_list(self) -> List[NewsRecord]:
        try:
            resp = self.session.get(urljoin(self.base_url, self.listing_path), timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 Daily Mail 首页失败: %s", exc)
            return []
        return self._parse_listing(resp.text)

    def get_news_detail(self, record: NewsRecord) -> NewsRecord:
        if not record.url:
            return record
        try:
            resp = self.session.get(record.url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 Daily Mail 详情失败 (%s): %s", record.url, exc)
            return record
        return self._parse_detail(resp.text, record)

    def _parse_listing(self, html: str) -> List[NewsRecord]:
        soup = BeautifulSoup(html, "html.parser")
        records: List[NewsRecord] = []
        seen: set[str] = set()
        for article in soup.select("div.article"):
            anchor = article.find("a", href=True)
            if not anchor:
                continue
            href = anchor["href"]
            if "/article-" not in href:
                continue
            title = self._clean_text(anchor.get_text(" ", strip=True))
            if not title:
                continue
            url = urljoin(self.base_url, href)
            if not self._is_supported_domain(url):
                continue
            if url in seen:
                continue
            summary = self._extract_summary(article)
            channel = self._infer_channel(href)
            image = self._extract_image(article)
            record = NewsRecord(
                source=self.name,
                title=title,
                url=url,
                summary=summary,
                raw={
                    "channel": channel,
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
            record.raw["schema"] = schema
            description = schema.get("description")
            if isinstance(description, str) and description.strip():
                record.summary = description.strip()
            published = schema.get("datePublished")
            if published:
                iso = self._normalize_datetime(published)
                if iso:
                    record.published_at = iso
        title = self._extract_title(soup)
        if title:
            record.title = title
        author = self._extract_author(soup)
        if author:
            record.authors = [author]
        published_time = self._extract_timestamp(soup, ".article-timestamp-published time[datetime]")
        if published_time:
            record.published_at = published_time
        updated_time = self._extract_timestamp(soup, ".article-timestamp-updated time[datetime]")
        if updated_time:
            record.raw["updated_at"] = updated_time
        body = self._extract_body(soup)
        if body:
            record.raw["content_text"] = body
            if not record.summary:
                record.summary = body.split("\n\n", 1)[0][:200]
        keywords = self._meta_keywords(soup)
        if keywords:
            record.raw["keywords"] = keywords
        channel = self._meta_content(soup, "channel")
        if channel:
            record.raw["channel"] = channel
        return record

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        headline = soup.select_one("h1")
        if headline:
            return self._clean_text(headline.get_text(" ", strip=True))
        meta_title = self._meta_content(soup, "og:title")
        return meta_title

    def _extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        author_link = soup.select_one(".article-text .author")
        if author_link:
            return self._normalize_author(author_link.get_text(" ", strip=True))
        meta_author = self._meta_content(soup, "author")
        if meta_author:
            return self._normalize_author(meta_author)
        return None

    def _extract_body(self, soup: BeautifulSoup) -> Optional[str]:
        container = soup.select_one('[itemprop="articleBody"]') or soup.select_one(".article-text")
        if not container:
            return None
        paragraphs: List[str] = []
        for node in container.find_all(["p", "li"]):
            text = node.get_text(" ", strip=True)
            text = self._clean_text(text)
            if text:
                paragraphs.append(text)
        return "\n\n".join(paragraphs).strip() if paragraphs else None

    def _extract_summary(self, article: Tag) -> Optional[str]:
        para = article.select_one(".articletext p") or article.find("p")
        if not para:
            return None
        return self._clean_text(para.get_text(" ", strip=True))

    def _extract_image(self, article: Tag) -> Optional[str]:
        img = article.find("img")
        if not img:
            return None
        for attr in ("data-src", "data-srcset", "src"):
            value = img.get(attr)
            if value:
                return value.split()[0]
        return None

    def _infer_channel(self, href: str) -> Optional[str]:
        parsed = urlparse(urljoin(self.base_url, href))
        parts = parsed.path.strip("/").split("/")
        if parts:
            return parts[0]
        return None

    def _is_supported_domain(self, url: str) -> bool:
        hostname = urlparse(url).hostname
        if not hostname:
            return False
        return hostname.endswith("dailymail.co.uk")

    def _extract_schema(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("@type") == "NewsArticle":
                return data
        return None

    def _extract_timestamp(self, soup: BeautifulSoup, selector: str) -> Optional[str]:
        node = soup.select_one(selector)
        if not node:
            return None
        datetime_attr = node.get("datetime")
        if not datetime_attr:
            return None
        return self._normalize_datetime(datetime_attr)

    def _normalize_datetime(self, value: str) -> Optional[str]:
        value = value.strip()
        try:
            dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            return None
        return dt.isoformat()

    def _normalize_author(self, text: str) -> str:
        cleaned = text.replace("By", "").replace("BY", "").strip(" :")
        if not cleaned:
            return "Daily Mail"
        # title-case the name but keep the remainder intact
        parts = cleaned.split(",", 1)
        name = parts[0].title()
        if len(parts) == 2:
            suffix = parts[1].strip()
            suffix = suffix.title() if suffix else ""
            return f"{name}, {suffix}".strip()
        return name

    def _clean_text(self, text: str) -> str:
        return " ".join(text.split())

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
