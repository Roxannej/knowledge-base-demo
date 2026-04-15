"""
Agent 可调用的工具定义。

search_docs 由大模型通过 **function calling** 触发（bind_tools），应用层不根据用户原文手写
`if tool == ...` 来选择工具；工具路由交给 LangGraph + ToolNode 处理。
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import tool

from kb_rag.retrieval import retrieve_with_multiquery_rerank
from kb_rag.vector_store import InMemoryVectorStore


def build_search_docs_tool(
    store: InMemoryVectorStore,
    llm: BaseChatModel,
    *,
    max_alternates: int = 4,
    per_query_k: int = 6,
    max_candidates: int = 16,
    rerank_top_n: int = 4,
):
    """
    构造绑定向量库与 LLM 的 search_docs 工具（闭包捕获 store / llm）。

    内部走 multi-query + 向量 cosine 召回 + LLM rerank，与 RAG 流水线一致。
    """

    @tool
    async def search_docs(query: str) -> str:
        """
        在已上传的文档中检索与查询语义相关的原文片段。

        适用：需要引用文档事实、数据、表格或条款时再调用；传入简短、具体的检索 query。
        """
        q = (query or "").strip()
        if not q:
            return "（search_docs）查询为空，请提供非空关键词或问题短语。"

        if store.size == 0:
            return "（search_docs）当前知识库为空，请先上传文档。"

        hits = await retrieve_with_multiquery_rerank(
            store,
            llm,
            q,
            max_alternates=max_alternates,
            per_query_k=per_query_k,
            max_candidates=max_candidates,
            rerank_top_n=rerank_top_n,
        )
        if not hits:
            return "（search_docs）未找到与查询足够相关的片段。"

        blocks: list[str] = []
        for i, h in enumerate(hits, start=1):
            blocks.append(
                f"[{i}] chunk_id={h.chunk_id} embedding_score={h.score:.4f}\n{h.text.strip()}"
            )
        return "\n\n---\n\n".join(blocks)

    return search_docs
