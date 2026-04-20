"""
FAISS 落盘向量库：与 InMemoryVectorStore 相同检索语义（L2 归一化后内积 = 余弦相似度）。

索引与元数据写入 `index_dir`（默认 `backend/data/indexes/default`），服务重启后自动加载。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import List, Optional, Union

import numpy as np

from .chunking import chunk_plain_text
from .document_loader import bytes_to_plain_text
from .embeddings import HashEmbedding, SentenceTransformerEmbedding, create_default_embedder, embedding_backend_label
from .vector_store import SearchResult

logger = logging.getLogger(__name__)

_INDEX_NAME = "index.faiss"
_META_NAME = "store_meta.json"


class FaissPersistedVectorStore:
    """
    IndexFlatIP + 元数据 JSON；线程安全。嵌入维度或 embedding 后端与磁盘不一致时拒绝加载并清空损坏文件。
    """

    def __init__(
        self,
        index_dir: Path | str,
        embedder: Optional[Union[SentenceTransformerEmbedding, HashEmbedding]] = None,
    ) -> None:
        self.index_dir = Path(index_dir).expanduser().resolve()
        self._embedder = embedder or create_default_embedder()
        self._lock = threading.Lock()
        self._ids: List[str] = []
        self._texts: List[str] = []
        self._index = None  # faiss.IndexFlatIP | None
        self._dim: int | None = None
        self._cached_embed_dim: int | None = None

        import faiss  # noqa: PLC0415

        self._faiss = faiss
        self._load_if_exists()

    def _embedder_dim(self) -> int:
        if self._cached_embed_dim is None:
            v = self._embedder.encode(["."])
            if v.ndim != 2 or v.shape[0] != 1:
                raise RuntimeError("Expected single-row embedding for dim probe")
            self._cached_embed_dim = int(v.shape[1])
        return self._cached_embed_dim

    def _faiss_index_path(self) -> Path:
        return self.index_dir / _INDEX_NAME

    def _meta_path(self) -> Path:
        return self.index_dir / _META_NAME

    def _load_if_exists(self) -> None:
        index_path = self._faiss_index_path()
        meta_path = self._meta_path()
        if not index_path.is_file() or not meta_path.is_file():
            return

        try:
            raw = json.loads(meta_path.read_text(encoding="utf-8"))
            ids = list(raw.get("ids") or [])
            texts = list(raw.get("texts") or [])
            dim_meta = raw.get("dim")
            backend_meta = raw.get("embedding_backend")
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read vector meta %s: %s", meta_path, exc)
            self._unlink_store_files()
            return

        try:
            index = self._faiss.read_index(str(index_path))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read FAISS index %s: %s", index_path, exc)
            self._unlink_store_files()
            return

        ntotal = int(index.ntotal)
        if ntotal == 0:
            self._unlink_store_files()
            return

        if len(ids) != ntotal or len(texts) != ntotal:
            logger.warning("Meta row count mismatch (ids=%s index=%s); clearing store", len(ids), ntotal)
            self._unlink_store_files()
            return

        dim_now = self._embedder_dim()
        if dim_meta != dim_now or backend_meta != embedding_backend_label():
            logger.warning(
                "Persisted index incompatible with current embedder "
                "(disk dim=%s backend=%s vs now dim=%s backend=%s); clearing store",
                dim_meta,
                backend_meta,
                dim_now,
                embedding_backend_label(),
            )
            self._unlink_store_files()
            return

        self._ids = ids
        self._texts = texts
        self._index = index
        self._dim = dim_now

    def _unlink_store_files(self) -> None:
        for p in (self._faiss_index_path(), self._meta_path()):
            try:
                if p.is_file():
                    p.unlink()
            except OSError:
                pass

    @property
    def size(self) -> int:
        return len(self._ids)

    def _persist_unlocked(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        index_final = self._faiss_index_path()
        meta_final = self._meta_path()
        index_part = self.index_dir / f"{_INDEX_NAME}.part"
        meta_part = self.index_dir / f"{_META_NAME}.part"

        if self._index is None or self._index.ntotal == 0:
            self._unlink_store_files()
            return

        self._faiss.write_index(self._index, str(index_part))
        payload = {
            "ids": self._ids,
            "texts": self._texts,
            "dim": self._dim,
            "embedding_backend": embedding_backend_label(),
        }
        meta_part.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(index_part, index_final)
        os.replace(meta_part, meta_final)

    def clear(self) -> None:
        with self._lock:
            self._ids.clear()
            self._texts.clear()
            self._index = None
            self._dim = None
            self._persist_unlocked()

    def add_texts(self, texts: list[str]) -> list[str]:
        cleaned = [t.strip() for t in texts if t and t.strip()]
        if not cleaned:
            return []

        new_vectors = self._embedder.encode(cleaned)
        if new_vectors.ndim != 2 or new_vectors.shape[0] != len(cleaned):
            raise RuntimeError("Embedding shape mismatch")

        d = int(new_vectors.shape[1])
        vecs = np.ascontiguousarray(new_vectors.astype(np.float32, copy=False))
        new_ids = [str(uuid.uuid4()) for _ in cleaned]

        with self._lock:
            if self._index is None:
                self._dim = d
                self._index = self._faiss.IndexFlatIP(d)
            elif self._dim != d:
                raise ValueError("Embedding dimension mismatch; clear store before changing model")

            if self._index.ntotal != len(self._ids):
                raise RuntimeError("Inconsistent FAISS index state")

            self._index.add(vecs)
            self._ids.extend(new_ids)
            self._texts.extend(cleaned)
            self._persist_unlocked()

        return new_ids

    def add_document_bytes(self, *, filename: str, data: bytes) -> list[str]:
        plain = bytes_to_plain_text(filename=filename, data=data)
        chunks = chunk_plain_text(plain)
        return self.add_texts(chunks)

    def encode_query(self, query: str) -> np.ndarray:
        q = self._embedder.encode([query])
        if q.shape[0] != 1:
            raise RuntimeError("Expected single query vector")
        return q[0]

    def similarity_search(self, query: str, k: int = 4) -> list[SearchResult]:
        if k <= 0:
            return []
        q = self.encode_query(query)
        with self._lock:
            if self._index is None or self._index.ntotal == 0:
                return []
            index = self._index
            ids = list(self._ids)
            texts = list(self._texts)
            if int(q.shape[0]) != int(index.d):
                raise RuntimeError("Query embedding dimension mismatch")

            q32 = np.ascontiguousarray(q.astype(np.float32, copy=False).reshape(1, -1))
            k_eff = min(k, int(index.ntotal))
            scores, idx_labels = index.search(q32, k_eff)
            row_scores = scores[0]
            row_idx = idx_labels[0]
            out: list[SearchResult] = []
            for j in range(k_eff):
                i = int(row_idx[j])
                if i < 0:
                    continue
                out.append(SearchResult(chunk_id=ids[i], text=texts[i], score=float(row_scores[j])))
            return out
