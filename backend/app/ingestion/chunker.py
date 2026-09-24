"""LaTeX-aware paragraph chunker (ported from the old `EngineeringChunker`).

Never ends a chunk inside an open `$$…$$` block; hard-splits oversized paragraphs on sentence
boundaries; carries a small overlap between chunks.
"""

from __future__ import annotations

import re

_SENT = re.compile(r"(?<=[.!?])\s+")


def _math_balanced(text: str) -> bool:
    return text.count("$$") % 2 == 0


def _split_long(para: str, size: int) -> list[str]:
    if len(para) <= size or not _math_balanced(para) or "$$" in para:
        return [para]
    out, cur = [], ""
    for sent in _SENT.split(para):
        if cur and len(cur) + len(sent) + 1 > size:
            out.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    return out


def split_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[str]:
    text = text.replace("\r\n", "\n")
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces = [s for p in paras for s in _split_long(p, chunk_size)]
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for piece in pieces:
        joined = "\n\n".join(cur)
        if cur and cur_len + len(piece) > chunk_size and _math_balanced(joined):
            chunks.append(joined)
            tail = joined[-overlap:] if overlap and len(joined) > overlap else ""
            cur = [tail, piece] if tail else [piece]
            cur_len = len(tail) + len(piece)
        else:
            cur.append(piece)
            cur_len += len(piece)
    if cur:
        chunks.append("\n\n".join(cur))
    return [c for c in chunks if c.strip()]
