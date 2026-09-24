"""One LLM entry point for the whole app: `models.yaml`-driven routing, fallbacks and cost logging.

Every attempt (success or failure) is written to `llm_calls` with tokens, cost and latency.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.config.models_config import ModelsConfigStore, get_models_store
from app.config.settings import Settings, get_settings
from app.db.engine import user_session
from app.db.models import LLMCall
from app.llm.providers import DEFAULT_ADAPTERS, Adapter, ProviderSpec, provider_specs
from app.llm.types import CallContext, LLMError, LLMResponse, LLMUnavailable, Message, ToolSpec

log = logging.getLogger("studilo.llm")
M = TypeVar("M", bound=BaseModel)


class LLMClient:
    def __init__(self, settings: Settings | None = None, store: ModelsConfigStore | None = None,
                 adapters: dict[str, Adapter] | None = None, extra_providers: dict[str, ProviderSpec] | None = None):
        self.settings = settings or get_settings()
        self.store = store or get_models_store()
        self.adapters = dict(DEFAULT_ADAPTERS, **(adapters or {}))
        self.extra_providers = extra_providers or {}

    def specs(self) -> dict[str, ProviderSpec]:
        return {**provider_specs(self.settings), **self.extra_providers}

    def model_for(self, task: str) -> str:
        t = self.store.get().task(task)
        return f"{t.provider}/{t.model}"

    async def chat(self, task: str, messages: list[Message], *, ctx: CallContext, tools: list[ToolSpec] | None = None,
                   json_mode: bool = False, reason: str = "") -> LLMResponse:
        cfg = self.store.get()
        tcfg = cfg.task(task)
        specs = self.specs()
        errors: list[str] = []
        for i, ref in enumerate(tcfg.chain()):
            spec = specs.get(ref.provider)
            if spec is None:
                errors.append(f"{ref.label}: unknown provider")
                continue
            adapter = self.adapters[spec.kind]
            try:
                resp = await adapter.complete(spec, spec.key(self.settings), ref.model, messages, tools, json_mode,
                                              tcfg.max_tokens, tcfg.temperature)
            except LLMError as exc:
                log.warning("LLM call failed task=%s model=%s: %s", task, ref.label, exc)
                self._log(ctx, task, spec.name, ref.model, None, ok=False, error=str(exc)[:1000],
                          is_fallback=i > 0, reason=reason)
                errors.append(str(exc)[:300])
                continue
            priced = ref.model in cfg.pricing
            resp.cost_usd = cfg.cost(ref.model, resp.input_tokens, resp.output_tokens)
            resp.is_fallback = i > 0
            self._log(ctx, task, spec.name, ref.model, resp, ok=True, is_fallback=i > 0,
                      reason=reason + (" [fallback]" if i > 0 else ""), priced=priced)
            return resp
        raise LLMUnavailable(task, errors)

    async def structured(self, task: str, messages: list[Message], schema: type[M], *, ctx: CallContext,
                         reason: str = "", retries: int = 1) -> tuple[M | None, list[LLMResponse]]:
        """Closed-form output validated by Pydantic. One retry on invalid output, then None (caller defaults)."""
        schema_json = json.dumps(schema.model_json_schema())
        convo: list[Message] = list(messages) + [{
            "role": "user",
            "content": "Answer ONLY with a JSON object that validates against this JSON schema:\n" + schema_json,
        }]
        responses: list[LLMResponse] = []
        for attempt in range(retries + 1):
            resp = await self.chat(task, convo, ctx=ctx, json_mode=True,
                                   reason=reason + (f" (retry {attempt})" if attempt else ""))
            responses.append(resp)
            try:
                return schema.model_validate_json(extract_json(resp.text)), responses
            except (ValidationError, ValueError) as exc:
                log.info("Invalid structured output for %s (attempt %d): %s", task, attempt, str(exc)[:200])
                convo += [{"role": "assistant", "content": resp.text},
                          {"role": "user", "content": f"That output was invalid: {str(exc)[:500]}. Reply with valid JSON only."}]
        return None, responses

    async def test_provider(self, name: str) -> str:
        spec = self.specs().get(name)
        if spec is None:
            raise LLMError(name, "-", "unknown provider")
        return await self.adapters[spec.kind].test_connection(spec, spec.key(self.settings))

    def _log(self, ctx: CallContext, task: str, provider: str, model: str, resp: LLMResponse | None, *, ok: bool,
             error: str = "", is_fallback: bool = False, reason: str = "", priced: bool = True) -> None:
        row = LLMCall(
            agent_run_id=ctx.agent_run_id, task=task, provider=provider, model=model,
            input_tokens=resp.input_tokens if resp else 0, output_tokens=resp.output_tokens if resp else 0,
            cost_usd=resp.cost_usd if resp else 0.0, priced=priced, latency_ms=resp.latency_ms if resp else 0,
            ok=ok, error=error, is_fallback=is_fallback, reason=reason[:300],
        )
        if ctx.session is not None:
            ctx.session.add(row)
            ctx.session.commit()
            return
        with user_session(ctx.user_id) as db:
            db.add(row)


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> str:
    """Pull a JSON object out of a model reply (tolerates code fences / leading prose)."""
    m = _FENCE.search(text)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object in reply")
    return text[start:end + 1]


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


def set_llm(client: LLMClient | None) -> None:
    global _client
    _client = client
