"""CNA fetcher tests."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fetcher.cna import CNAFetcher  # noqa: E402
from fetcher.base_fetcher import NewsRecord  # noqa: E402

LISTING_FIXTURE = ROOT / "fetcher" / "data" / "cna.html"
DETAIL_FIXTURE = ROOT / "fetcher" / "data" / "cna_detail.html"


def test_cna_parse_listing() -> None:
    html = LISTING_FIXTURE.read_text(encoding="utf-8")
    fetcher = CNAFetcher()
    records = fetcher._parse_listing(html)  # type: ignore[attr-defined]
    assert len(records) >= 20
    urls = {record.url for record in records}
    assert "https://www.cna.com.tw/news/aipl/202511260338.aspx" in urls


def test_cna_parse_detail() -> None:
    html = DETAIL_FIXTURE.read_text(encoding="utf-8")
    fetcher = CNAFetcher()
    record = NewsRecord(
        source=fetcher.name,
        title="",
        url="https://www.cna.com.tw/news/aipl/202511260051.aspx",
    )
    updated = fetcher._parse_detail(html, record)  # type: ignore[attr-defined]
    assert updated.published_at == "2025-11-26T10:28:00+08:00"
    assert "總統府今天表示" in (updated.summary or "")
    assert updated.authors == ["溫貴香"]
