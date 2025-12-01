"""朝日新聞首页抓取器。"""
from __future__ import annotations

import logging
import re
from typing import List, Optional, Sequence
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Tag

from .base_fetcher import BaseNewsFetcher, NewsRecord

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.8,zh;q=0.7",
}


class AsahiNewsFetcher(BaseNewsFetcher):
    """抓取朝日新聞首页的速報ニュース以及详情。"""

    name = "朝日新聞"
    base_url = "https://www.asahi.com/"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()

    def get_news_list(self) -> List[NewsRecord]:
        try:
            resp = self.session.get(self.base_url, timeout=20, headers=DEFAULT_HEADERS)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取朝日新聞首页失败: %s", exc)
            return []
        html = self._ensure_utf8(resp)
        return self._parse_listing(html)

    def _parse_listing(self, html: str) -> List[NewsRecord]:
        soup = BeautifulSoup(html, "html.parser")
        records: List[NewsRecord] = []
        seen_urls: set[str] = set()
        records.extend(self._collect_breaking_news(soup, seen_urls))
        records.extend(self._collect_all_articles(soup, seen_urls))
        return records

    def _collect_breaking_news(self, soup: BeautifulSoup, seen_urls: set[str]) -> List[NewsRecord]:
        breaking_records: List[NewsRecord] = []
        items = soup.select("ul.p-breaking__List li.p-breaking__listItem a")
        for anchor in items:
            href = anchor.get("href")
            if not href:
                continue
            url, clean_path = self._normalize_article_url(href)
            if url in seen_urls:
                continue
            title = self._extract_breaking_title(anchor)
            if not title:
                continue
            seen_urls.add(url)
            time_cell = anchor.select_one(".p-breaking__timeCell")
            breaking_records.append(
                NewsRecord(
                    source=self.name,
                    title=title,
                    url=url,
                    raw={
                        "path": clean_path,
                        "relative_time": time_cell.get_text(strip=True) if time_cell else None,
                        "section": "速報ニュース",
                    },
                )
            )
        return breaking_records

    def _collect_all_articles(self, soup: BeautifulSoup, seen_urls: set[str]) -> List[NewsRecord]:
        generic_records: List[NewsRecord] = []
        for anchor in soup.select('a[href^="/articles/"]'):
            href = anchor.get("href")
            if not href:
                continue
            url, clean_path = self._normalize_article_url(href)
            if url in seen_urls:
                continue
            title = self._extract_generic_title(anchor)
            if not title or len(title) < 4:
                continue
            seen_urls.add(url)
            section = self._guess_section(anchor)
            generic_records.append(
                NewsRecord(
                    source=self.name,
                    title=title,
                    url=url,
                    raw={
                        "path": clean_path,
                        "section": section,
                    },
                )
            )
        return generic_records

    def _extract_breaking_title(self, anchor: Tag) -> str:
        span_nodes = anchor.find_all("span")
        if len(span_nodes) >= 2:
            return self._normalize_text(span_nodes[-1].get_text(strip=True))
        return self._normalize_text(anchor.get_text(strip=True))

    def _extract_generic_title(self, anchor: Tag) -> str:
        text = anchor.get_text(" ", strip=True)
        if text:
            return self._normalize_text(text)
        title_attr = anchor.get("title")
        if isinstance(title_attr, str):
            return self._normalize_text(title_attr.strip())
        return ""

    def _guess_section(self, anchor: Tag) -> Optional[str]:
        section_node = anchor.find_parent(attrs={"data-area-name": True})
        if section_node:
            value = section_node.get("data-area-name")
            if value:
                return str(value)
        heading = anchor.find_parent("section")
        if heading:
            header_el = heading.find("h2")
            if header_el:
                title_text = header_el.get_text(strip=True)
                if title_text:
                    return title_text
        return None

    def _normalize_text(self, text: str) -> str:
        cleaned = text.replace("\u3000", " ").replace("\xa0", " ")
        return re.sub(r"\s+", " ", cleaned).strip()

    def get_news_detail(self, record: NewsRecord) -> NewsRecord:
        if not record.url:
            return record
        try:
            resp = self.session.get(record.url, timeout=20, headers=DEFAULT_HEADERS)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取朝日新聞详情失败 (%s): %s", record.url, exc)
            return record
        html = self._ensure_utf8(resp)
        return self._parse_detail(html, record)

    def _parse_detail(self, html: str, record: NewsRecord) -> NewsRecord:
        soup = BeautifulSoup(html, "html.parser")
        content_text = self._extract_content_text(soup)
        if content_text:
            record.raw["content_text"] = content_text
            if not record.summary:
                record.summary = content_text.split("\n", 1)[0][:160]
        published = self._extract_published_time(soup)
        if published:
            record.published_at = published
        tags = self._extract_tags(soup)
        if tags:
            record.raw["tags"] = tags
        record.raw.setdefault("detail_path", record.raw.get("path"))
        return record

    def _extract_published_time(self, soup: BeautifulSoup) -> Optional[str]:
        meta = soup.find("meta", attrs={"property": "article:published_time"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        meta = soup.find("meta", attrs={"name": "pubdate"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        return None

    def _extract_tags(self, soup: BeautifulSoup) -> List[str]:
        metas = soup.find_all("meta", attrs={"name": "cXenseParse:ash-tag"})
        tags: List[str] = []
        for meta in metas:
            content = meta.get("content")
            if content:
                cleaned = self._normalize_text(content)
                if cleaned:
                    tags.append(cleaned)
        return tags

    def _extract_content_text(self, soup: BeautifulSoup) -> Optional[str]:
        selectors = [
            "div.nfyQp",
            "div.p-article__body",
            "div.c-article__body",
            "div[role='main']",
        ]
        paragraphs: List[str] = []
        for selector in selectors:
            container = soup.select_one(selector)
            if not container:
                continue
            paragraphs = self._collect_text_blocks(container)
            if paragraphs:
                break
        if not paragraphs:
            body = soup.find("body")
            if body:
                paragraphs = self._collect_text_blocks(body)
        filtered = self._filter_paragraphs(paragraphs)
        if filtered:
            return "\n\n".join(filtered)
        return None

    def _collect_text_blocks(self, container: Tag) -> List[str]:
        texts: List[str] = []
        for tag_name in ("p", "li"):
            for node in container.find_all(tag_name):
                text = self._normalize_text(node.get_text(" ", strip=True))
                if text:
                    texts.append(text)
        return texts

    def _filter_paragraphs(self, paragraphs: Sequence[str]) -> List[str]:
        filtered: List[str] = []
        blacklist = {"有料記事"}
        for text in paragraphs:
            if text in blacklist:
                continue
            # 排除明显广告标记
            if text.startswith("[PR]"):
                continue
            if text:
                filtered.append(text)
        return filtered

    def _ensure_utf8(self, resp: requests.Response) -> str:
        """确保响应正确以 UTF-8 解码。"""

        encoding = resp.apparent_encoding or resp.encoding or "utf-8"
        resp.encoding = encoding
        try:
            return resp.text
        except UnicodeDecodeError:
            return resp.content.decode("utf-8", errors="ignore")

    def _normalize_article_url(self, href: str) -> tuple[str, str]:
        """
        统一处理文章链接：
        - 与 base_url 拼接成绝对地址
        - 去掉 query / fragment，避免同一文章因参数不同重复
        - 返回 (绝对地址, path)
        """

        absolute_url = urljoin(self.base_url, href)
        parsed = urlparse(absolute_url)
        normalized = parsed._replace(query="", fragment="")
        clean_url = urlunparse(normalized)
        clean_path = normalized.path or href
        return clean_url, clean_path
