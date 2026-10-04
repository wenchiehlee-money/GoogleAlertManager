"""Amplitude event tracking for LLM usage — 同步 HTTP 直送，無背景 thread。"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_AMPLITUDE_URL = "https://api2.amplitude.com/2/httpapi"
_api_key: str | None = None   # None=未初始化, ""=無 key（停用）
_app_name: str = "unknown"


def _get_api_key() -> str:
    global _api_key
    if _api_key is not None:
        return _api_key
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    _api_key = os.getenv("AMPLITUDE_API_KEY", "")
    if not _api_key:
        logger.debug("AMPLITUDE_API_KEY 未設定，Amplitude 追蹤停用")
    return _api_key


def configure(app_name: str) -> None:
    global _app_name
    _app_name = app_name


def _classify_error(exc_type: type) -> str:
    name = exc_type.__name__.lower()
    if "auth" in name or "permission" in name or "forbidden" in name or "403" in name:
        return "auth_error"
    if "quota" in name or "ratelimit" in name or "429" in name:
        return "rate_limit"
    if "timeout" in name:
        return "timeout"
    if "connect" in name or "network" in name or "http" in name:
        return "network_error"
    if "json" in name or "decode" in name or "parse" in name:
        return "parse_error"
    if "value" in name or "type" in name:
        return "input_error"
    return "provider_error"


def _first_n_chars(text: str, n: int) -> str:
    return text[:n] if text else ""


def _first_n_words(text: str, n: int) -> str:
    words = text.split()
    return " ".join(words[:n]) if words else ""


def _send_sync(event_type: str, user_id: str, props: dict[str, Any]) -> None:
    """同步 HTTP POST 到 Amplitude API v2 — 不使用背景 thread。"""
    api_key = _get_api_key()
    if not api_key:
        return
    payload = json.dumps({
        "api_key": api_key,
        "events": [{
            "event_type":       event_type,
            "user_id":          user_id,
            "time":             int(time.time() * 1000),
            "event_properties": props,
        }],
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            _AMPLITUDE_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status != 200:
                logger.debug("Amplitude 回傳 %d", resp.status)
    except Exception as e:
        logger.debug("Amplitude 發送失敗（靜默）：%s", e)


class LLMCallTracker:
    """context manager：呼叫結束後同步送出單一 llm_call event。"""

    def __init__(
        self,
        provider: str,
        model: str,
        prompt: str,
        model_repo: str = "",
        routing_task: str | None = None,
        draft_provider: str | None = None,
        smart_route_status: str | None = None,
    ):
        self.provider = provider
        self.model = model
        self.model_repo = model_repo
        self.prompt = prompt
        self.routing_task = routing_task
        self.draft_provider = draft_provider
        self.smart_route_status = smart_route_status
        self.result: str = ""
        self.key_used: str = ""
        self._start: float = 0.0

    def __enter__(self) -> "LLMCallTracker":
        self._start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_sec = round(time.monotonic() - self._start, 2)
        success = exc_type is None

        props: dict[str, Any] = {
            "provider":       self.provider,
            "model":          self.model,
            "model_repo":     self.model_repo,
            "app_name":       _app_name,
            "key_used":       self.key_used,
            "input_preview":  _first_n_chars(self.prompt, 100),
            "output_preview": _first_n_words(self.result, 100),
            "duration_sec":   duration_sec,
            "success":        success,
        }
        if self.routing_task:
            props["routing_task"] = self.routing_task
        if self.draft_provider:
            props["draft_provider"] = self.draft_provider
        if self.smart_route_status:
            props["smart_route_status"] = self.smart_route_status

        if not success and exc_type is not None:
            props["error_type"] = _classify_error(exc_type)

        _send_sync("llm_call", _app_name, props)
        return False  # 不吃掉例外
