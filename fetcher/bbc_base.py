"""BBC 公用工具函数。"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from bs4 import BeautifulSoup


def extract_schema_data(soup: BeautifulSoup) -> Optional[dict]:
    """在详情页中提取 NewsArticle schema。"""
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") in {"NewsArticle", "Article", "ReportageNewsArticle"}:
            return data
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("@type") in {"NewsArticle", "Article", "ReportageNewsArticle"}:
                    return item
    return None


def extract_body_from_next_data(soup: BeautifulSoup) -> Optional[str]:
    """解析 __NEXT_DATA__ 中的正文。"""
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return None
    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        return None
    paragraphs = _extract_from_page_structure(data)
    return "\n\n".join(paragraphs) if paragraphs else None


def _extract_from_page_structure(data: dict) -> List[str]:
    props = data.get("props", {}).get("pageProps", {})
    paragraphs: List[str] = []
    page = props.get("page")
    if isinstance(page, dict):
        page_obj = next(iter(page.values()), None)
        if isinstance(page_obj, dict):
            paragraphs.extend(_collect_paragraphs(page_obj.get("contents", [])))
    if not paragraphs:
        page_data = props.get("pageData", {})
        content_blocks = (
            page_data.get("content", {})
            .get("model", {})
            .get("blocks", [])
        )
        paragraphs.extend(_collect_paragraphs(content_blocks))
    return paragraphs


def _collect_paragraphs(blocks: List[dict]) -> List[str]:
    paragraphs: List[str] = []
    for block in blocks:
        block_type = block.get("type")
        model = block.get("model", {})
        if block_type == "text":
            paragraphs.extend(_collect_paragraphs(model.get("blocks", [])))
            continue
        if block_type == "paragraph":
            text_fragments = []
            for child in model.get("blocks", []):
                if child.get("type") == "fragment":
                    text = child.get("model", {}).get("text", "")
                    if text:
                        text_fragments.append(text)
                elif child.get("model"):
                    text_fragments.extend(_collect_paragraphs([child]))
            text = "".join(text_fragments).strip()
            if text:
                paragraphs.append(text)
            continue
        nested = model.get("blocks")
        if isinstance(nested, list):
            paragraphs.extend(_collect_paragraphs(nested))
    return paragraphs
