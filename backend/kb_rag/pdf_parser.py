"""
使用 pypdf 将 PDF 二进制内容提取为纯文本。

按页 extract_text，页与页之间用双换行拼接；复杂排版/扫描件可能效果有限。
"""

from __future__ import annotations

import io

from pypdf import PdfReader


def pdf_bytes_to_plain_text(data: bytes) -> str:
    """从 PDF 字节流解析出纯文本。"""
    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts).strip()
