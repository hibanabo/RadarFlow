"""VOA 中文网抓取器解析测试。"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fetcher.voachinese import VOAChineseNewsFetcher  # noqa: E402
from fetcher.base_fetcher import NewsRecord  # noqa: E402

LISTING_FIXTURE = ROOT / "fetcher" / "data" / "voachinese.html"
DETAIL_FIXTURE = ROOT / "fetcher" / "data" / "voachinese_detail.html"


def test_parse_listing_fixture() -> None:
    html = LISTING_FIXTURE.read_text(encoding="utf-8")
    fetcher = VOAChineseNewsFetcher()
    records = fetcher._parse_listing(html)  # type: ignore[attr-defined]
    assert len(records) >= 20

    print(len(records))

    for record in records:
        print(record)





def test_parse_detail_fixture() -> None:
    html = DETAIL_FIXTURE.read_text(encoding="utf-8")
    fetcher = VOAChineseNewsFetcher()
    record = NewsRecord(
        source=fetcher.name,
        title="日本首相：与特朗普通话并确认了日美之间的紧密合作",
        url="https://www.voachinese.com/a/takaichi-us-japan-confirm-close-coordination-in-phone-talks-with-trump-20251125/8086053.html",
    )
    updated = fetcher._parse_detail(html, record)  # type: ignore[attr-defined]
    assert updated.published_at == "2025-11-26T05:07:12+08:00"
    assert "日本首相高市早苗" in (updated.summary or "")
    assert "特朗普与高市早苗的通话" in updated.raw.get("content_text", "")
    assert updated.authors == ["斯洋"]
    assert "印太" in (updated.raw.get("keywords") or [])

