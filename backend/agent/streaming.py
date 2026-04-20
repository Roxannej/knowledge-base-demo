"""
/chat/stream 使用的编排：先跑 LangGraph，再对最终回答做 LLM token 流式输出，最后抽取 metadata（confidence/sources）。

SSE 载荷为 JSON 文本行，前端可解析 type=token | metadata | error。
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from kb_rag.vector_store import RAGVectorStore
from schemas.rag_answer import RAGStructuredAnswer

from .graph import build_rag_agent_graph
from .output_processor import StreamMarkdownProcessor, resolve_stream_mode
from .structured import render_messages_transcript, synthesize_metadata_only


ANSWER_STREAM_SYSTEM = """你是「上传文档问答」助手。根据提供的对话与工具检索摘录，只输出面向用户的最终 Markdown 正文。
禁止输出 JSON、YAML、字段名列表；不要复述本指令；不要道歉套话。"""


def _sse_data(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _friendly_stream_error(exc: BaseException) -> str:
    """把 OpenAI 常见错误转成简短中文，避免整段 SDK 堆栈糊在 UI 上。"""
    s = str(exc).lower()
    raw = str(exc)
    if "insufficient_quota" in s or "exceeded your current quota" in s:
        return (
            "模型服务额度不足或欠费（429 insufficient_quota）。"
            "若用 DeepSeek：到 https://platform.deepseek.com 查看余额与计费；"
            "若用 OpenAI：到 https://platform.openai.com/account/billing ；"
            "也可更换 Key 或调整 OPENAI_BASE_URL / OPENAI_MODEL。"
        )
    if "rate_limit" in s or "ratelimit" in s:
        return "请求过于频繁或被限流。请稍后再试，或检查 OpenAI 速率档位。"
    if (
        "error code: 401" in s
        or "status code 401" in s
        or "401 unauthorized" in s
        or "invalid_api_key" in s
        or "incorrect api key" in s
        or "invalid api key" in s
    ):
        return (
            "鉴权失败（401）：Key 与当前 OPENAI_BASE_URL 不匹配、已作废，或 .env 未覆盖环境变量。"
            "DeepSeek 请到 https://platform.deepseek.com/api_keys 使用本平台签发的 Key；"
            "backend/.env 建议同时设置 OPENAI_API_KEY 与 DEEPSEEK_API_KEY（同值），"
            "并确认 main.py 使用 load_dotenv(..., override=True)；改后务必重启 uvicorn。"
        )
    if "402" in raw or "payment required" in s:
        return "需要完成付款或绑定支付方式后才能调用该模型。"
    return str(exc)


def _extract_text_delta(chunk: BaseMessage) -> str:
    content = getattr(chunk, "content", "") or ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


async def stream_rag_sse_events(
    llm: BaseChatModel,
    store: RAGVectorStore,
    user_message: str,
    *,
    recursion_limit: int = 25,
    max_metadata_retries: int = 3,
) -> AsyncIterator[str]:
    """
    异步迭代 SSE 文本帧（含 `data: ...\\n\\n` 前缀行）。

    事件：
    - `{type:"token", content:"..."}` — LLM 流式增量
    - `{type:"metadata", confidence:..., sources:[...]}`
    - `{type:"done"}` — 结束标记
    - `{type:"error", message:"..."}` — 失败
    """
    try:
        stream_mode = resolve_stream_mode()
        processor = StreamMarkdownProcessor(mode=stream_mode)

        graph = build_rag_agent_graph(llm, store)
        state = await graph.ainvoke(
            {"messages": [HumanMessage(content=user_message)]},
            config={"recursion_limit": recursion_limit},
        )
        messages: list[BaseMessage] = state["messages"]
        transcript = render_messages_transcript(messages)

        stream_messages: list[BaseMessage] = [
            SystemMessage(content=ANSWER_STREAM_SYSTEM),
            HumanMessage(
                content=(
                    "下面是内部对话与检索摘录（含工具返回）。请直接输出最终 Markdown 回答给用户。\n\n"
                    f"---\n{transcript}\n---"
                )
            ),
        ]

        pieces: list[str] = []
        async for chunk in llm.astream(stream_messages):
            delta = _extract_text_delta(chunk)
            if not delta:
                continue
            for safe_piece in processor.push(delta):
                if not safe_piece:
                    continue
                pieces.append(safe_piece)
                yield _sse_data({"type": "token", "content": safe_piece})

        for safe_piece in processor.flush():
            if not safe_piece:
                continue
            pieces.append(safe_piece)
            yield _sse_data({"type": "token", "content": safe_piece})

        answer = "".join(pieces).strip()
        if not answer:
            answer = "（未能生成可见正文；请检查是否已上传文档或稍后重试。）"

        meta = await synthesize_metadata_only(
            llm,
            messages=messages,
            answer_markdown=answer,
            max_retries=max_metadata_retries,
        )

        final = RAGStructuredAnswer(
            answer=answer,
            confidence=meta.confidence,
            sources=meta.sources,
        )
        _ = RAGStructuredAnswer.model_validate(final.model_dump())

        yield _sse_data(
            {
                "type": "metadata",
                "confidence": meta.confidence,
                "sources": meta.sources,
            }
        )
        yield _sse_data({"type": "done"})
    except Exception as exc:  # noqa: BLE001
        yield _sse_data({"type": "error", "message": _friendly_stream_error(exc)})
        yield _sse_data({"type": "done"})
