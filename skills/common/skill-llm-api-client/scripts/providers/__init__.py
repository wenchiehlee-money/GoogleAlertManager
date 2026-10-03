"""LLM provider abstraction."""
from __future__ import annotations
from abc import ABC, abstractmethod


class BaseProvider(ABC):
    name: str
    model: str = ""  # 各 provider 覆寫，供 Amplitude 記錄
    model_repo: str = ""  # 權重 / API model source，供追蹤

    @abstractmethod
    def generate(self, prompt: str, *, json_mode: bool = False, max_tokens: int = 8192) -> str:
        """Send prompt, return response text."""
