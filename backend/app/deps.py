"""
FastAPI 依赖：进程级单例向量库与聊天模型，避免每次请求重复加载 embedding 模型。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel

from kb_rag import create_rag_chat_model
from kb_rag.faiss_store import FaissPersistedVectorStore
from kb_rag.vector_store import RAGVectorStore

_BACKEND_ROOT = Path(__file__).resolve().parent.parent

_vector_store: RAGVectorStore | None = None


def _default_faiss_index_dir() -> Path:
    raw = (os.environ.get("RAG_FAISS_INDEX_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (_BACKEND_ROOT / "data" / "indexes" / "default").resolve()


def get_vector_store() -> RAGVectorStore:
    """返回进程内共享的 FAISS 持久化向量库（启动时加载磁盘索引）。"""
    global _vector_store
    if _vector_store is None:
        _vector_store = FaissPersistedVectorStore(_default_faiss_index_dir())
    return _vector_store


@lru_cache(maxsize=1)
def get_chat_model() -> BaseChatModel:
    """返回进程内缓存的 Chat 模型（用于 Agent / 结构化 / 流式）。"""
    return create_rag_chat_model()
