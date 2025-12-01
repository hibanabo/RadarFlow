"""VNExpress fetcher tests."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fetcher.vnexpress import VnExpressNewsFetcher  # noqa: E402
from fetcher.base_fetcher import NewsRecord  # noqa: E402

LISTING_FIXTURE = ROOT / "fetcher" / "data" / "vnexpress.html"
DETAIL_FIXTURE = ROOT / "fetcher" / "data" / "vnexpress_detail.html"


def test_vnexpress_parse_listing_fixture() -> None:
    html = LISTING_FIXTURE.read_text(encoding="utf-8")
    fetcher = VnExpressNewsFetcher()
    records = fetcher._parse_listing(html, seen=set())  # type: ignore[attr-defined]
    assert len(records) >= 20
    urls = [record.url for record in records]
    assert "https://vnexpress.net/danh-cuoc-mang-song-trong-chung-cu-quan-tai-hong-kong-4986780.html" in urls


def test_vnexpress_parse_detail_fixture() -> None:
    html = DETAIL_FIXTURE.read_text(encoding="utf-8")
    fetcher = VnExpressNewsFetcher()
    record = NewsRecord(
        source=fetcher.name,
        title="",
        url="https://vnexpress.net/danh-cuoc-mang-song-trong-chung-cu-quan-tai-hong-kong-4986780.html",
    )
    updated = fetcher._parse_detail(html, record)  # type: ignore[attr-defined]
    assert updated.published_at == "2025-11-28T09:37:54+07:00"
    assert "Wang Fuk Court" in (updated.raw.get("content_text") or "")
    assert updated.title.startswith("Mồi lửa")
