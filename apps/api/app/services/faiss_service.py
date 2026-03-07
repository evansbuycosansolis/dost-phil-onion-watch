from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import settings

try:
    import faiss  # type: ignore
except Exception:  # pragma: no cover
    faiss = None


class LocalEmbeddingAdapter:
    def __init__(self, dim: int):
        self.dim = dim

    def embed(self, text: str) -> np.ndarray:
        # Hashing-based deterministic embedding fallback.
        vector = np.zeros(self.dim, dtype=np.float32)
        tokens = [token for token in text.lower().split() if token]
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dim
            vector[idx] += 1.0
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector /= norm
        return vector


class FaissStore:
    def __init__(self, dim: int, index_path: str, metadata_path: str):
        self.dim = dim
        self.index_path = Path(index_path)
        self.metadata_path = Path(metadata_path)
        self.embedder = LocalEmbeddingAdapter(dim)
        self.metadata: list[dict[str, Any]] = []
        self._vectors: np.ndarray | None = None
        self.index = None

        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)

        self._load()

    def _load(self) -> None:
        if self.metadata_path.exists():
            self.metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        if not self.index_path.exists():
            if faiss is None:
                self._vectors = np.empty((0, self.dim), dtype=np.float32)
            return

        if faiss is not None:
            try:
                self.index = faiss.read_index(str(self.index_path))
                self._vectors = None
                return
            except Exception:
                self.index = None

        try:
            with self.index_path.open("rb") as stream:
                self._vectors = np.load(stream, allow_pickle=False)
        except Exception:
            self._vectors = np.empty((0, self.dim), dtype=np.float32)

    def _save(self) -> None:
        self.metadata_path.write_text(json.dumps(self.metadata), encoding="utf-8")
        if faiss is not None and self.index is not None:
            faiss.write_index(self.index, str(self.index_path))
        elif self._vectors is not None:
            with self.index_path.open("wb") as stream:
                np.save(stream, self._vectors)

    def rebuild(self, payloads: list[dict[str, Any]]) -> None:
        if not payloads:
            self.metadata = []
            self.index = faiss.IndexFlatL2(self.dim) if faiss is not None else None
            self._vectors = np.empty((0, self.dim), dtype=np.float32)
            self._save()
            return

        vectors = np.vstack([self.embedder.embed(item["content"]) for item in payloads]).astype(np.float32)
        self.metadata = payloads
        if faiss is not None:
            self.index = faiss.IndexFlatL2(self.dim)
            self.index.add(vectors)
            self._vectors = None
        else:
            self.index = None
            self._vectors = vectors
        self._save()

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        if not self.metadata:
            return []

        q_vec = self.embedder.embed(query).reshape(1, -1).astype(np.float32)

        if faiss is not None and self.index is not None:
            distances, indices = self.index.search(q_vec, min(top_k, len(self.metadata)))
            rows = []
            for i, idx in enumerate(indices[0]):
                if idx < 0:
                    continue
                score = float(1.0 / (1.0 + distances[0][i]))
                rows.append({**self.metadata[idx], "score": score})
            return rows

        if self._vectors is None or len(self._vectors) == 0:
            return []

        dots = np.dot(self._vectors, q_vec[0])
        top_idx = np.argsort(-dots)[:top_k]
        return [{**self.metadata[int(idx)], "score": float(dots[int(idx)])} for idx in top_idx]


_store: FaissStore | None = None


def get_store() -> FaissStore:
    global _store
    if _store is None:
        _store = FaissStore(
            dim=settings.local_embedding_dim,
            index_path=settings.faiss_index_path,
            metadata_path=settings.faiss_metadata_path,
        )
    return _store


def chunk_text(text: str, chunk_size: int = 700, overlap: int = 120) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        chunks.append(cleaned[start:end])
        if end == len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks
