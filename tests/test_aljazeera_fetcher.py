"""Al Jazeera fetcher parsing tests."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fetcher.aljazeera import AlJazeeraNewsFetcher  # noqa: E402
from fetcher.base_fetcher import NewsRecord  # noqa: E402

LISTING_FIXTURE = ROOT / "fetcher" / "data" / "aljazeera.html"
DETAIL_FIXTURE = ROOT / "fetcher" / "data" / "aljazeera_detail.html"


def test_aljazeera_parse_listing_fixture() -> None:
    html = LISTING_FIXTURE.read_text(encoding="utf-8")
    fetcher = AlJazeeraNewsFetcher()
    records = fetcher._parse_listing(html)  # type: ignore[attr-defined]
    assert len(records) == 20
    gaza_story = next(record for record in records if "Amnesty warns" in record.title)
    assert gaza_story.url == "https://www.aljazeera.com/news/2025/11/27/israel-escalates-aerial-assault-of-southern-central-gaza-past-yellow-line"
    assert gaza_story.raw.get("tag") is None


def test_aljazeera_parse_detail_fixture() -> None:
    html = DETAIL_FIXTURE.read_text(encoding="utf-8")
    fetcher = AlJazeeraNewsFetcher()
    record = NewsRecord(
        source=fetcher.name,
        title="Amnesty warns ‘genocide not over’ as Israel strikes across Gaza",
        url="https://www.aljazeera.com/news/2025/11/27/israel-escalates-aerial-assault-of-southern-central-gaza-past-yellow-line",
    )
    updated = fetcher._parse_detail(html, record)  # type: ignore[attr-defined]
    assert updated.published_at == "2025-11-27T08:32:23+00:00"
    assert updated.raw.get("updated_at") == "2025-11-27T10:10:36+00:00"
    assert updated.authors == ["Stephen Quillen", "News Agencies"]
    assert updated.summary and "genocidal intent" in updated.summary
    body = updated.raw.get("content_text") or ""
    assert "Amnesty International has warned" in body
    assert "The first stage of the Gaza truce moved closer to completion" in body
    keywords = updated.raw.get("keywords") or []
    assert "Gaza" in keywords
