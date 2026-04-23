"""
/chat/stream 使用的编排：先跑 LangGraph，再对最终回答做 LLM token 流式输出，最后抽取 metadata（confidence/sources）。

SSE 载荷为 JSON 文本行，前端可解析 type=token | metadata | error。
"""

from __future__ import annotations

import json
from uuid import uuid4
from typing import Any, AsyncIterator

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from kb_rag.retrieval import RetrievalConfig
from kb_rag.vector_store import RAGVectorStore
from schemas.rag_answer import RAGStructuredAnswer
from guardrails import GuardrailViolation, validate_structured_output

from .graph import build_rag_agent_graph
from .output_processor import StreamMarkdownProcessor, resolve_stream_mode
from .structured import render_messages_transcript, synthesize_metadata_only
from .task_workflow import build_task_workflow_graph


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
    index_name: str = "default",
    recursion_limit: int = 25,
    max_metadata_retries: int = 3,
    workflow_mode: str = "agent",
    guardrail_mode: str = "relaxed",
    thread_id: str | None = None,
    include_workflow_events: bool = False,
    retrieval_config: RetrievalConfig | None = None,
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

        graph = (
            build_task_workflow_graph(
                llm,
                store,
                index_name=index_name,
                retrieval_config=retrieval_config,
            )
            if workflow_mode == "task"
            else build_rag_agent_graph(
                llm,
                store,
                index_name=index_name,
                retrieval_config=retrieval_config,
            )
        )
        invoke_config: dict[str, Any] = {"recursion_limit": recursion_limit}
        invoke_config["tags"] = [f"route:chat_stream", f"workflow:{workflow_mode}", f"index:{index_name}"]
        invoke_config["metadata"] = {
            "route": "chat_stream",
            "workflow_mode": workflow_mode,
            "index_name": index_name,
            "has_thread_id": bool(thread_id),
        }
        effective_thread_id = thread_id
        if workflow_mode == "task" and include_workflow_events and not effective_thread_id:
            effective_thread_id = f"stream-{uuid4().hex[:12]}"
        if effective_thread_id:
            invoke_config["configurable"] = {"thread_id": effective_thread_id}

        messages: list[BaseMessage]
        if workflow_mode == "task" and include_workflow_events:
            async for chunk in graph.astream(
                {"messages": [HumanMessage(content=user_message)]},
                config=invoke_config,
                stream_mode="updates",
            ):
                if isinstance(chunk, dict):
                    for node_name, payload in chunk.items():
                        if not isinstance(payload, dict):
                            continue
                        yield _sse_data(
                            {
                                "type": "workflow_event",
                                "node": node_name,
                                "updated_keys": sorted(payload.keys()),
                            }
                        )
            if effective_thread_id:
                snapshot = graph.get_state({"configurable": {"thread_id": effective_thread_id}})
                values = snapshot.values if snapshot is not None else {}
                msgs = values.get("messages", []) if isinstance(values, dict) else []
                messages = list(msgs) if isinstance(msgs, list) else []
            else:
                messages = []
        else:
            state = await graph.ainvoke(
                {"messages": [HumanMessage(content=user_message)]},
                config=invoke_config,
            )
            messages = state["messages"]
        if not messages:
            messages = [HumanMessage(content=user_message)]
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
        final = validate_structured_output(final, mode=guardrail_mode)

        yield _sse_data(
            {
                "type": "metadata",
                "confidence": meta.confidence,
                "sources": meta.sources,
            }
        )
        yield _sse_data({"type": "done"})
    except GuardrailViolation as exc:
        yield _sse_data({"type": "error", "message": f"Guardrails 拦截：{exc}"})
        yield _sse_data({"type": "done"})
    except Exception as exc:  # noqa: BLE001
        yield _sse_data({"type": "error", "message": _friendly_stream_error(exc)})
        yield _sse_data({"type": "done"})
