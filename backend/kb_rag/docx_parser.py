"""
使用 python-docx 将 .docx 转为纯文本。

按 Word 文档主体（w:body）中元素的先后顺序遍历，保证段落与表格穿插时的阅读顺序正确。
同时提取：普通段落文本、表格（逐行逐单元格）。
"""

from __future__ import annotations

import io
from typing import Iterator, Union

from docx import Document
from docx.document import Document as DocumentObject
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph


def _iter_body_blocks(document: DocumentObject) -> Iterator[Union[Paragraph, Table]]:
    """按 body 子元素顺序产出段落与表格块。"""
    body = document.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _table_to_text(table: Table, cell_sep: str = " | ", row_sep: str = "\n") -> str:
    """
    将表格转为可读纯文本（每行一条记录，单元格用分隔符连接）。

    说明：合并单元格在 python-docx 中可能重复出现同一文本，此处以可检索性为主，不尝试还原合并拓扑。
    """
    lines: list[str] = []
    for row in table.rows:
        cells = [c.text.replace("\n", " ").strip() for c in row.cells]
        lines.append(cell_sep.join(cells))
    return row_sep.join(lines).strip()


def docx_bytes_to_plain_text(data: bytes) -> str:
    """
    从 docx 二进制内容解析出纯文本（段落 + 表格）。

    段落之间使用双换行分隔；表格前后使用双换行，并在内容前加一行标记便于检索。
    """
    document = Document(io.BytesIO(data))
    parts: list[str] = []

    for block in _iter_body_blocks(document):
        if isinstance(block, Paragraph):
            text = (block.text or "").strip()
            if text:
                parts.append(text)
        elif isinstance(block, Table):
            t = _table_to_text(block)
            if t:
                parts.append("[TABLE]\n" + t)

    return "\n\n".join(parts).strip()
