"""Provider adapters. Two wire formats cover all supported providers (DECISIONS D-08)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.config.settings import Settings
from app.llm.types import LLMError, LLMResponse, Message, ToolCall, ToolSpec

TIMEOUT = httpx.Timeout(180.0, connect=15.0)


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    kind: str  # openai_compat | anthropic | local | fastembed
    base_url: str

    def key(self, settings: Settings) -> str | None:
        return settings.provider_key(self.name)


def provider_specs(settings: Settings) -> dict[str, ProviderSpec]:
    return {
        "openai": ProviderSpec("openai", "openai_compat", "https://api.openai.com/v1"),
        "deepseek": ProviderSpec("deepseek", "openai_compat", "https://api.deepseek.com/v1"),
        "openrouter": ProviderSpec("openrouter", "openai_compat", "https://openrouter.ai/api/v1"),
        "google": ProviderSpec("google", "openai_compat", "https://generativelanguage.googleapis.com/v1beta/openai"),
        "ollama": ProviderSpec("ollama", "openai_compat", settings.OLLAMA_BASE_URL + "/v1"),
        "anthropic": ProviderSpec("anthropic", "anthropic", "https://api.anthropic.com/v1"),
        "local": ProviderSpec("local", "local", "(built-in)"),
        "fastembed": ProviderSpec("fastembed", "fastembed", "(local ONNX model)"),
    }


class Adapter(Protocol):
    async def complete(self, spec: ProviderSpec, key: str | None, model: str, messages: list[Message],
                       tools: list[ToolSpec] | None, json_mode: bool, max_tokens: int | None,
                       temperature: float | None) -> LLMResponse: ...

    async def test_connection(self, spec: ProviderSpec, key: str | None) -> str: ...


def _raise_for(resp: httpx.Response, spec: ProviderSpec, model: str) -> None:
    if resp.status_code >= 400:
        body = resp.text[:400].replace("\n", " ")
        raise LLMError(spec.name, model, f"HTTP {resp.status_code}: {body}", resp.status_code)


# --------------------------------------------------------------------------- OpenAI-compatible
class OpenAICompatAdapter:
    def _headers(self, key: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {key}"} if key else {}

    def _messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            role = m["role"]
            if role == "tool":
                out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": _as_text(m.get("content", ""))})
            elif role == "assistant" and m.get("tool_calls"):
                calls = []
                for tc in m["tool_calls"]:
                    call: dict[str, Any] = {"id": tc["id"], "type": "function",
                                            "function": {"name": tc["name"], "arguments": json.dumps(tc.get("arguments", {}))}}
                    call.update(tc.get("extra", {}))
                    calls.append(call)
                out.append({"role": "assistant", "content": _as_text(m.get("content", "")) or None, "tool_calls": calls})
            else:
                content = m.get("content", "")
                if isinstance(content, list):
                    parts: list[dict[str, Any]] = []
                    for p in content:
                        if p["type"] == "text":
                            parts.append({"type": "text", "text": p["text"]})
                        else:
                            parts.append({"type": "image_url",
                                          "image_url": {"url": f"data:{p['media_type']};base64,{p['data']}"}})
                    out.append({"role": role, "content": parts})
                else:
                    out.append({"role": role, "content": content})
        return out

    async def complete(self, spec: ProviderSpec, key: str | None, model: str, messages: list[Message],
                       tools: list[ToolSpec] | None, json_mode: bool, max_tokens: int | None,
                       temperature: float | None) -> LLMResponse:
        body: dict[str, Any] = {"model": model, "messages": self._messages(messages)}
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
        if json_mode and not tools:
            body["response_format"] = {"type": "json_object"}
        if max_tokens:
            body["max_completion_tokens" if spec.name == "openai" else "max_tokens"] = max_tokens
        if temperature is not None:
            body["temperature"] = temperature
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.post(f"{spec.base_url}/chat/completions", json=body, headers=self._headers(key))
        except httpx.HTTPError as exc:
            raise LLMError(spec.name, model, f"network error: {type(exc).__name__}: {exc}") from exc
        _raise_for(resp, spec, model)
        data = resp.json()
        try:
            choice = data["choices"][0]
            msg = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(spec.name, model, f"unexpected response shape: {str(data)[:300]}") from exc
        calls: list[ToolCall] = []
        for raw in msg.get("tool_calls") or []:
            fn = raw.get("function", {})
            tc: ToolCall = {"id": raw.get("id") or f"call_{len(calls)}", "name": fn.get("name", "")}
            extra = {k: v for k, v in raw.items() if k not in ("id", "type", "function", "index")}
            if extra:
                tc["extra"] = extra
            try:
                args = json.loads(fn.get("arguments") or "{}")
                tc["arguments"] = args if isinstance(args, dict) else {"value": args}
            except json.JSONDecodeError as exc:
                tc["arguments"] = {}
                tc["arguments_error"] = f"invalid JSON arguments: {exc}"
            calls.append(tc)
        usage = data.get("usage") or {}
        return LLMResponse(
            text=_as_text(msg.get("content") or ""), tool_calls=calls,
            input_tokens=int(usage.get("prompt_tokens") or 0), output_tokens=int(usage.get("completion_tokens") or 0),
            provider=spec.name, model=model, finish_reason=str(choice.get("finish_reason") or ""),
            latency_ms=int((time.monotonic() - t0) * 1000), raw_usage=usage,
        )

    async def test_connection(self, spec: ProviderSpec, key: str | None) -> str:
        url = f"{spec.base_url}/models" if spec.name != "ollama" else spec.base_url.removesuffix("/v1") + "/api/tags"
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.get(url, headers=self._headers(key))
        _raise_for(resp, spec, "-")
        data = resp.json()
        n = len(data.get("data") or data.get("models") or [])
        return f"OK: {n} models visible"


# --------------------------------------------------------------------------- Anthropic
class AnthropicAdapter:
    VERSION = "2023-06-01"

    def _headers(self, key: str | None) -> dict[str, str]:
        return {"x-api-key": key or "", "anthropic-version": self.VERSION}

    def _convert(self, messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
        system = "\n\n".join(_as_text(m.get("content", "")) for m in messages if m["role"] == "system")
        out: list[dict[str, Any]] = []
        for m in messages:
            role = m["role"]
            if role == "system":
                continue
            if role == "tool":
                block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": _as_text(m.get("content", ""))}
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list) and \
                        all(b.get("type") == "tool_result" for b in out[-1]["content"]):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
                continue
            blocks: list[dict[str, Any]] = []
            content = m.get("content", "")
            if isinstance(content, list):
                for p in content:
                    if p["type"] == "text":
                        blocks.append({"type": "text", "text": p["text"]})
                    else:
                        blocks.append({"type": "image", "source": {"type": "base64", "media_type": p["media_type"],
                                                                   "data": p["data"]}})
            elif content:
                blocks.append({"type": "text", "text": content})
            for tc in m.get("tool_calls", []) or []:
                blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc.get("arguments", {})})
            out.append({"role": role, "content": blocks or [{"type": "text", "text": "(empty)"}]})
        return system, out

    async def complete(self, spec: ProviderSpec, key: str | None, model: str, messages: list[Message],
                       tools: list[ToolSpec] | None, json_mode: bool, max_tokens: int | None,
                       temperature: float | None) -> LLMResponse:
        system, msgs = self._convert(messages)
        if json_mode:
            system = (system + "\n\nRespond with a single JSON object only, no prose, no code fences.").strip()
        body: dict[str, Any] = {"model": model, "max_tokens": max_tokens or 8192, "messages": msgs}
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                             for t in tools]
        if temperature is not None:
            body["temperature"] = temperature
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.post(f"{spec.base_url}/messages", json=body, headers=self._headers(key))
        except httpx.HTTPError as exc:
            raise LLMError(spec.name, model, f"network error: {type(exc).__name__}: {exc}") from exc
        _raise_for(resp, spec, model)
        data = resp.json()
        texts, calls = [], []
        for block in data.get("content", []):
            if block.get("type") == "text":
                texts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append(ToolCall(id=block["id"], name=block["name"], arguments=block.get("input") or {}))
        usage = data.get("usage") or {}
        return LLMResponse(
            text="".join(texts), tool_calls=calls,
            input_tokens=int(usage.get("input_tokens") or 0), output_tokens=int(usage.get("output_tokens") or 0),
            provider=spec.name, model=model, finish_reason=str(data.get("stop_reason") or ""),
            latency_ms=int((time.monotonic() - t0) * 1000), raw_usage=usage,
        )

    async def test_connection(self, spec: ProviderSpec, key: str | None) -> str:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.get(f"{spec.base_url}/models", headers=self._headers(key))
        _raise_for(resp, spec, "-")
        return f"OK: {len(resp.json().get('data', []))} models visible"


class LocalAdapter:
    """Built-in local providers (embeddings only). Chat is not supported."""

    async def complete(self, spec: ProviderSpec, key: str | None, model: str, messages: list[Message],
                       tools: list[ToolSpec] | None, json_mode: bool, max_tokens: int | None,
                       temperature: float | None) -> LLMResponse:
        raise LLMError(spec.name, model, "provider only supports embeddings")

    async def test_connection(self, spec: ProviderSpec, key: str | None) -> str:
        return "OK: built-in, no network needed"


def _as_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content or "")


DEFAULT_ADAPTERS: dict[str, Adapter] = {
    "openai_compat": OpenAICompatAdapter(),
    "anthropic": AnthropicAdapter(),
    "local": LocalAdapter(),
    "fastembed": LocalAdapter(),
}
