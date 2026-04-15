"""
RAG 最终对外结构化输出：Markdown 回答、置信度、引用片段列表。

供 LangChain `with_structured_output` 与 Pydantic 二次校验使用。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class RAGStructuredAnswer(BaseModel):
    """符合 API 契约的结构化回答。"""

    answer: str = Field(
        ...,
        min_length=1,
        description="面向用户的最终回答，使用 Markdown 格式。",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="对「回答与引用依据一致」的主观置信度，0-1。",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="来自检索文档的简短原文引用片段列表；无可靠依据时可为空。",
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v: Any) -> float:
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            return float(v.strip())
        raise TypeError("confidence 必须为数字")

    @field_validator("answer")
    @classmethod
    def _answer_not_blank(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("answer 不能为空或仅空白")
        return v

    @field_validator("sources", mode="before")
    @classmethod
    def _normalize_sources(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            raise TypeError("sources 必须为字符串列表")
        out: list[str] = []
        for item in v:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                out.append(s)
        return out
