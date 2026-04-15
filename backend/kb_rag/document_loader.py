"""
根据文件名/扩展名选择解析策略，将上传文件统一转为 UTF-8 纯文本。

支持：.docx（python-docx）、.pdf（pypdf）、.txt / .md（直接解码）。
扩展名异常、无后缀或标准 PDF 文件头（%PDF）时，也会按 PDF 解析。
"""

from __future__ import annotations

from pathlib import PurePath

from .docx_parser import docx_bytes_to_plain_text
from .pdf_parser import pdf_bytes_to_plain_text

# 供 API 暴露，便于确认当前进程已加载的配置
SUPPORTED_UPLOAD_EXTENSIONS: tuple[str, ...] = (".docx", ".pdf", ".txt", ".md", ".markdown")


class UnsupportedDocumentError(ValueError):
    """不支持的文件类型。"""


def normalize_upload_filename(name: str) -> str:
    """
    清理上传文件名，避免尾随点/空白导致 pathlib 得到错误 suffix（例如 `.` 而不是 `.pdf`）。
    """
    n = (name or "").strip().strip('"').strip("'")
    n = n.replace("\u00a0", " ").strip()
    while n.endswith((".", " ", "\t")):
        n = n.rstrip(". \t")
    return n


def _suffix_from_filename(name: str) -> str:
    n = normalize_upload_filename(name)
    if not n:
        return ""
    return PurePath(n).suffix.lower()


def _looks_like_pdf_bytes(data: bytes) -> bool:
    """识别标准 PDF 文件头（允许 UTF-8 BOM 与前置空白）。"""
    if not data:
        return False
    i = 0
    if data.startswith(b"\xef\xbb\xbf"):
        i = 3
    while i < len(data) and data[i] in (9, 10, 13, 32):
        i += 1
    return len(data) >= i + 4 and data[i : i + 4] == b"%PDF"


def bytes_to_plain_text(*, filename: str, data: bytes) -> str:
    """
    将上传文件内容解析为纯文本。

    :param filename: 原始文件名（用于判断扩展名）
    :param data: 文件二进制内容
    :raises UnsupportedDocumentError: 扩展名不在支持列表
    :raises UnicodeDecodeError: 文本类文件非 UTF-8 时可能抛出
    """
    ext = _suffix_from_filename(filename)

    if ext == ".docx":
        return docx_bytes_to_plain_text(data)

    if ext in {".txt", ".md", ".markdown"}:
        return data.decode("utf-8").strip()

    # PDF：显式 .pdf，或魔数匹配（兼容无后缀、blob 名、后缀被污染等情况）
    if ext == ".pdf" or _looks_like_pdf_bytes(data):
        try:
            return pdf_bytes_to_plain_text(data)
        except Exception as exc:  # noqa: BLE001 — pypdf 可能抛出多种异常
            raise UnsupportedDocumentError(
                f"PDF 无法解析（可能已损坏、加密或不是有效 PDF）: {exc}"
            ) from exc

    raise UnsupportedDocumentError(
        f"Unsupported file extension: {ext or '(empty)'}; "
        f"supported: {', '.join(SUPPORTED_UPLOAD_EXTENSIONS)}"
    )
