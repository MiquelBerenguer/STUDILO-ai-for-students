"""OpenAI-compatible adapter wire behaviour (no network: httpx MockTransport)."""

from __future__ import annotations

import asyncio
import json

import httpx

from app.llm import providers
from app.llm.providers import OpenAICompatAdapter, ProviderSpec

TOOLS = [{"name": "answer", "description": "d", "parameters": {"type": "object", "properties": {}}}]
OK = {"choices": [{"message": {"content": "hi", "tool_calls": []}, "finish_reason": "stop"}],
      "usage": {"prompt_tokens": 3, "completion_tokens": 1}}
REFUSAL = {"error": {"message": "Function tools with reasoning_effort are not supported for gpt-5.6-luna in "
                                "/v1/chat/completions. To use function tools, use /v1/responses or set "
                                "reasoning_effort to 'none'.", "param": "reasoning_effort"}}


def _patch(monkeypatch, handler):  # type: ignore[no-untyped-def]
    real = httpx.AsyncClient
    monkeypatch.setattr(providers.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def test_reasoning_models_get_reasoning_off_when_tools_are_used(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    OpenAICompatAdapter._no_reasoning_with_tools.clear()
    bodies: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        bodies.append(body)
        if "tools" in body and body.get("reasoning_effort") != "none":
            return httpx.Response(400, json=REFUSAL)
        return httpx.Response(200, json=OK)

    _patch(monkeypatch, handler)
    spec = ProviderSpec("openai", "openai_compat", "https://api.openai.example/v1")
    ad = OpenAICompatAdapter()
    msgs = [{"role": "user", "content": "q"}]
    r = asyncio.run(ad.complete(spec, "k", "gpt-5.6-luna", msgs, TOOLS, False, None, None))  # type: ignore[arg-type]
    assert r.text == "hi" and len(bodies) == 2 and bodies[1]["reasoning_effort"] == "none"
    asyncio.run(ad.complete(spec, "k", "gpt-5.6-luna", msgs, TOOLS, False, None, None))  # type: ignore[arg-type]
    assert len(bodies) == 3 and bodies[2]["reasoning_effort"] == "none"  # learned: no second refusal
    asyncio.run(ad.complete(spec, "k", "gpt-5.6-luna", msgs, None, True, None, None))  # type: ignore[arg-type]
    assert "reasoning_effort" not in bodies[3]  # without tools the model's default reasoning is kept


def test_other_400s_are_not_retried(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    OpenAICompatAdapter._no_reasoning_with_tools.clear()
    calls: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": {"message": "bad schema"}})

    _patch(monkeypatch, handler)
    spec = ProviderSpec("openai", "openai_compat", "https://api.openai.example/v1")
    try:
        asyncio.run(OpenAICompatAdapter().complete(spec, "k", "m", [{"role": "user", "content": "q"}], TOOLS,  # type: ignore[arg-type]
                                                   False, None, None))
    except providers.LLMError as exc:
        assert "bad schema" in str(exc)
    assert len(calls) == 1
