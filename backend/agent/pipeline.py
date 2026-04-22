"""
将第五步 LangGraph 对话与第六步结构化输出串联，形成「用户问题 -> Agent -> Pydantic 结果」的单入口。

供 FastAPI /chat 等接口复用，避免在路由层散落编排逻辑。
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from kb_rag.retrieval import RetrievalConfig
from kb_rag.vector_store import RAGVectorStore
from schemas.rag_answer import RAGStructuredAnswer

from .graph import build_rag_agent_graph
from .task_workflow import build_task_workflow_graph
from .structured import synthesize_structured_rag_answer


async def run_rag_conversation_to_structured(
    llm: BaseChatModel,
    store: RAGVectorStore,
    user_message: str,
    *,
    index_name: str = "default",
    recursion_limit: int = 25,
    max_structured_retries: int = 3,
    workflow_mode: str = "agent",
    thread_id: str | None = None,
    retrieval_config: RetrievalConfig | None = None,
) -> RAGStructuredAnswer:
    """
    先执行带 tools 的 LangGraph，再对完整消息历史做结构化抽取与重试校验。
    """
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
    invoke_config: dict = {"recursion_limit": recursion_limit}
    invoke_config["tags"] = [f"route:chat", f"workflow:{workflow_mode}", f"index:{index_name}"]
    invoke_config["metadata"] = {
        "route": "chat",
        "workflow_mode": workflow_mode,
        "index_name": index_name,
        "has_thread_id": bool(thread_id),
    }
    if thread_id:
        invoke_config["configurable"] = {"thread_id": thread_id}
    state = await graph.ainvoke(
        {"messages": [HumanMessage(content=user_message)]},
        config=invoke_config,
    )
    return await synthesize_structured_rag_answer(
        llm,
        messages=state["messages"],
        max_retries=max_structured_retries,
    )
