"""AI 预过滤逻辑，在关键词过滤前做一次语义筛选。"""
from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

from fetcher.base_fetcher import NewsRecord
from filters import FilterRule
from utils.config_loader import DEFAULT_CONFIG_PATH, load_settings

logger = logging.getLogger(__name__)

DEFAULT_PREFILTER_PROMPT = Path("prompts/ai_prefilter.md")


@dataclass
class PrefilterResult:
    relevant: bool
    matched_rules: List[str]
    reason: str


class AIPreFilter:
    """调用轻量模型，对新闻与关键词的关联做初筛。"""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        settings = load_settings(self.config_path)
        cfg = settings.get("ai_prefilter", {}) or {}
        ai_cfg = settings.get("ai", {}) or {}
        self.enabled = bool(cfg.get("enabled", False))
        self.base_url = cfg.get("base_url") or ai_cfg.get("base_url") or "https://api.openai.com/v1"
        self.model = cfg.get("model") or ai_cfg.get("model") or "gpt-4o-mini"
        self.api_key = (
            os.environ.get("ARK_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or cfg.get("api_key")
            or ai_cfg.get("api_key")
            or ""
        )
        prompt_file = cfg.get("prompt_file") or str(DEFAULT_PREFILTER_PROMPT)
        prompt_path = Path(prompt_file)
        self.prompt_template = (
            prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else DEFAULT_PREFILTER_PROMPT.read_text(encoding="utf-8")
        )
        self.system_prompt = cfg.get(
            "system_prompt",
            "你是一名资深的中英文新闻审核员，擅长理解不同语言的同义表达并判断是否命中指定情报需求。",
        )
        self.temperature = cfg.get("temperature")
        self.reasoning_effort = cfg.get("reasoning_effort")
        self.timeout = int(cfg.get("timeout_sec", 30))
        self.include_article_body = bool(cfg.get("include_article_body", False))
        self.max_text_chars = int(cfg.get("max_text_chars", 300))
        self.log_rejections = bool(cfg.get("log_rejections", False))
        self.fail_open_on_error = bool(cfg.get("fail_open_on_error", True))
        workers_raw = cfg.get("max_workers")
        try:
            workers_val = int(workers_raw) if workers_raw is not None else 3
        except (TypeError, ValueError):
            workers_val = 3
        self.max_workers = max(1, workers_val)

    def apply(
        self,
        records: Sequence[NewsRecord],
        rules: Sequence[FilterRule],
        filters_enabled: bool,
    ) -> List[NewsRecord]:
        """当配置启用且存在关键词规则时，对新闻做 AI 预筛。"""
        if not (self.enabled and self.api_key and filters_enabled and rules):
            return list(records)
        active_rules = [rule for rule in rules if rule.enabled]
        if not active_rules:
            return list(records)
        kept: List[NewsRecord] = []
        removed = 0
        total = len(records)
        evaluations = self._evaluate_batch(records, active_rules)
        for index, record, result in evaluations:
            if result is None:
                if self.fail_open_on_error:
                    logging.warning(
                        "AI 预过滤 %d/%d 无返回，默认保留: %s",
                        index,
                        total,
                        record.title or record.source or record.url or "未知标题",
                    )
                    if isinstance(record.raw, dict):
                        record.raw["_prefilter_relevant"] = True
                        record.raw["_prefilter_reason"] = "AI 预过滤无返回，默认保留"
                        record.raw["_prefilter_error"] = "no_result"
                    kept.append(record)
                else:
                    removed += 1
                    logging.warning(
                        "AI 预过滤 %d/%d 无返回，按配置拦截: %s",
                        index,
                        total,
                        record.title or record.source or record.url or "未知标题",
                    )
                    if isinstance(record.raw, dict):
                        record.raw["_prefilter_relevant"] = False
                        record.raw["_prefilter_error"] = "no_result"
                continue
            if result.relevant:
                if isinstance(record.raw, dict):
                    record.raw["_prefilter_relevant"] = True
                    if result.matched_rules:
                        record.raw["_prefilter_rules"] = result.matched_rules
                    if result.reason:
                        record.raw["_prefilter_reason"] = result.reason
                kept.append(record)
                logging.info(
                    "AI 预过滤 %d/%d 保留: %s",
                    index,
                    total,
                    record.title or record.source or record.url or "未知标题",
                )
            else:
                removed += 1
                logging.info(
                    "AI 预过滤 %d/%d 剔除: %s",
                    index,
                    total,
                    record.title or record.source or record.url or "未知标题",
                )
                if self.log_rejections:
                    logger.debug(
                        "AI 预过滤剔除: %s - %s (%s)",
                        record.source,
                        record.title,
                        result.reason if result else "无返回",
                    )
        if removed:
            logger.info("AI 预过滤过滤 %d 条新闻，剩余 %d 条。", removed, len(kept))
        return kept

    def _evaluate_batch(
        self,
        records: Sequence[NewsRecord],
        active_rules: Sequence[FilterRule],
    ) -> List[Tuple[int, NewsRecord, Optional[PrefilterResult]]]:
        total = len(records)
        if total == 0:
            return []
        max_workers = min(self.max_workers, total)
        if max_workers <= 1:
            return [
                (index, record, self._evaluate_record(record, active_rules))
                for index, record in enumerate(records, 1)
            ]
        results: List[Tuple[int, NewsRecord, Optional[PrefilterResult]]] = []
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ai-prefilter") as executor:
            future_map = {
                executor.submit(self._evaluate_record, record, active_rules): (index, record)
                for index, record in enumerate(records, 1)
            }
            for future in as_completed(future_map):
                index, record = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001
                    logger.exception("AI 预过滤单条调用失败: %s", exc)
                    result = None
                results.append((index, record, result))
        results.sort(key=lambda item: item[0])
        return results

    def _evaluate_record(self, record: NewsRecord, rules: Sequence[FilterRule]) -> Optional[PrefilterResult]:
        prompt = self._render_prompt(record, rules)
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("AI 预过滤请求失败: %s", exc)
            return None
        data = response.json()
        self._log_usage(data.get("usage"), record.title, stage="AI 预过滤")
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        parsed = self._parse_ai_output(content)
        if not parsed:
            return None
        matched = [str(name).strip() for name in parsed.get("matched_rules", []) if str(name).strip()]
        reason = str(parsed.get("reason") or "").strip()
        return PrefilterResult(bool(parsed.get("relevant")), matched, reason)

    def _render_prompt(self, record: NewsRecord, rules: Sequence[FilterRule]) -> str:
        rules_payload = [
            {
                "name": rule.name,
                "all_of": list(rule.all_of or []),
                "any_of": list(rule.any_of or []),
                "none_of": list(rule.none_of or []),
            }
            for rule in rules
        ]
        rules_json = json.dumps(rules_payload, ensure_ascii=False, indent=2)
        summary_text = self._select_text(record)
        values = {
            "title": record.title or "",
            "summary": summary_text,
            "rules": rules_json,
            "source": record.source or "",
            "url": record.url or "",
        }
        rendered = self.prompt_template
        for key, value in values.items():
            rendered = rendered.replace(f"{{{key}}}", value)
        return rendered

    def _select_text(self, record: NewsRecord) -> str:
        parts: List[str] = []
        if record.summary:
            parts.append(str(record.summary))
        if not parts and isinstance(record.raw, dict):
            fallback = record.raw.get("content_text") or record.raw.get("description")
            if fallback:
                parts.append(str(fallback))
        if self.include_article_body and isinstance(record.raw, dict):
            body = record.raw.get("content_text")
            if body:
                parts.append(str(body))
        text = "\n".join(part for part in parts if part).strip()
        if len(text) > self.max_text_chars:
            return text[: self.max_text_chars] + "..."
        if text:
            return text
        return record.title or ""

    def _parse_ai_output(self, content: str) -> Optional[Dict[str, Any]]:
        cleaned = self._clean_ai_content(content)
        parsed = self._try_decode_json(cleaned)
        if isinstance(parsed, dict):
            parsed.setdefault("matched_rules", [])
            return parsed
        return None

    def _clean_ai_content(self, content: str) -> str:
        text = content.strip()
        text = self._strip_code_block(text)
        return self._strip_json_prefix(text).strip()

    def _strip_code_block(self, text: str) -> str:
        if not text.startswith("```"):
            return text
        without_open = text.split("```", 2)
        if len(without_open) >= 3:
            return without_open[1].strip()
        return text

    def _strip_json_prefix(self, text: str) -> str:
        stripped = text.lstrip()
        if stripped.lower().startswith("json"):
            return stripped[4:].lstrip(" :\n")
        return stripped

    def _try_decode_json(self, text: str) -> Optional[Any]:
        if not text:
            return None
        decoder = json.JSONDecoder()
        try:
            return decoder.decode(text)
        except json.JSONDecodeError:
            pass
        for idx, ch in enumerate(text):
            if ch in "{[":
                try:
                    parsed, _ = decoder.raw_decode(text[idx:])
                    return parsed
                except json.JSONDecodeError:
                    continue
        return None

    def _log_usage(self, usage: Any, title: Optional[str], stage: str) -> None:
        if not isinstance(usage, dict):
            return

        def _to_int(value: Any) -> Optional[int]:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        prompt = _to_int(usage.get("prompt_tokens"))
        completion = _to_int(usage.get("completion_tokens"))
        total = _to_int(usage.get("total_tokens"))
        if total is None and prompt is not None and completion is not None:
            total = prompt + completion
        if all(v is None for v in (prompt, completion, total)):
            return
        safe_title = (title or "").strip() or "未知标题"
        logger.info(
            "[AI tokens] %s | %s | prompt=%s completion=%s total=%s",
            stage,
            safe_title,
            prompt if prompt is not None else "-",
            completion if completion is not None else "-",
            total if total is not None else "-",
        )
