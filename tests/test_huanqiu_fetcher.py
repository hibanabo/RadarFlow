"""环球网抓取器解析测试。"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fetcher.huanqiu import HuanqiuNewsFetcher  # noqa: E402
from fetcher.base_fetcher import NewsRecord  # noqa: E402

LISTING_FIXTURE = ROOT / "fetcher" / "data" / "huanqiu.html"
DETAIL_FIXTURE = ROOT / "fetcher" / "data" / "huanqiu_detail.html"


def test_huanqiu_parse_listing_fixture() -> None:
    html = LISTING_FIXTURE.read_text(encoding="utf-8")
    fetcher = HuanqiuNewsFetcher()
    records = fetcher._parse_listing(html)  # type: ignore[attr-defined]
    assert len(records) == 50
    article = next(record for record in records if "俄乌和平协议" in record.title)
    assert article.url == "https://m.huanqiu.com/article/4PIkUS6dU7y"
    assert article.raw.get("source", {}).get("name") == "环球网"
    assert article.raw.get("cover") == "https://img.huanqiucdn.cn/dp/api/files/imageDir/afc3852abc0e7bff8ebe8f7e3d248e02.jpg"


def test_huanqiu_parse_detail_fixture() -> None:
    html = DETAIL_FIXTURE.read_text(encoding="utf-8")
    fetcher = HuanqiuNewsFetcher()
    record = NewsRecord(
        source=fetcher.name,
        title="美报告竟建议台湾出资3500亿至5500亿美元升级菲律宾军事基地，国台办回应",
        url="https://m.huanqiu.com/article/4PIUcyhURRf",
    )
    updated = fetcher._parse_detail(html, record)  # type: ignore[attr-defined]
    assert updated.published_at == "2025-11-26T05:56:46.139000+00:00"
    assert updated.authors == ["徐思琦"]
    assert (updated.summary or "").startswith("11月26日上午")
    body = updated.raw.get("content_text") or ""
    assert "美国“美中经济与安全评估委员会”" in body
    keywords = updated.raw.get("keywords") or []
    assert "台湾" in keywords
    assert updated.raw.get("editor") == "王亚天"
