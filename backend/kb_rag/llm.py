"""
为 RAG 相关步骤提供默认的聊天模型构造方法（multi-query、rerank、后续 Agent）。

默认对接 **DeepSeek**（OpenAI 兼容 HTTPS）：设置 OPENAI_BASE_URL + DEEPSEEK_API_KEY（或 OPENAI_API_KEY）即可。
也支持官方 OpenAI 或其它兼容网关；模型名须与当前 Base URL 匹配。
"""

from __future__ import annotations

import os
from typing import Any

from langchain_openai import ChatOpenAI


def _resolve_openai_compatible_base_url() -> str | None:
    """
    兼容网关地址：支持 OPENAI_BASE_URL（与 OpenAI 官方 SDK 一致）或 OPENAI_API_BASE（旧名）。
    去掉末尾斜杠，避免与路径拼接时出现双斜杠。
    """
    for key in ("OPENAI_BASE_URL", "OPENAI_API_BASE"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v.rstrip("/")
    return None


def _ensure_openai_api_key_from_aliases() -> None:
    """
    若未设置 OPENAI_API_KEY，则按顺序用别名写入，供 OpenAI SDK / LangChain 读取：

    DEEPSEEK_API_KEY → CHATGPT_API_KEY → CHATGPT_KEY
    """
    current = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if current:
        return
    for name in ("DEEPSEEK_API_KEY", "CHATGPT_API_KEY", "CHATGPT_KEY"):
        alt = (os.environ.get(name) or "").strip()
        if alt:
            os.environ["OPENAI_API_KEY"] = alt
            return


def openai_chat_env_status() -> dict[str, bool]:
    """
    供 /health 排查：不暴露密钥，仅表示是否已配置非空 Key 与兼容网关 Base URL。
    """
    _ensure_openai_api_key_from_aliases()
    return {
        "openai_api_key_configured": bool((os.environ.get("OPENAI_API_KEY") or "").strip()),
        "deepseek_api_key_in_env": bool((os.environ.get("DEEPSEEK_API_KEY") or "").strip()),
        "openai_compatible_base_url_configured": bool(_resolve_openai_compatible_base_url()),
    }


def _default_chat_model_for_env(*, resolved_base: str | None = None) -> str:
    """未显式传 model 时：按 Base URL 推断 DeepSeek，否则用官方默认 gpt-3.5-turbo。"""
    env_model = (os.environ.get("OPENAI_MODEL") or "").strip()
    if env_model:
        return env_model
    b = (resolved_base or _resolve_openai_compatible_base_url() or "").lower()
    if "deepseek" in b:
        return "deepseek-chat"
    return "gpt-3.5-turbo"


def create_rag_chat_model(**kwargs: Any) -> ChatOpenAI:
    """
    创建用于检索增强的 ChatOpenAI 实例（temperature 默认 0 以提高稳定性）。

    常用环境变量：
    - **OPENAI_BASE_URL**：默认 DeepSeek 为 ``https://api.deepseek.com/v1``（见 .env.example）
    - **OPENAI_API_KEY** 或 **DEEPSEEK_API_KEY**（及 CHATGPT_* 别名，会写入 OPENAI_API_KEY）
    - **OPENAI_MODEL**：不设且 Base 为 DeepSeek 时默认 ``deepseek-chat``
    """
    _ensure_openai_api_key_from_aliases()
    merged: dict[str, Any] = {"temperature": 0}
    merged.update(kwargs)
    base = _resolve_openai_compatible_base_url()
    if not base and (os.environ.get("DEEPSEEK_API_KEY") or "").strip():
        base = "https://api.deepseek.com/v1"
    if base and merged.get("base_url") is None and merged.get("openai_api_base") is None:
        merged["base_url"] = base.rstrip("/")
    if "model" not in merged:
        merged["model"] = _default_chat_model_for_env(resolved_base=base)
    # 显式传入 api_key，避免仅依赖进程环境时部分路径未执行别名或 env 被占空
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if api_key and merged.get("api_key") is None:
        merged["api_key"] = api_key
    return ChatOpenAI(**merged)
