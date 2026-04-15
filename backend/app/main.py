"""
FastAPI 入口：文档上传、同步聊天（结构化 JSON）、SSE 流式聊天。

运行（建议在 backend 目录；在 backend/.env 配置 DeepSeek 等，见 .env.example）：
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import sys
from pathlib import Path, PurePath

# 确保优先加载「本仓库 backend/」下的 kb_rag/agent，避免 sys.path 顺序导致加载到错误目录
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_backend_root_str = str(_BACKEND_ROOT)
if _backend_root_str not in sys.path:
    sys.path.insert(0, _backend_root_str)

from dotenv import load_dotenv

# 必须在 import agent / kb_rag 之前加载，否则部分依赖在 import 时读不到 Key
# override=True：避免 shell 里已存在空 OPENAI_API_KEY 时 .env 里的 DeepSeek Key 无法注入导致 401
load_dotenv(_BACKEND_ROOT / ".env", override=True)

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.language_models.chat_models import BaseChatModel
from starlette.datastructures import UploadFile as StarletteUploadFile

from agent import run_rag_conversation_to_structured, stream_rag_sse_events
from app.deps import get_chat_model, get_vector_store
from app.schemas_http import ChatRequest
import kb_rag.document_loader as _document_loader
from kb_rag import InMemoryVectorStore, SUPPORTED_UPLOAD_EXTENSIONS, UnsupportedDocumentError
from kb_rag.chunking import chunk_plain_text
from kb_rag.embeddings import embedding_backend_label
from kb_rag.llm import openai_chat_env_status

app = FastAPI(title="LangGraph RAG Demo", version="0.1.0")


def _merge_description_into_plain(*, plain: str, description: str | None) -> str:
    d = (description or "").strip()
    if not d:
        return plain
    body = (plain or "").strip()
    if body:
        return f"【文档说明】{d}\n\n{body}"
    return f"【文档说明】{d}"


async def _ingest_document(
    *,
    filename: str,
    data: bytes,
    description: str | None,
    replace: bool,
    store: InMemoryVectorStore,
) -> dict:
    """解析、分块、入库；失败时不执行 replace 清空。"""
    if not data:
        raise HTTPException(
            status_code=400,
            detail=(
                "空文件：未收到任何字节。字段名必须是 file。"
                "不要用浏览器「复制为 cURL」里带空正文的 --data-raw；"
                "请用：curl -F \"file=@/绝对路径/文档.pdf\" \"http://localhost:5173/api/upload?replace=true\""
                " 或使用 POST /upload/binary 见接口文档。"
            ),
        )

    desc_stripped = (description or "").strip() or None

    try:
        plain = _document_loader.bytes_to_plain_text(filename=filename, data=data)
        plain = _merge_description_into_plain(plain=plain, description=desc_stripped)
        chunks = chunk_plain_text(plain)
        texts = [t.strip() for t in chunks if t and t.strip()]
        if not texts:
            raise HTTPException(
                status_code=400,
                detail=(
                    "未能从文件中提取出可入库的文本（常见于扫描版 PDF、纯图片或空文档）。"
                    "可在 multipart 中增加字段 description 补充说明文字以便入库；向量库未修改。"
                ),
            )
        if replace:
            store.clear()
        ids = store.add_texts(texts)
    except HTTPException:
        raise
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"解析或入库失败: {exc}") from exc

    return {
        "filename": filename,
        "chunks": len(ids),
        "replaced_all": replace,
        "vector_store_size": store.size,
        "description": desc_stripped,
    }

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "supported_upload_extensions": list(SUPPORTED_UPLOAD_EXTENSIONS),
        # 用于排查加载路径：应指向本项目 backend/kb_rag/document_loader.py
        "document_loader_file": getattr(_document_loader, "__file__", None),
        "embedding_backend": embedding_backend_label(),
        **openai_chat_env_status(),
    }


@app.post("/upload")
async def upload(
    request: Request,
    replace: bool = Query(False, description="为 true 时先清空向量库再写入"),
    store: InMemoryVectorStore = Depends(get_vector_store),
):
    """
    上传文档并写入向量库（`multipart/form-data`）。

    使用 `await request.form()` 读取字段，避免 FastAPI 同时声明 File+Form 时部分客户端/代理下
    出现「file 正文为空」的兼容问题。表单字段：

    - **file**（必选）：文件；也兼容字段名 **upload**。
    - **description**（可选）：说明文字，会并入待索引文本前缀（扫描件无字时可借此入库）。
    """
    form = await request.form()
    raw = form.get("file")
    if raw is None:
        raw = form.get("upload")
    if raw is None:
        raise HTTPException(
            status_code=400,
            detail="缺少 multipart 表单字段 file（文件）。请使用字段名 file 上传二进制内容。",
        )
    if not isinstance(raw, StarletteUploadFile):
        raise HTTPException(
            status_code=400,
            detail="表单字段 file 必须是文件类型，不能是纯文本字段。",
        )

    filename = (raw.filename or "unnamed").strip()
    data = await raw.read()

    desc_val = form.get("description")
    description: str | None
    if desc_val is None:
        description = None
    elif isinstance(desc_val, StarletteUploadFile):
        description = (await desc_val.read()).decode("utf-8", errors="replace")
    else:
        description = str(desc_val)

    return await _ingest_document(
        filename=filename,
        data=data,
        description=description,
        replace=replace,
        store=store,
    )


@app.post("/upload/binary")
async def upload_binary(
    request: Request,
    filename: str = Query(
        ...,
        min_length=1,
        max_length=512,
        description="含扩展名的文件名，用于判断类型，例如 document.pdf",
    ),
    replace: bool = Query(False),
    description: str | None = Query(
        default=None,
        max_length=4000,
        description="可选说明（URL 编码）；会并入待索引文本前缀",
    ),
    store: InMemoryVectorStore = Depends(get_vector_store),
):
    """
    原始请求体即文件字节（非 multipart），适合命令行：

    curl --data-binary \"@/path/to/a.pdf\" \\
      \"http://localhost:5173/api/upload/binary?filename=a.pdf&replace=true\"
    """
    data = await request.body()
    name = PurePath((filename or "").strip()).name.strip() or "upload.bin"
    return await _ingest_document(
        filename=name,
        data=data,
        description=description,
        replace=replace,
        store=store,
    )


@app.post("/chat")
async def chat(
    body: ChatRequest,
    store: InMemoryVectorStore = Depends(get_vector_store),
    llm: BaseChatModel = Depends(get_chat_model),
):
    """同步聊天：返回 Pydantic 校验后的结构化 JSON。"""
    try:
        result = await run_rag_conversation_to_structured(llm, store, body.message)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result.model_dump()


@app.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    store: InMemoryVectorStore = Depends(get_vector_store),
    llm: BaseChatModel = Depends(get_chat_model),
):
    """
    SSE 流式聊天：`data:` 行为 JSON。

    - `type=token`：模型增量文本（Markdown 片段）
    - `type=metadata`：confidence + sources
    - `type=done`：结束
    - `type=error`：错误信息
    """
    gen = stream_rag_sse_events(llm, store, body.message)

    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
