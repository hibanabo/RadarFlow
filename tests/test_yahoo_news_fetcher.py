"""Yahoo News fetcher parsing tests."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fetcher.yahoo_news import YahooNewsFetcher  # noqa: E402
from fetcher.base_fetcher import NewsRecord  # noqa: E402

LISTING_FIXTURE = ROOT / "fetcher" / "data" / "yahoo-news.html"
DETAIL_FIXTURE = ROOT / "fetcher" / "data" / "yahoo-news_detail.html"


def test_yahoo_news_parse_listing_fixture() -> None:
    html = LISTING_FIXTURE.read_text(encoding="utf-8")
    fetcher = YahooNewsFetcher()
    records = fetcher._parse_listing(html)  # type: ignore[attr-defined]
    assert len(records) == 12
    rare_earth = next(
        record for record in records if "rare earth gap" in record.title.lower()
    )
    assert rare_earth.url == "https://www.yahoo.com/news/articles/us-set-narrow-rare-earth-115044071.html"
    assert "rare earth" in (rare_earth.summary or "").lower()
    assert rare_earth.raw.get("category") == "Business"
    assert rare_earth.raw.get("publisher") == "Reuters"


def test_yahoo_news_parse_detail_fixture() -> None:
    html = DETAIL_FIXTURE.read_text(encoding="utf-8")
    fetcher = YahooNewsFetcher()
    record = NewsRecord(
        source=fetcher.name,
        title="Death toll in Hong Kong high-rise fire rises to 36, with 279 people reported missing",
        url="https://www.yahoo.com/news/articles/fire-traps-people-hong-kong-084823915.html",
    )
    updated = fetcher._parse_detail(html, record)  # type: ignore[attr-defined]
    assert updated.published_at == "2025-11-26T08:48:23.000Z"
    assert "deadliest fire in years blazed late into the night" in (updated.summary or "")
    content = updated.raw.get("content_text") or ""
    assert "A column of flames and thick smoke rose as the blaze spread quickly" in content
    assert updated.authors == ["CHAN HO-HIM and KEN MORITSUGU"]
    keywords = updated.raw.get("keywords") or []
    assert "HONG KONG" in keywords
    assert updated.raw.get("reading_time") == "3 min read"
