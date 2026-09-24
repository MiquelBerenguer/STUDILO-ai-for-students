from __future__ import annotations

from pathlib import Path

import pytest

from app.config.models_config import ConfigError, ModelsConfigStore, validate_models_config
from app.config.settings import Settings, mask_secret

REAL_MODELS = Path(__file__).resolve().parents[1] / "config" / "models.yaml"


def _settings(**keys: str) -> Settings:
    base = {k: "" for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GOOGLE_API_KEY",
                            "OPENROUTER_API_KEY")}
    base.update(keys)
    return Settings(_env_file=None, APP_SECRET_KEY="x" * 40, **base)  # type: ignore[call-arg]


def test_committed_models_yaml_is_valid_with_its_keys() -> None:
    cfg = ModelsConfigStore(REAL_MODELS).get()
    validate_models_config(cfg, _settings(GOOGLE_API_KEY="g-key-123456", OPENAI_API_KEY="sk-test-123456"))


def test_missing_provider_key_fails_fast_naming_the_key() -> None:
    cfg = ModelsConfigStore(REAL_MODELS).get()
    with pytest.raises(ConfigError) as exc:
        validate_models_config(cfg, _settings(GOOGLE_API_KEY="g-key-123456"))
    msg = str(exc.value)
    assert "OPENAI_API_KEY is not set" in msg and "exam_generation" in msg
    assert "GOOGLE_API_KEY" not in msg


def test_app_secret_key_required(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config.settings import get_settings
    from app.startup import validate_settings

    monkeypatch.setenv("APP_SECRET_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(ConfigError, match="APP_SECRET_KEY"):
        validate_settings(get_settings(), {"scripted"})


def test_swapping_a_model_is_one_line_and_hot_reloaded(env: Path) -> None:
    import os
    import time

    from app.config.models_config import get_models_store

    store = get_models_store()
    assert store.get().task("exam_generation").model == "strong"
    path = store.path
    path.write_text(path.read_text().replace("exam_generation: { provider: scripted, model: strong }",
                                             "exam_generation: { provider: scripted, model: mid }"))
    os.utime(path, (time.time() + 5, time.time() + 5))
    assert store.get().task("exam_generation").model == "mid"


def test_ui_update_writes_back_preserving_comments(tmp_path: Path) -> None:
    p = tmp_path / "models.yaml"
    p.write_text(REAL_MODELS.read_text())
    store = ModelsConfigStore(p)
    s = _settings(GOOGLE_API_KEY="g-key-123456", OPENAI_API_KEY="sk-test-123456")
    store.update_task("exam_generation", "google", "gemini-3.5-flash", ["openai/gpt-5.6-terra"], s)
    text = p.read_text()
    assert "Swap a model by editing one line" in text
    assert ModelsConfigStore(p).get().task("exam_generation").model == "gemini-3.5-flash"
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        store.update_task("notes_structuring", "anthropic", "claude-sonnet-5", [], s)
    assert ModelsConfigStore(p).get().task("notes_structuring").provider == "google"


def test_mask_secret_never_reveals_value() -> None:
    assert mask_secret("sk-abcdefghijklmnopa3f9") == "sk-...a3f9"
    assert mask_secret(None) is None
    assert "abcdef" not in (mask_secret("abcdefgh") or "")


def test_settings_api_masks_keys(client, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    from app.config.settings import get_settings

    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-SUPERSECRETVALUE-a3f9")
    get_settings.cache_clear()
    from app.llm.client import get_llm

    get_llm().settings = get_settings()
    r = client.get("/api/v1/settings/providers")
    assert r.status_code == 200
    assert "SUPERSECRETVALUE" not in r.text
    openai = next(p for p in r.json() if p["name"] == "openai")
    assert openai["configured"] and openai["masked_key"] == "sk-...a3f9"
