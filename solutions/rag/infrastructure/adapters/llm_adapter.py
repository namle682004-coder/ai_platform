"""
LLM Service Adapter for AIP Enterprise RAG Solution.

Resolves the OpenAI-compatible chat completions endpoint from the model alias registry
(e.g. `chat-general-standard` -> Qwen2.5-7B-Instruct llama-server) and supports SSE streaming.
Upstream failures raise LLMGenerationError; the adapter never fabricates an answer.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx

from ...config import rag_settings
from ...domain.exceptions import LLMGenerationError, LLMStreamInterruptedError
from ...domain.ports import LLMPort
from .runtime_guard import RuntimeOverloadedError, queue_allowance, runtime_guard
from .model_registry import (
    ModelEndpointNotFoundError,
    ModelEndpointResolver,
    ModelRuntimeError,
    is_kv_cache_full,
    model_endpoint_resolver,
    post_json_with_retry,
    runtime_headers,
)

logger = logging.getLogger("aip-rag.adapter.llm")

CONTEXT_WINDOW_CACHE_SECONDS = 300.0


class HttpLlmAdapter(LLMPort):
    """Chat completion client for llama-server / vLLM runtimes registered as model aliases."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        default_model: str = "chat-general-standard",
        resolver: Optional[ModelEndpointResolver] = None,
        timeout: Optional[float] = None,
    ) -> None:
        # Only an explicit RAG_LLM_URL (or constructor argument) bypasses the alias registry.
        self.override_url = (base_url if base_url is not None else rag_settings.llm_base_url) or ""
        self.default_model = default_model
        self.resolver = resolver or model_endpoint_resolver
        self.timeout = timeout or rag_settings.llm_timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None
        self._context_windows: Dict[str, Tuple[Optional[int], float]] = {}

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=20, max_connections=100))
        return self._client

    async def _resolve_base_url(self, model: str) -> str:
        for alias in dict.fromkeys([model, self.default_model]):
            try:
                endpoint = await self.resolver.resolve(alias, override_url=self.override_url)
                return endpoint.base_url
            except ModelEndpointNotFoundError:
                continue
        if rag_settings.vllm_server_url:
            return rag_settings.vllm_server_url.rstrip("/")
        raise LLMGenerationError(f"No chat runtime registered for model alias '{model}'")

    @staticmethod
    def _headers(authorization: Optional[str]) -> Dict[str, str]:
        return runtime_headers(authorization)

    @staticmethod
    def _payload(model: str, messages: List[Dict[str, str]], temperature: float, max_tokens: int) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if rag_settings.llm_seed >= 0:
            payload["seed"] = rag_settings.llm_seed  # same question + same passages -> same answer
        return payload

    async def generate(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        authorization: Optional[str] = None,
    ) -> Tuple[str, int, int]:
        model = model or self.default_model
        base_url = await self._resolve_base_url(model)
        await self._probe_once(model, base_url)
        try:
            data = await post_json_with_retry(
                self._get_client(),
                f"{base_url}/chat/completions",
                self._payload(model, messages, temperature, max_tokens),
                headers=self._headers(authorization),
                timeout=self.timeout,
                kind="llm",
            )
        except ModelRuntimeError as exc:
            raise LLMGenerationError(f"LLM runtime for '{model}' at {base_url} unavailable: {exc}") from exc

        try:
            answer = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMGenerationError(f"Malformed chat completion response from {base_url}") from exc
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or len(str(messages)) // 4)
        completion_tokens = int(usage.get("completion_tokens") or len(answer) // 4)
        return answer, prompt_tokens, completion_tokens

    async def stream_generate(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        authorization: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        model = model or self.default_model
        base_url = await self._resolve_base_url(model)
        await self._probe_once(model, base_url)
        endpoint = f"{base_url}/chat/completions"
        emitted = False
        guard = runtime_guard("llm")
        try:
            # The slot is held for the whole stream: a streaming answer occupies the runtime until its end.
            async with guard.slot():
                async with self._get_client().stream(
                    "POST",
                    endpoint,
                    json={**self._payload(model, messages, temperature, max_tokens), "stream": True},
                    headers=self._headers(authorization),
                    timeout=self.timeout,
                ) as response:
                    if response.status_code != 200:
                        body = (await response.aread()).decode("utf-8", "replace")[:300]
                        if response.status_code == 500 and is_kv_cache_full(body):
                            # Busy, not broken: serialize and let the non-streaming path retry. Raised as
                            # an overload so the breaker does not count it as a runtime failure.
                            guard.throttle()
                            raise RuntimeOverloadedError("llm", "KV cache full under load", 2)
                        raise ModelRuntimeError(f"HTTP {response.status_code}: {body}", status_code=response.status_code)
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:].strip()
                        if raw == "[DONE]":
                            guard.record_success()
                            return
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(event, dict) and event.get("error"):
                            # e.g. llama.cpp "Context size has been exceeded" mid-generation: the answer
                            # is truncated, so it must not be returned as a complete one.
                            err = event["error"]
                            message = err.get("message") if isinstance(err, dict) else str(err)
                            if is_kv_cache_full(message or ""):
                                guard.throttle()
                                if not emitted:
                                    raise RuntimeOverloadedError("llm", "KV cache full under load", 2)
                                # Tokens already went to the caller: only the caller knows whether they
                                # reached the user, so it decides whether to generate again.
                                raise LLMStreamInterruptedError(
                                    f"LLM stream from {endpoint} cut off: runtime out of KV space under load")
                            raise ModelRuntimeError(
                                f"stream error: {err.get('message') if isinstance(err, dict) else err}",
                                status_code=err.get("code") if isinstance(err, dict) else None,
                            )
                        try:
                            delta = event["choices"][0].get("delta", {}).get("content", "")
                        except (KeyError, IndexError, TypeError, AttributeError):
                            continue
                        if delta:
                            emitted = True
                            yield delta
                    guard.record_success()
                    return
        except (httpx.HTTPError, ModelRuntimeError, RuntimeOverloadedError) as exc:
            if isinstance(exc, RuntimeOverloadedError) and "KV cache" not in str(exc):
                raise  # no slot / breaker open: the caller answers "busy"
            if emitted or isinstance(exc, httpx.TimeoutException):
                # Part of the answer already reached the client (replaying it would duplicate text), or the
                # runtime is too slow to answer: a second, non-streaming attempt would only add load.
                raise LLMGenerationError(f"LLM stream from {endpoint} failed: {exc}") from exc
            logger.warning("Streaming from %s failed before first token (%s); retrying without streaming", endpoint, exc)

        answer, _, _ = await self.generate(messages, model, temperature, max_tokens, authorization)
        yield answer

    async def context_window(self, model: str) -> Optional[int]:
        if rag_settings.llm_context_window_tokens > 0:
            return rag_settings.llm_context_window_tokens
        try:
            base_url = await self._resolve_base_url(model or self.default_model)
        except LLMGenerationError:
            return None
        cached = self._context_windows.get(base_url)
        if cached and time.monotonic() - cached[1] < CONTEXT_WINDOW_CACHE_SECONDS:
            return cached[0]
        window = await self._probe_context_window(base_url)
        self._context_windows[base_url] = (window, time.monotonic())
        return window

    @staticmethod
    def queue_allowance() -> float:
        """Seconds a caller's timeout should add now because every runtime slot is taken (see runtime_guard)."""
        return queue_allowance("llm")

    async def _probe_once(self, model: str, base_url: str) -> None:
        """Window and slot count of a runtime are read before its first call (the slots size the bulkhead)."""
        if base_url not in self._context_windows:
            try:
                await self.context_window(model)
            except Exception as exc:  # noqa: BLE001 - probing never fails a call
                logger.debug("Runtime probe failed for %s: %s", base_url, exc)
                self._context_windows[base_url] = (None, time.monotonic())

    async def count_tokens(self, text: str, model: str) -> Optional[int]:
        """
        Exact prompt size from the serving runtime's tokenizer (llama.cpp and vLLM expose /tokenize):
        digits, codes, URLs and table markup take far more tokens per character than prose, so a
        characters-per-token estimate overfills the window on exactly the documents that need it most.
        """
        try:
            base_url = await self._resolve_base_url(model or self.default_model)
        except LLMGenerationError:
            return None
        root = base_url[:-3] if base_url.endswith("/v1") else base_url
        client = self._get_client()
        try:
            res = await client.post(f"{root}/tokenize", json={"content": text, "prompt": text}, timeout=5.0)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data.get("tokens"), list):
                    return len(data["tokens"])
                if isinstance(data.get("count"), int):
                    return int(data["count"])
        except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
            logger.debug("Token count unavailable from %s: %s", root, exc)
        return None

    async def _probe_context_window(self, base_url: str) -> Optional[int]:
        """llama.cpp reports the per-request n_ctx on /props, vLLM reports max_model_len on /v1/models."""
        root = base_url[:-3] if base_url.endswith("/v1") else base_url
        client = self._get_client()
        try:
            res = await client.get(f"{root}/props", timeout=3.0)
            if res.status_code == 200:
                props = res.json()
                slots = props.get("total_slots")
                if rag_settings.concurrency_from_runtime_slots and isinstance(slots, int) and slots > 0:
                    runtime_guard("llm").adopt_capacity(slots)
                n_ctx = (props.get("default_generation_settings") or {}).get("n_ctx")
                if n_ctx:
                    return int(n_ctx)
            res = await client.get(f"{base_url}/models", timeout=3.0)
            if res.status_code == 200:
                for entry in res.json().get("data") or []:
                    if entry.get("max_model_len"):
                        return int(entry["max_model_len"])
        except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
            logger.warning("Could not read the context window of %s: %s", base_url, exc)
        return None

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
