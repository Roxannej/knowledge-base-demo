"""
FastAPI 依赖：进程级单例向量库与聊天模型，避免每次请求重复加载 embedding 模型。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel

from kb_rag import create_rag_chat_model
from kb_rag.index_manager import IndexManager, IndexNotFoundError
from kb_rag.vector_store import RAGVectorStore

_BACKEND_ROOT = Path(__file__).resolve().parent.parent

_index_manager: IndexManager | None = None


def _default_faiss_root_dir() -> Path:
    raw = (os.environ.get("RAG_FAISS_INDEX_ROOT") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    legacy = (os.environ.get("RAG_FAISS_INDEX_DIR") or "").strip()
    if legacy:
        return Path(legacy).expanduser().resolve().parent
    return (_BACKEND_ROOT / "data" / "indexes").resolve()


def get_index_manager() -> IndexManager:
    """返回进程内共享的索引管理器。"""
    global _index_manager
    if _index_manager is None:
        _index_manager = IndexManager(_default_faiss_root_dir())
    return _index_manager


def get_vector_store(index_name: str = "default") -> RAGVectorStore:
    """返回指定索引名的向量库实例（默认 default）。"""
    manager = get_index_manager()
    try:
        return manager.get_store(index_name)
    except IndexNotFoundError as exc:
        raise ValueError(str(exc)) from exc


@lru_cache(maxsize=1)
def get_chat_model() -> BaseChatModel:
    """返回进程内缓存的 Chat 模型（用于 Agent / 结构化 / 流式）。"""
    return create_rag_chat_model()
