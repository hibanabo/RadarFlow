"""RFI fetcher parsing tests."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fetcher.rfi import RFINewsFetcher  # noqa: E402
from fetcher.base_fetcher import NewsRecord  # noqa: E402

LISTING_FIXTURE = ROOT / "fetcher" / "data" / "rfi.html"
DETAIL_FIXTURE = ROOT / "fetcher" / "data" / "rfi_detail.html"


def test_rfi_parse_listing_from_fixture() -> None:
    html = LISTING_FIXTURE.read_text(encoding="utf-8")
    fetcher = RFINewsFetcher()
    records = fetcher._parse_listing(html)  # type: ignore[attr-defined]
    assert len(records) >= 10
    titles = [record.title for record in records]
    assert any("台湾增加400亿美元国防开支" in title for title in titles)
    assert records[0].url.startswith("https://www.rfi.fr/")


def test_rfi_parse_detail_from_fixture() -> None:
    html = DETAIL_FIXTURE.read_text(encoding="utf-8")
    fetcher = RFINewsFetcher()
    record = NewsRecord(
        source=fetcher.name,
        title="台湾增加400亿美元国防开支 加速部署T-Dome防空系统",
        url="https://www.rfi.fr/cn/%E6%94%BF%E6%B2%BB/20251130-%E5%8F%B0%E6%B9%BE%E5%A2%9E%E5%8A%A0400%E4%BA%BF%E7%BE%8E%E5%85%83%E5%9B%BD%E9%98%B2%E5%BC%80%E6%94%AF-%E5%8A%A0%E9%80%9F%E9%83%A8%E7%BD%B2t-dome%E9%98%B2%E7%A9%BA%E7%B3%BB%E7%BB%9F",
    )
    updated = fetcher._parse_detail(html, record)  # type: ignore[attr-defined]
    assert updated.published_at == "2025-11-30T09:13:47+00:00"
    assert "台湾政府计划在未来八年内增加400亿美元" in (updated.summary or "")
    assert "与以色列的“铁穹”防御系统相比" in updated.raw.get("content_text", "")
    assert updated.raw.get("section") == "政治"
    assert "中国" in updated.raw.get("keywords", [])
