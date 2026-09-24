"""Legibility check for text extracted from a PDF text layer (DECISIONS D-11).

Signals: characters per page, garbage-character ratio, dictionary-word ratio (en/es/ca/fr/de via
wordfreq), and broken-encoding (mojibake) detection via ftfy. If the check passes, no LLM is used.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass

from ftfy.badness import badness
from wordfreq import zipf_frequency

LANGS = ("en", "es", "ca", "fr", "de")
_TOKEN = re.compile(r"[^\W\d_]{2,}", re.U)
_CID = re.compile(r"\(cid:\d+\)")


@dataclass(frozen=True)
class LegibilityThresholds:
    min_chars_text_layer: int = 25  # below this a page has no usable text layer
    max_garbage_ratio: float = 0.02
    min_dict_ratio: float = 0.55
    min_tokens_for_dict: int = 8
    max_mojibake_per_1k: float = 2.0


@dataclass
class LegibilityReport:
    chars: int
    garbage_ratio: float
    dict_ratio: float
    tokens: int
    mojibake_per_1k: float
    has_text_layer: bool
    passed: bool
    score: float
    reason: str

    def as_dict(self) -> dict[str, float | int | bool | str]:
        return asdict(self)


def _is_garbage(ch: str) -> bool:
    if ch == "\ufffd":
        return True
    cat = unicodedata.category(ch)
    if cat == "Co":  # private use area: unmapped glyphs
        return True
    return cat == "Cc" and ch not in "\n\r\t"


def _dict_ratio(text: str, limit: int = 3000) -> tuple[float, int]:
    tokens = _TOKEN.findall(text)[:limit]
    if not tokens:
        return 0.0, 0
    known = 0
    for tok in tokens:
        low = tok.lower()
        if any(zipf_frequency(low, lang) >= 1.0 for lang in LANGS):
            known += 1
    return known / len(tokens), len(tokens)


def check_legibility(text: str, th: LegibilityThresholds = LegibilityThresholds()) -> LegibilityReport:
    stripped = "".join(text.split())
    chars = len(stripped)
    if chars < th.min_chars_text_layer:
        return LegibilityReport(chars, 0.0, 0.0, 0, 0.0, False, False, 0.0, f"no usable text layer ({chars} chars)")
    garbage = sum(1 for ch in stripped if _is_garbage(ch)) + 5 * len(_CID.findall(text))
    garbage_ratio = min(1.0, garbage / chars)
    dict_ratio, n_tokens = _dict_ratio(text)
    moji = badness(text[:20000]) * 1000 / max(1, min(len(text), 20000))

    reasons = []
    if garbage_ratio > th.max_garbage_ratio:
        reasons.append(f"garbage characters {garbage_ratio:.1%}")
    if n_tokens >= th.min_tokens_for_dict and dict_ratio < th.min_dict_ratio:
        reasons.append(f"only {dict_ratio:.0%} dictionary words")
    if moji > th.max_mojibake_per_1k:
        reasons.append(f"broken encoding ({moji:.1f} mojibake/1k chars)")
    passed = not reasons
    density = min(1.0, chars / 300)
    score = round(0.2 * density + 0.3 * max(0.0, 1 - garbage_ratio * 20) + 0.5 * dict_ratio
                  - (0.3 if moji > th.max_mojibake_per_1k else 0.0), 3)
    return LegibilityReport(
        chars=chars, garbage_ratio=round(garbage_ratio, 4), dict_ratio=round(dict_ratio, 3), tokens=n_tokens,
        mojibake_per_1k=round(moji, 2), has_text_layer=True, passed=passed, score=max(0.0, score),
        reason="legible text layer" if passed else "; ".join(reasons),
    )
