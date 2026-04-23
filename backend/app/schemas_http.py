"""
HTTP 层请求/响应模型（与业务 schemas 区分，避免与 RAG 结构化输出混淆）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RetrievalStrategy = Literal["similarity", "mmr", "score_threshold", "hybrid"]
WorkflowMode = Literal["agent", "task"]
GuardrailMode = Literal["strict", "relaxed"]


class ChatRequest(BaseModel):
    """聊天请求体。"""

    message: str = Field(min_length=1, description="用户问题")


class CreateIndexRequest(BaseModel):
    """创建索引请求体。"""

    name: str = Field(
        min_length=1,
        max_length=64,
        description="索引名称，仅允许字母、数字、下划线和中划线",
    )
    description: str = Field(default="", max_length=500, description="索引描述")


class IndexResponse(BaseModel):
    """索引元数据响应。"""

    name: str
    description: str = ""
    document_count: int = Field(ge=0)
    updated_at: str


class RetrievalOptions(BaseModel):
    """检索策略参数（Day 3）。"""

    strategy: RetrievalStrategy = Field(default="similarity")
    score_threshold: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="score_threshold 策略使用的最小相似度阈值",
    )
    mmr_lambda: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description="MMR 中 query 相关性权重（越高越偏相关性）",
    )
    hybrid_alpha: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="hybrid 策略里 similarity 与 mmr 的融合权重",
    )
