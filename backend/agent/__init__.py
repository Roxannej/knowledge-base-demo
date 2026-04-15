"""
agent 包：基于 LangGraph 的 Agent 编排、bind_tools（function calling）与 ToolNode 工具执行。

第五步：search_docs + agent/tools 循环。
第六步：对话结束后整理为 Pydantic 结构化输出并带失败重试。
"""

from .graph import build_rag_agent_graph
from .pipeline import run_rag_conversation_to_structured
from .streaming import stream_rag_sse_events
from .structured import render_messages_transcript, synthesize_metadata_only, synthesize_structured_rag_answer
from .tools import build_search_docs_tool

__all__ = [
    "build_rag_agent_graph",
    "build_search_docs_tool",
    "render_messages_transcript",
    "run_rag_conversation_to_structured",
    "stream_rag_sse_events",
    "synthesize_metadata_only",
    "synthesize_structured_rag_answer",
]
