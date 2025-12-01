"""VNExpress 新闻抓取器。"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from .base_fetcher import BaseNewsFetcher, NewsRecord

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}


class VnExpressNewsFetcher(BaseNewsFetcher):
    """抓取越南 VnExpress 首页新闻。"""

    name = "越南VnExpress"
    base_url = "https://vnexpress.net"
    listing_paths: List[str] = [
        "/",
        "/the-gioi",
        "/thoi-su/chinh-tri",
        "/the-gioi/quan-su",
        "/the-gioi/tu-lieu",
        "/the-gioi/cuoc-song-do-day",
        "/the-gioi/nguoi-viet-5-chau",
        "/the-gioi/phan-tich",
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
                logger.warning("抓取 VnExpress 列表失败 (%s): %s", url, exc)
                continue
            records.extend(self._parse_listing(resp.text, seen))
        return records

    def get_news_detail(self, record: NewsRecord) -> NewsRecord:
        if not record.url:
            return record
        try:
            resp = self.session.get(record.url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取 VnExpress 详情失败 (%s): %s", record.url, exc)
            return record
        return self._parse_detail(resp.text, record)

    def _parse_listing(self, html: str, seen: set[str]) -> List[NewsRecord]:
        soup = BeautifulSoup(html, "html.parser")
        records: List[NewsRecord] = []
        for article in soup.find_all("article"):
            anchor = article.find("a", href=True)
            if not anchor:
                continue
            href = anchor["href"]
            if not href:
                continue
            url = href if href.startswith("http") else urljoin(self.base_url, href)
            if url in seen or not url.startswith(self.base_url):
                continue
            title = anchor.get_text(" ", strip=True)
            if not title:
                title_node = article.select_one("h3 a, h2 a")
                if title_node:
                    title = title_node.get_text(" ", strip=True)
            if not title:
                continue
            summary_node = article.select_one("p.description")
            summary = summary_node.get_text(" ", strip=True) if summary_node else None
            time_node = article.select_one(".time-public")
            published_text = time_node.get_text(" ", strip=True) if time_node else None
            image = None
            img = article.find("img")
            if img and img.get("data-src"):
                image = img["data-src"]
            elif img and img.get("src"):
                image = img["src"]
            record = NewsRecord(
                source=self.name,
                title=title,
                url=url,
                summary=summary,
                raw={
                    "published_label": published_text,
                    "image": image,
                },
            )
            records.append(record)
            seen.add(url)
        return records

    def _parse_detail(self, html: str, record: NewsRecord) -> NewsRecord:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.select_one("h1")
        if title:
            record.title = title.get_text(" ", strip=True)
        summary = soup.select_one(".short_intro")
        if summary:
            record.summary = summary.get_text(" ", strip=True)
        pub_meta = soup.find("meta", attrs={"name": "pubdate"})
        if pub_meta and pub_meta.get("content"):
            normalized = self._normalize_datetime(pub_meta["content"])
            if normalized:
                record.published_at = normalized
        last_meta = soup.find("meta", attrs={"name": "lastmod"})
        if last_meta and last_meta.get("content"):
            normalized = self._normalize_datetime(last_meta["content"])
            if normalized:
                record.raw["updated_at"] = normalized
        body = self._extract_body(soup)
        if body:
            record.raw["content_text"] = body
            if not record.summary:
                record.summary = body.split("\n\n", 1)[0][:200]
        keywords_meta = soup.find("meta", attrs={"name": "keywords"})
        if keywords_meta and keywords_meta.get("content"):
            record.raw["keywords"] = [token.strip() for token in keywords_meta["content"].split(",") if token.strip()]
        author = self._extract_author(soup)
        if author:
            record.authors = [author]
        return record

    def _extract_body(self, soup: BeautifulSoup) -> Optional[str]:
        container = soup.select_one(".fck_detail")
        if not container:
            return None
        paragraphs: List[str] = []
        for node in container.find_all(["p", "li"]):
            text = node.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)
        return "\n\n".join(paragraphs).strip() if paragraphs else None

    def _normalize_datetime(self, value: str) -> Optional[str]:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt.isoformat()

    def _extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        node = soup.select_one(".author span, .author strong, .sidebar-1 .author")
        if node:
            text = node.get_text(" ", strip=True)
            if text:
                return text
        # try to get element before article-end marker
        article_end = soup.select_one("#article-end")
        if article_end and article_end.previous_sibling:
            candidate = article_end.previous_sibling
            while candidate and getattr(candidate, "name", None) is None:
                candidate = candidate.previous_sibling
            if candidate and candidate.name == "p":
                strong = candidate.find("strong")
                if strong:
                    text = strong.get_text(" ", strip=True)
                    if text:
                        return text
        fck = soup.select_one(".fck_detail")
        if not fck:
            return None
        for p in fck.find_all("p", class_="Normal"):
            style = (p.get("style") or "").replace(" ", "").lower()
            if "text-align:right" in style:
                text = p.get_text(" ", strip=True)
                if text:
                    return text
        return None
