"""
串联检索：multi-query 向量召回 → 去合并集 → LLM rerank，供 Agent 或 API 直接调用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal

import numpy as np
from langchain_core.language_models.chat_models import BaseChatModel

from .multi_query import generate_multi_queries
from .rerank import rerank_passages
from .vector_store import RAGVectorStore, SearchResult

RetrievalStrategy = Literal["similarity", "mmr", "score_threshold", "hybrid"]


@dataclass(frozen=True)
class RetrievalConfig:
    strategy: RetrievalStrategy = "similarity"
    score_threshold: float = 0.25
    mmr_lambda: float = 0.65
    mmr_fetch_k: int = 24
    hybrid_alpha: float = 0.6


@dataclass(frozen=True)
class RetrievalDebugInfo:
    strategy: RetrievalStrategy
    query_count: int
    merged_candidates: int
    threshold_filtered: int
    rerank_input: int
    rerank_output: int
    hybrid_alpha: float | None = None


def _mmr_pick(
    *,
    store: RAGVectorStore,
    query: str,
    candidates: list[SearchResult],
    limit: int,
    lambda_mult: float,
) -> list[SearchResult]:
    if not candidates or limit <= 0:
        return []

    q_vec = store.encode_query(query)
    cand_vecs = np.stack([store.encode_query(c.text) for c in candidates], axis=0)
    query_scores = cand_vecs @ q_vec

    remaining = list(range(len(candidates)))
    selected: list[int] = []
    cap = min(limit, len(remaining))
    while remaining and len(selected) < cap:
        best_idx = None
        best_score = -float("inf")
        for idx in remaining:
            if not selected:
                diversity_penalty = 0.0
            else:
                sim_to_selected = cand_vecs[selected] @ cand_vecs[idx]
                diversity_penalty = float(np.max(sim_to_selected))
            score = float(lambda_mult * query_scores[idx] - (1.0 - lambda_mult) * diversity_penalty)
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_idx is None:
            break
        selected.append(best_idx)
        remaining.remove(best_idx)

    return [candidates[i] for i in selected]


def _run_single_query(
    store: RAGVectorStore,
    query: str,
    *,
    per_query_k: int,
    cfg: RetrievalConfig,
) -> tuple[list[SearchResult], int]:
    if cfg.strategy == "mmr":
        raw_hits = store.similarity_search(query, k=max(per_query_k, cfg.mmr_fetch_k))
        return (
            _mmr_pick(
                store=store,
                query=query,
                candidates=raw_hits,
                limit=per_query_k,
                lambda_mult=cfg.mmr_lambda,
            ),
            0,
        )
    if cfg.strategy == "score_threshold":
        raw_hits = store.similarity_search(query, k=max(per_query_k * 3, per_query_k))
        filtered = [h for h in raw_hits if h.score >= cfg.score_threshold][:per_query_k]
        return filtered, max(0, len(raw_hits) - len(filtered))
    if cfg.strategy == "hybrid":
        base = store.similarity_search(query, k=per_query_k)
        base_rank: dict[str, int] = {x.chunk_id: i for i, x in enumerate(base)}
        mmr = _mmr_pick(
            store=store,
            query=query,
            candidates=store.similarity_search(query, k=max(per_query_k, cfg.mmr_fetch_k)),
            limit=per_query_k,
            lambda_mult=cfg.mmr_lambda,
        )
        mmr_rank: dict[str, int] = {x.chunk_id: i for i, x in enumerate(mmr)}
        by_id: Dict[str, SearchResult] = {x.chunk_id: x for x in [*base, *mmr]}
        all_ids = list(by_id.keys())
        max_base_rank = max(len(base), 1)
        max_mmr_rank = max(len(mmr), 1)

        def _normalized_rank_score(rank_pos: int, rank_size: int) -> float:
            return 1.0 - (rank_pos / max(rank_size, 1))

        alpha = min(max(cfg.hybrid_alpha, 0.0), 1.0)
        blended: list[tuple[float, SearchResult]] = []
        for cid in all_ids:
            bpos = base_rank.get(cid, max_base_rank)
            mpos = mmr_rank.get(cid, max_mmr_rank)
            s_base = _normalized_rank_score(bpos, max_base_rank)
            s_mmr = _normalized_rank_score(mpos, max_mmr_rank)
            score = alpha * s_base + (1.0 - alpha) * s_mmr
            blended.append((score, by_id[cid]))

        blended.sort(key=lambda x: -x[0])
        return [item for _, item in blended[:per_query_k]], 0
    return store.similarity_search(query, k=per_query_k), 0


async def retrieve_with_multiquery_rerank(
    store: RAGVectorStore,
    llm: BaseChatModel,
    question: str,
    *,
    max_alternates: int = 4,
    per_query_k: int = 6,
    max_candidates: int = 16,
    rerank_top_n: int = 4,
    retrieval_config: RetrievalConfig | None = None,
) -> list[SearchResult]:
    hits, _ = await retrieve_with_multiquery_rerank_debug(
        store,
        llm,
        question,
        max_alternates=max_alternates,
        per_query_k=per_query_k,
        max_candidates=max_candidates,
        rerank_top_n=rerank_top_n,
        retrieval_config=retrieval_config,
    )
    return hits


async def retrieve_with_multiquery_rerank_debug(
    store: RAGVectorStore,
    llm: BaseChatModel,
    question: str,
    *,
    max_alternates: int = 4,
    per_query_k: int = 6,
    max_candidates: int = 16,
    rerank_top_n: int = 4,
    retrieval_config: RetrievalConfig | None = None,
) -> tuple[list[SearchResult], RetrievalDebugInfo]:
    """
    1) LLM 生成多查询；2) 各查询做 cosine 检索；3) 按 chunk_id 合并保留最高向量分；
    4) 截断为 max_candidates；5) LLM rerank 取 rerank_top_n。
    """
    cfg = retrieval_config or RetrievalConfig()
    queries = await generate_multi_queries(llm, question, max_alternates=max_alternates)
    merged: Dict[str, SearchResult] = {}
    threshold_filtered = 0
    for q in queries:
        hits, filtered = _run_single_query(
            store,
            q,
            per_query_k=per_query_k,
            cfg=cfg,
        )
        threshold_filtered += filtered
        for h in hits:
            prev = merged.get(h.chunk_id)
            if prev is None or h.score > prev.score:
                merged[h.chunk_id] = h

    candidates = sorted(merged.values(), key=lambda r: -r.score)[:max_candidates]
    if not candidates:
        return [], RetrievalDebugInfo(
            strategy=cfg.strategy,
            query_count=len(queries),
            merged_candidates=0,
            threshold_filtered=threshold_filtered,
            rerank_input=0,
            rerank_output=0,
            hybrid_alpha=cfg.hybrid_alpha if cfg.strategy == "hybrid" else None,
        )

    passages: List[str] = [c.text for c in candidates]
    order = await rerank_passages(
        llm,
        question=question,
        passages=passages,
        top_n=min(rerank_top_n, len(passages)),
    )
    final_hits = [candidates[i] for i in order]
    return final_hits, RetrievalDebugInfo(
        strategy=cfg.strategy,
        query_count=len(queries),
        merged_candidates=len(merged),
        threshold_filtered=threshold_filtered,
        rerank_input=len(passages),
        rerank_output=len(final_hits),
        hybrid_alpha=cfg.hybrid_alpha if cfg.strategy == "hybrid" else None,
    )
