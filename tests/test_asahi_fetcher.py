"""Asahi fetcher parsing tests."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fetcher.asahi import AsahiNewsFetcher  # noqa: E402
from fetcher.base_fetcher import NewsRecord  # noqa: E402

LISTING_FIXTURE = ROOT / "fetcher" / "data" / "asahi.html"
DETAIL_FIXTURE = ROOT / "fetcher" / "data" / "asahi_detail.html"


def test_parse_listing_from_fixture() -> None:
    html = LISTING_FIXTURE.read_text(encoding="utf-8")
    fetcher = AsahiNewsFetcher()
    records = fetcher._parse_listing(html)  # type: ignore[attr-defined]
    assert len(records) >= 80
    urls = {record.url for record in records}
    assert len(urls) == len(records)

    first = records[0]
    assert first.source == fetcher.name
    assert first.title.startswith("ルーブル宝飾品盗難")
    assert first.raw.get("section") == "速報ニュース"
    assert first.raw.get("relative_time") == "2時間前"
    assert "\u3000" not in first.title
    assert any("桐朋女子高校" in record.title for record in records)
    assert all("\u3000" not in record.title for record in records)


def test_parse_detail_from_fixture() -> None:
    html = DETAIL_FIXTURE.read_text(encoding="utf-8")
    fetcher = AsahiNewsFetcher()
    record = NewsRecord(
        source=fetcher.name,
        title="トランプ氏、米中電話協議を要請か　日本への「伝達役」を担った訳は",
        url="https://www.asahi.com/articles/ASTCT3DFPTCTUTFK00PM.html",
    )
    record = fetcher._parse_detail(html, record)  # type: ignore[attr-defined]
    assert record.published_at == "2025-11-25T20:30:00+09:00"
    assert "台湾有事" in (record.summary or "")
    assert "米中首脳" in record.raw.get("content_text", "")
    assert record.raw.get("tags")
