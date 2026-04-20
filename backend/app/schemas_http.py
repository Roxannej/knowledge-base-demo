"""
HTTP 层请求/响应模型（与业务 schemas 区分，避免与 RAG 结构化输出混淆）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


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
