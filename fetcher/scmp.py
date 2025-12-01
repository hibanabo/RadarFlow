"""South China Morning Post 抓取器."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from html import unescape
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .base_fetcher import BaseNewsFetcher, NewsRecord

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}


class SCMPNewsFetcher(BaseNewsFetcher):
    """抓取 https://www.scmp.com/ 最新焦點新聞."""

    name = "香港南华早报"
    base_url = "https://www.scmp.com"
    homepage_url = "https://www.scmp.com/"
    default_section_urls: List[str] = [
        homepage_url,
        "https://www.scmp.com/news/china",
        "https://www.scmp.com/economy",
        "https://www.scmp.com/news/hong-kong",
        "https://www.scmp.com/week-asia",
        "https://www.scmp.com/news/world",
        "https://www.scmp.com/news/asia",
    ]

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        section_urls: Optional[Iterable[str]] = None,
    ) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        if section_urls:
            urls = list(section_urls)
        else:
            urls = list(self.default_section_urls)
        # 去掉重复 URL，保持顺序
        unique: List[str] = []
        seen: set[str] = set()
        for url in urls:
            if not url or url in seen:
                continue
            unique.append(url)
            seen.add(url)
        self.section_urls = unique

    def get_news_list(self) -> List[NewsRecord]:
        records: List[NewsRecord] = []
        seen_url: set[str] = set()
        for url in self.section_urls:
            nodes = self._load_section_nodes(url)
            for node in nodes:
                record = self._node_to_record(node)
                if not record:
                    continue
                if record.url in seen_url:
                    continue
                records.append(record)
                seen_url.add(record.url)
        return records

    def get_news_detail(self, record: NewsRecord) -> NewsRecord:
        if not record.url:
            return record
        try:
            resp = self.session.get(record.url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 SCMP 详情失败 (%s): %s", record.url, exc)
            return record
        next_data = self._extract_next_data(resp.text)
        if not next_data:
            return record
        article = (
            next_data.get("props", {})
            .get("pageProps", {})
            .get("payload", {})
            .get("data", {})
            .get("article")
        )
        if not isinstance(article, dict):
            return record
        return self._apply_article_detail(record, article)

    def _load_section_nodes(self, url: str) -> List[Dict[str, Any]]:
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 SCMP 页面失败 (%s): %s", url, exc)
            return []
        next_data = self._extract_next_data(resp.text)
        if not next_data:
            return []
        payload = (
            next_data.get("props", {})
            .get("pageProps", {})
            .get("payload", {})
            .get("data")
        )
        if not isinstance(payload, dict):
            return []
        return self._collect_nodes(payload)

    def _extract_next_data(self, html: str) -> Dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        script = soup.find("script", id="__NEXT_DATA__", type="application/json")
        if not script or not script.string:
            logger.warning("SCMP 页面缺少 __NEXT_DATA__")
            return {}
        try:
            return json.loads(script.string)
        except json.JSONDecodeError as exc:  # noqa: BLE001
            logger.warning("解析 SCMP __NEXT_DATA__ 失败: %s", exc)
            return {}

    def _collect_nodes(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        buckets: List[Any] = [
            payload.get("contents"),
            payload.get("topStories"),
            payload.get("storyPackageArticles"),
            payload.get("secondaryStoryPackageArticles"),
            payload.get("highlightQueue"),
            payload.get("spotlightQueue"),
            payload.get("focus"),
            payload.get("commentQueue"),
            payload.get("morningStudioQueue"),
            payload.get("thingToDoQueue"),
            payload.get("seriesWidgetArticles"),
            payload.get("chinaScienceQueue"),
            payload.get("chinaFutureTechStoryPackageArticles"),
        ]
        nodes: List[Dict[str, Any]] = []
        for bucket in buckets:
            nodes.extend(self._extract_nodes(bucket))
        return nodes

    def _extract_nodes(self, bucket: Any) -> List[Dict[str, Any]]:
        if not bucket:
            return []
        if isinstance(bucket, dict):
            if "edges" in bucket:
                return [
                    edge.get("node")  # type: ignore[return-value]
                    for edge in bucket.get("edges", [])
                    if isinstance(edge, dict) and isinstance(edge.get("node"), dict)
                ]
            if "items" in bucket:
                return self._extract_nodes(bucket.get("items"))
        if isinstance(bucket, list):
            nodes: List[Dict[str, Any]] = []
            for item in bucket:
                nodes.extend(self._extract_nodes(item))
            return nodes
        return []

    def _node_to_record(self, node: Dict[str, Any]) -> Optional[NewsRecord]:
        headline = self._clean_text(
            node.get("headline") or node.get("title") or node.get("seriesShortLabel")
        )
        url_alias = node.get("urlAlias")
        if not headline or not url_alias:
            return None
        summary = self._extract_plain_text(node.get("summary"))
        if not summary:
            summary = self._clean_text(node.get("socialHeadline"))
        url = urljoin(self.base_url, url_alias.lstrip("/"))
        published_at = self._normalize_timestamp(node.get("publishedDate"))
        record = NewsRecord(
            source=self.name,
            title=headline,
            url=url,
            summary=summary,
        )
        if published_at:
            record.published_at = published_at
        record.raw = {
            "entityId": str(node.get("entityId") or ""),
            "entityUuid": node.get("entityUuid"),
            "sections": self._collect_sections(node),
            "images": node.get("images"),
        }
        return record

    def _apply_article_detail(self, record: NewsRecord, article: Dict[str, Any]) -> NewsRecord:
        title = self._clean_text(article.get("headline") or article.get("title"))
        if title:
            record.title = title
        summary = self._extract_plain_text(article.get("summary"))
        if summary:
            record.summary = summary
        body_text = self._extract_plain_text(article.get("body"))
        if body_text:
            record.raw["content_text"] = body_text.strip()
            if not record.summary:
                record.summary = body_text.strip().split("\n\n", 1)[0][:200]
        authors = [
            self._clean_text(author.get("name"))
            for author in article.get("authors", [])
            if isinstance(author, dict) and self._clean_text(author.get("name"))
        ]
        if authors:
            record.authors = authors
        published_at = self._normalize_timestamp(article.get("publishedDate"))
        if published_at:
            record.published_at = published_at
        updated_at = self._normalize_timestamp(article.get("updatedDate"))
        if updated_at:
            record.raw["updated_at"] = updated_at
        keywords = [
            self._clean_text(keyword)
            for keyword in article.get("keywords", [])
            if isinstance(keyword, str)
        ]
        if keywords:
            record.raw["keywords"] = keywords
        topics = [
            self._clean_text(topic.get("name"))
            for topic in article.get("topics", [])
            if isinstance(topic, dict) and self._clean_text(topic.get("name"))
        ]
        if topics:
            record.raw["topics"] = topics
        record.raw["comment_count"] = article.get("commentCount")
        record.raw["reading_time"] = article.get("readingTime")
        record.raw["short_url"] = article.get("shortUrl")
        return record

    def _collect_sections(self, node: Dict[str, Any]) -> List[str]:
        sections: List[str] = []
        for group in node.get("sections", []):
            values = group.get("value") if isinstance(group, dict) else None
            if not isinstance(values, list):
                continue
            for item in values:
                if isinstance(item, dict):
                    name = self._clean_text(item.get("name"))
                    if name:
                        sections.append(name)
        return sections

    def _extract_plain_text(self, data: Any) -> Optional[str]:
        if isinstance(data, dict):
            if "text" in data and isinstance(data["text"], str):
                return self._clean_text(data["text"])
            if "json" in data and isinstance(data["json"], list):
                return self._flatten_body_nodes(data["json"])
        if isinstance(data, str):
            return self._clean_text(data)
        return None

    def _flatten_body_nodes(self, nodes: Iterable[Any]) -> Optional[str]:
        parts: List[str] = []
        for node in nodes:
            text = self._extract_from_node(node)
            if text:
                parts.append(text)
        if not parts:
            return None
        return "\n\n".join(part for part in parts if part)

    def _extract_from_node(self, node: Any) -> Optional[str]:
        if not isinstance(node, dict):
            return None
        node_type = node.get("type")
        if node_type in {"p", "h2", "h3", "blockquote"}:
            pieces: List[str] = []
            for child in node.get("children", []):
                child_text = self._extract_from_node(child)
                if child_text:
                    pieces.append(child_text)
            joined = "".join(pieces).strip()
            return joined or None
        if node_type == "text":
            return self._clean_text(node.get("data"))
        if node_type == "a":
            pieces = []
            for child in node.get("children", []):
                child_text = self._extract_from_node(child)
                if child_text:
                    pieces.append(child_text)
            return "".join(pieces) or None
        if node_type == "image":
            caption = self._clean_text(node.get("caption"))
            return caption
        return None

    def _clean_text(self, value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return None
        cleaned = unescape(value).strip()
        return cleaned or None

    def _normalize_timestamp(self, raw: Any) -> Optional[str]:
        if isinstance(raw, (int, float)):
            dt = datetime.fromtimestamp(raw / 1000, tz=timezone.utc)
            return dt.isoformat()
        if isinstance(raw, str):
            try:
                # Some API responses already return ISO 格式
                return datetime.fromisoformat(raw).astimezone(timezone.utc).isoformat()
            except ValueError:
                return None
        return None
