"""Provider credential status (masked, never values) and task → model mapping."""

from __future__ import annotations

import socket

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.api.schemas import ProviderStatus, TaskMappingIn
from app.config.models_config import KNOWN_TASKS, ConfigError, get_models_store
from app.config.settings import PROVIDER_KEY_ENV, get_settings, mask_secret
from app.llm.client import get_llm
from app.llm.types import LLMError

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/providers", response_model=list[ProviderStatus])
def providers(user: CurrentUser) -> list[ProviderStatus]:
    settings = get_settings()
    used = get_models_store().get().referenced_providers()
    out = []
    for name, spec in get_llm().specs().items():
        env = PROVIDER_KEY_ENV.get(name)
        key = settings.provider_key(name)
        out.append(ProviderStatus(name=name, key_env=env, configured=bool(key) or env is None,
                                  masked_key=mask_secret(key), base_url=spec.base_url, used_by=used.get(name, [])))
    return out


class TestOut(BaseModel):
    ok: bool
    message: str


@router.post("/providers/{name}/test", response_model=TestOut)
async def test_provider(name: str, user: CurrentUser) -> TestOut:
    try:
        return TestOut(ok=True, message=await get_llm().test_provider(name))
    except LLMError as exc:
        return TestOut(ok=False, message=str(exc)[:400])
    except Exception as exc:  # network/DNS problems: report, do not crash the settings screen
        return TestOut(ok=False, message=f"{type(exc).__name__}: {exc}"[:400])


class TaskOut(BaseModel):
    task: str
    provider: str
    model: str
    fallback: list[str]
    priced: bool


class ModelsOut(BaseModel):
    tasks: list[TaskOut]
    pricing: dict[str, dict[str, float]]
    path: str


@router.get("/models", response_model=ModelsOut)
def models(user: CurrentUser) -> ModelsOut:
    cfg = get_models_store().get()
    return ModelsOut(
        tasks=[TaskOut(task=t, provider=cfg.tasks[t].provider, model=cfg.tasks[t].model,
                       fallback=cfg.tasks[t].fallback, priced=cfg.tasks[t].model in cfg.pricing or
                       cfg.tasks[t].provider in ("local", "fastembed", "ollama")) for t in KNOWN_TASKS],
        pricing={k: v.model_dump() for k, v in cfg.pricing.items()}, path=str(get_settings().models_config_path))


@router.put("/models/{task}", response_model=ModelsOut)
def update_model(task: str, body: TaskMappingIn, user: CurrentUser) -> ModelsOut:
    if task not in KNOWN_TASKS:
        raise HTTPException(404, f"Unknown task {task!r}")
    try:
        get_models_store().update_task(task, body.provider.strip(), body.model.strip(),
                                       [f.strip() for f in body.fallback if f.strip()], get_settings(),
                                       set(get_llm().extra_providers))
    except ConfigError as exc:
        raise HTTPException(422, str(exc)) from exc
    return models(user)


class LanOut(BaseModel):
    urls: list[str]


@router.get("/lan", response_model=LanOut)
def lan(user: CurrentUser, port: int = 5173) -> LanOut:
    """LAN addresses so a phone on the same network can open the upload page."""
    ips: set[str] = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))  # TEST-NET address: no packet is sent for UDP connect
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    return LanOut(urls=[f"http://{ip}:{port}" for ip in sorted(ips) if not ip.startswith("127.")])
