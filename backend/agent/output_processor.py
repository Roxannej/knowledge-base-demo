"""
流式 Markdown 输出处理器。

目标：
1) 解决 LLM token 任意切分导致的表格断裂问题；
2) 在后端进行 table block 级控制与规范化；
3) 保持对前端的兼容（输出仍是文本片段，SSE 协议可不变）。
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Iterable, Literal

StreamMode = Literal["raw", "line", "block"]


def _normalize_mode(mode: str | None) -> StreamMode:
    m = (mode or "").strip().lower()
    if m in ("raw", "line", "block"):
        return m  # type: ignore[return-value]
    return "block"


def resolve_stream_mode() -> StreamMode:
    """
    从环境变量读取流式模式。

    - raw:   原样按 token 输出
    - line:  按完整行输出
    - block: 对 table block 做完整缓冲后输出（默认，推荐）
    """
    return _normalize_mode(os.getenv("TABLE_STREAM_MODE", "block"))


_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")


def _is_table_candidate(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    # 至少 2 个管道，避免把普通句子误判为表格
    return s.count("|") >= 2


def _is_table_separator(line: str) -> bool:
    return bool(_TABLE_SEPARATOR_RE.match(line))


def _count_table_columns(line: str) -> int:
    s = line.strip()
    if not s:
        return 0
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    # 简化处理：按竖线拆列，工业场景建议进一步处理转义字符
    cols = [c.strip() for c in s.split("|")]
    return len(cols)


def _normalize_table_lines(lines: list[str]) -> list[str]:
    """
    标准化 table block：
    - 自动补分隔行；
    - 统一列数（不足补空列，超出截断）；
    """
    if not lines:
        return lines

    header = lines[0].rstrip("\n")
    header_cols = max(_count_table_columns(header), 1)

    body_start = 1
    if len(lines) > 1 and _is_table_separator(lines[1]):
        body_start = 2
    else:
        sep = "|" + "|".join([" --- "] * header_cols) + "|"
        lines.insert(1, sep)
        body_start = 2

    def _normalize_row(row: str, cols: int) -> str:
        raw = row.rstrip("\n").strip()
        if raw.startswith("|"):
            raw = raw[1:]
        if raw.endswith("|"):
            raw = raw[:-1]
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) < cols:
            parts.extend([""] * (cols - len(parts)))
        elif len(parts) > cols:
            parts = parts[:cols]
        return "|" + "|".join(f" {p} " for p in parts) + "|"

    normalized = [_normalize_row(lines[0], header_cols), _normalize_row(lines[1], header_cols)]
    for row in lines[body_start:]:
        if not row.strip():
            continue
        normalized.append(_normalize_row(row, header_cols))
    return normalized


@dataclass
class StreamMarkdownProcessor:
    """
    增量 Markdown 处理器（面向流式输出）。
    """

    mode: StreamMode = "block"

    def __post_init__(self) -> None:
        self._buf = ""
        self._table_lines: list[str] = []

    def push(self, token: str) -> list[str]:
        """
        输入 token，返回可安全下发的文本片段列表。
        """
        if not token:
            return []
        if self.mode == "raw":
            return [token]

        self._buf += token
        out: list[str] = []

        while True:
            idx = self._buf.find("\n")
            if idx == -1:
                break
            line = self._buf[: idx + 1]
            self._buf = self._buf[idx + 1 :]
            out.extend(self._consume_line(line))
        return out

    def flush(self) -> list[str]:
        """
        流结束时冲刷剩余内容。
        """
        out: list[str] = []
        if self._buf:
            out.extend(self._consume_line(self._buf))
            self._buf = ""
        if self._table_lines:
            out.extend(self._flush_table_block())
        return out

    def _consume_line(self, line: str) -> list[str]:
        if self.mode == "line":
            return [line]

        # block 模式：做 table block 缓冲
        if self._table_lines:
            if _is_table_candidate(line) or not line.strip():
                self._table_lines.append(line)
                return []
            out = self._flush_table_block()
            out.append(line)
            return out

        # 未处于 table block
        if _is_table_candidate(line):
            self._table_lines.append(line)
            return []
        return [line]

    def _flush_table_block(self) -> list[str]:
        raw_lines = self._table_lines
        self._table_lines = []
        if not raw_lines:
            return []

        # 非表格（单行或没有分隔行）直接原样回退，避免误伤
        if len(raw_lines) < 2:
            return raw_lines

        # 若第二行不是 separator，仍尝试标准化（补 separator）
        normalized = _normalize_table_lines([l.rstrip("\n") for l in raw_lines if l.strip()])
        if not normalized:
            return raw_lines

        text = "\n".join(normalized) + "\n\n"
        return [text]

    def process_iterable(self, chunks: Iterable[str]) -> list[str]:
        """
        便于单测：一次性处理多个 chunk。
        """
        out: list[str] = []
        for chunk in chunks:
            out.extend(self.push(chunk))
        out.extend(self.flush())
        return out

