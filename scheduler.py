"""简单的调度器，按 cron 规则执行抓取任务。"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from main import main as run_once
from utils.config_loader import DEFAULT_CONFIG_PATH, load_settings
from utils.time_utils import get_timezone_helper

DEFAULT_RUNTIME_CONFIG = DEFAULT_CONFIG_PATH
logger = logging.getLogger(__name__)


def load_scheduler_config(path: Path = DEFAULT_RUNTIME_CONFIG) -> Dict[str, Any]:
    settings = load_settings(path)
    return settings.get("scheduler", {})


@dataclass
class CronSchedule:
    """最简单版 cron 解析器，仅支持 5 段表达式（分 时 日 月 周）。"""

    expression: str
    minutes: Set[int]
    hours: Set[int]
    days: Set[int]
    months: Set[int]
    weekdays: Set[int]

    _WEEKDAY_MAP = {
        "sun": 0,
        "mon": 1,
        "tue": 2,
        "wed": 3,
        "thu": 4,
        "fri": 5,
        "sat": 6,
    }

    def __init__(self, expression: str) -> None:
        parts = expression.split()
        if len(parts) != 5:
            raise ValueError(f"无效的 cron 表达式: {expression!r}")
        self.expression = expression
        self.minutes = self._parse_field(parts[0], 0, 59)
        self.hours = self._parse_field(parts[1], 0, 23)
        self.days = self._parse_field(parts[2], 1, 31)
        self.months = self._parse_field(parts[3], 1, 12)
        self.weekdays = self._parse_field(parts[4], 0, 6, self._WEEKDAY_MAP)

    def _parse_field(
        self,
        field: str,
        minimum: int,
        maximum: int,
        name_map: Optional[Dict[str, int]] = None,
    ) -> Set[int]:
        values: Set[int] = set()
        tokens = [token.strip() for token in field.split(",") if token.strip()]
        if not tokens:
            tokens = ["*"]
        for token in tokens:
            token, step = self._extract_step(token)
            start, end = self._extract_range(token, minimum, maximum, name_map)
            for value in range(start, end + 1, step):
                if minimum <= value <= maximum:
                    values.add(value)
        return values or set(range(minimum, maximum + 1))

    def _extract_step(self, token: str) -> tuple[str, int]:
        if "/" not in token:
            return token, 1
        base, step_str = token.split("/", 1)
        try:
            step = max(1, int(step_str))
        except ValueError as exc:  # noqa: BLE001
            raise ValueError(f"非法步长: {token!r}") from exc
        return base or "*", step

    def _extract_range(
        self,
        token: str,
        minimum: int,
        maximum: int,
        name_map: Optional[Dict[str, int]],
    ) -> tuple[int, int]:
        if token == "*":
            return minimum, maximum
        if "-" in token:
            start, end = token.split("-", 1)
        else:
            start = end = token
        return self._resolve_value(start, minimum, maximum, name_map), self._resolve_value(
            end, minimum, maximum, name_map
        )

    def _resolve_value(
        self,
        token: str,
        minimum: int,
        maximum: int,
        name_map: Optional[Dict[str, int]],
    ) -> int:
        stripped = token.strip().lower()
        if name_map and stripped in name_map:
            return name_map[stripped]
        try:
            value = int(token)
        except ValueError as exc:  # noqa: BLE001
            raise ValueError(f"非法取值: {token!r}") from exc
        if not minimum <= value <= maximum:
            raise ValueError(f"取值超出范围: {token!r}")
        return value

    def next_run(self, after: datetime) -> datetime:
        """返回严格大于 after 的下一个触发时间（向上取整到分钟）。"""

        candidate = after.replace(second=0, microsecond=0)
        if candidate <= after:
            candidate += timedelta(minutes=1)
        while True:
            if self._match(candidate):
                return candidate
            candidate += timedelta(minutes=1)

    def _match(self, moment: datetime) -> bool:
        weekday = (moment.weekday() + 1) % 7  # 调整为 cron 习惯：0 表示周日
        return (
            moment.minute in self.minutes
            and moment.hour in self.hours
            and moment.day in self.days
            and moment.month in self.months
            and weekday in self.weekdays
        )


def run_scheduler(config_path: Optional[Path] = None) -> None:
    runtime_path = Path(config_path) if config_path else DEFAULT_RUNTIME_CONFIG
    cfg = load_scheduler_config(runtime_path)
    enabled = bool(cfg.get("enabled", False))
    cron_schedules = _load_cron_schedules(cfg)
    max_runs = cfg.get("max_runs")
    run_on_start = bool(cfg.get("run_on_start", False))
    tz_helper = get_timezone_helper(runtime_path)
    tz = tz_helper.tzinfo

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    if not enabled:
        logger.info("调度器未启用，直接运行一次抓取任务。")
        run_once()
        return

    if not cron_schedules:
        logger.error("已启用调度，但未配置 cron 表达式。请在 config/config.yaml 中填写 scheduler.cron。")
        return

    run_count = 0
    if run_on_start:
        logger.info("启动后立即执行一次抓取任务。")
        try:
            run_once()
        except Exception:  # noqa: BLE001
            logger.exception("启动阶段执行失败，将继续按照 cron 调度。")
        run_count = 1
        if isinstance(max_runs, int) and run_count >= max_runs:
            logger.info("达到配置的最大执行次数(%d)，自动退出。", max_runs)
            return

    logger.info(
        "按 cron 规则执行，共 %d 条表达式，使用时区：%s。",
        len(cron_schedules),
        tz.tzname(datetime.now(tz)) if hasattr(tz, "tzname") else tz,
    )
    _run_with_cron(cron_schedules, max_runs, tz=tz, initial_runs=run_count)


def _run_with_cron(
    schedules: Sequence[CronSchedule],
    max_runs: Optional[int],
    *,
    tz: tzinfo,
    initial_runs: int = 0,
) -> None:
    run_count = initial_runs
    if isinstance(max_runs, int) and run_count >= max_runs:
        logger.info("达到配置的最大执行次数(%d)，自动退出。", max_runs)
        return
    next_time = _next_cron_run(schedules, datetime.now(tz))
    logger.info("下次执行时间：%s", next_time.isoformat(" ", "seconds"))
    try:
        while True:
            now = datetime.now(tz)
            wait_seconds = max(0.0, (next_time - now).total_seconds())
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            run_count += 1
            logger.info("达成第 %d 次 cron 触发 (%s)。", run_count, next_time.isoformat(" ", "seconds"))
            try:
                run_once()
            except Exception:  # noqa: BLE001
                logger.exception("本次执行发生异常，将继续下一轮。")
            if isinstance(max_runs, int) and run_count >= max_runs:
                logger.info("达到配置的最大执行次数(%d)，自动退出。", max_runs)
                break
            next_time = _next_cron_run(schedules, next_time)
            logger.info("下一次执行时间：%s", next_time.isoformat(" ", "seconds"))
    except KeyboardInterrupt:
        logger.info("收到中断信号，调度器退出。")


def _next_cron_run(schedules: Sequence[CronSchedule], after: datetime) -> datetime:
    return min(schedule.next_run(after) for schedule in schedules)


def _load_cron_schedules(cfg: Dict[str, Any]) -> List[CronSchedule]:
    cron_field = cfg.get("cron")
    if not cron_field:
        return []
    expressions: Iterable[str]
    if isinstance(cron_field, str):
        expressions = [cron_field]
    elif isinstance(cron_field, list):
        expressions = [str(expr) for expr in cron_field if str(expr).strip()]
    else:
        logger.warning("cron 配置格式不正确: %r", cron_field)
        return []
    schedules: List[CronSchedule] = []
    for expr in expressions:
        expr = expr.strip()
        if not expr:
            continue
        try:
            schedules.append(CronSchedule(expr))
        except ValueError as exc:
            logger.warning("忽略无效 cron 表达式 %r: %s", expr, exc)
    return schedules


if __name__ == "__main__":
    run_scheduler()
