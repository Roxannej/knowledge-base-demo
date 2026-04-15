"""
流式场景下使用的「元数据」结构化模型：仅 confidence + sources。

最终对外仍组装为 `RAGStructuredAnswer`（answer 来自流式累积的正文）。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class RAGAnswerMetadata(BaseModel):
    """与流式生成的 Markdown 正文配套的元数据。"""

    confidence: float = Field(ge=0.0, le=1.0, description="0-1 置信度")
    sources: list[str] = Field(default_factory=list, description="文档引用片段")

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v: Any) -> float:
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            return float(v.strip())
        raise TypeError("confidence 必须为数字")

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
