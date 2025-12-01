"""自由時報抓取器測試。"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fetcher.ltn import LTNFetcher  # noqa: E402
from fetcher.base_fetcher import NewsRecord  # noqa: E402

LISTING_FIXTURE = ROOT / "fetcher" / "data" / "itn.html"
DETAIL_FIXTURE = ROOT / "fetcher" / "data" / "itn_detail.html"


def test_ltn_parse_listing() -> None:
    html = LISTING_FIXTURE.read_text(encoding="utf-8")
    fetcher = LTNFetcher()
    records = fetcher._parse_listing(html)  # type: ignore[attr-defined]
    assert len(records) >= 20
    urls = {record.url for record in records}
    assert "https://news.ltn.com.tw/news/world/breakingnews/5259222" in urls


def test_ltn_parse_detail() -> None:
    html = DETAIL_FIXTURE.read_text(encoding="utf-8")
    fetcher = LTNFetcher()
    record = NewsRecord(
        source=fetcher.name,
        title="",
        url="https://news.ltn.com.tw/news/politics/breakingnews/5259222",
    )
    updated = fetcher._parse_detail(html, record)  # type: ignore[attr-defined]
    assert updated.published_at == "2025-11-26T11:54:00+08:00"
    assert "賴清德總統" in (updated.summary or "")
    assert "賴總統示警" in updated.raw.get("description", "")
