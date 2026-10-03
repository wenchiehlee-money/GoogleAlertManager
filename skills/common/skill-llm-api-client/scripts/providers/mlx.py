"""MLX-API-Server provider — HTTP client for Mac-mini MLX inference server."""
from __future__ import annotations

import logging
import os
import re

import httpx

from . import BaseProvider

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 10
_READ_TIMEOUT    = 900   # MLX 大模型推理最長 15 分鐘

_MODEL_ALIASES = {
    "mlx-qwen3":  "mlx-community/Qwen3.5-9B-MLX-4bit",
    "qwen3-mlx":  "mlx-community/Qwen3.5-9B-MLX-4bit",
    "mlx-gemma4": "mlx-community/gemma-4-e4b-it-8bit",
}

# VLM models echo the prompt back in output — need extra stripping
_VLM_ALIASES = {"mlx-gemma4"}


def _parse_mlx_output(raw: str, is_vlm: bool = False) -> str:
    """Extract clean answer from mlx_lm / mlx_vlm output.

    mlx_lm format:          mlx_vlm format:
        ==========              ==========
        [Thinking...]           Files: []
        </think>                Prompt: <bos>...<|turn>model
        ANSWER                  ANSWER
        ==========              ==========
        Prompt: X tokens...     Prompt: X tokens...
    """
    # Strip trailing stats block (==========\nPrompt: ...)
    raw = re.sub(r"\n=+\nPrompt:.*$", "", raw, flags=re.DOTALL).strip()
    # Strip leading ========== separator
    raw = re.sub(r"^=+\n", "", raw).strip()
    if is_vlm:
        # Strip "Files: [...]\n" header
        raw = re.sub(r"^Files:.*?\n", "", raw).strip()
        # Strip echoed prompt (everything up to and including <|turn>model\n)
        if "<|turn>model" in raw:
            raw = raw.split("<|turn>model", 1)[1].strip()
    else:
        # Strip thinking section up to and including </think>
        if "</think>" in raw:
            raw = raw.split("</think>", 1)[1].strip()
    return raw


class MLXProvider(BaseProvider):
    name = "mlx"

    def __init__(self, model: str | None = None, url: str | None = None, api_key: str | None = None):
        self.url     = (url     or os.getenv("MLX_API_URL",        "")).rstrip("/")
        self.api_key = api_key  or os.getenv("MLX_SERVER_API_KEY", "")
        if not self.url:
            raise RuntimeError("Missing env var: MLX_API_URL (e.g. http://mac-mini.tail28f10.ts.net:5001)")
        if not self.api_key:
            raise RuntimeError("Missing env var: MLX_SERVER_API_KEY")

        alias = model or os.getenv("MLX_MODEL", "mlx-qwen3")
        self.model      = alias
        self.model_repo = _MODEL_ALIASES.get(alias, alias)

    def generate(self, prompt: str, *, json_mode: bool = False, max_tokens: int = 8192) -> str:
        if json_mode:
            prompt = prompt + "\n\nRespond with valid JSON only, no markdown fences, no explanation."

        payload: dict = {"prompt": prompt, "model": self.model}

        resp = httpx.post(
            f"{self.url}/exec",
            json=payload,
            headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
            timeout=httpx.Timeout(connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT,
                                  write=_CONNECT_TIMEOUT, pool=_CONNECT_TIMEOUT),
        )
        resp.raise_for_status()
        raw = resp.json().get("output", "")
        return _parse_mlx_output(raw, is_vlm=self.model in _VLM_ALIASES)
