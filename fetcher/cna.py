"""中央社 CNA 抓取器。"""
from __future__ import annotations

import logging
import re
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .base_fetcher import BaseNewsFetcher, NewsRecord

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

LOCATION_SUFFIXES = [
    "台北",
    "台中",
    "台南",
    "台東",
    "高雄",
    "新北",
    "桃園",
    "屏東",
    "基隆",
    "新竹",
    "嘉義",
    "台灣",
    "香港",
    "北京",
    "上海",
    "廣州",
    "新加坡",
    "洛杉磯",
    "紐約",
    "華盛頓",
    "綜合外電",
]


class CNAFetcher(BaseNewsFetcher):
    """抓取中央社 CNA 首頁與文章。"""

    name = "台湾中央通讯社"
    base_url = "https://www.cna.com.tw"
    listing_path = "/"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def get_news_list(self) -> List[NewsRecord]:
        try:
            resp = self.session.get(urljoin(self.base_url, self.listing_path), timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 CNA 首頁失敗: %s", exc)
            return []
        html = resp.text
        return self._parse_listing(html)

    def get_news_detail(self, record: NewsRecord) -> NewsRecord:
        if not record.url:
            return record
        try:
            resp = self.session.get(record.url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 CNA 文章失敗 (%s): %s", record.url, exc)
            return record
        html = resp.text
        return self._parse_detail(html, record)

    def _parse_listing(self, html: str) -> List[NewsRecord]:
        soup = BeautifulSoup(html, "html.parser")
        anchors = soup.select("a[href*='/news/']")
        records: List[NewsRecord] = []
        seen: set[str] = set()
        for anchor in anchors:
            href = anchor.get("href") or ""
            if not href.startswith("/news") or not href.endswith(".aspx"):
                continue
            title = anchor.get_text(" ", strip=True)
            if not title:
                continue
            url = urljoin(self.base_url, href)
            if url in seen:
                continue
            summary = self._extract_summary(anchor)
            record = NewsRecord(
                source=self.name,
                title=title,
                url=url,
                summary=summary,
            )
            records.append(record)
            seen.add(url)
        return records

    def _parse_detail(self, html: str, record: NewsRecord) -> NewsRecord:
        soup = BeautifulSoup(html, "html.parser")
        published = (
            self._meta_content(soup, "article:published_time")
            or self._meta_content(soup, "datePublished")
            or self._meta_content(soup, "pubdate")
        )
        if published:
            record.published_at = published
        title_el = soup.select_one("h1")
        if title_el:
            record.title = title_el.get_text(" ", strip=True)
        summary = self._parse_summary_and_body(soup, record)
        if summary:
            record.summary = summary
            author_name = self._extract_author(summary)
            if author_name:
                record.authors = [author_name]
        section = self._meta_content(soup, "article:section") or self._meta_content(soup, "sectionname")
        if section:
            record.raw["section"] = section
        keywords = self._meta_content(soup, "news_keywords")
        if keywords:
            record.raw["keywords"] = [kw.strip() for kw in keywords.split(",") if kw.strip()]
        return record

    def _extract_summary(self, anchor) -> Optional[str]:
        parent = anchor.find_parent("div", class_="articleBox")
        if parent:
            desc = parent.select_one("p")
            if desc:
                text = desc.get_text(" ", strip=True)
                if text:
                    return text
        return None

    def _parse_summary_and_body(self, soup: BeautifulSoup, record: NewsRecord) -> Optional[str]:
        paragraphs: List[str] = []
        container = soup.find("div", class_="paragraph") or soup.find("article")
        nodes = container.find_all("p") if container else []
        if not nodes:
            nodes = soup.find_all("p")
        for node in nodes:
            text = node.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)
        if paragraphs:
            body = "\n\n".join(paragraphs)
            record.raw["content_text"] = body
            return paragraphs[0][:200]
        meta_desc = self._meta_content(soup, "description")
        if meta_desc:
            record.raw["content_text"] = meta_desc
            return meta_desc[:200]
        return None

    def _meta_content(self, soup: BeautifulSoup, name: str) -> Optional[str]:
        meta = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if meta and meta.get("content"):
            return meta["content"].strip()
        return None

    def _extract_author(self, text: str) -> Optional[str]:
        if not text:
            return None
        match = re.search(r"中央社記者([\u4e00-\u9fa5·‧．]+)", text)
        if not match:
            return None
        name = match.group(1)
        for suffix in LOCATION_SUFFIXES:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        name = name.strip(" ，、．。")
        if name:
            return name
        return None
