"""时区与日期格式工具。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config_loader import DEFAULT_CONFIG_PATH, load_settings

DEFAULT_DISPLAY_FORMAT = "%Y-%m-%d %H:%M"
_CACHE: Dict[str, "TimeZoneHelper"] = {}


def _from_unix_timestamp(raw: float) -> Optional[datetime]:
    try:
        seconds = raw / 1000 if raw > 10**11 else raw
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def parse_datetime_string(value: Optional[str | int | float]) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return _from_unix_timestamp(float(value))
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return _from_unix_timestamp(float(text))
    normalized = text
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


class TimeZoneHelper:
    """根据配置转换时间。"""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        settings = load_settings(config_path or DEFAULT_CONFIG_PATH)
        tz_config = settings.get("timezone", {}) or {}
        self.display_format = tz_config.get("display_format") or DEFAULT_DISPLAY_FORMAT
        self.tzinfo = self._resolve_timezone(tz_config)

    def _resolve_timezone(self, cfg: Dict[str, any]) -> timezone:
        name = cfg.get("name")
        if name:
            try:
                return ZoneInfo(str(name))
            except ZoneInfoNotFoundError:
                pass
        offset = cfg.get("offset_hours")
        if isinstance(offset, (int, float)):
            return timezone(timedelta(hours=float(offset)))
        return timezone.utc

    def to_iso(self, value: Optional[str]) -> Optional[str]:
        dt = parse_datetime_string(value)
        if not dt:
            return value
        return dt.astimezone(self.tzinfo).isoformat()

    def to_display(self, value: Optional[str]) -> Optional[str]:
        dt = parse_datetime_string(value)
        if not dt:
            return value
        return dt.astimezone(self.tzinfo).strftime(self.display_format)


def get_timezone_helper(path: Optional[Path] = None) -> TimeZoneHelper:
    target = str((path or DEFAULT_CONFIG_PATH).resolve())
    helper = _CACHE.get(target)
    if helper is None:
        helper = TimeZoneHelper(Path(target))
        _CACHE[target] = helper
    return helper


def to_utc_iso(value: Optional[str | int | float]) -> Optional[str]:
    dt = parse_datetime_string(value)
    if not dt:
        return None
    return dt.astimezone(timezone.utc).isoformat()
