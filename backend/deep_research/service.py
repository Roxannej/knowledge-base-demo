from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from agent.tools import build_get_index_stats_tool, build_search_docs_tool
from kb_rag.retrieval import RetrievalConfig
from kb_rag.vector_store import RAGVectorStore


RESEARCHER_PROMPT = """你是 Researcher。
任务：基于给定研究问题与检索材料，整理“事实清单 + 关键来源”。
要求：
1) 只基于提供材料，不要编造；
2) 输出 Markdown；
3) 分两节：## Facts 与 ## Sources。"""

ANALYST_PROMPT = """你是 Analyst。
任务：把研究材料提炼为可执行洞察。
要求：
1) 输出 Markdown；
2) 包含：## Key Findings、## Risks、## Open Questions；
3) 每条尽量短句，避免空泛表达。"""

WRITER_PROMPT = """你是 Writer。
任务：根据研究问题、Researcher/Analyst 产物，写最终研究报告。
要求：
1) 输出完整 Markdown 报告；
2) 至少包含：# Title、## Executive Summary、## Detailed Analysis、## References；
3) 结论必须可追溯到已有材料。"""


@dataclass
class DeepResearchResult:
    report_id: str
    report_path: str
    question: str
    index_name: str
    created_at: str
    researcher_notes: str
    analyst_notes: str
    report_markdown: str


def _utc_timestamp() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _safe_report_id() -> str:
    return datetime.utcnow().strftime("%Y%m%d-%H%M%S")


async def run_deep_research(
    llm: BaseChatModel,
    store: RAGVectorStore,
    *,
    question: str,
    index_name: str = "default",
    retrieval_config: RetrievalConfig | None = None,
    report_dir: Path | None = None,
) -> DeepResearchResult:
    q = question.strip()
    if not q:
        raise ValueError("question 不能为空")

    reports_root = report_dir or (Path(__file__).resolve().parents[1] / "data" / "reports")
    reports_root.mkdir(parents=True, exist_ok=True)

    search_docs = build_search_docs_tool(store, llm, retrieval_config=retrieval_config)
    get_index_stats = build_get_index_stats_tool(store, index_name=index_name)

    stats_text = await get_index_stats.ainvoke({})
    retrieved_text = await search_docs.ainvoke({"query": q})
    material = f"[index_stats]\n{stats_text}\n\n[retrieval]\n{retrieved_text}"

    researcher_msg = await llm.ainvoke(
        [
            SystemMessage(content=RESEARCHER_PROMPT),
            HumanMessage(content=f"研究问题：{q}\n\n检索材料：\n{material}"),
        ]
    )
    researcher_notes = str(researcher_msg.content).strip()

    analyst_msg = await llm.ainvoke(
        [
            SystemMessage(content=ANALYST_PROMPT),
            HumanMessage(content=f"研究问题：{q}\n\nResearcher 输出：\n{researcher_notes}"),
        ]
    )
    analyst_notes = str(analyst_msg.content).strip()

    writer_msg = await llm.ainvoke(
        [
            SystemMessage(content=WRITER_PROMPT),
            HumanMessage(
                content=(
                    f"研究问题：{q}\n\n"
                    f"Researcher 输出：\n{researcher_notes}\n\n"
                    f"Analyst 输出：\n{analyst_notes}\n\n"
                    "请产出最终报告。"
                )
            ),
        ]
    )
    report_markdown = str(writer_msg.content).strip()

    created_at = _utc_timestamp()
    report_id = _safe_report_id()
    report_file = reports_root / f"{report_id}.md"
    final_doc = (
        f"# Deep Research Report\n\n"
        f"- report_id: `{report_id}`\n"
        f"- created_at: `{created_at}`\n"
        f"- index_name: `{index_name}`\n\n"
        f"## Question\n\n{q}\n\n"
        f"## Researcher Notes\n\n{researcher_notes}\n\n"
        f"## Analyst Notes\n\n{analyst_notes}\n\n"
        f"## Final Report\n\n{report_markdown}\n"
    )
    report_file.write_text(final_doc, encoding="utf-8")

    return DeepResearchResult(
        report_id=report_id,
        report_path=str(report_file),
        question=q,
        index_name=index_name,
        created_at=created_at,
        researcher_notes=researcher_notes,
        analyst_notes=analyst_notes,
        report_markdown=report_markdown,
    )
