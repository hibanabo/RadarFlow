"""Filter rule matching tests."""
from __future__ import annotations

from filters import FilterRule


def test_all_of_groups_support_or_logic() -> None:
    rule = FilterRule(
        name="china_or_taiwan_with_us_allies",
        all_of=[["中国", "台湾"], ["美国", "日本", "韩国"]],
    )
    assert rule.matches("中国与美国讨论台湾问题")
    assert rule.matches("台湾与日本关系更新")
    assert not rule.matches("中国经济数据公布")
    assert not rule.matches("美国与日本举行会议")


def test_none_of_and_any_of_behaviour() -> None:
    rule = FilterRule(
        name="deny_keywords",
        all_of=["中国"],
        any_of=["美国", "日本"],
        none_of=["旅游", ["体育", "文娱"]],
    )
    assert rule.matches("中国与美国进行安全会晤")
    assert not rule.matches("中国旅游业恢复")
    assert not rule.matches("中国体育赛事与日本合作")
