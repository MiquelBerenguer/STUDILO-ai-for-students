"""Single typed settings object. Secrets come only from the environment / `.env`."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

# Provider name -> env var holding its key. `None` means the provider needs no key.
PROVIDER_KEY_ENV: dict[str, str | None] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "google": "GOOGLE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "ollama": None,
    "local": None,
    "fastembed": None,
}


def mask_secret(value: str | None) -> str | None:
    """Mask a secret for display: `sk-...a3f9`. Never returns the full value."""
    if not value:
        return None
    if len(value) <= 10:
        return "…" + value[-2:]
    return f"{value[:3]}...{value[-4:]}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- LLM providers ---
    ANTHROPIC_API_KEY: SecretStr | None = None
    OPENAI_API_KEY: SecretStr | None = None
    DEEPSEEK_API_KEY: SecretStr | None = None
    GOOGLE_API_KEY: SecretStr | None = None
    OPENROUTER_API_KEY: SecretStr | None = None
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    # --- Embeddings ---
    EMBEDDINGS_API_KEY: SecretStr | None = None
    # --- App ---
    APP_SECRET_KEY: SecretStr = Field(default=SecretStr(""))
    DATABASE_URL: str = "sqlite:///./data/app.db"
    DATA_DIR: str = "./data"
    MODELS_CONFIG: str = str(BACKEND_DIR / "config" / "models.yaml")
    COOKIE_SECURE: bool = False
    SESSION_TTL_DAYS: int = 14
    MAX_UPLOAD_MB: int = 25
    # --- Orchestrator / triggers ---
    ENABLE_BACKGROUND: bool = True
    SCHEDULER_INTERVAL_SECONDS: int = 30
    WORKER_CONCURRENCY: int = 2
    MISSED_UPLOAD_AFTER_HOURS: int = 12
    EXAM_PACK_PRACTICE_EXAMS: int = 2
    EXAM_PACK_QUESTIONS_PER_EXAM: int = 4

    @field_validator("OLLAMA_BASE_URL")
    @classmethod
    def _strip_slash(cls, v: str) -> str:
        return v.rstrip("/")

    # ---- derived paths -------------------------------------------------
    @property
    def data_dir(self) -> Path:
        p = Path(self.DATA_DIR)
        return p if p.is_absolute() else (REPO_ROOT / p).resolve()

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def database_url(self) -> str:
        """Resolve relative sqlite paths against the repo root, so cwd does not matter."""
        prefix = "sqlite:///"
        url = self.DATABASE_URL
        if url.startswith(prefix) and not url.startswith("sqlite:////") and ":memory:" not in url:
            rel = url[len(prefix):]
            path = (REPO_ROOT / rel).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            return prefix + str(path)
        return url

    @property
    def models_config_path(self) -> Path:
        p = Path(self.MODELS_CONFIG)
        return p if p.is_absolute() else (REPO_ROOT / p).resolve()

    def provider_key(self, provider: str) -> str | None:
        env = PROVIDER_KEY_ENV.get(provider)
        if env is None:
            return None
        secret: SecretStr | None = getattr(self, env, None)
        value = secret.get_secret_value().strip() if secret else ""
        return value or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
