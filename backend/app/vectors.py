"""sqlite-vec store. One vec0 table per embedding dimension, partitioned by user_id.

The user id is a required argument of every function here and is bound into the KNN query
(`AND user_id = :uid` on the partition key), so vector search can never cross users.
"""

from __future__ import annotations

import re

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

_TABLE_RE = re.compile(r"^vec_chunks_\d+$")


def _table(dim: int) -> str:
    name = f"vec_chunks_{int(dim)}"
    assert _TABLE_RE.match(name)
    return name


def ensure_table(session: Session, dim: int) -> str:
    """Tables for non-default dimensions are created on demand when the embedding model changes (D-12)."""
    name = _table(dim)
    session.execute(text(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {name} USING vec0("
        f"chunk_id INTEGER PRIMARY KEY, user_id TEXT PARTITION KEY, embedding FLOAT[{int(dim)}] distance_metric=cosine)"
    ))
    return name


def _blob(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def upsert(session: Session, user_id: str, chunk_id: int, vec: np.ndarray) -> None:
    name = ensure_table(session, len(vec))
    session.execute(text(f"DELETE FROM {name} WHERE chunk_id = :cid"), {"cid": chunk_id})
    session.execute(
        text(f"INSERT INTO {name}(chunk_id, user_id, embedding) VALUES (:cid, :uid, :emb)"),
        {"cid": chunk_id, "uid": user_id, "emb": _blob(vec)},
    )


def delete(session: Session, chunk_ids: list[int], dim: int) -> None:
    if not chunk_ids:
        return
    name = ensure_table(session, dim)
    for cid in chunk_ids:
        session.execute(text(f"DELETE FROM {name} WHERE chunk_id = :cid"), {"cid": cid})


def knn(session: Session, user_id: str, vec: np.ndarray, k: int = 8) -> list[tuple[int, float]]:
    """Return [(chunk_id, cosine_distance)] for this user only."""
    if not user_id:
        raise PermissionError("vector search requires a user_id")
    name = ensure_table(session, len(vec))
    rows = session.execute(
        text(f"SELECT chunk_id, distance FROM {name} WHERE embedding MATCH :emb AND k = :k AND user_id = :uid "
             "ORDER BY distance"),
        {"emb": _blob(vec), "k": int(k), "uid": user_id},
    ).all()
    return [(int(r[0]), float(r[1])) for r in rows]
