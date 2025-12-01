"""Yonhap News Agency fetcher tests."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fetcher.yna import YNAFetcher  # noqa: E402
from fetcher.base_fetcher import NewsRecord  # noqa: E402

LISTING_FIXTURE = ROOT / "fetcher" / "data" / "yna.html"
DETAIL_FIXTURE = ROOT / "fetcher" / "data" / "yna_detail.html"


def test_yna_parse_listing() -> None:
    html = LISTING_FIXTURE.read_text(encoding="utf-8")
    fetcher = YNAFetcher()
    records = fetcher._parse_listing(html)  # type: ignore[attr-defined]
    assert len(records) >= 50
    print(len(records))
    titles = [record.title for record in records]
    assert any("수사외압" in title for title in titles)
    assert all(record.url.startswith("https://www.yna.co.kr") for record in records)


def test_yna_parse_detail() -> None:
    html = DETAIL_FIXTURE.read_text(encoding="utf-8")
    fetcher = YNAFetcher()
    record = NewsRecord(
        source=fetcher.name,
        title="",
        url="https://www.yna.co.kr/view/AKR20251126132551001",
    )
    updated = fetcher._parse_detail(html, record)  # type: ignore[attr-defined]
    assert updated.published_at == "2025-11-26T17:56:30+09:00"
    assert updated.summary and "법관 모욕" in updated.summary
    assert "이재명 대통령" in updated.raw.get("content_text", "")
    assert "정치" == updated.raw.get("section")
    assert "대통령" in updated.raw.get("keywords", [])
