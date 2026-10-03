"""Unified LLM client with provider fallback chain."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Sequence

from .providers import BaseProvider
from .analytics.amplitude import LLMCallTracker, configure as amplitude_configure

logger = logging.getLogger(__name__)

_DEFAULT_CHAIN = ["codex", "gemini", "mlx"]  # 優先順序：codex → gemini → mlx(本機)
MAX_PROMPT_LENGTH = 50_000


def _build_provider(name: str, model: str | None = None) -> BaseProvider:
    if name == "gemini":
        from .providers.gemini import GeminiProvider
        return GeminiProvider(model=model)
    if name in ("codex", "llm-cli"):
        from .providers.codex import CodexProvider
        return CodexProvider(model=model)
    if name == "mlx":
        from .providers.mlx import MLXProvider
        return MLXProvider(model=model)
    raise ValueError(f"Unknown provider: {name}")


def _detect_available(chain: list[str], model: str | None = None) -> list[BaseProvider]:
    providers: list[BaseProvider] = []
    for name in chain:
        try:
            providers.append(_build_provider(name, model=model))
        except RuntimeError as e:
            logger.debug("跳過 %s（%s）", name, e)
    return providers


def _strip_markdown(text: str) -> str:
    """去除 ```json ... ``` 標記。"""
    text = text.strip()
    if text.startswith("```"):
        # 移除開頭的 ```json 或 ```
        text = re.sub(r"^```(?:json)?\n?", "", text, flags=re.IGNORECASE)
        # 移除結尾的 ```
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


class LLMClient:
    """
    使用方式：
        from llm import LLMClient

        # 自動偵測 provider（codex → gemini）
        client = LLMClient()

        # 指定 provider
        client = LLMClient(providers=["gemini"])
        client = LLMClient(providers=["codex", "gemini"])

        # 指定 Gemini 模型
        client = LLMClient(model="gemini-2.0-flash")
        client = LLMClient(providers=["gemini"], model="gemini-2.5-pro")

        # Amplitude app 名稱
        client = LLMClient(app_name="GoogleAlertManager")

    呼叫時也可臨時覆寫 provider / model：
        client.generate(prompt, provider="gemini", model="gemini-2.0-flash")
    """

    def __init__(
        self,
        providers: Sequence[str] | None = None,
        model: str | None = None,
        app_name: str | None = None,
    ):
        self._chain = list(providers) if providers else _DEFAULT_CHAIN
        self._default_model = model
        self._providers = _detect_available(self._chain, model=model)
        if not self._providers:
            raise RuntimeError(f"沒有可用的 LLM provider（嘗試過：{self._chain}）")
        self.last_provider: str = self._providers[0].name  # updated after each successful call
        self.last_model: str = self._providers[0].model
        self.last_model_repo: str = getattr(self._providers[0], "model_repo", "")

        logger.info(
            "LLMClient 初始化，可用 provider：%s",
            ", ".join(p.name for p in self._providers),
        )
        amplitude_configure(app_name or os.getenv("LLM_APP_NAME", "llm"))

    def _resolve_providers(self, provider: str | None, model: str | None) -> list[BaseProvider]:
        """若呼叫時指定 provider/model，臨時建立；否則使用預設清單。"""
        if provider is None and model is None:
            return self._providers
        chain = [provider] if provider else self._chain
        override = _detect_available(chain, model=model or self._default_model)
        if not override:
            raise RuntimeError(f"指定的 provider '{provider}' 不可用")
        return override

    def generate_smart(
        self,
        task_name: str,
        prompt: str,
        *,
        draft_provider: str = "mlx",
        draft_model: str | None = None,
        judge_provider: str | None = None,
        judge_model: str | None = None,
        json_mode: bool = False,
        max_tokens: int = 8192,
    ) -> str:
        """
        智慧路由模式 (Stateless)：
        1. 優先嘗試 Server-Side 路由 (NAS 伺服器端自我反思)。
        2. 取得草稿 (Draft Stage)。
        3. 將草稿送給強大模型評審 (Judge Stage)。
        4. 所有過程皆會紀錄於 Amplitude 以供分析。
        """

        # --- 效能優化 (Server-Side Smart Routing) ---
        if draft_provider == "codex" and judge_provider is None:
            try:
                codex_p = next((p for p in self._providers if p.name == "llm-cli"), None)
                if codex_p and hasattr(codex_p, "generate_smart"):
                    result = codex_p.generate_smart(
                        task_name, prompt, draft_cli="gemini", judge_cli="gemini",
                        model=draft_model, json_mode=json_mode, max_tokens=max_tokens
                    )
                    self.last_provider = getattr(codex_p, "last_provider_used", "llm-cli")
                    
                    # 紀錄 Server-side 執行 (透過一個空呼叫 tracker 或在 generate 內處理)
                    # 這裡我們模擬一次成功的 generate 呼叫來送出 Amplitude 事件
                    with LLMCallTracker(
                        self.last_provider, "", prompt, 
                        routing_task=task_name, draft_provider=draft_provider,
                        smart_route_status="server_side_executed"
                    ) as tracker:
                        tracker.result = result
                    
                    return result
            except Exception as e:
                logger.warning("SmartRoute [%s] Server-side 失敗: %s", task_name, e)

        # --- 標準流程 (Client-Side Smart Routing) ---
        # 1. 取得草稿
        draft_result = ""
        try:
            draft_result = self.generate(
                prompt, provider=draft_provider, model=draft_model, json_mode=json_mode, max_tokens=max_tokens,
                routing_task=task_name, draft_provider=draft_provider  # 這裡不傳 status，因為這只是過程
            )
        except Exception as e:
            logger.warning("SmartRoute [%s] 取得草稿失敗 (%s): %s", task_name, draft_provider, e)
            # 發生失敗，標記為 draft_failed 並退回標準備援
            return self.generate(
                prompt, json_mode=json_mode, max_tokens=max_tokens,
                routing_task=task_name, draft_provider=draft_provider, smart_route_status="draft_failed"
            )

        # 2. 準備評審 Prompt
        judge_prompt = (
            f"你是評審員。以下是使用者的問題與本地模型的回答。\n"
            f"如果本地模型的回答已經達到你的水準（正確、完整且格式正確），請回覆：OK\n"
            f"如果本地模型的回答不夠好，請直接回覆你認為正確的完整答案。\n\n"
            f"問題：{prompt}\n"
            f"本地回答：{draft_result}"
        )
        if json_mode:
            judge_prompt += "\n注意：請確保你的回覆是合法的 JSON 格式（除非你回覆 OK）。"

        # 3. 挑選強大模型進行評審
        strong_p_name = judge_provider
        if not strong_p_name:
            for p in self._providers:
                if p.name not in ("mlx", "gemini"):
                    strong_p_name = p.name
                    break
            if not strong_p_name:
                for p in self._providers:
                    if p.name != "mlx":
                        strong_p_name = p.name
                        break

        if not strong_p_name:
            logger.error("SmartRoute [%s] 找不到可用於評審的強大模型", task_name)
            return draft_result

        # 4. 執行評審 (手動執行以精確控制事件屬性)
        providers = self._resolve_providers(strong_p_name, judge_model)
        judge_response = ""
        last_exc = None
        
        for p in providers:
            try:
                # 評審過程不帶 status，這只是一個內部的輔助呼叫
                with LLMCallTracker(
                    p.name, p.model, judge_prompt, model_repo=getattr(p, "model_repo", ""),
                    routing_task=task_name, draft_provider=draft_provider
                ) as tracker:
                    judge_response = p.generate(judge_prompt, json_mode=json_mode, max_tokens=max_tokens).strip()
                    tracker.result = judge_response
                    self.last_provider = p.name
                    self.last_model = p.model
                break
            except Exception as e:
                last_exc = e
                continue
        
        if not judge_response and last_exc:
            logger.error("SmartRoute [%s] 評審過程失敗: %s", task_name, last_exc)
            return draft_result

        # 5. 根據評審結果送出最終狀態並回傳
        if re.match(r"^OK[.!]*$", judge_response, re.IGNORECASE):
            logger.info("SmartRoute [%s] %s 通過評審", task_name, draft_provider)
            # 成功：紀錄 judged_passed 並回傳草稿
            with LLMCallTracker(
                draft_provider, draft_model or "", prompt,
                routing_task=task_name, draft_provider=draft_provider,
                smart_route_status="judged_passed"
            ) as tracker:
                tracker.result = draft_result
            self.last_provider = draft_provider
            return draft_result
        else:
            logger.info("SmartRoute [%s] %s 評審失敗，使用強大模型回傳", task_name, draft_provider)
            # 失敗：紀錄 judged_failed 並回傳強大模型的答案
            with LLMCallTracker(
                self.last_provider, self.last_model, prompt,
                routing_task=task_name, draft_provider=draft_provider,
                smart_route_status="judged_failed"
            ) as tracker:
                tracker.result = judge_response
            return judge_response

    def generate_json_smart(
        self,
        task_name: str,
        prompt: str,
        *,
        draft_provider: str = "mlx",
        draft_model: str | None = None,
        judge_provider: str | None = None,
        judge_model: str | None = None,
        max_tokens: int = 8192,
    ) -> dict | list:
        """智慧路由模式，並自動解析 JSON 回傳。"""
        text = self.generate_smart(
            task_name,
            prompt,
            draft_provider=draft_provider,
            draft_model=draft_model,
            judge_provider=judge_provider,
            judge_model=judge_model,
            json_mode=True,
            max_tokens=max_tokens,
        )
        try:
            return json.loads(_strip_markdown(text))
        except json.JSONDecodeError as e:
            logger.error("SmartRoute [%s] 回傳非 JSON：%s\n內容：%s", task_name, e, text)
            return self.generate_json(prompt, max_tokens=max_tokens, routing_task=task_name)

    def generate(
        self,
        prompt: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        json_mode: bool = False,
        max_tokens: int = 8192,
        routing_task: str | None = None,
        draft_provider: str | None = None,
        smart_route_status: str | None = None,
    ) -> str:
        """
        Args:
            prompt:   輸入文字
            provider: 臨時指定 provider（"gemini" / "llm-cli"），覆寫初始化設定
            model:    臨時指定模型（如 "gemini-2.0-flash"），僅對 gemini 有效
            json_mode: 是否回傳 JSON 格式
            max_tokens: 最大輸出 token 數
        """
        if not prompt or not isinstance(prompt, str):
            raise ValueError("prompt 不能為空")

        providers = self._resolve_providers(provider, model)
        if len(prompt) > MAX_PROMPT_LENGTH:
            p = providers[0]
            with LLMCallTracker(
                p.name, p.model, prompt, model_repo=getattr(p, "model_repo", ""),
                routing_task=routing_task, draft_provider=draft_provider,
                smart_route_status=smart_route_status
            ):
                raise ValueError(f"prompt 超過長度上限（{len(prompt)} > {MAX_PROMPT_LENGTH}）")

        last_exc: Exception | None = None
        for p in providers:
            try:
                with LLMCallTracker(
                    p.name, p.model, prompt, model_repo=getattr(p, "model_repo", ""),
                    routing_task=routing_task, draft_provider=draft_provider,
                    smart_route_status=smart_route_status
                ) as tracker:
                    result = p.generate(prompt, json_mode=json_mode, max_tokens=max_tokens)
                    tracker.result = result
                    tracker.key_used = getattr(p, "last_key_used", "")
                    self.last_provider = p.name
                    self.last_model = p.model
                    self.last_model_repo = getattr(p, "model_repo", "")
                    return result
            except Exception as e:
                logger.warning("%s 失敗，嘗試下一個 provider：%s", p.name, e)
                last_exc = e
        raise RuntimeError("所有 provider 均失敗") from last_exc

    def generate_json(
        self,
        prompt: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        max_tokens: int = 8192,
        routing_task: str | None = None,
        draft_provider: str | None = None,
        smart_route_status: str | None = None,
    ) -> dict | list:
        """同 generate()，但自動解析 JSON 回傳。"""
        if not prompt or not isinstance(prompt, str):
            raise ValueError("prompt 不能為空")

        providers = self._resolve_providers(provider, model)
        if len(prompt) > MAX_PROMPT_LENGTH:
            p = providers[0]
            with LLMCallTracker(
                p.name, p.model, prompt, model_repo=getattr(p, "model_repo", ""),
                routing_task=routing_task, draft_provider=draft_provider,
                smart_route_status=smart_route_status
            ):
                raise ValueError(f"prompt 超過長度上限（{len(prompt)} > {MAX_PROMPT_LENGTH}）")

        last_exc: Exception | None = None
        for p in providers:
            try:
                with LLMCallTracker(
                    p.name, p.model, prompt, model_repo=getattr(p, "model_repo", ""),
                    routing_task=routing_task, draft_provider=draft_provider,
                    smart_route_status=smart_route_status
                ) as tracker:
                    text = p.generate(prompt, json_mode=True, max_tokens=max_tokens)
                    tracker.result = text
                    tracker.key_used = getattr(p, "last_key_used", "")
                    self.last_provider = p.name
                    self.last_model = p.model
                    self.last_model_repo = getattr(p, "model_repo", "")
                    return json.loads(_strip_markdown(text))
            except json.JSONDecodeError as e:
                logger.warning("%s 回傳非 JSON：%s", p.name, e)
                last_exc = e
            except Exception as e:
                logger.warning("%s 失敗：%s", p.name, e)
                last_exc = e
        raise RuntimeError("所有 provider 均失敗") from last_exc
