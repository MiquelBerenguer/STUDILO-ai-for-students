"""Embeddings routed by the `embeddings` task in models.yaml (DECISIONS D-12)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import threading
import time
from typing import Protocol

import httpx
import numpy as np

from app.config.models_config import get_models_store
from app.config.settings import get_settings
from app.db.engine import user_session
from app.db.models import LLMCall

log = logging.getLogger("studilo.embeddings")
_WORD = re.compile(r"\w+", re.U)


class Embedder(Protocol):
    label: str
    dim: int

    def embed(self, texts: list[str], user_id: str | None = None) -> np.ndarray: ...


class HashingEmbedder:
    """Deterministic feature-hashing embedder (word unigrams + char trigrams). Offline, zero cost."""

    def __init__(self, dim: int = 384):
        self.dim = dim
        self.label = f"local/hashing-{dim}"

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        words = [w.lower() for w in _WORD.findall(text)]
        feats = words + [f"#{w[i:i + 3]}" for w in words if len(w) > 3 for i in range(len(w) - 2)]
        for f in feats:
            h = hashlib.blake2b(f.encode(), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % self.dim
            v[idx] += 1.0 if h[4] & 1 else -1.0
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed(self, texts: list[str], user_id: str | None = None) -> np.ndarray:
        return np.stack([self._vec(t) for t in texts]) if texts else np.zeros((0, self.dim), dtype=np.float32)


class FastEmbedder:
    def __init__(self, model: str):
        from fastembed import TextEmbedding  # local import: heavy

        self._model = TextEmbedding(model_name=model, cache_dir=str(get_settings().data_dir / "models"))
        self.label = f"fastembed/{model}"
        self.dim = int(self._model.embed(["dimension probe"]).__next__().shape[0])

    def embed(self, texts: list[str], user_id: str | None = None) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vecs = np.stack(list(self._model.embed(texts))).astype(np.float32)
        return vecs / np.clip(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-9, None)


class OpenAIEmbedder:
    """Remote embeddings (OpenAI API) using EMBEDDINGS_API_KEY. Calls are cost-logged."""

    def __init__(self, model: str, key: str):
        self.model, self._key = model, key
        self.label = f"openai/{model}"
        self.dim = 1536 if "small" in model or "ada" in model else 3072

    def embed(self, texts: list[str], user_id: str | None = None) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        t0 = time.monotonic()
        resp = httpx.post("https://api.openai.com/v1/embeddings", json={"model": self.model, "input": texts},
                          headers={"Authorization": f"Bearer {self._key}"}, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        tokens = int(data.get("usage", {}).get("prompt_tokens", 0))
        if user_id:
            cfg = get_models_store().get()
            with user_session(user_id) as db:
                db.add(LLMCall(task="embeddings", provider="openai", model=self.model, input_tokens=tokens,
                               cost_usd=cfg.cost(self.model, tokens, 0), priced=self.model in cfg.pricing,
                               latency_ms=int((time.monotonic() - t0) * 1000), reason="embed note chunks"))
        return np.array([d["embedding"] for d in data["data"]], dtype=np.float32)


_cache: dict[str, Embedder] = {}
_lock = threading.Lock()


def get_embedder() -> Embedder:
    """First embedder in the chain that loads. Load failures are logged as escalations to the fallback."""
    task = get_models_store().get().task("embeddings")
    with _lock:
        for ref in task.chain():
            if ref.label in _cache:
                return _cache[ref.label]
            try:
                emb: Embedder
                if ref.provider == "local":
                    m = re.match(r"hashing-(\d+)$", ref.model)
                    if not m:
                        raise ValueError(f"unknown local embedding model {ref.model!r} (use hashing-<dim>)")
                    emb = HashingEmbedder(int(m.group(1)))
                elif ref.provider == "fastembed":
                    emb = FastEmbedder(ref.model)
                elif ref.provider == "openai":
                    key = get_settings().EMBEDDINGS_API_KEY
                    if not key or not key.get_secret_value():
                        raise ValueError("EMBEDDINGS_API_KEY not set")
                    emb = OpenAIEmbedder(ref.model, key.get_secret_value())
                else:
                    raise ValueError(f"provider {ref.provider!r} does not support embeddings")
            except Exception as exc:  # noqa: BLE001 — any load failure escalates to the next embedder, logged
                log.warning("Embedder %s unavailable (%s: %s); trying fallback", ref.label, type(exc).__name__, exc)
                continue
            _cache[ref.label] = emb
            return emb
    raise RuntimeError("No embedding model could be loaded; check the 'embeddings' task in models.yaml")


async def embed_texts(texts: list[str], user_id: str | None = None) -> tuple[np.ndarray, str]:
    emb = await asyncio.to_thread(get_embedder)
    vecs = await asyncio.to_thread(emb.embed, texts, user_id)
    return vecs, emb.label


def reset_embedders() -> None:
    _cache.clear()
