"""Schema-driven adapter for every structured LLM response."""
from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.llm.client import ChatMessage, LLMClient, LLMError
from app.llm.errors import StructuredOutputError
from app.utils.logging import get_logger
from app.utils.metrics import (
    STRUCTURED_LLM_LATENCY,
    STRUCTURED_LLM_REPAIR,
    STRUCTURED_LLM_REQUEST,
    STRUCTURED_LLM_VALIDATION_ERROR,
)

logger = get_logger(__name__)
ModelT = TypeVar("ModelT", bound=BaseModel)


class _ParseFailure(ValueError):
    pass


class StructuredLLM:
    """Request JSON, validate it with Pydantic and repair it at most once."""

    def __init__(
        self,
        llm: LLMClient,
        *,
        mode: str = "auto",
        max_repairs: int = 1,
        raw_log_max_chars: int = 1000,
    ) -> None:
        if mode not in {"auto", "json_schema", "json_object"}:
            raise ValueError(f"unsupported structured output mode: {mode}")
        self.llm = llm
        self.mode = mode
        self.max_repairs = max(0, min(int(max_repairs), 2))
        self.raw_log_max_chars = max(0, int(raw_log_max_chars))
        self._json_schema_support: dict[tuple[str, str], bool] = {}

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        schema: type[ModelT],
        agent_name: str,
        temperature: float = 0.0,
    ) -> ModelT:
        trace_id = "structured_" + uuid.uuid4().hex
        schema_json = schema.model_json_schema()
        prepared = [
            ChatMessage.system(
                "你必须只返回一个符合下方 JSON Schema 的 JSON 对象，不得返回 Markdown 或解释。\n"
                + json.dumps(schema_json, ensure_ascii=False)
            ),
            *messages,
        ]
        started = time.monotonic()
        raw = ""
        errors: list[dict[str, Any]] = []
        attempts = 0
        try:
            for attempts in range(1, self.max_repairs + 2):
                request_messages = prepared if attempts == 1 else self._repair_messages(
                    prepared, raw, errors, schema_json
                )
                if attempts > 1:
                    STRUCTURED_LLM_REPAIR.labels(agent=agent_name, outcome="attempt").inc()
                try:
                    raw, used_format = await self._request(
                        request_messages,
                        schema=schema,
                        temperature=temperature,
                        agent_name=agent_name,
                    )
                except LLMError as exc:
                    stage = "unsupported_format" if self._unsupported_schema(exc) else "transport"
                    raise StructuredOutputError(
                        agent=agent_name,
                        schema_name=schema.__name__,
                        stage=stage,
                        attempts=attempts,
                        errors=[{"type": exc.error_kind, "msg": str(exc), "status_code": exc.status_code}],
                        trace_id=trace_id,
                    ) from exc
                try:
                    data = self.parse_json_object(raw)
                    result = schema.model_validate(data)
                    STRUCTURED_LLM_REQUEST.labels(
                        agent=agent_name, format=used_format, outcome="success"
                    ).inc()
                    if attempts > 1:
                        STRUCTURED_LLM_REPAIR.labels(agent=agent_name, outcome="success").inc()
                    return result
                except _ParseFailure as exc:
                    errors = [{"loc": [], "type": "json_parse", "msg": str(exc)}]
                    stage = "parse"
                except ValidationError as exc:
                    errors = self._safe_errors(exc.errors(include_url=False, include_input=False))
                    stage = "validation"
                    for item in errors:
                        loc = item.get("loc") or ("root",)
                        STRUCTURED_LLM_VALIDATION_ERROR.labels(
                            agent=agent_name, field=str(loc[0])
                        ).inc()
                STRUCTURED_LLM_REQUEST.labels(
                    agent=agent_name, format=used_format, outcome=stage
                ).inc()
                logger.warning(
                    "结构化输出未通过: agent=%s schema=%s trace_id=%s stage=%s attempt=%d errors=%s raw=%s",
                    agent_name, schema.__name__, trace_id, stage, attempts, errors,
                    self._excerpt(raw),
                )
            if attempts > 1:
                STRUCTURED_LLM_REPAIR.labels(agent=agent_name, outcome="failed").inc()
            raise StructuredOutputError(
                agent=agent_name,
                schema_name=schema.__name__,
                stage=stage,
                attempts=attempts,
                errors=errors,
                trace_id=trace_id,
                raw_excerpt=self._excerpt(raw),
            )
        finally:
            STRUCTURED_LLM_LATENCY.labels(agent=agent_name).observe(time.monotonic() - started)

    async def _request(
        self,
        messages: list[dict[str, str]],
        *,
        schema: type[BaseModel],
        temperature: float,
        agent_name: str,
    ) -> tuple[str, str]:
        key = (self.llm.base_url, self.llm.model)
        use_schema = self.mode == "json_schema" or (
            self.mode == "auto" and self._json_schema_support.get(key, True)
        )
        if use_schema:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": self._schema_name(schema.__name__),
                    "strict": True,
                    "schema": schema.model_json_schema(),
                },
            }
            try:
                raw = await self.llm.complete(
                    messages, temperature=temperature, response_format=response_format
                )
                self._json_schema_support[key] = True
                return raw, "json_schema"
            except LLMError as exc:
                STRUCTURED_LLM_REQUEST.labels(
                    agent=agent_name, format="json_schema", outcome="unsupported" if self._unsupported_schema(exc) else "failed"
                ).inc()
                if self.mode != "auto" or not self._unsupported_schema(exc):
                    raise
                self._json_schema_support[key] = False
        raw = await self.llm.complete(
            messages, temperature=temperature, response_format={"type": "json_object"}
        )
        return raw, "json_object"

    @staticmethod
    def parse_json_object(text: str) -> dict[str, Any]:
        value = text.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, flags=re.I | re.S)
        if fenced:
            value = fenced.group(1).strip()
        start = value.find("{")
        array_start = value.find("[")
        if array_start >= 0 and (start < 0 or array_start < start):
            raise _ParseFailure("顶层 JSON 必须是对象")
        if start < 0:
            raise _ParseFailure("未找到 JSON 对象")
        try:
            data, end = json.JSONDecoder().raw_decode(value[start:])
        except json.JSONDecodeError as exc:
            raise _ParseFailure(f"JSON 解析失败: {exc.msg}") from exc
        if not isinstance(data, dict):
            raise _ParseFailure("顶层 JSON 必须是对象")
        trailing = value[start + end:].strip()
        if trailing and re.search(r"[\[{]", trailing):
            raise _ParseFailure("响应包含多个 JSON 值")
        return data

    @staticmethod
    def _repair_messages(
        original_messages: list[dict[str, str]],
        raw: str,
        errors: list[dict[str, Any]],
        schema_json: dict[str, Any],
    ) -> list[dict[str, str]]:
        repair = (
            "上一次输出不符合要求。请保持原始业务语义，只修复 JSON 格式和字段类型。"
            "只返回一个 JSON 对象，不得返回解释或 Markdown。\n"
            f"校验错误：{json.dumps(errors, ensure_ascii=False)}\n"
            f"原始输出：{raw}\n"
            f"JSON Schema：{json.dumps(schema_json, ensure_ascii=False)}"
        )
        return [*original_messages, ChatMessage.assistant(raw), ChatMessage.user(repair)]

    @staticmethod
    def _unsupported_schema(exc: LLMError) -> bool:
        if exc.status_code not in {400, 404, 422}:
            return False
        body = (exc.response_body or str(exc)).lower()
        return any(token in body for token in ("json_schema", "response_format", "unsupported", "not support"))

    @staticmethod
    def _schema_name(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]", "_", value)[:64]

    def _excerpt(self, raw: str) -> str:
        if not self.raw_log_max_chars:
            return ""
        compact = re.sub(r"\s+", " ", raw).strip()
        return compact[:self.raw_log_max_chars]

    @staticmethod
    def _safe_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return json.loads(json.dumps(errors, ensure_ascii=False, default=str))
