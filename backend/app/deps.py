"""
FastAPI 依赖：进程级单例向量库与聊天模型，避免每次请求重复加载 embedding 模型。
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel

from kb_rag import InMemoryVectorStore, create_rag_chat_model

_vector_store: InMemoryVectorStore | None = None


def get_vector_store() -> InMemoryVectorStore:
    """返回进程内共享的内存向量库。"""
    global _vector_store
    if _vector_store is None:
        _vector_store = InMemoryVectorStore()
    return _vector_store


@lru_cache(maxsize=1)
def get_chat_model() -> BaseChatModel:
    """返回进程内缓存的 Chat 模型（用于 Agent / 结构化 / 流式）。"""
    return create_rag_chat_model()
