"""
LangGraph Agent：模型 bind_tools + ToolNode，形成 agent <-> tools 循环直到不再产生 tool_calls（自然结束）。

说明：分支仅判断「是否存在 tool_calls」以符合图执行需要；具体调用哪个工具由模型与 ToolNode 根据
OpenAI function calling 结果决定，不在此处对工具名写死分支。
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langgraph.graph import END, MessagesState, START, StateGraph
from langgraph.prebuilt import ToolNode

from kb_rag.vector_store import InMemoryVectorStore

from .tools import build_search_docs_tool


DEFAULT_SYSTEM_PROMPT = """你是「上传文档问答」助手。

规则：
1. 当用户问题依赖文档中的事实、数字、表格、条款或专有名词时，必须先调用 search_docs 做检索。
2. 可多次检索（换 query）直到信息足够；不要编造文档中不存在的内容。
3. 当已能完整回答时，不要再调用工具；直接给出最终自然语言回答（Markdown 可读格式）。"""


def _route_after_agent(state: MessagesState):
    last: BaseMessage = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


def build_rag_agent_graph(
    llm: BaseChatModel,
    store: InMemoryVectorStore,
    *,
    system_prompt: str | None = None,
):
    """
    构建已编译的 LangGraph。

    - 节点 agent：SystemMessage + 历史消息 -> bind_tools 模型
    - 节点 tools：ToolNode 执行模型选择的工具（含 search_docs）
    - 边：tools -> agent 循环；agent 无 tool_calls 时结束（即 final_answer）
    """
    search_docs = build_search_docs_tool(store, llm)
    tools = [search_docs]
    llm_with_tools = llm.bind_tools(tools)
    tool_node = ToolNode(tools)

    sys_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    async def agent_node(state: MessagesState):
        messages: list[BaseMessage] = [SystemMessage(content=sys_prompt), *state["messages"]]
        reply = await llm_with_tools.ainvoke(messages)
        return {"messages": [reply]}

    workflow = StateGraph(MessagesState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        _route_after_agent,
        {"tools": "tools", END: END},
    )
    workflow.add_edge("tools", "agent")

    return workflow.compile()
