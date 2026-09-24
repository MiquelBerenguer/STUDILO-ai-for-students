from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi.testclient import TestClient


def drain(now: datetime | None = None) -> int:
    from app.orchestrator.worker import drain as _drain

    return asyncio.run(_drain(now))


def upload(client: TestClient, course_id: str, filename: str, data: bytes, kind: str = "notes",
           session_id: str | None = None, run: bool = True) -> dict:
    form = {"course_id": course_id, "kind": kind}
    if session_id:
        form["class_session_id"] = session_id
    r = client.post("/api/v1/uploads", data=form, files=[("files", (filename, data, "application/octet-stream"))])
    assert r.status_code == 201, r.text
    up = r.json()[0]
    if run:
        drain()
    return client.get(f"/api/v1/uploads/{up['id']}").json()


def llm_calls(client: TestClient, task: str | None = None) -> list[dict]:
    calls = client.get("/api/v1/activity/llm-calls?limit=500").json()
    return [c for c in calls if task is None or c["task"] == task]
