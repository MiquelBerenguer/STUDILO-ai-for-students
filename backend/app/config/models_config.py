"""`models.yaml`: task -> provider/model mapping, fallbacks and pricing.

The file is re-read whenever its mtime changes, so editing one line switches a model without a
restart or code change. Writes (from the Settings screen) preserve comments via ruamel.
"""

from __future__ import annotations

import threading
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from ruamel.yaml import YAML

from app.config.settings import PROVIDER_KEY_ENV, Settings, get_settings

KNOWN_TASKS = (
    "jev_classification",
    "vision_transcribe",
    "notes_structuring",
    "course_memory",
    "exam_generation",
    "exam_verification",
    "course_qa",
    "timetable_extraction",
    "embeddings",
)


class ConfigError(RuntimeError):
    """Raised at startup when configuration is invalid. Message is user-facing."""


class ModelRef(BaseModel):
    provider: str
    model: str

    @property
    def label(self) -> str:
        return f"{self.provider}/{self.model}"


def parse_ref(text: str) -> ModelRef:
    if "/" not in text:
        raise ConfigError(f"Fallback '{text}' must be written as provider/model")
    provider, model = text.split("/", 1)
    return ModelRef(provider=provider.strip(), model=model.strip())


class TaskConfig(BaseModel):
    provider: str
    model: str
    fallback: list[str] = Field(default_factory=list)
    max_tokens: int | None = None
    temperature: float | None = None

    @field_validator("fallback", mode="before")
    @classmethod
    def _none_to_list(cls, v: object) -> object:
        return v or []

    def chain(self) -> list[ModelRef]:
        return [ModelRef(provider=self.provider, model=self.model)] + [parse_ref(f) for f in self.fallback]


class Pricing(BaseModel):
    input: float = 0.0
    output: float = 0.0


class ModelsConfig(BaseModel):
    tasks: dict[str, TaskConfig]
    pricing: dict[str, Pricing] = Field(default_factory=dict)

    def task(self, name: str) -> TaskConfig:
        if name not in self.tasks:
            raise ConfigError(f"models.yaml has no task '{name}'")
        return self.tasks[name]

    def cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        p = self.pricing.get(model)
        if p is None:
            return 0.0
        return (input_tokens * p.input + output_tokens * p.output) / 1_000_000

    def referenced_providers(self) -> dict[str, list[str]]:
        """provider -> tasks that reference it (primary or fallback)."""
        out: dict[str, list[str]] = {}
        for tname, t in self.tasks.items():
            for ref in t.chain():
                out.setdefault(ref.provider, [])
                if tname not in out[ref.provider]:
                    out[ref.provider].append(tname)
        return out


def validate_models_config(cfg: ModelsConfig, settings: Settings, extra_providers: set[str] | None = None) -> None:
    """Fail fast: every referenced provider must be known and have its key set."""
    known = set(PROVIDER_KEY_ENV) | (extra_providers or set())
    missing_tasks = [t for t in KNOWN_TASKS if t not in cfg.tasks]
    if missing_tasks:
        raise ConfigError(f"models.yaml is missing task(s): {', '.join(missing_tasks)}")
    problems: list[str] = []
    for provider, tasks in sorted(cfg.referenced_providers().items()):
        if provider not in known:
            problems.append(f"unknown provider '{provider}' (used by: {', '.join(tasks)})")
            continue
        env = PROVIDER_KEY_ENV.get(provider)
        if env and not settings.provider_key(provider):
            problems.append(f"{env} is not set (required by provider '{provider}' for: {', '.join(tasks)})")
    emb = cfg.tasks["embeddings"]
    if emb.provider == "openai" and not (settings.EMBEDDINGS_API_KEY and settings.EMBEDDINGS_API_KEY.get_secret_value()):
        problems.append("EMBEDDINGS_API_KEY is not set (required by the 'embeddings' task using provider 'openai')")
    if problems:
        raise ConfigError(
            "Invalid model configuration in " + str(settings.models_config_path) + ":\n  - " + "\n  - ".join(problems)
            + "\nFill the key(s) in .env or change the provider in models.yaml."
        )


class ModelsConfigStore:
    """Thread-safe, mtime-reloading access to models.yaml."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._mtime: float | None = None
        self._cfg: ModelsConfig | None = None
        self._yaml = YAML()
        self._yaml.preserve_quotes = True

    def get(self) -> ModelsConfig:
        with self._lock:
            mtime = self.path.stat().st_mtime
            if self._cfg is None or mtime != self._mtime:
                with self.path.open() as fh:
                    raw = self._yaml.load(fh)
                self._cfg = ModelsConfig.model_validate(_plain(raw))
                self._mtime = mtime
            return self._cfg

    def update_task(self, task: str, provider: str, model: str, fallback: list[str],
                    settings: Settings, extra_providers: set[str] | None = None) -> ModelsConfig:
        """Write a task mapping back to models.yaml (validating first; comments preserved)."""
        with self._lock:
            with self.path.open() as fh:
                raw = self._yaml.load(fh)
            if task not in raw["tasks"]:
                raise ConfigError(f"Unknown task '{task}'")
            entry = raw["tasks"][task]
            entry["provider"] = provider
            entry["model"] = model
            if fallback:
                entry["fallback"] = list(fallback)
            elif "fallback" in entry:
                del entry["fallback"]
            candidate = ModelsConfig.model_validate(_plain(raw))
            validate_models_config(candidate, settings, extra_providers)
            with self.path.open("w") as fh:
                self._yaml.dump(raw, fh)
            self._cfg = candidate
            self._mtime = self.path.stat().st_mtime
            return candidate


def _plain(obj: object) -> object:
    """Convert ruamel CommentedMap/Seq into plain python containers."""
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_plain(v) for v in obj]
    return obj


_store: ModelsConfigStore | None = None


def get_models_store() -> ModelsConfigStore:
    global _store
    path = get_settings().models_config_path
    if _store is None or _store.path != path:
        _store = ModelsConfigStore(path)
    return _store


def reset_models_store() -> None:
    global _store
    _store = None
