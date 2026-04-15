"""
HTTP 层请求/响应模型（与业务 schemas 区分，避免与 RAG 结构化输出混淆）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """聊天请求体。"""

    message: str = Field(min_length=1, description="用户问题")
