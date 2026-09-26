"""The product name lives in one place (config/brand.json) and flows everywhere from there."""

from __future__ import annotations

import json

from app.agents.base import load_prompt
from app.config.brand import get_brand
from app.config.settings import REPO_ROOT


def test_brand_comes_from_the_shared_json() -> None:
    data = json.loads((REPO_ROOT / "config" / "brand.json").read_text())
    assert get_brand().name == data["name"] and data["tagline"]
    frontend = (REPO_ROOT / "frontend" / "src" / "brand.ts").read_text()
    assert "config/brand.json" in frontend


def test_prompts_and_api_title_use_the_brand(app) -> None:  # type: ignore[no-untyped-def]
    for name in ("notes_agent", "course_memory_agent", "exam_agent"):
        _, text = load_prompt(name)
        assert "{brand}" not in text and get_brand().name in text
    assert app.title == f"{get_brand().name} API"
