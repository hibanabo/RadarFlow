"""联合早报·即时新闻抓取实现。"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from .base_fetcher import BaseNewsFetcher, NewsRecord

logger = logging.getLogger(__name__)


class ZaobaoRealtimeFetcher(BaseNewsFetcher):
    """抓取联合早报即时新闻列表及详情。"""

    name = "联合早报·即时"
    base_url = "https://www.zaobao.com.sg"
    realtime_path = "/realtime"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()

    def get_news_list(self) -> List[NewsRecord]:
        resp = self.session.get(self.base_url + self.realtime_path, timeout=15)
        resp.raise_for_status()
        return self._parse_listing(resp.text)

    def _parse_listing(self, html: str) -> List[NewsRecord]:
        soup = BeautifulSoup(html, "html.parser")
        records: List[NewsRecord] = []
        for listing in soup.select("ul.card-listing"):
            category = self._extract_category(listing)
            for card in listing.select("div.card.timestamp-card"):
                anchor = card.select_one("a[href]")
                title_el = card.select_one("h2.card-header")
                if not anchor or not title_el:
                    continue
                href = anchor.get("href", "")
                url = self._absolute_url(href)
                timestamp_el = card.select_one(".text-brand-primary")
                timestamp = timestamp_el.get_text(strip=True) if timestamp_el else None
                record = NewsRecord(
                    source=self.name,
                    title=title_el.get_text(strip=True),
                    url=url,
                    summary=None,
                    published_at=timestamp,
                    raw={"category": category, "timestamp": timestamp, "path": href},
                )
                records.append(record)
        return records

    def _extract_category(self, listing) -> Optional[str]:
        header = listing.find_previous_sibling(
            lambda tag: tag.name == "div"
            and tag.get("class")
            and "card-header" in tag.get("class", [])
            and "flex" in tag.get("class", [])
        )
        if header:
            link = header.find("a")
            if link:
                return link.get_text(strip=True)
        return None

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
            logger.warning("抓取早报详情失败 (%s): %s", record.url, exc)
            return record

        soup = BeautifulSoup(resp.text, "html.parser")
        schema_article = self._parse_schema_article(soup)
        ga_meta = self._extract_ga_data_layer(soup)
        script = soup.find(
            "script",
            string=lambda text: isinstance(text, str) and "window.__staticRouterHydrationData" in text,
        )
        if not script or not script.string:
            record.raw.setdefault("detail_html", resp.text)
            return record
        data = self._extract_json(script.string)
        if not data:
            record.raw.setdefault("detail_html", resp.text)
            return record
        article = (
            data.get("loaderData", {})
            .get("0-0", {})
            .get("context", {})
            .get("payload", {})
            .get("article")
        )
        if not article:
            return record
        body_html = article.get("body_cn")
        if body_html:
            record.raw["content_html"] = body_html
            text = BeautifulSoup(body_html, "html.parser").get_text("\n", strip=True)
            record.raw["content_text"] = text
            if not record.summary:
                record.summary = article.get("teaser") or text[:120]
        if schema_article:
            date_published = schema_article.get("datePublished")
            if date_published:
                record.published_at = date_published
            authors = self._extract_authors(schema_article.get("author"))
            if authors:
                record.authors = authors
                record.raw["authors"] = authors
        if not record.authors:
            authors = self._extract_authors(article.get("author"))
            if authors:
                record.authors = authors
                record.raw["authors"] = authors
        if not record.published_at:
            record.published_at = self._normalize_datetime(
                article.get("created_at") or article.get("publish_time") or article.get("update_time")
            )
        if not record.published_at and ga_meta.get("pubdate"):
            record.published_at = self._normalize_datetime(ga_meta.get("pubdate"))
        if not record.authors and ga_meta.get("author"):
            record.authors = [ga_meta["author"]]
            record.raw["authors"] = record.authors
        record.raw["tags"] = article.get("tags")
        record.raw["detail"] = article
        return record

    def _extract_json(self, script_text: str) -> Optional[dict]:
        marker = 'JSON.parse("'
        start = script_text.find(marker)
        if start == -1:
            return None
        start += len(marker)
        chars: List[str] = []
        i = start
        escaped = False
        while i < len(script_text):
            ch = script_text[i]
            if ch == "\\" and not escaped:
                escaped = True
                chars.append(ch)
                i += 1
                continue
            if ch == '"' and not escaped:
                break
            chars.append(ch)
            escaped = False
            i += 1
        raw_json = "".join(chars)
        try:
            decoded = json.loads(f'"{raw_json}"')
            return json.loads(decoded)
        except json.JSONDecodeError as exc:  # noqa: BLE001
            logger.warning("解析早报详情 JSON 失败: %s", exc)
            return None

    def _parse_schema_article(self, soup: BeautifulSoup) -> Optional[dict]:
        script = soup.find("script", id="seo-article-page", type="application/ld+json")
        if not script or not script.string:
            return None
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            return None
        graph = data.get("@graph")
        candidates = graph if isinstance(graph, list) else [data]
        for item in candidates:
            if isinstance(item, dict) and item.get("@type") in {"NewsArticle", "ReportageNewsArticle"}:
                return item
        return None

    def _extract_authors(self, author_field: Optional[any]) -> List[str]:
        authors: List[str] = []
        if isinstance(author_field, list):
            for entry in author_field:
                if isinstance(entry, dict) and entry.get("name"):
                    authors.append(entry["name"])
                elif isinstance(entry, str):
                    authors.append(entry)
        elif isinstance(author_field, dict) and author_field.get("name"):
            authors.append(author_field["name"])
        elif isinstance(author_field, str):
            authors.append(author_field)
        return authors

    def _normalize_datetime(self, value: Optional[Any]) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            try:
                return (
                    datetime.fromtimestamp(float(value), tz=timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z")
                )
            except (OverflowError, ValueError):
                return None
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            if text.isdigit():
                return self._normalize_datetime(int(text))
            if "T" not in text and " " in text:
                text = text.replace(" ", "T")
            return text
        return None

    def _extract_ga_data_layer(self, soup: BeautifulSoup) -> Dict[str, str]:
        script = soup.find("script", id="ga_data_layer")
        if not script or not script.string:
            return {}
        match = re.search(r"var\s+_data\s*=\s*({.*?})", script.string, re.S)
        if not match:
            return {}
        block = match.group(1)
        result: Dict[str, str] = {}
        for key in ("pubdate", "author"):
            pattern = re.compile(rf'"{key}"\s*:\s*"([^"]+)"')
            field_match = pattern.search(block)
            if field_match:
                result[key] = field_match.group(1).strip()
        return result
