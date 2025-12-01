"""The Guardian fetcher tests."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fetcher.theguardian import TheGuardianNewsFetcher  # noqa: E402
from fetcher.base_fetcher import NewsRecord  # noqa: E402

LISTING_FIXTURE = ROOT / "fetcher" / "data" / "theguardian.html"
DETAIL_FIXTURE = ROOT / "fetcher" / "data" / "theguardian_detail.html"


def test_guardian_parse_listing_fixture() -> None:
    html = LISTING_FIXTURE.read_text(encoding="utf-8")
    fetcher = TheGuardianNewsFetcher()
    records = fetcher._parse_listing(html, seen=set())  # type: ignore[attr-defined]
    assert len(records) == 19
    urls = [record.url for record in records]
    assert "https://www.theguardian.com/world/2025/nov/27/denmark-sets-up-night-watch-to-monitor-trump-since-greenland-row" in urls


def test_guardian_parse_detail_fixture() -> None:
    html = DETAIL_FIXTURE.read_text(encoding="utf-8")
    fetcher = TheGuardianNewsFetcher()
    record = NewsRecord(
        source=fetcher.name,
        title="",
        url="https://www.theguardian.com/world/2025/nov/28/usa-terminating-myanmar-protected-status-deportation-fears",
    )
    updated = fetcher._parse_detail(html, record)  # type: ignore[attr-defined]
    assert updated.published_at == "2025-11-28T03:01:51+00:00"
    assert updated.raw.get("updated_at") == "2025-11-28T03:02:59+00:00"
    assert "Lorcan Lovett" in updated.authors[0]
    assert "Temporary Protective Status" in (updated.summary or "")
    body = updated.raw.get("content_text") or ""
    assert "Temporary Protective Status" in body
    assert "junta plans to hold" in body
