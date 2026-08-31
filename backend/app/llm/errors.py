"""Typed errors for schema-constrained LLM output."""
from __future__ import annotations

from typing import Any


class StructuredOutputError(Exception):
    """A structured LLM response could not be transported, parsed or validated."""

    def __init__(
        self,
        *,
        agent: str,
        schema_name: str,
        stage: str,
        attempts: int,
        errors: list[dict[str, Any]] | None = None,
        trace_id: str = "",
        raw_excerpt: str = "",
    ) -> None:
        self.agent = agent
        self.schema_name = schema_name
        self.stage = stage
        self.attempts = attempts
        self.errors = errors or []
        self.trace_id = trace_id
        self.raw_excerpt = raw_excerpt
        super().__init__(
            f"{agent} 的 LLM 输出未通过 {schema_name} 协议"
            f"（stage={stage}, attempts={attempts}, trace_id={trace_id}）"
        )

