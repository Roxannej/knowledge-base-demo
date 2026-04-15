"""
内存向量库：存储 chunk 文本与对应 embedding，使用余弦相似度（归一化后点积）检索 Top-K。
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import List, Optional, Union

import numpy as np

from .chunking import chunk_plain_text
from .document_loader import bytes_to_plain_text
from .embeddings import HashEmbedding, SentenceTransformerEmbedding, create_default_embedder


@dataclass(frozen=True)
class SearchResult:
    """单次向量检索命中项。"""

    chunk_id: str
    text: str
    score: float


def _top_k_indices(scores: np.ndarray, k: int) -> np.ndarray:
    k = min(k, int(scores.shape[0]))
    if k <= 0:
        return np.array([], dtype=np.int64)
    # argpartition 避免全量排序
    if k == scores.shape[0]:
        return np.argsort(-scores)
    partition = np.argpartition(-scores, kth=k - 1)[:k]
    order = np.argsort(-scores[partition])
    return partition[order]


class InMemoryVectorStore:
    """
    进程内向量库：追加写入、按查询向量检索；线程安全（简单互斥锁）。

    向量均为 L2 归一化，score = cosine_similarity(query, doc) = dot(q, d)。
    """

    def __init__(
        self,
        embedder: Optional[Union[SentenceTransformerEmbedding, HashEmbedding]] = None,
    ) -> None:
        self._embedder = embedder or create_default_embedder()
        self._lock = threading.Lock()
        self._ids: List[str] = []
        self._texts: List[str] = []
        self._matrix: Optional[np.ndarray] = None  # shape (n, d), float32, row-normalized

    @property
    def size(self) -> int:
        return len(self._ids)

    def clear(self) -> None:
        with self._lock:
            self._ids.clear()
            self._texts.clear()
            self._matrix = None

    def add_texts(self, texts: list[str]) -> list[str]:
        """对一批纯文本 chunk 编码并入库，返回 chunk_id 列表。"""
        cleaned = [t.strip() for t in texts if t and t.strip()]
        if not cleaned:
            return []

        new_vectors = self._embedder.encode(cleaned)
        if new_vectors.ndim != 2 or new_vectors.shape[0] != len(cleaned):
            raise RuntimeError("Embedding shape mismatch")

        new_ids = [str(uuid.uuid4()) for _ in cleaned]

        with self._lock:
            self._ids.extend(new_ids)
            self._texts.extend(cleaned)
            if self._matrix is None:
                self._matrix = new_vectors
            else:
                if self._matrix.shape[1] != new_vectors.shape[1]:
                    raise ValueError("Embedding dimension mismatch; clear store before changing model")
                self._matrix = np.vstack([self._matrix, new_vectors])

        return new_ids

    def add_document_bytes(self, *, filename: str, data: bytes) -> list[str]:
        """解析上传文件 → 语义分块 → 入库（供 /upload 使用）。"""
        plain = bytes_to_plain_text(filename=filename, data=data)
        chunks = chunk_plain_text(plain)
        return self.add_texts(chunks)

    def encode_query(self, query: str) -> np.ndarray:
        """将单条查询编码为 (d,) 的归一化向量。"""
        q = self._embedder.encode([query])
        if q.shape[0] != 1:
            raise RuntimeError("Expected single query vector")
        return q[0]

    def similarity_search(self, query: str, k: int = 4) -> list[SearchResult]:
        """对查询文本编码后，与库内向量做余弦相似度检索。"""
        if k <= 0:
            return []
        with self._lock:
            if not self._ids or self._matrix is None or self._matrix.shape[0] == 0:
                return []
            matrix = self._matrix
            ids = list(self._ids)
            texts = list(self._texts)

        q = self.encode_query(query)
        if q.shape[0] != matrix.shape[1]:
            raise RuntimeError("Query embedding dimension mismatch")

        scores = matrix @ q  # (n,)
        idx = _top_k_indices(scores, k)
        return [
            SearchResult(chunk_id=ids[int(i)], text=texts[int(i)], score=float(scores[int(i)]))
            for i in idx
        ]
