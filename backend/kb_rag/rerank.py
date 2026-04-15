"""
LLM Rerank：对候选 passage 列表进行相关性打分并排序（Structured Output + Pydantic）。

不手写特征打分；由模型输出每条 passage 的 relevance，再据此重排。
"""

from __future__ import annotations

from typing import List, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field


class PassageScore(BaseModel):
    """单条候选的 LLM 相关性评分。"""

    index: int = Field(ge=0, description="候选在输入列表中的从 0 开始的下标")
    relevance: float = Field(ge=0.0, le=1.0, description="与当前用户问题的相关程度，越大越相关")


class RerankLLMOutput(BaseModel):
    """对一批 passage 的打分结果。"""

    scores: list[PassageScore] = Field(default_factory=list, description="覆盖所有给定 passage 的评分")


RERANK_SYSTEM = """你是检索重排序助手。给定用户问题与若干候选文本（带编号），请为每个候选评估与问题的相关性。
评分范围 0-1，越大越相关；必须对每个候选都给出一个 index 与 relevance。"""


def _build_passage_block(passages: Sequence[str]) -> str:
    lines: list[str] = []
    for i, p in enumerate(passages):
        body = p.strip().replace("\r\n", "\n")
        lines.append(f"[{i}]\n{body}")
    return "\n\n".join(lines)


def _fallback_order(n: int) -> list[int]:
    return list(range(n))


def _order_from_scores(n: int, scores: list[PassageScore]) -> list[int]:
    valid = [s for s in scores if 0 <= s.index < n]
    valid.sort(key=lambda s: (-s.relevance, s.index))
    used: set[int] = set()
    ordered: list[int] = []
    for s in valid:
        if s.index in used:
            continue
        ordered.append(s.index)
        used.add(s.index)
    for i in range(n):
        if i not in used:
            ordered.append(i)
    return ordered


async def rerank_passages(
    llm: BaseChatModel,
    *,
    question: str,
    passages: Sequence[str],
    top_n: int,
) -> list[int]:
    """
    返回按相关性从高到低排序的「原始下标」列表，长度不超过 top_n。

    passages 为空时返回 []；单条时直接 [0] 以节省调用。
    """
    texts = [p for p in passages if p is not None]
    n = len(texts)
    if n == 0:
        return []
    if n == 1:
        return [0]

    k = min(max(top_n, 1), n)
    structured = llm.with_structured_output(RerankLLMOutput)
    block = _build_passage_block(texts)
    messages = [
        SystemMessage(content=RERANK_SYSTEM),
        HumanMessage(
            content=(
                f"用户问题：\n{question.strip()}\n\n"
                f"候选 passage（共 {n} 条）：\n{block}\n\n"
                "请输出结构化字段 scores：对每个下标 0..n-1 给出 relevance。"
            )
        ),
    ]

    try:
        parsed: RerankLLMOutput | None = await structured.ainvoke(messages)
    except Exception:
        parsed = None

    if not parsed or not parsed.scores:
        return _fallback_order(n)[:k]

    ordered = _order_from_scores(n, parsed.scores)
    return ordered[:k]


def rerank_passages_sync(
    llm: BaseChatModel,
    *,
    question: str,
    passages: Sequence[str],
    top_n: int,
) -> list[int]:
    """同步版 rerank。"""
    texts = [p for p in passages if p is not None]
    n = len(texts)
    if n == 0:
        return []
    if n == 1:
        return [0]

    k = min(max(top_n, 1), n)
    structured = llm.with_structured_output(RerankLLMOutput)
    block = _build_passage_block(texts)
    messages = [
        SystemMessage(content=RERANK_SYSTEM),
        HumanMessage(
            content=(
                f"用户问题：\n{question.strip()}\n\n"
                f"候选 passage（共 {n} 条）：\n{block}\n\n"
                "请输出结构化字段 scores：对每个下标 0..n-1 给出 relevance。"
            )
        ),
    ]

    try:
        parsed: RerankLLMOutput | None = structured.invoke(messages)
    except Exception:
        parsed = None

    if not parsed or not parsed.scores:
        return _fallback_order(n)[:k]

    ordered = _order_from_scores(n, parsed.scores)
    return ordered[:k]
