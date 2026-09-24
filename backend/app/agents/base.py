"""Agent primitives: typed tools, a trace recorder, and the tool-calling loop (DECISIONS D-04, D-05).

* `Tool` = name + description + Pydantic argument model + function. Argument models never contain a
  `user_id`: tools act for `ctx.user_id`, which the orchestrator derives from the job's owner.
* `AgentTrace` writes `agent_runs` / `agent_steps` rows, so every decision is visible in Activity.
* `ToolLoopAgent` runs model → tool calls → results → model … with a step limit and a stop condition.
"""

from __future__ import annotations

import inspect
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.config.settings import BACKEND_DIR
from app.db.base import utcnow
from app.db.models import AgentRun, AgentStep
from app.llm.client import LLMClient
from app.llm.types import CallContext, LLMResponse, Message, ToolSpec

log = logging.getLogger("studilo.agents")
PROMPTS_DIR = BACKEND_DIR / "prompts"
MAX_TOOL_RESULT_CHARS = 12000


class ToolError(Exception):
    """Expected, model-visible tool failure (bad id, validation, precondition)."""


@dataclass
class ToolContext:
    user_id: str
    db: Session  # user-scoped session (app.db.engine)
    llm: LLMClient
    now: datetime
    job_id: str | None = None
    run_id: str | None = None
    progress: Callable[[str], None] = field(default=lambda _msg: None)
    state: dict[str, Any] = field(default_factory=dict)  # per-run scratch (e.g. ids touched)

    def call_ctx(self) -> CallContext:
        return CallContext(user_id=self.user_id, agent_run_id=self.run_id, session=self.db)


ToolFn = Callable[[ToolContext, Any], Any | Awaitable[Any]]


@dataclass
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    fn: ToolFn
    terminal: bool = False  # a successful call ends the loop

    def spec(self) -> ToolSpec:
        return {"name": self.name, "description": self.description, "parameters": clean_schema(self.args)}

    async def invoke(self, ctx: ToolContext, raw_args: dict[str, Any]) -> Any:
        if "user_id" in raw_args:
            raise ToolError("user_id is not an accepted argument; tools always act for the signed-in student")
        try:
            args = self.args.model_validate(raw_args)
        except ValidationError as exc:
            raise ToolError(f"invalid arguments: {exc.errors(include_url=False)}") from exc
        out = self.fn(ctx, args)
        if inspect.isawaitable(out):
            out = await out
        return out


def clean_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema → portable subset (refs inlined, Optional collapsed, titles dropped)."""
    raw = model.model_json_schema()
    defs = raw.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            if "anyOf" in node:
                opts = [o for o in node["anyOf"] if o.get("type") != "null"]
                if len(opts) == 1:
                    merged = {**walk(opts[0]), **{k: v for k, v in node.items() if k in ("description",)}}
                    return merged
            return {k: walk(v) for k, v in node.items()
                    if k not in ("title", "$defs", "additionalProperties", "default", "examples")}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    schema = walk(raw)
    schema.setdefault("properties", {})
    schema["type"] = "object"
    return schema


def load_prompt(name: str) -> tuple[str, str]:
    """Return (version, text) of `prompts/<name>.md`. Files start with `---\\nversion: N\\n---`."""
    text = (PROMPTS_DIR / f"{name}.md").read_text()
    version = "0"
    if text.startswith("---"):
        _, header, body = text.split("---", 2)
        for line in header.strip().splitlines():
            k, _, v = line.partition(":")
            if k.strip() == "version":
                version = v.strip()
        text = body.strip()
    return version, text


def _jsonable(obj: Any) -> Any:
    try:
        json.dumps(obj)
        return obj
    except TypeError:
        return json.loads(json.dumps(obj, default=str))


class AgentTrace:
    """Persists one agent run and its steps. Commits after every step so the UI sees live progress."""

    def __init__(self, ctx: ToolContext, agent: str, mode: str, goal: str, task: str = "", prompt_version: str = ""):
        self.ctx = ctx
        self.run = AgentRun(agent=agent, mode=mode, goal=goal[:4000], task=task, prompt_version=prompt_version,
                            job_id=ctx.job_id)
        ctx.db.add(self.run)
        ctx.db.flush()
        ctx.run_id = self.run.id
        ctx.db.commit()
        self._idx = 0

    def step(self, kind: str, name: str, input: Any, output: Any, ok: bool = True, latency_ms: int = 0) -> None:
        self.ctx.db.add(AgentStep(run_id=self.run.id, idx=self._idx, kind=kind, name=name[:64],
                                  input=_jsonable(input), output=_jsonable(output), ok=ok, latency_ms=latency_ms))
        self._idx += 1
        self.run.steps = self._idx
        self.ctx.db.commit()

    def llm(self, resp: LLMResponse) -> None:
        self.run.llm_calls += 1
        self.run.cost_usd += resp.cost_usd
        self.step("llm", f"{resp.provider}/{resp.model}",
                  {"tokens_in": resp.input_tokens},
                  {"text": resp.text[:2000], "tool_calls": [c.get("name") for c in resp.tool_calls],
                   "tokens_out": resp.output_tokens, "cost_usd": round(resp.cost_usd, 6),
                   "fallback": resp.is_fallback},
                  latency_ms=resp.latency_ms)

    async def call(self, tool: Tool, args: dict[str, Any]) -> Any:
        """Invoke a tool and record it (used by deterministic agents and the LLM loop)."""
        t0 = time.monotonic()
        try:
            out = await tool.invoke(self.ctx, args)
        except ToolError as exc:
            self.step("tool", tool.name, args, {"error": str(exc)}, ok=False, latency_ms=_ms(t0))
            raise
        self.step("tool", tool.name, args, _truncate(out), latency_ms=_ms(t0))
        return out

    def decision(self, name: str, detail: dict[str, Any]) -> None:
        self.step("decision", name, {}, detail)

    def finish(self, state: str, output: str = "", error: str = "") -> None:
        self.run.state = state
        self.run.output = output[:8000]
        self.run.error = error[:4000]
        self.run.finished_at = utcnow()
        self.ctx.db.commit()


def _ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def _truncate(out: Any) -> Any:
    text = json.dumps(out, default=str)
    if len(text) <= MAX_TOOL_RESULT_CHARS:
        return out
    return {"truncated": True, "preview": text[:MAX_TOOL_RESULT_CHARS]}


@dataclass
class AgentResult:
    state: str  # succeeded | failed | step_limit
    output: str
    run_id: str
    finished_by: str | None = None
    terminal_result: Any = None


class ToolLoopAgent:
    """Base class for LLM agents. Subclasses set name/prompt/task and implement `tools()`."""

    name: str = "agent"
    prompt: str = ""
    task: str = ""
    max_steps: int = 20
    require_terminal: bool = False  # if True, a reply without tool calls is nudged instead of ending

    def tools(self) -> list[Tool]:
        raise NotImplementedError

    async def run(self, ctx: ToolContext, goal: str) -> AgentResult:
        version, system = load_prompt(self.prompt)
        tools = {t.name: t for t in self.tools()}
        specs = [t.spec() for t in tools.values()]
        trace = AgentTrace(ctx, self.name, "llm", goal, task=self.task, prompt_version=f"{self.prompt}@v{version}")
        messages: list[Message] = [{"role": "system", "content": system}, {"role": "user", "content": goal}]
        nudged = 0
        try:
            for _ in range(self.max_steps):
                ctx.db.commit()
                resp = await ctx.llm.chat(self.task, messages, ctx=ctx.call_ctx(), tools=specs,
                                          reason=f"{self.name} agent step")
                trace.llm(resp)
                if not resp.tool_calls:
                    if self.require_terminal and nudged < 2:
                        nudged += 1
                        messages += [{"role": "assistant", "content": resp.text or "(no reply)"},
                                     {"role": "user", "content": "You have not finished. Continue using the tools; "
                                      "the task only ends when the finishing tool succeeds."}]
                        continue
                    trace.finish("succeeded" if not self.require_terminal else "failed", resp.text,
                                 "" if not self.require_terminal else "model stopped without finishing")
                    return AgentResult(trace.run.state, resp.text, trace.run.id)
                messages.append({"role": "assistant", "content": resp.text, "tool_calls": resp.tool_calls})
                for call in resp.tool_calls:
                    tool = tools.get(call.get("name", ""))
                    if tool is None:
                        result: Any = {"error": f"unknown tool {call.get('name')!r}"}
                        trace.step("tool", str(call.get("name"))[:64], call.get("arguments"), result, ok=False)
                    elif call.get("arguments_error"):
                        result = {"error": call["arguments_error"]}
                        trace.step("tool", tool.name, {}, result, ok=False)
                    else:
                        try:
                            result = await trace.call(tool, call.get("arguments", {}))
                        except ToolError as exc:
                            result = {"error": str(exc)}
                        except Exception as exc:  # unexpected: record, tell the model, keep the loop alive
                            log.exception("tool %s crashed", tool.name)
                            ctx.db.rollback()
                            result = {"error": f"internal tool error: {type(exc).__name__}: {exc}"}
                            trace.step("tool", tool.name, call.get("arguments"), result, ok=False)
                        else:
                            if tool.terminal:
                                messages.append(_tool_msg(call, result))
                                trace.finish("succeeded", json.dumps(result, default=str)[:4000])
                                return AgentResult("succeeded", json.dumps(result, default=str), trace.run.id,
                                                   finished_by=tool.name, terminal_result=result)
                    messages.append(_tool_msg(call, result))
            trace.finish("step_limit", error=f"stopped after {self.max_steps} steps without finishing")
            return AgentResult("step_limit", "", trace.run.id)
        except Exception as exc:
            ctx.db.rollback()
            trace.finish("failed", error=f"{type(exc).__name__}: {exc}")
            raise


def _tool_msg(call: dict[str, Any], result: Any) -> Message:
    text = json.dumps(result, default=str, ensure_ascii=False)
    if len(text) > MAX_TOOL_RESULT_CHARS:
        text = text[:MAX_TOOL_RESULT_CHARS] + "…(truncated)"
    return {"role": "tool", "tool_call_id": call.get("id", ""), "name": call.get("name", ""), "content": text}


def prompt_path(name: str) -> Path:
    return PROMPTS_DIR / f"{name}.md"
