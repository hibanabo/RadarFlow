"""Daily Mail fetcher parsing tests."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fetcher.dailymail import DailyMailNewsFetcher  # noqa: E402
from fetcher.base_fetcher import NewsRecord  # noqa: E402

LISTING_FIXTURE = ROOT / "fetcher" / "data" / "dailymail.html"
DETAIL_FIXTURE = ROOT / "fetcher" / "data" / "dailymail_detail.html"


def test_dailymail_parse_listing_fixture() -> None:
    html = LISTING_FIXTURE.read_text(encoding="utf-8")
    fetcher = DailyMailNewsFetcher()
    records = fetcher._parse_listing(html)  # type: ignore[attr-defined]
    assert len(records) == 149
    target = next(record for record in records if "Amol Rajan" in record.title)
    assert target.url == "https://www.dailymail.co.uk/news/article-15331353/BBC-Today-host-Amol-Rajan-forced-make-air-apology-describing-benefits-claimants-scroungers.html"
    assert target.raw.get("channel") == "news"


def test_dailymail_parse_detail_fixture() -> None:
    html = DETAIL_FIXTURE.read_text(encoding="utf-8")
    fetcher = DailyMailNewsFetcher()
    record = NewsRecord(
        source=fetcher.name,
        title="BBC Today host Amol Rajan is forced to make on-air apology after describing benefits claimants as 'scroungers'",
        url="https://www.dailymail.co.uk/news/article-15331353/BBC-Today-host-Amol-Rajan-forced-make-air-apology-describing-benefits-claimants-scroungers.html",
    )
    updated = fetcher._parse_detail(html, record)  # type: ignore[attr-defined]
    assert updated.published_at == "2025-11-27T10:15:32+00:00"
    assert updated.raw.get("updated_at") == "2025-11-27T11:13:20+00:00"
    assert updated.authors == ["Elizabeth Haigh, Senior News Reporter"]
    assert (updated.summary or "").startswith("Mr Rajan, who has been a presenter")
    body = updated.raw.get("content_text") or ""
    assert "benefits claimants are 'scroungers'" in body
    assert "Rachel Reeves" in body
    keywords = updated.raw.get("keywords") or []
    assert "Rachel Reeves" in keywords
