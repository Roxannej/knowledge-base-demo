"""
在 Agent 对话结束后，将完整消息历史整理为「answer + confidence + sources」结构化结果。

使用 LangChain `with_structured_output(Pydantic)`；若 Pydantic 校验失败或内容不合法，则追加纠错提示并重试，
最多「1 次初始 + max_retries 次重试」（默认 max_retries=3，共 4 次模型调用上限）。
"""

from __future__ import annotations

from typing import Iterable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import ValidationError

from schemas.rag_answer import RAGStructuredAnswer
from schemas.rag_metadata import RAGAnswerMetadata


STRUCTURER_SYSTEM = """你是「结构化输出整理器」。输入是一段多轮对话（含工具 search_docs 返回的文档摘录）。
请输出一个结构化对象，字段含义如下：
- answer：给用户看的最终回答，使用 Markdown；内容应综合对话中的事实，不要输出 JSON、不要复述字段名。
- confidence：0 到 1 的浮点数，表示你对答案与引用依据一致性的把握；无据可查时应偏低。
- sources：字符串数组，每条为文档中的短引用原文（尽量来自工具返回），不要编造未出现的句子。

严格要求：confidence 必须在 [0,1]；sources 为字符串列表；answer 非空。"""

METADATA_SYSTEM = """你是「元数据校验器」。给定对话检索上下文以及已写好的最终 Markdown 回答，请输出：
- confidence：0-1，表示回答与引用依据一致性的把握；若回答超出检索依据或检索为空，应明显偏低。
- sources：字符串数组，每条为可在工具摘录中找到的短引用；不要编造未出现的句子。"""


def render_messages_transcript(messages: Iterable[BaseMessage]) -> str:
    """将消息历史压缩为可读文本，供结构化模型或流式回答模型消费。"""
    parts: list[str] = []
    for m in messages:
        role = getattr(m, "type", m.__class__.__name__)
        content = m.content
        if isinstance(content, list):
            content = repr(content)

        extra = ""
        if role == "ai":
            tool_calls = getattr(m, "tool_calls", None) or None
            if tool_calls:
                extra = f"\n(tool_calls={tool_calls})"

        name = getattr(m, "name", None)
        prefix = f"{role}"
        if name:
            prefix = f"{role}({name})"

        parts.append(f"[{prefix}]\n{content}{extra}".strip())

    return "\n\n".join(parts).strip()


def _validate_business_rules(obj: RAGStructuredAnswer) -> None:
    """Pydantic 之外的轻量业务校验，失败将触发重试。"""
    if not obj.answer.strip():
        raise ValueError("answer 不能为空")
    if obj.confidence < 0 or obj.confidence > 1:
        raise ValueError("confidence 超出 [0,1]")


def _validate_metadata(obj: RAGAnswerMetadata) -> None:
    if obj.confidence < 0 or obj.confidence > 1:
        raise ValueError("confidence 超出 [0,1]")


async def synthesize_structured_rag_answer(
    llm: BaseChatModel,
    *,
    messages: list[BaseMessage],
    max_retries: int = 3,
) -> RAGStructuredAnswer:
    """
    基于完整对话消息，生成并校验 `RAGStructuredAnswer`。

    :param max_retries: 校验/解析失败后的额外重试次数（不含首次），默认 3。
    """
    transcript = render_messages_transcript(messages)
    base_human = HumanMessage(
        content=(
            "下面是完整对话转写。请生成结构化最终结果。\n\n"
            f"---\n{transcript}\n---"
        )
    )

    convo: list[BaseMessage] = [SystemMessage(content=STRUCTURER_SYSTEM), base_human]

    structured = llm.with_structured_output(RAGStructuredAnswer)
    last_error: str | None = None

    total_attempts = max_retries + 1
    for _ in range(total_attempts):
        try:
            raw = await structured.ainvoke(convo)
            if isinstance(raw, RAGStructuredAnswer):
                candidate = raw
            else:
                candidate = RAGStructuredAnswer.model_validate(raw)
            _validate_business_rules(candidate)
            return candidate
        except (ValidationError, ValueError, TypeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"

        convo.append(
            HumanMessage(
                content=(
                    "上一次输出未通过校验。请严格修正后重新输出结构化结果。\n"
                    f"错误信息：{last_error}\n"
                    "注意：confidence 为 0-1 浮点数；sources 为字符串列表；answer 为 Markdown 且非空。"
                )
            )
        )

    raise RuntimeError(
        f"结构化输出在 {total_attempts} 次尝试后仍失败。最后一次错误：{last_error}"
    )


async def synthesize_metadata_only(
    llm: BaseChatModel,
    *,
    messages: list[BaseMessage],
    answer_markdown: str,
    max_retries: int = 3,
) -> RAGAnswerMetadata:
    """
    在 answer 已由流式生成确定的前提下，仅抽取 confidence + sources，并带重试。
    """
    transcript = render_messages_transcript(messages)
    answer = (answer_markdown or "").strip()
    if not answer:
        return RAGAnswerMetadata(confidence=0.0, sources=[])

    base_human = HumanMessage(
        content=(
            "下面是完整对话转写，以及已写好的最终回答（不要再改写回答正文）。\n\n"
            f"--- 对话 ---\n{transcript}\n---\n\n"
            f"--- 最终回答（Markdown）---\n{answer}\n---\n\n"
            "请输出结构化字段：confidence 与 sources。"
        )
    )

    convo: list[BaseMessage] = [SystemMessage(content=METADATA_SYSTEM), base_human]
    structured = llm.with_structured_output(RAGAnswerMetadata)
    last_error: str | None = None

    total_attempts = max_retries + 1
    for _ in range(total_attempts):
        try:
            raw = await structured.ainvoke(convo)
            if isinstance(raw, RAGAnswerMetadata):
                candidate = raw
            else:
                candidate = RAGAnswerMetadata.model_validate(raw)
            _validate_metadata(candidate)
            return candidate
        except (ValidationError, ValueError, TypeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"

        convo.append(
            HumanMessage(
                content=(
                    "上一次元数据未通过校验，请修正。\n"
                    f"错误信息：{last_error}\n"
                    "confidence 必须在 [0,1]；sources 为字符串列表且尽量可在对话摘录中找到依据。"
                )
            )
        )

    return RAGAnswerMetadata(confidence=0.35, sources=[])
