"""
语义导向的文本分块：以“段落/空行”为第一粒度，再合并过短块、切分过长块。

策略概要：
1. 用空行将全文拆成段落单元（来自 Word 的段落、表格块通常已被 document_loader 用双换行隔开）。
2. 顺序合并相邻段落，直到接近最大长度（形成语义更完整的 chunk）。
3. 对超长单元：按句号/问号/感叹号等断句后再组装；仍超长则按字符窗口硬切并带重叠。
"""

from __future__ import annotations

import re
from typing import List

# 过短段落单独成块不利于向量检索：与相邻段落合并，直到达到下限（近似“语义段”）。
_MIN_CHUNK_CHARS = 120
_MAX_CHUNK_CHARS = 900
_OVERLAP_CHARS = 120

# 中英文常见句末标点（含省略号）
_SENTENCE_SPLIT = re.compile(r"(?<=[。．\\.!?？…])\s+")


def _normalize_newlines(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def _split_paragraph_units(text: str) -> List[str]:
    """按空行切分为段落单元（保留表格块内的换行）。"""
    text = _normalize_newlines(text)
    units = [u.strip() for u in re.split(r"\n\s*\n+", text)]
    return [u for u in units if u]


def _hard_split_with_overlap(text: str) -> List[str]:
    """无明确句子边界时的兜底：滑动窗口 + 重叠，避免硬切断关键信息。"""
    if len(text) <= _MAX_CHUNK_CHARS:
        return [text]
    out: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + _MAX_CHUNK_CHARS, len(text))
        out.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - _OVERLAP_CHARS, start + 1)
    return [x for x in out if x]


def _split_oversized_unit(unit: str) -> List[str]:
    """对单个过长单元：先按句子切，再必要时按字符窗口切分。"""
    if len(unit) <= _MAX_CHUNK_CHARS:
        return [unit]

    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(unit) if s.strip()]
    if len(sentences) <= 1:
        return _hard_split_with_overlap(unit)

    pieces: List[str] = []
    buf = ""
    for s in sentences:
        if not buf:
            buf = s
            continue
        if len(buf) + 1 + len(s) <= _MAX_CHUNK_CHARS:
            buf = f"{buf} {s}"
        else:
            pieces.extend(_split_oversized_unit(buf) if len(buf) > _MAX_CHUNK_CHARS else [buf])
            buf = s
    if buf:
        pieces.extend(_split_oversized_unit(buf) if len(buf) > _MAX_CHUNK_CHARS else [buf])
    return pieces


def _finalize_buffer(text: str) -> List[str]:
    text = text.strip()
    if not text:
        return []
    return _split_oversized_unit(text)


def merge_and_split_units(units: List[str]) -> List[str]:
    """将段落单元合并为长度适中的 chunks，并对过长单元切分。"""
    merged_units: List[str] = []
    buf = ""

    for raw in units:
        u = raw.strip()
        if not u:
            continue
        if not buf:
            buf = u
            continue
        if len(buf) + 2 + len(u) <= _MAX_CHUNK_CHARS:
            buf = f"{buf}\n\n{u}"
        else:
            merged_units.extend(_finalize_buffer(buf))
            buf = u

    merged_units.extend(_finalize_buffer(buf))

    # 二次合并：把过短块并入相邻块（前一块优先，其次后一块逻辑通过双向条件覆盖）
    out: List[str] = []
    for piece in merged_units:
        if not out:
            out.append(piece)
            continue
        prev = out[-1]
        if (
            len(piece) < _MIN_CHUNK_CHARS
            or len(prev) < _MIN_CHUNK_CHARS
        ) and len(prev) + 2 + len(piece) <= _MAX_CHUNK_CHARS:
            out[-1] = f"{prev}\n\n{piece}"
        else:
            out.append(piece)

    return out


def chunk_plain_text(text: str) -> List[str]:
    """对整篇纯文本做语义段落分块，返回 chunk 列表。"""
    units = _split_paragraph_units(text)
    if not units:
        return []
    return merge_and_split_units(units)
