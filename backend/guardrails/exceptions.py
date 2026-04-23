"""
Guardrails 相关异常定义。
"""

from __future__ import annotations


class GuardrailViolation(ValueError):
    """当输入或输出违反 guardrail 规则时抛出。"""

