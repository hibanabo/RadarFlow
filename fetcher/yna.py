"""Yonhap News Agency (연합뉴스) 列表与详情抓取器。"""
from __future__ import annotations

import logging
import json
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from .base_fetcher import BaseNewsFetcher, NewsRecord

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept-Language": "ko,en;q=0.8",
}


class YNAFetcher(BaseNewsFetcher):
    """抓取 연합뉴스 首页及详情。"""

    name = "韩联社"
    base_url = "https://www.yna.co.kr"
    listing_path = "/"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def get_news_list(self) -> List[NewsRecord]:
        try:
            resp = self.session.get(urljoin(self.base_url, self.listing_path), timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 연합뉴스 首页失败: %s", exc)
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
            logger.warning("抓取 연합뉴스 详情失败 (%s): %s", record.url, exc)
            return record
        html = resp.text
        return self._parse_detail(html, record)

    def _parse_listing(self, html: str) -> List[NewsRecord]:
        soup = BeautifulSoup(html, "html.parser")
        anchors = soup.find_all("a", href=True)
        records: List[NewsRecord] = []
        seen: set[str] = set()
        for anchor in anchors:
            href = anchor.get("href") or ""
            if "/view/AKR" not in href:
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
                raw={},
            )
            records.append(record)
            seen.add(url)
        return records

    def _parse_detail(self, html: str, record: NewsRecord) -> NewsRecord:
        soup = BeautifulSoup(html, "html.parser")
        published = self._meta_content(soup, "article:published_time")
        if published:
            record.published_at = published
        title_el = soup.select_one("h1.tit01") or soup.select_one("strong.tit-news")
        if title_el:
            record.title = title_el.get_text(" ", strip=True)
        else:
            meta_title = self._meta_content(soup, "og:title")
            if meta_title:
                record.title = meta_title.split("|")[0].strip()
        chapo = soup.select_one(".summary")
        if chapo:
            record.summary = chapo.get_text(" ", strip=True)
        body = self._extract_body(soup)
        if body:
            record.raw["content_text"] = body
            if not record.summary or len(record.summary) < 10 or record.summary.startswith("["):
                for paragraph in body.split("\n\n"):
                    cleaned = paragraph.strip()
                    if not cleaned:
                        continue
                    if cleaned.startswith("[") and cleaned.endswith("]"):
                        continue
                    record.summary = cleaned[:200]
                    break
                else:
                    record.summary = body[:200]
        authors = self._extract_authors(soup)
        if authors:
            record.authors = authors
        keywords = self._extract_keywords(soup)
        if keywords:
            record.raw["keywords"] = keywords
        section = self._meta_content(soup, "article:section")
        if section:
            record.raw["section"] = section
        return record

    def _meta_content(self, soup: BeautifulSoup, name: str) -> Optional[str]:
        meta = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if meta and meta.get("content"):
            return meta["content"].strip()
        return None

    def _extract_body(self, soup: BeautifulSoup) -> Optional[str]:
        container = soup.select_one(".story-news") or soup.select_one(".detail-body") or soup.select_one(".article-txt01")
        if not container:
            return None
        paragraphs: List[str] = []
        for node in container.find_all(["p", "li"]):
            text = node.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)
        return "\n\n".join(paragraphs).strip() if paragraphs else None

    def _extract_summary(self, anchor: Tag) -> Optional[str]:
        container = anchor.find_parent(class_="news-con")
        if container:
            lead = container.find("p", class_="lead")
            if lead:
                return lead.get_text(" ", strip=True)
        sibling = anchor.find_next_sibling("p")
        if sibling and sibling.get_text(strip=True):
            return sibling.get_text(" ", strip=True)
        return None

    def _extract_authors(self, soup: BeautifulSoup) -> List[str]:
        authors: List[str] = []
        meta_author = self._meta_content(soup, "author")
        if meta_author:
            authors.append(meta_author)
        reporter_nodes = soup.select(".reporter")
        for node in reporter_nodes:
            text = node.get_text(" ", strip=True)
            if text:
                authors.append(text)
        return list(dict.fromkeys(authors))

    def _extract_keywords(self, soup: BeautifulSoup) -> List[str]:
        keywords: List[str] = []
        keywords_text = self._meta_content(soup, "keyword")
        if keywords_text:
            for token in keywords_text.replace(",", ";").split(";"):
                text = token.strip()
                if text:
                    keywords.append(text)
        script = soup.find("script", id="pfrtData")
        if script and script.string:
            try:
                data = json.loads(script.string)
                script_keywords = data.get("keyword")
                if isinstance(script_keywords, str):
                    for token in script_keywords.split(";"):
                        text = token.strip()
                        if text:
                            keywords.append(text)
            except (json.JSONDecodeError, TypeError):
                pass
        tag_nodes = soup.select(".keyword-list a")
        for node in tag_nodes:
            text = node.get_text(" ", strip=True)
            if text:
                keywords.append(text)
        return list(dict.fromkeys(keywords))
