"""
Multi-query：由 LLM 生成多条改写查询，用于缓解单一表述与向量库语义不匹配的问题。

使用 Pydantic Structured Output（LangChain with_structured_output），不做手写关键词规则。
"""

from __future__ import annotations

from typing import List, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field


class MultiQuerySpec(BaseModel):
    """LLM 输出的多查询结构。"""

    alternate_queries: list[str] = Field(
        default_factory=list,
        description="2-5 条与原始问题语义等价或互补的简短检索查询，适合向量检索；不要解释，不要编号前缀。",
    )


MULTI_QUERY_SYSTEM = """你是检索查询改写助手。根据用户问题，生成若干条简短、可用于向量检索的查询变体。
要求：覆盖不同措辞与同义词；不要输出推理过程；每条一行语义完整；使用与用户问题相同的语言为主。"""


def _dedupe_preserve_order(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        key = it.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it.strip())
    return out


async def generate_multi_queries(
    llm: BaseChatModel,
    user_question: str,
    *,
    max_alternates: int = 4,
) -> list[str]:
    """
    返回「原始问题 + 若干改写」，已去重；LLM 不可用时回退为仅原始问题。

    :param max_alternates: 改写条数上限（不含原问题）
    """
    question = user_question.strip()
    if not question:
        return []

    structured = llm.with_structured_output(MultiQuerySpec)
    messages = [
        SystemMessage(content=MULTI_QUERY_SYSTEM),
        HumanMessage(
            content=f"用户问题：\n{question}\n\n请生成改写查询（结构化字段 alternate_queries）。"
        ),
    ]

    try:
        parsed: MultiQuerySpec | None = await structured.ainvoke(messages)
    except Exception:
        parsed = None

    alternates: List[str] = []
    if parsed:
        alternates = [q.strip() for q in parsed.alternate_queries if q.strip()]
    alternates = alternates[:max_alternates]

    combined = _dedupe_preserve_order([question, *alternates])
    return combined if combined else [question]


def generate_multi_queries_sync(
    llm: BaseChatModel,
    user_question: str,
    *,
    max_alternates: int = 4,
) -> list[str]:
    """同步版本，便于脚本或非 async 环境调试。"""
    question = user_question.strip()
    if not question:
        return []

    structured = llm.with_structured_output(MultiQuerySpec)
    messages = [
        SystemMessage(content=MULTI_QUERY_SYSTEM),
        HumanMessage(
            content=f"用户问题：\n{question}\n\n请生成改写查询（结构化字段 alternate_queries）。"
        ),
    ]

    try:
        parsed: MultiQuerySpec | None = structured.invoke(messages)
    except Exception:
        parsed = None

    alternates = []
    if parsed:
        alternates = [q.strip() for q in parsed.alternate_queries if q.strip()]
    alternates = alternates[:max_alternates]

    combined = _dedupe_preserve_order([question, *alternates])
    return combined if combined else [question]
