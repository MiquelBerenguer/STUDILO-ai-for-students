"""Product name and tagline. Single source of truth: `config/brand.json` at the repo root.

The frontend imports the same file, so renaming the product is a one-line change there.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from app.config.settings import REPO_ROOT


@dataclass(frozen=True)
class Brand:
    name: str
    tagline: str
    slug: str


@lru_cache
def get_brand() -> Brand:
    data = json.loads((REPO_ROOT / "config" / "brand.json").read_text())
    return Brand(name=data["name"], tagline=data["tagline"], slug=data["slug"])
