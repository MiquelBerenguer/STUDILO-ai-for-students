from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_MODELS_YAML = """
tasks:
  jev_classification: { provider: scripted, model: cheap }
  vision_transcribe: { provider: scripted, model: vision-cheap }
  notes_structuring: { provider: scripted, model: mid }
  course_memory: { provider: scripted, model: mid }
  exam_generation: { provider: scripted, model: strong }
  exam_verification: { provider: scripted, model: mid }
  embeddings: { provider: local, model: hashing-384 }
pricing:
  cheap: { input: 0.1, output: 0.4 }
  vision-cheap: { input: 0.25, output: 1.5 }
  mid: { input: 1.0, output: 5.0 }
  strong: { input: 3.0, output: 15.0 }
"""


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    models = tmp_path / "models.yaml"
    models.write_text(TEST_MODELS_YAML)
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("APP_SECRET_KEY", secrets.token_urlsafe(40))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MODELS_CONFIG", str(models))
    monkeypatch.setenv("ENABLE_BACKGROUND", "false")
    monkeypatch.setenv("EXAM_PACK_PRACTICE_EXAMS", "2")
    monkeypatch.setenv("EXAM_PACK_QUESTIONS_PER_EXAM", "2")

    from app.config.models_config import reset_models_store
    from app.config.settings import get_settings
    from app.db.engine import make_engine, set_engine
    from app.llm.client import LLMClient, set_llm
    from app.llm.embeddings import reset_embedders
    from app.startup import run_migrations
    from tests.fakes import SCRIPTED, ScriptedAdapter

    get_settings.cache_clear()
    reset_models_store()
    reset_embedders()
    engine = make_engine(get_settings().database_url)
    set_engine(engine)
    run_migrations()
    adapter = ScriptedAdapter()
    set_llm(LLMClient(adapters={"scripted": adapter}, extra_providers={"scripted": SCRIPTED}))
    os.environ["_STUDILO_TEST"] = "1"
    yield tmp_path
    set_llm(None)
    engine.dispose()
    get_settings.cache_clear()
    reset_models_store()


@pytest.fixture()
def scripted(env: Path):  # type: ignore[no-untyped-def]
    from app.llm.client import get_llm

    return get_llm().adapters["scripted"]


@pytest.fixture()
def app(env: Path):  # type: ignore[no-untyped-def]
    from app.main import create_app

    return create_app(with_lifespan=False)


def make_client(app) -> TestClient:  # type: ignore[no-untyped-def]
    return TestClient(app)


def register(client: TestClient, email: str, password: str = "correct-horse-1") -> dict[str, str]:
    r = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def client(app) -> TestClient:  # type: ignore[no-untyped-def]
    c = make_client(app)
    register(c, "alice@example.com")
    return c


def onboard(client: TestClient, tz: str = "UTC") -> dict[str, object]:
    """Two subjects, a weekly schedule, semester dates, one exam."""
    client.put("/api/v1/me/profile", json={"timezone": tz, "semester_start": "2026-09-01",
                                           "semester_end": "2027-01-31", "missed_after_hours": 12})
    thermo = client.post("/api/v1/courses", json={"name": "Thermodynamics", "syllabus": "1. First law\n2. Second law"}).json()
    fluids = client.post("/api/v1/courses", json={"name": "Fluid Dynamics"}).json()
    slot = client.post(f"/api/v1/courses/{thermo['id']}/slots",
                       json={"weekday": 3, "start_time": "09:00", "end_time": "11:00"}).json()
    client.post(f"/api/v1/courses/{fluids['id']}/slots", json={"weekday": 4, "start_time": "12:00", "end_time": "14:00"})
    exam = client.post("/api/v1/exams", json={"course_id": thermo["id"], "title": "Thermo midterm",
                                              "exam_date": "2026-10-22"}).json()
    r = client.post("/api/v1/me/complete-onboarding")
    assert r.status_code == 200, r.text
    return {"thermo": thermo, "fluids": fluids, "slot": slot, "exam": exam}
