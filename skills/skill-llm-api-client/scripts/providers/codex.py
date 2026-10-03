"""LLM-CLI-APIServer provider（Mac-mini Flask bridge to ChatGPT Pro）。"""
from __future__ import annotations

import logging
import os
import re
import time

import httpx

from . import BaseProvider

logger = logging.getLogger(__name__)

MAX_PROMPT_LENGTH = 50_000  # 與 LLM-CLI-APIServer CODEX_MAX_PROMPT_LENGTH 一致
_CONNECT_TIMEOUT = 10       # 連線建立上限（秒）
_READ_TIMEOUT = 180         # codex exec 最長執行時間（秒）
_PROBE_CONNECT_TIMEOUT = 1.5  # 健康檢查連線上限（秒）
_PROBE_READ_TIMEOUT = 2.0     # 健康檢查讀取上限（秒）

# 已知的雙端點候選位址（Tailscale 內網直連 + 外網反向代理）
DEFAULT_CODEX_URLS = [
    "http://llm-cli-api.tail28f10.ts.net:5001",
    "https://api.wenchiehlee.synology.me:8443",
]

# /gemini/exec 在伺服器端實際執行的是 agy（Antigravity CLI，取代已停用的
# gemini-cli 消費者 OAuth），它的 --model 認的是自家顯示名稱（如
# "Gemini 3.6 Flash (Medium)"），不是 Google API 的 model id（如
# "gemini-2.5-flash"）。呼叫端習慣傳 API id，這裡盡量轉成 agy 目前認得的名稱；
# agy 的可用模型清單會隨版本更新而變動，對照不到的字串原樣送出——agy 會回傳
# 錯誤並列出目前可用清單，上層 LLMClient 會自動 fallback 到下一個 provider，
# 不會整個失敗。
_AGY_MODEL_ALIASES = {
    "gemini-flash": "Gemini 3.6 Flash (Medium)",
    "gemini-2.5-flash": "Gemini 3.6 Flash (Medium)",
    "gemini-2.0-flash": "Gemini 3.6 Flash (Medium)",
    "gemini-pro": "Gemini 3.1 Pro (Low)",
    "gemini-2.5-pro": "Gemini 3.1 Pro (Low)",
    "gemini-1.5-pro": "Gemini 3.1 Pro (Low)",
}
_AGY_NATIVE_NAME_RE = re.compile(r"^Gemini \d")  # 已經是 agy 格式（如 "Gemini 3.6 Flash (Medium)"）

# agy（Antigravity CLI）支援多 provider 聚合介面（Gemini/Claude/GPT-OSS）
_AGY_MODEL_PREFIXES = ("gemini", "claude", "gpt-oss")


def _wants_agy(model: str) -> bool:
    m = (model or "").lower()
    return any(m.startswith(p) for p in _AGY_MODEL_PREFIXES)


def _resolve_agy_model(model: str) -> str:
    if not model or _AGY_NATIVE_NAME_RE.match(model):
        return model
    return _AGY_MODEL_ALIASES.get(model, model)


def _parse_candidate_urls(raw: str | None) -> list[str]:
    """解析候選 URL 清單，若為已知伺服器位址則自動納入雙端點備援。"""
    candidates: list[str] = []
    if raw:
        for item in re.split(r"[,;\s]+", raw.strip()):
            u = item.strip().rstrip("/")
            if u and u not in candidates:
                candidates.append(u)

    if not candidates:
        return list(DEFAULT_CODEX_URLS)

    # 若設定包含預設主機之一，自動將另一已知端點加入候選清單末端作備援
    if any(c in DEFAULT_CODEX_URLS for c in candidates):
        for default in DEFAULT_CODEX_URLS:
            if default not in candidates:
                candidates.append(default)

    return candidates


class CodexProvider(BaseProvider):
    name = "llm-cli"

    def __init__(self, url: str | None = None, api_key: str | None = None, model: str | None = None):
        raw_url = url or os.getenv("CODEX_API_URL", "")
        self.candidate_urls = _parse_candidate_urls(raw_url)
        self.api_key = api_key or os.getenv("CODEX_API_KEY", "")
        self.model = model or "chatgpt-pro"
        self._active_url: str | None = None

        if not self.candidate_urls:
            raise RuntimeError("Missing env var: CODEX_API_URL")
        if not self.api_key:
            raise RuntimeError("Missing env var: CODEX_API_KEY")

    @property
    def url(self) -> str:
        """回傳目前活躍的 API URL。"""
        return self.get_active_url()

    @url.setter
    def url(self, value: str) -> None:
        if value:
            clean = value.rstrip("/")
            self.candidate_urls = _parse_candidate_urls(clean)
            self._active_url = clean
        else:
            self.candidate_urls = list(DEFAULT_CODEX_URLS)
            self._active_url = None

    def _is_server_alive(self, base_url: str, timeout_connect: float = _PROBE_CONNECT_TIMEOUT, timeout_read: float = _PROBE_READ_TIMEOUT) -> bool:
        """快速探測伺服器是否正常回應 /codex/status。"""
        try:
            headers = {"X-API-Key": self.api_key} if self.api_key else {}
            resp = httpx.get(
                f"{base_url}/codex/status",
                headers=headers,
                timeout=httpx.Timeout(connect=timeout_connect, read=timeout_read, write=timeout_connect, pool=timeout_connect),
            )
            return resp.status_code == 200
        except Exception:
            return False

    def get_active_url(self, force_probe: bool = False) -> str:
        """取得目前可連通的活躍伺服器 URL。"""
        if self._active_url and not force_probe:
            return self._active_url

        for candidate in self.candidate_urls:
            if self._is_server_alive(candidate):
                logger.info("CodexProvider: 偵測到可用伺服器 %s", candidate)
                self._active_url = candidate
                return self._active_url

        # 若探測皆未連通，預設使用第一個候選者
        logger.warning(
            "CodexProvider: 所有候選 URL 探測皆無回應，暫時使用 %s",
            self.candidate_urls[0],
        )
        self._active_url = self.candidate_urls[0]
        return self._active_url

    def probe_servers(self) -> dict[str, dict[str, object]]:
        """探測所有候選伺服器的連線狀態與延遲（SOP 診斷工具）。"""
        results: dict[str, dict[str, object]] = {}
        for candidate in self.candidate_urls:
            t0 = time.perf_counter()
            alive = self._is_server_alive(candidate)
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
            results[candidate] = {
                "alive": alive,
                "latency_ms": elapsed_ms if alive else None,
            }
        return results

    def _post(self, endpoint: str, payload: dict, timeout: httpx.Timeout) -> dict:
        """向活躍伺服器發送請求，若發生連線錯誤則自動容錯切換至備用候選 URL。"""
        active = self.get_active_url()
        ordered_urls = [active] + [u for u in self.candidate_urls if u != active]
        last_exception: Exception | None = None

        for u in ordered_urls:
            try:
                resp = httpx.post(
                    f"{u}{endpoint}",
                    json=payload,
                    headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
                    timeout=timeout,
                )
                resp.raise_for_status()
                self._active_url = u
                return resp.json()
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError) as e:
                logger.warning("CodexProvider 連線至 %s%s 失敗 (%s)，嘗試備用 URL...", u, endpoint, e)
                last_exception = e
                continue
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (502, 503, 504):
                    logger.warning("CodexProvider 呼叫 %s%s 回傳 HTTP %d，嘗試備用 URL...", u, endpoint, e.response.status_code)
                    last_exception = e
                    continue
                raise

        if last_exception:
            raise last_exception
        raise RuntimeError("CodexProvider: 無可用的伺服器 URL")

    def generate(self, prompt: str, *, json_mode: bool = False, max_tokens: int = 8192) -> str:
        if len(prompt) > MAX_PROMPT_LENGTH:
            raise ValueError(f"Prompt 超過長度上限（{len(prompt)} > {MAX_PROMPT_LENGTH}）")

        # 若模型屬於 agy 目前已知的 family（Gemini/Claude/GPT-OSS），走 /gemini/exec 端點
        if _wants_agy(self.model):
            endpoint = "/gemini/exec"
            payload = {"prompt": prompt, "model": _resolve_agy_model(self.model), "json_mode": json_mode}
        else:
            endpoint = "/exec"
            payload = {"prompt": prompt, "json_mode": json_mode}

        timeout = httpx.Timeout(
            connect=_CONNECT_TIMEOUT,
            read=_READ_TIMEOUT,
            write=_CONNECT_TIMEOUT,
            pool=_CONNECT_TIMEOUT,
        )
        data = self._post(endpoint, payload, timeout)
        return data.get("output", "")

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

        candidate_model = model or self.model
        resolved_model = candidate_model if _wants_agy(candidate_model) else ""
        if "gemini" in (draft_cli, judge_cli):
            resolved_model = _resolve_agy_model(resolved_model)

        endpoint = "/smart/exec"
        payload = {
            "task_name": task_name,
            "prompt": prompt,
            "draft_cli": draft_cli,
            "judge_cli": judge_cli,
            "model": resolved_model,
            "json_mode": json_mode,
        }

        timeout = httpx.Timeout(
            connect=_CONNECT_TIMEOUT,
            read=_READ_TIMEOUT * 2,
            write=_CONNECT_TIMEOUT,
            pool=_CONNECT_TIMEOUT,
        )
        data = self._post(endpoint, payload, timeout)

        # 紀錄最後使用的 provider (可能是 draft 或 judge)
        self.last_provider_used = data.get("provider", self.name)
        return data.get("output", "")
