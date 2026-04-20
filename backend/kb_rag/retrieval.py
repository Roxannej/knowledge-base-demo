"""
串联检索：multi-query 向量召回 → 去合并集 → LLM rerank，供 Agent 或 API 直接调用。
"""

from __future__ import annotations

from typing import Dict, List

from langchain_core.language_models.chat_models import BaseChatModel

from .multi_query import generate_multi_queries
from .rerank import rerank_passages
from .vector_store import RAGVectorStore, SearchResult


async def retrieve_with_multiquery_rerank(
    store: RAGVectorStore,
    llm: BaseChatModel,
    question: str,
    *,
    max_alternates: int = 4,
    per_query_k: int = 6,
    max_candidates: int = 16,
    rerank_top_n: int = 4,
) -> list[SearchResult]:
    """
    1) LLM 生成多查询；2) 各查询做 cosine 检索；3) 按 chunk_id 合并保留最高向量分；
    4) 截断为 max_candidates；5) LLM rerank 取 rerank_top_n。
    """
    queries = await generate_multi_queries(llm, question, max_alternates=max_alternates)
    merged: Dict[str, SearchResult] = {}
    for q in queries:
        hits = store.similarity_search(q, k=per_query_k)
        for h in hits:
            prev = merged.get(h.chunk_id)
            if prev is None or h.score > prev.score:
                merged[h.chunk_id] = h

    candidates = sorted(merged.values(), key=lambda r: -r.score)[:max_candidates]
    if not candidates:
        return []

    passages: List[str] = [c.text for c in candidates]
    order = await rerank_passages(
        llm,
        question=question,
        passages=passages,
        top_n=min(rerank_top_n, len(passages)),
    )
    return [candidates[i] for i in order]
