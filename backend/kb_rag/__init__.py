"""
kb_rag 包：文档解析、分块、向量嵌入、内存向量库、multi-query 与 rerank 等检索增强逻辑。

（包名避免与 PyPI 上同名 `rag` 冲突，防止误加载第三方包导致上传逻辑异常。）

已提供：解析（含 docx/pdf/文本）、分块、sentence-transformers 嵌入、内存向量库与余弦相似度检索。
"""

from .chunking import chunk_plain_text
from .document_loader import (
    SUPPORTED_UPLOAD_EXTENSIONS,
    UnsupportedDocumentError,
    bytes_to_plain_text,
    normalize_upload_filename,
)
from .embeddings import DEFAULT_EMBEDDING_MODEL, SentenceTransformerEmbedding
from .llm import create_rag_chat_model
from .multi_query import MultiQuerySpec, generate_multi_queries, generate_multi_queries_sync
from .rerank import PassageScore, RerankLLMOutput, rerank_passages, rerank_passages_sync
from .retrieval import retrieve_with_multiquery_rerank
from .vector_store import InMemoryVectorStore, SearchResult

__all__ = [
    "DEFAULT_EMBEDDING_MODEL",
    "InMemoryVectorStore",
    "SUPPORTED_UPLOAD_EXTENSIONS",
    "normalize_upload_filename",
    "MultiQuerySpec",
    "PassageScore",
    "RerankLLMOutput",
    "SearchResult",
    "SentenceTransformerEmbedding",
    "UnsupportedDocumentError",
    "bytes_to_plain_text",
    "chunk_plain_text",
    "create_rag_chat_model",
    "generate_multi_queries",
    "generate_multi_queries_sync",
    "rerank_passages",
    "rerank_passages_sync",
    "retrieve_with_multiquery_rerank",
]
