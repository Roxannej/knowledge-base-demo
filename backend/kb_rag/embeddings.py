"""
sentence-transformers 封装：将文本编码为向量，并做 L2 归一化以便用点积等价于余弦相似度。

依赖在首次编码时才加载（延迟 import），避免未安装 torch/sentence-transformers 时 FastAPI 无法启动。

若本机未安装 torch / sentence-transformers，则 `create_default_embedder()` 自动使用仅 numpy 的
`HashEmbedding`（弱语义，仅保证上传与检索接口可跑通；生产请安装完整依赖）。
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from typing import TYPE_CHECKING, Any, Optional, Union

import numpy as np

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

# 体量较小、速度较快，适合演示；可按需通过构造参数替换
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# 与 all-MiniLM-L6-v2 维度一致，便于以后切换后端时减少「混维度」踩坑
HASH_EMBEDDING_DIM = 384


def _sentence_transformers_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        return False
    return True


def embedding_backend_label() -> str:
    """供 /health 展示当前会选用的编码后端（与 create_default_embedder 逻辑一致）。"""
    raw = (os.environ.get("RAG_FORCE_HASH_EMBEDDINGS") or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return "hash-fallback"
    if _sentence_transformers_available():
        return "sentence-transformers"
    return "hash-fallback"


class HashEmbedding:
    """
    仅依赖 numpy：字符/词级哈希到固定维度，L2 归一化。

    无语义检索质量，用于未安装 torch 与 sentence-transformers 时的开发演示。
    """

    def encode(
        self,
        texts: list[str],
        *,
        batch_size: int = 32,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        _ = batch_size, show_progress_bar
        if not texts:
            return np.zeros((0, HASH_EMBEDDING_DIM), dtype=np.float32)
        rows = [self._encode_one(t) for t in texts]
        return np.stack(rows, axis=0)

    def _encode_one(self, text: str) -> np.ndarray:
        v = np.zeros(HASH_EMBEDDING_DIM, dtype=np.float32)
        t = (text or "").strip()
        if not t:
            v[0] = 1.0
            return v
        data = t.encode("utf-8", errors="ignore")
        for win in (8, 16, 32, 64):
            step = max(1, win // 2)
            for i in range(0, len(data), step):
                chunk = data[i : i + win]
                if not chunk:
                    continue
                h = int.from_bytes(hashlib.sha256(chunk).digest()[:8], "little", signed=False)
                v[h % HASH_EMBEDDING_DIM] += 1.0
        for tok in re.findall(r"[\w\u4e00-\u9fff]+", t):
            h = int.from_bytes(hashlib.sha256(tok.encode("utf-8")).digest()[:8], "little", signed=False)
            v[(h // 7) % HASH_EMBEDDING_DIM] += 0.25
        n = float(np.linalg.norm(v))
        if n < 1e-9:
            v[0] = 1.0
        else:
            v /= n
        return v.astype(np.float32, copy=False)


def create_default_embedder() -> Union[SentenceTransformerEmbedding, HashEmbedding]:
    if embedding_backend_label() == "hash-fallback":
        return HashEmbedding()
    return SentenceTransformerEmbedding()


class SentenceTransformerEmbedding:
    """
    懒加载本地 SentenceTransformer 模型，避免在 import 阶段拉取权重。

    encode() 默认返回 float32 的 (n, d) 矩阵，且行向量已 L2 归一化。
    """

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL) -> None:
        self.model_name = model_name
        self._model: Optional[Any] = None
        self._lock = threading.Lock()

    def _ensure_model(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    try:
                        from sentence_transformers import SentenceTransformer
                    except ImportError as exc:  # pragma: no cover
                        raise RuntimeError(
                            "未安装 sentence-transformers / torch。请在 backend 虚拟环境中执行："
                            " pip install -r requirements.txt"
                        ) from exc
                    self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(
        self,
        texts: list[str],
        *,
        batch_size: int = 32,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        model = self._ensure_model()
        vectors = model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=show_progress_bar,
        )
        out = np.asarray(vectors, dtype=np.float32)
        return out
