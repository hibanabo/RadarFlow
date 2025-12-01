"""ABS-CBN fetcher parsing tests."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fetcher.abs_cbn import AbsCbnNewsFetcher  # noqa: E402
from fetcher.base_fetcher import NewsRecord  # noqa: E402

LISTING_FIXTURE = ROOT / "fetcher" / "data" / "abs-cbn.html"
DETAIL_FIXTURE = ROOT / "fetcher" / "data" / "abs-cbn_detail.html"


def test_abs_cbn_parse_listing_fixture() -> None:
    html = LISTING_FIXTURE.read_text(encoding="utf-8")
    fetcher = AbsCbnNewsFetcher()
    records = fetcher._parse_listing(html, seen=set())  # type: ignore[attr-defined]
    assert len(records) == 5
    titles = [record.title for record in records]
    assert any("Filipina still missing" in title for title in titles)


def test_abs_cbn_parse_detail_fixture() -> None:
    html = DETAIL_FIXTURE.read_text(encoding="utf-8")
    fetcher = AbsCbnNewsFetcher()
    record = NewsRecord(
        source=fetcher.name,
        title="",
        url="https://www.abs-cbn.com/news/nation/2025/11/28/marcos-jr-zelenskyy-tackle-food-security-digitalization-cooperation-0820",
    )
    updated = fetcher._parse_detail(html, record)  # type: ignore[attr-defined]
    assert updated.published_at == "2025-11-28T00:20:19+00:00"
    assert any("Katrina" in name for name in updated.authors)
    assert "Volodymyr Zelenskyy" in (updated.summary or "")
    body = updated.raw.get("content_text") or ""
    assert "food security" in body
    keywords = updated.raw.get("keywords") or []
    assert "Ferdinand Marcos Jr." in keywords
