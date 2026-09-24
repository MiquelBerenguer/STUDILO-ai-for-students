"""Fill APP_SECRET_KEY in .env if it is empty. Never prints the value."""

from __future__ import annotations

import re
import secrets
from pathlib import Path

env = Path(__file__).resolve().parents[1] / ".env"
text = env.read_text()
match = re.search(r"^APP_SECRET_KEY=(\S*)", text, re.M)
if match is None:
    text += f"\nAPP_SECRET_KEY={secrets.token_urlsafe(48)}\n"
elif not match.group(1) or match.group(1).startswith("#"):
    text = text[: match.start()] + f"APP_SECRET_KEY={secrets.token_urlsafe(48)}" + text[match.end():]
else:
    raise SystemExit(0)
env.write_text(text)
env.chmod(0o600)
print("generated APP_SECRET_KEY in .env")
