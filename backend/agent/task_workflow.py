from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from kb_rag.retrieval import RetrievalConfig
from kb_rag.vector_store import RAGVectorStore

from .tools import build_get_index_stats_tool, build_search_docs_tool

PLANNER_PROMPT = """你是任务规划节点。目标是把用户问题转成更适合检索的短 query。
只输出一行 query 文本，不要解释。"""

GENERATOR_PROMPT = """你是基于检索结果回答问题的助手。
必须优先依据检索片段回答，无法确认时明确说明不确定，不得编造。"""

EVALUATOR_PROMPT = """你是回答质量评估节点。
请根据回答是否覆盖用户问题且引用了检索信息进行评分。
只输出 0 到 1 的数字，保留两位小数。"""

_CHECKPOINTER = MemorySaver()


class TaskWorkflowState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    planned_query: str
    retrieved_context: str
    quality_score: float
    retry_count: int
    max_retries: int


def _last_human_text(messages: list[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return str(msg.content)
    return ""


def _parse_score(raw: str) -> float:
    text = (raw or "").strip()
    try:
        value = float(text)
    except ValueError:
        return 0.0
    return max(0.0, min(1.0, value))


def _route_after_evaluate(state: TaskWorkflowState):
    score = float(state.get("quality_score", 0.0) or 0.0)
    retry_count = int(state.get("retry_count", 0) or 0)
    max_retries = int(state.get("max_retries", 1) or 1)
    if score >= 0.6:
        return END
    if retry_count >= max_retries:
        return END
    return "retrieve"


def build_task_workflow_graph(
    llm: BaseChatModel,
    store: RAGVectorStore,
    *,
    index_name: str = "default",
    retrieval_config: RetrievalConfig | None = None,
):
    search_docs = build_search_docs_tool(store, llm, retrieval_config=retrieval_config)
    get_index_stats = build_get_index_stats_tool(store, index_name=index_name)

    async def planner_node(state: TaskWorkflowState):
        question = _last_human_text(state["messages"]).strip()
        if not question:
            question = "请根据上下文总结核心要点"
        planned = await llm.ainvoke(
            [
                SystemMessage(content=PLANNER_PROMPT),
                HumanMessage(content=question),
            ]
        )
        planned_query = str(planned.content).strip() or question
        return {"planned_query": planned_query, "retry_count": int(state.get("retry_count", 0))}

    async def retrieve_node(state: TaskWorkflowState):
        query = (state.get("planned_query") or "").strip() or _last_human_text(state["messages"])
        if int(state.get("retry_count", 0)) > 0:
            query = f"{query} 关键细节"
        stats = await get_index_stats.ainvoke({})
        context = await search_docs.ainvoke({"query": query})
        return {
            "retrieved_context": f"[index_stats]\n{stats}\n\n[search_docs]\n{context}",
            "retry_count": int(state.get("retry_count", 0)),
        }

    async def generate_node(state: TaskWorkflowState):
        question = _last_human_text(state["messages"]).strip()
        context = (state.get("retrieved_context") or "").strip()
        answer = await llm.ainvoke(
            [
                SystemMessage(content=GENERATOR_PROMPT),
                HumanMessage(
                    content=f"用户问题：{question}\n\n检索片段：\n{context}\n\n请给出最终回答。"
                ),
            ]
        )
        return {"messages": [AIMessage(content=str(answer.content))]}

    async def evaluate_node(state: TaskWorkflowState):
        question = _last_human_text(state["messages"]).strip()
        answer = str(state["messages"][-1].content) if state["messages"] else ""
        score_msg = await llm.ainvoke(
            [
                SystemMessage(content=EVALUATOR_PROMPT),
                HumanMessage(content=f"问题：{question}\n\n回答：{answer}"),
            ]
        )
        score = _parse_score(str(score_msg.content))
        return {
            "quality_score": score,
            "retry_count": int(state.get("retry_count", 0)) + (1 if score < 0.6 else 0),
        }

    workflow = StateGraph(TaskWorkflowState)
    workflow.add_node("planner", planner_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("generate", generate_node)
    workflow.add_node("evaluate", evaluate_node)
    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "retrieve")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", "evaluate")
    workflow.add_conditional_edges("evaluate", _route_after_evaluate, {"retrieve": "retrieve", END: END})
    return workflow.compile(checkpointer=_CHECKPOINTER)


async def get_task_workflow_thread_state(
    llm: BaseChatModel,
    store: RAGVectorStore,
    *,
    thread_id: str,
    index_name: str = "default",
    retrieval_config: RetrievalConfig | None = None,
) -> dict:
    graph = build_task_workflow_graph(
        llm,
        store,
        index_name=index_name,
        retrieval_config=retrieval_config,
    )
    snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
    values = snapshot.values if snapshot is not None else {}
    return {
        "thread_id": thread_id,
        "next": list(snapshot.next) if snapshot is not None else [],
        "has_values": bool(values),
        "retry_count": values.get("retry_count", 0) if isinstance(values, dict) else 0,
        "quality_score": values.get("quality_score", 0.0) if isinstance(values, dict) else 0.0,
    }
