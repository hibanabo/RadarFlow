"""RFI 中文版抓取器，必要时使用 Playwright 规避反爬。"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

try:  # pragma: no cover
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None  # type: ignore[assignment]

from .base_fetcher import BaseNewsFetcher, NewsRecord

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "Referer": "https://www.rfi.fr/cn",
    "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br, zstd",
}

PLAYWRIGHT_TIMEOUT = 25_000


class RFINewsFetcher(BaseNewsFetcher):
    """抓取 RFI 中文网站首页以及详情。"""

    name = "RFI"
    base_url = "https://www.rfi.fr"
    listing_path = "/cn/"
    section_paths: tuple[str, ...] = (
        "/cn/",
        "/cn/中国/",
        "/cn/法国/",
        "/cn/港澳台/",
        "/cn/亚洲/",
        "/cn/非洲/",
        "/cn/美洲/",
        "/cn/欧洲/",
        "/cn/中东/",
    )

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def get_news_list(self) -> List[NewsRecord]:
        records: List[NewsRecord] = []
        seen_urls: set[str] = set()
        for path in self.section_paths:
            html = self._fetch_html(urljoin(self.base_url, path))
            if not html:
                continue
            page_records = self._parse_listing(html)
            section_label = self._section_label(path)
            for record in page_records:
                if not record.url or record.url in seen_urls:
                    continue
                seen_urls.add(record.url)
                if section_label:
                    record.raw.setdefault("section_page", section_label)
                records.append(record)
        return records

    def get_news_detail(self, record: NewsRecord) -> NewsRecord:
        if not record.url:
            return record
        html = self._fetch_html(record.url)
        if not html:
            return record
        return self._parse_detail(html, record)

    def _parse_listing(self, html: str) -> List[NewsRecord]:
        soup = BeautifulSoup(self._normalize_html(html), "html.parser")
        articles = soup.select("div.m-item-list-article[data-article-list]")
        records: List[NewsRecord] = []
        seen: set[str] = set()
        for node in articles:
            title = self._extract_title(node)
            href = self._extract_href(node)
            if not title or not href:
                continue
            full_url = urljoin(self.base_url, href)
            if not self._is_article_url(full_url):
                continue
            if full_url in seen:
                continue
            tag_text = self._extract_tag(node)
            record = NewsRecord(
                source=self.name,
                title=title,
                url=full_url,
                raw={"section": tag_text} if tag_text else {},
            )
            records.append(record)
            seen.add(full_url)
        if not records:
            items = self._extract_itemlist(soup)
            for entry in items:
                title = (entry.get("name") or "").strip()
                url = entry.get("url")
                if not title or not url:
                    continue
                full_url = urljoin(self.base_url, url)
                if not self._is_article_url(full_url):
                    continue
                if full_url in seen:
                    continue
                record = NewsRecord(
                    source=self.name,
                    title=title,
                    url=full_url,
                    raw={"position": entry.get("position")},
                )
                records.append(record)
                seen.add(full_url)
        return records

    def _parse_detail(self, html: str, record: NewsRecord) -> NewsRecord:
        soup = BeautifulSoup(self._normalize_html(html), "html.parser")
        published = self._meta_content(soup, "article:published_time")
        if published:
            record.published_at = published
        title_el = soup.select_one(".t-content__title")
        if title_el:
            record.title = title_el.get_text(" ", strip=True)
        chapo = soup.select_one(".t-content__chapo")
        if chapo:
            record.summary = chapo.get_text(" ", strip=True)
        body = self._extract_body(soup)
        if body:
            record.raw["content_text"] = body
            if not record.summary:
                record.summary = body.split("\n\n", 1)[0][:200]
        authors = [a.get_text(" ", strip=True) for a in soup.select(".t-content__authors a")]
        if authors:
            record.authors = authors
        tags = [a.get_text(" ", strip=True) for a in soup.select(".t-content__tags a[href]")]
        keywords = self._meta_keywords(soup)
        combined = [tag for tag in tags + keywords if tag]
        if combined:
            record.raw["keywords"] = combined
        section = self._meta_content(soup, "article:section")
        if section:
            record.raw["section"] = section
        return record

    def _fetch_html(self, url: str) -> Optional[str]:
        try:
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("RFI 请求失败(%s): %s", url, exc)
            return self._fetch_with_playwright(url)

    def _fetch_with_playwright(self, url: str) -> Optional[str]:
        if sync_playwright is None:
            logger.warning("Playwright 未安装，无法抓取 RFI: %s", url)
            return None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=DEFAULT_HEADERS["User-Agent"],
                    locale="zh-CN",
                    extra_http_headers=DEFAULT_HEADERS,
                )
                page = context.new_page()
                page.goto(url, wait_until="networkidle", timeout=PLAYWRIGHT_TIMEOUT)
                html = page.content()
                browser.close()
                return html
        except Exception as exc:  # noqa: BLE001
            logger.warning("Playwright 抓取 RFI 失败(%s): %s", url, exc)
            return None

    def _extract_itemlist(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            text = script.string
            if not text:
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            results.extend(self._collect_items(data))
        return results

    def _collect_items(self, data: Any) -> List[Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            if data.get("@type") == "ItemList":
                for element in data.get("itemListElement", []):
                    if isinstance(element, dict):
                        if "item" in element and isinstance(element["item"], dict):
                            item_data = element["item"]
                            collected.append(
                                {
                                    "name": item_data.get("name"),
                                    "url": item_data.get("@id") or item_data.get("url"),
                                    "position": element.get("position"),
                                }
                            )
                        else:
                            collected.append(
                                {
                                    "name": element.get("name"),
                                    "url": element.get("url"),
                                    "position": element.get("position"),
                                }
                            )
            for value in data.values():
                collected.extend(self._collect_items(value))
        elif isinstance(data, list):
            for value in data:
                collected.extend(self._collect_items(value))
        return collected

    def _extract_body(self, soup: BeautifulSoup) -> Optional[str]:
        container = soup.select_one(".t-content__body")
        if not container:
            return None
        paragraphs: List[str] = []
        for node in container.find_all(["p", "li"]):
            text = node.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)
        return "\n\n".join(paragraphs).strip() if paragraphs else None

    def _meta_content(self, soup: BeautifulSoup, name: str) -> Optional[str]:
        meta = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if meta and meta.get("content"):
            return meta["content"].strip()
        return None

    def _meta_keywords(self, soup: BeautifulSoup) -> List[str]:
        keywords_content = self._meta_content(soup, "keywords")
        if not keywords_content:
            return []
        return [token.strip() for token in keywords_content.split(",") if token.strip()]

    def _normalize_html(self, html: str) -> str:
        return html.replace("< ", "<").replace("</ ", "</")

    def _extract_title(self, node: Tag) -> str:
        title_node = node.select_one(".article__title h2") or node.select_one(".article__title")
        if title_node:
            text = title_node.get_text(" ", strip=True)
            if text:
                return text
        link_node = node.select_one("[data-article-item-link]")
        if link_node:
            text = link_node.get_text(" ", strip=True)
            if text:
                return text
        return ""

    def _extract_href(self, node: Tag) -> Optional[str]:
        link_node = node.select_one(".article__title a[data-article-item-link]") or node.select_one("a[data-article-item-link]")
        if link_node and link_node.get("href"):
            return link_node["href"]
        return None

    def _extract_tag(self, node: Tag) -> Optional[str]:
        tag_node = node.select_one(".a-tag")
        if not tag_node:
            return None
        text = tag_node.get_text(" ", strip=True)
        return text or None

    _article_path_pattern = re.compile(r"/\d{6,}")

    def _is_article_url(self, url: str) -> bool:
        """过滤专题/标签页，确保只留下含日期 slug 的文章链接。"""

        path = urlparse(url).path
        return bool(self._article_path_pattern.search(path))

    def _section_label(self, path: str) -> Optional[str]:
        normalized = unquote(path or "").strip("/")
        if not normalized or normalized == "cn":
            return None
        parts = normalized.split("/")
        if len(parts) < 2:
            return None
        label = parts[-1]
        return label or None
