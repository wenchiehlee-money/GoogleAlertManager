"""Gemini provider with round-robin key rotation."""
from __future__ import annotations

import logging
import os
import re
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from . import BaseProvider

logger = logging.getLogger(__name__)

_RETRY_DELAYS = [5, 15, 30]
MAX_PROMPT_LENGTH = 50_000


class GeminiProvider(BaseProvider):
    name = "gemini"
    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self, model: str | None = None):
        self.model = model or self.DEFAULT_MODEL
        self._keys: list[tuple[str, str]] = []
        self._exhausted: set[str] = set()
        self._index: int = 0
        self.last_key_used: str = ""  # env var 名稱，供 Amplitude 追蹤

    # ── key loading ──────────────────────────────────────────────────────────

    def _load_keys(self) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        if k := os.getenv("GEMINI_API_KEY"):
            pairs.append(("GEMINI_API_KEY", k))
        for i in range(1, 20):
            name = f"GEMINI_API_KEY_{i}"
            if k := os.getenv(name):
                pairs.append((name, k))
        if not pairs:
            raise RuntimeError("Missing env var: GEMINI_API_KEY")

        skip = {s.strip() for s in os.getenv("GEMINI_SKIP_KEYS", "").split(",") if s.strip()}
        if skip:
            before = len(pairs)
            pairs = [(n, k) for n, k in pairs if n not in skip]
            logger.info("預先跳過 %d 把 key", before - len(pairs))

        # 去重
        seen: set[str] = set()
        unique = []
        for name, k in pairs:
            if k not in seen:
                seen.add(k)
                unique.append((name, k))
        logger.info("載入 %d 把 Gemini key", len(unique))  # 不印 key 名稱
        return unique

    def _get_keys(self) -> list[tuple[str, str]]:
        if not self._keys:
            self._keys = self._load_keys()
        return self._keys

    def _next_available(self) -> tuple[str, str]:
        """Round-robin，跳過已耗盡的 key。"""
        all_keys = self._get_keys()
        for offset in range(len(all_keys)):
            idx = (self._index + offset) % len(all_keys)
            name, key = all_keys[idx]
            if key not in self._exhausted:
                self._index = (idx + 1) % len(all_keys)
                return name, key
        raise RuntimeError("所有 Gemini API key 的每日配額均已耗盡。")

    # ── generate ─────────────────────────────────────────────────────────────

    @staticmethod
    def _is_daily_quota(err_str: str) -> bool:
        return "PerDay" in err_str or "per_day" in err_str.lower() or "daily" in err_str.lower()

    def generate(self, prompt: str, *, json_mode: bool = False, max_tokens: int = 8192) -> str:
        if len(prompt) > MAX_PROMPT_LENGTH:
            raise ValueError(f"Prompt 超過長度上限（{len(prompt)} > {MAX_PROMPT_LENGTH}）")
        available = [(n, k) for n, k in self._get_keys() if k not in self._exhausted]
        if not available:
            raise RuntimeError("所有 Gemini API key 的每日配額均已耗盡。")

        # round-robin 起點
        start_name, start_key = self._next_available()
        start_idx = next(i for i, (n, k) in enumerate(available) if k == start_key)
        ordered = available[start_idx:] + available[:start_idx]

        last_exc: Exception | None = None
        cfg_kwargs: dict = {"max_output_tokens": max_tokens}
        if json_mode:
            cfg_kwargs["response_mime_type"] = "application/json"

        for slot, (key_name, api_key) in enumerate(ordered):
            key_label = f"key#{slot}"  # 不印出 env var 名稱或實際 key
            client = genai.Client(api_key=api_key)
            for i, delay in enumerate([0] + _RETRY_DELAYS):
                if delay:
                    logger.warning("Gemini 重試 %d 秒（第 %d 次）…", delay, i)
                    time.sleep(delay)
                try:
                    resp = client.models.generate_content(
                        model=self.model,
                        contents=prompt,
                        config=types.GenerateContentConfig(**cfg_kwargs),
                    )
                    self.last_key_used = key_name
                    return resp.text
                except genai_errors.ServerError as e:
                    if e.code == 503:
                        last_exc = e
                        continue
                    raise
                except genai_errors.ClientError as e:
                    if e.code == 403:
                        self._exhausted.add(api_key)
                        last_exc = e
                        logger.warning("%s 無效（403），永久跳過（剩餘 %d 把）…",
                                       key_label, len(available) - len(self._exhausted))
                        break
                    if e.code == 429:
                        last_exc = e
                        err_str = str(e)
                        if self._is_daily_quota(err_str):
                            self._exhausted.add(api_key)
                            logger.warning("%s 每日配額耗盡，永久跳過（剩餘 %d 把）…",
                                           key_label, len(available) - len(self._exhausted))
                            break
                        m = re.search(r"retry[^\d]+(\d+)", err_str, re.IGNORECASE)
                        wait = int(m.group(1)) + 2 if m else 30
                        logger.warning("%s RPM 限速，%d 秒後重試…", key_label, wait)
                        time.sleep(wait)
                        continue
                    raise

        raise last_exc  # type: ignore[misc]
