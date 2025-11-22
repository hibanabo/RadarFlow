"""澎湃要闻（编辑精选）抓取实现。"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from .base_fetcher import BaseNewsFetcher, NewsRecord
from utils.time_utils import to_utc_iso

logger = logging.getLogger(__name__)


class ThePaperHandpickFetcher(BaseNewsFetcher):
    """澎湃要闻抓取类。"""

    name = "澎湃要闻"
    api_url = "https://api.thepaper.cn/contentapi/channel/editorHandpicked"

    def __init__(
        self,
        *,
        page_size: int = 20,
        page_num: int = 1,
        card_mode: int = 109,
        start_time: Optional[int] = None,
        filter_ids: Optional[List[int]] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.page_size = page_size
        self.page_num = page_num
        self.card_mode = card_mode
        self.start_time = start_time
        self.filter_ids = filter_ids or []
        self.session = session or requests.Session()

    def get_news_list(self) -> List[NewsRecord]:
        """调用列表接口并返回标准化记录列表。"""

        payload = {
            "pageSize": self.page_size,
            "cardMode": self.card_mode,
            "startTime": self.start_time,
            "filterIdArray": self.filter_ids,
            "pageNum": self.page_num,
        }
        logger.info("调用澎湃要闻接口: %s", payload)
        resp = self.session.post(self.api_url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        records: List[NewsRecord] = []
        for item in data.get("pageInfo", {}).get("list", []):
            cont_id = item.get("contId")
            url = f"https://www.thepaper.cn/newsDetail_forward_{cont_id}" if cont_id else ""
            published_at = to_utc_iso(item.get("pubTimeLong") or item.get("pubTime"))
            record = NewsRecord(
                source=self.name,
                title=item.get("name") or "",
                url=url,
                summary=None,
                published_at=published_at,
                raw=item,
            )
            records.append(record)
        return records

    def get_news_detail(self, record: NewsRecord) -> NewsRecord:
        """抓取详情页 HTML 并解析正文。"""

        if not record.url:
            return record
        try:
            resp = self.session.get(record.url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.warning("抓取详情失败 (%s): %s", record.url, exc)
            return record

        soup = BeautifulSoup(resp.text, "html.parser")
        # __NEXT_DATA__ 中包含详情页 JSON
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            record.raw.setdefault("detail_html", resp.text)
            return record
        try:
            payload = json.loads(script.string)
        except json.JSONDecodeError as exc:  # noqa: BLE001
            logger.warning("解析详情 JSON 失败: %s", exc)
            record.raw.setdefault("detail_html", resp.text)
            return record

        content_detail = (
            payload.get("props", {})
            .get("pageProps", {})
            .get("detailData", {})
            .get("contentDetail", {})
        )
        content_html = content_detail.get("content")
        if content_html:
            record.raw["content_html"] = content_html
            text = BeautifulSoup(content_html, "html.parser").get_text("\n", strip=True)
            record.raw["content_text"] = text
            if not record.summary:
                record.summary = text[:120]
        if content_detail.get("pubTime") and not record.published_at:
            record.published_at = to_utc_iso(content_detail["pubTime"])
        author_name = (content_detail.get("author") or "").strip()
        if author_name:
            record.authors = [author_name]
            record.raw["author"] = author_name
        record.raw["detail"] = content_detail
        record.raw["tags"] = content_detail.get("tagList")
        record.raw["voice_info"] = content_detail.get("voiceInfo")
        return record
