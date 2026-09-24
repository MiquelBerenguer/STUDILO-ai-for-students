"""Startup validation (fail fast with a clear message) and migrations."""

from __future__ import annotations

import sys

from alembic import command
from alembic.config import Config

from app.config.models_config import ConfigError, get_models_store, validate_models_config
from app.config.settings import BACKEND_DIR, Settings, get_settings


def validate_settings(settings: Settings, extra_providers: set[str] | None = None) -> None:
    secret = settings.APP_SECRET_KEY.get_secret_value()
    if len(secret) < 32:
        raise ConfigError("APP_SECRET_KEY is not set (or shorter than 32 characters). "
                          "Run `make setup` to generate one, or set it in .env.")
    if not settings.models_config_path.exists():
        raise ConfigError(f"models.yaml not found at {settings.models_config_path}")
    try:
        cfg = get_models_store().get()
    except Exception as exc:  # YAML / schema errors become a clear startup message
        raise ConfigError(f"models.yaml is invalid: {exc}") from exc
    validate_models_config(cfg, settings, extra_providers)


def run_migrations() -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "app" / "db" / "migrations"))
    command.upgrade(cfg, "head")


def main() -> int:
    """`python -m app.startup`: validate configuration without starting the server."""
    try:
        validate_settings(get_settings())
    except ConfigError as exc:
        print(f"\n[studilo] Configuration error:\n{exc}\n", file=sys.stderr)
        return 1
    print("[studilo] configuration OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
