"""
输出侧 Guardrails：结构校验与引用完整性检查。
"""

from __future__ import annotations

import re
from typing import Any, Literal

from schemas.rag_answer import RAGStructuredAnswer

from .exceptions import GuardrailViolation

GuardrailMode = Literal["strict", "relaxed"]


def validate_structured_output(
    payload: RAGStructuredAnswer | dict[str, Any],
    *,
    mode: GuardrailMode = "relaxed",
) -> RAGStructuredAnswer:
    """
    校验最终输出结构与引用质量。
    relaxed：尽量降级修复；strict：严格拒绝不合规输出。
    """
    answer = (
        payload
        if isinstance(payload, RAGStructuredAnswer)
        else RAGStructuredAnswer.model_validate(payload)
    )

    cleaned_sources = [s.strip() for s in answer.sources if (s or "").strip()]
    answer = answer.model_copy(update={"sources": cleaned_sources})

    citation_ids = [int(n) for n in re.findall(r"\[(\d+)\]", answer.answer)]
    max_citation = max(citation_ids) if citation_ids else 0
    if max_citation > len(answer.sources):
        raise GuardrailViolation(
            f"引用编号超过 sources 数量：最大 [{max_citation}]，sources 仅 {len(answer.sources)} 条。"
        )

    no_sources = len(answer.sources) == 0
    long_answer = len(answer.answer.strip()) >= 80
    if no_sources and long_answer:
        if mode == "strict":
            raise GuardrailViolation("严格模式要求长回答必须提供可追溯来源。")
        answer = answer.model_copy(update={"confidence": min(answer.confidence, 0.35)})

    if mode == "strict":
        too_short_sources = [s for s in answer.sources if len(s) < 6]
        if too_short_sources:
            raise GuardrailViolation("严格模式下 sources 存在过短片段，无法提供有效引用。")

    return answer

