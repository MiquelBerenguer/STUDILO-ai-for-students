"""Tool-loop mechanics, trace persistence, and real status progression (issue #8)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from app.agents.base import Tool, ToolContext, ToolLoopAgent, clean_schema
from app.db.base import utcnow
from app.db.engine import scoped_session_for
from app.db.models import AgentRun, AgentStep, Job
from app.llm.client import LLMClient
from app.llm.types import LLMResponse
from app.orchestrator.state_machines import JOB, UPLOAD, IllegalTransition
from tests import fixture_factory as ff
from tests.conftest import onboard, register
from tests.fakes import SCRIPTED
from tests.helpers import drain


class Echo(BaseModel):
    text: str


class Sequenced:
    """Adapter returning a fixed sequence of tool calls."""

    def __init__(self, script: list[list[dict[str, Any]]]):
        self.script = script
        self.seen: list[list[dict[str, Any]]] = []

    async def complete(self, spec, key, model, messages, tools, json_mode, max_tokens, temperature):  # type: ignore[no-untyped-def]
        self.seen.append(messages)
        calls = self.script.pop(0) if self.script else []
        return LLMResponse(text="" if calls else "done", tool_calls=calls, input_tokens=10, output_tokens=5,
                           provider="scripted", model=model)

    async def test_connection(self, spec, key):  # type: ignore[no-untyped-def]
        return "ok"


class TinyAgent(ToolLoopAgent):
    name = "tiny"
    prompt = "notes_agent"
    task = "notes_structuring"
    max_steps = 4
    require_terminal = True

    def tools(self) -> list[Tool]:
        return [Tool("echo", "echo", Echo, lambda ctx, a: {"echo": a.text}),
                Tool("finish", "finish", Echo, lambda ctx, a: {"done": a.text}, terminal=True)]


def _run(env, script: list[list[dict[str, Any]]]) -> tuple[Any, Sequenced, str]:  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    from app.main import create_app

    c = TestClient(create_app(with_lifespan=False))
    uid = register(c, "loop@example.com")["id"]
    adapter = Sequenced(script)
    llm = LLMClient(adapters={"scripted": adapter}, extra_providers={"scripted": SCRIPTED})
    db = scoped_session_for(uid)
    ctx = ToolContext(user_id=uid, db=db, llm=llm, now=utcnow())
    result = asyncio.run(TinyAgent().run(ctx, "say hi"))
    db.close()
    return result, adapter, uid


def test_loop_runs_tools_feeds_results_back_and_stops_on_terminal(env) -> None:  # type: ignore[no-untyped-def]
    result, adapter, uid = _run(env, [
        [{"id": "1", "name": "echo", "arguments": {"text": "hi"}}],
        [{"id": "2", "name": "finish", "arguments": {"text": "bye"}}],
    ])
    assert result.state == "succeeded" and result.finished_by == "finish"
    tool_msg = [m for m in adapter.seen[1] if m["role"] == "tool"][0]
    assert '"echo": "hi"' in tool_msg["content"]
    db = scoped_session_for(uid)
    run = db.get(AgentRun, result.run_id)
    steps = list(db.scalars(select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.idx)))
    assert [s.kind for s in steps] == ["llm", "tool", "llm", "tool"]
    assert run.llm_calls == 2 and run.prompt_version == "notes_agent@v2"
    db.close()


def test_invalid_args_and_user_id_injection_are_rejected_back_to_the_model(env) -> None:  # type: ignore[no-untyped-def]
    result, adapter, _ = _run(env, [
        [{"id": "1", "name": "echo", "arguments": {"wrong": 1}},
         {"id": "2", "name": "echo", "arguments": {"text": "x", "user_id": "someone-else"}},
         {"id": "3", "name": "nope", "arguments": {}}],
        [{"id": "4", "name": "finish", "arguments": {"text": "ok"}}],
    ])
    errors = [m["content"] for m in adapter.seen[1] if m["role"] == "tool"]
    assert "invalid arguments" in errors[0]
    assert "user_id is not an accepted argument" in errors[1]
    assert "unknown tool" in errors[2]
    assert result.state == "succeeded"


def test_step_limit_stops_the_loop(env) -> None:  # type: ignore[no-untyped-def]
    result, _, _ = _run(env, [[{"id": str(i), "name": "echo", "arguments": {"text": "again"}}] for i in range(10)])
    assert result.state == "step_limit"


def test_tool_schemas_never_expose_user_id() -> None:
    from app.tools.exam import exam_tools
    from app.tools.ingestion import INGESTION_TOOLS
    from app.tools.memory import memory_tools
    from app.tools.notes import notes_tools
    from app.tools.planner import PLANNER_TOOLS

    for tool in [*exam_tools(), *memory_tools(), *notes_tools(), *INGESTION_TOOLS.values(), *PLANNER_TOOLS.values()]:
        schema = clean_schema(tool.args)
        assert "user_id" not in str(schema), tool.name
        assert "$ref" not in str(schema)


def test_status_moves_through_real_states(client) -> None:  # type: ignore[no-untyped-def]
    """Issue #8: states come from the jobs/uploads rows, not a constant."""
    ids = onboard(client)
    r = client.post("/api/v1/uploads", data={"course_id": ids["thermo"]["id"]},
                    files=[("files", ("n.pdf", ff.text_pdf(), "application/pdf"))])
    up = r.json()[0]
    assert up["state"] == "received"
    job = client.get(f"/api/v1/jobs/{up['job_id']}").json()
    assert job["state"] == "queued"
    drain()
    assert client.get(f"/api/v1/jobs/{up['job_id']}").json()["state"] == "succeeded"
    assert client.get(f"/api/v1/uploads/{up['id']}").json()["state"] == "done"
    runs = {r["agent"] for r in client.get("/api/v1/activity/runs").json()}
    assert {"ingestion", "notes", "course_memory"} <= runs


def test_failures_are_recorded_not_swallowed(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    r = client.post(f"/api/v1/exams/{ids['exam']['id']}/build-pack")  # no notes yet → clear failure, no LLM spend
    drain()
    job = client.get(f"/api/v1/jobs/{r.json()['id']}").json()
    assert job["state"] == "failed" and "No notes yet" in job["error"]
    assert client.get("/api/v1/activity/llm-calls").json() == []
    retry = client.post(f"/api/v1/jobs/{job['id']}/retry")
    assert retry.json()["state"] == "queued"


def test_illegal_transitions_raise() -> None:
    with pytest.raises(IllegalTransition):
        UPLOAD.check("received", "done")
    with pytest.raises(IllegalTransition):
        JOB.check("succeeded", "running")
    assert Job  # model import sanity
