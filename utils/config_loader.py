"""统一的配置读取工具。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

DEFAULT_CONFIG_PATH = Path("config") / "config.yaml"


@lru_cache(maxsize=8)
def _load_cached(path_str: str) -> Dict[str, Any]:
    path = Path(path_str)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data


def load_settings(path: Path | None = None) -> Dict[str, Any]:
    """加载完整配置，可传入自定义路径。"""

    target = str((path or DEFAULT_CONFIG_PATH).resolve())
    return _load_cached(target)


def reload_settings(path: Path | None = None) -> Dict[str, Any]:
    """清理缓存后重新加载配置。"""

    _load_cached.cache_clear()
    return load_settings(path)
