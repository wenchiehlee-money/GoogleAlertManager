"""LLM-CLI-APIServer provider (Mac-mini Flask bridge to ChatGPT Pro)."""
from __future__ import annotations

import logging
import os
import re

import httpx

from . import BaseProvider

logger = logging.getLogger(__name__)

MAX_PROMPT_LENGTH = 50_000
_CONNECT_TIMEOUT = 10
_READ_TIMEOUT = 180

# Ordered fallback endpoints. These are service topology, not credentials.
CODEX_ENDPOINTS = (
    "https://api.wenchiehlee.synology.me:8443",
    "http://llm-cli-api.tail28f10.ts.net:5001",
)

_AGY_MODEL_ALIASES = {
    "gemini-flash": "Gemini 3.6 Flash (Medium)",
    "gemini-2.5-flash": "Gemini 3.6 Flash (Medium)",
    "gemini-2.0-flash": "Gemini 3.6 Flash (Medium)",
    "gemini-pro": "Gemini 3.1 Pro (Low)",
    "gemini-2.5-pro": "Gemini 3.1 Pro (Low)",
    "gemini-1.5-pro": "Gemini 3.1 Pro (Low)",
}
_AGY_NATIVE_NAME_RE = re.compile(r"^Gemini \d")


def _resolve_agy_model(model: str) -> str:
    if not model or _AGY_NATIVE_NAME_RE.match(model):
        return model
    return _AGY_MODEL_ALIASES.get(model, model)


class CodexProvider(BaseProvider):
    name = "llm-cli"

    def __init__(self, url: str | None = None, api_key: str | None = None, model: str | None = None):
        self.urls = [url.rstrip("/")] if url else list(CODEX_ENDPOINTS)
        self.url = self.urls[0]
        self.api_key = api_key or os.getenv("CODEX_API_KEY", "")
        self.model = model or "chatgpt-pro"
        if not self.api_key:
            raise RuntimeError("Missing env var: CODEX_API_KEY")

    def _post(self, path: str, payload: dict, timeout: httpx.Timeout) -> httpx.Response:
        last_exc: Exception | None = None
        for endpoint in self.urls:
            try:
                response = httpx.post(
                    f"{endpoint}{path}",
                    json=payload,
                    headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
                    timeout=timeout,
                )
                response.raise_for_status()
                self.url = endpoint
                return response
            except Exception as exc:
                last_exc = exc
                logger.warning("Codex endpoint %s failed; trying next endpoint: %s", endpoint, exc)
        assert last_exc is not None
        raise last_exc

    def generate(self, prompt: str, *, json_mode: bool = False, max_tokens: int = 8192) -> str:
        if len(prompt) > MAX_PROMPT_LENGTH:
            raise ValueError(f"Prompt 超過長度上限（{len(prompt)} > {MAX_PROMPT_LENGTH}）")

        if self.model.startswith("gemini"):
            endpoint = "/gemini/exec"
            payload = {"prompt": prompt, "model": _resolve_agy_model(self.model), "json_mode": json_mode}
        else:
            endpoint = "/exec"
            payload = {"prompt": prompt, "json_mode": json_mode}

        response = self._post(
            endpoint,
            payload,
            httpx.Timeout(connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT,
                          write=_CONNECT_TIMEOUT, pool=_CONNECT_TIMEOUT),
        )
        return response.json().get("output", "")

    def generate_smart(
        self,
        task_name: str,
        prompt: str,
        *,
        draft_cli: str = "gemini",
        judge_cli: str = "gemini",
        model: str | None = None,
        json_mode: bool = False,
        max_tokens: int = 8192,
    ) -> str:
        """調用伺服器端的智慧路由端點 (消除網路延遲)。"""
        if len(prompt) > MAX_PROMPT_LENGTH:
            raise ValueError(f"Prompt 超過長度上限（{len(prompt)} > {MAX_PROMPT_LENGTH}）")

        resolved_model = model or (self.model if self.model.startswith("gemini") else "")
        if "gemini" in (draft_cli, judge_cli):
            resolved_model = _resolve_agy_model(resolved_model)

        payload = {
            "task_name": task_name,
            "prompt": prompt,
            "draft_cli": draft_cli,
            "judge_cli": judge_cli,
            "model": resolved_model,
            "json_mode": json_mode,
        }
        response = self._post(
            "/smart/exec",
            payload,
            httpx.Timeout(connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT * 2,
                          write=_CONNECT_TIMEOUT, pool=_CONNECT_TIMEOUT),
        )
        data = response.json()
        self.last_provider_used = data.get("provider", self.name)
        return data.get("output", "")
