from __future__ import annotations

from collections import deque

import pytest
from pydantic import BaseModel, ConfigDict

from app.harness.manufacturing_schemas import ScenarioIntent
from app.llm.client import LLMError
from app.llm.errors import StructuredOutputError
from app.llm.structured import StructuredLLM


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    items: list[str]


class FakeLLM:
    base_url = "https://llm.test"
    model = "test-model"

    def __init__(self, outputs):
        self.outputs = deque(outputs)
        self.calls = []

    async def complete(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        value = self.outputs.popleft()
        if isinstance(value, Exception):
            raise value
        return value


@pytest.mark.asyncio
async def test_valid_json_returns_typed_model():
    llm = FakeLLM(['{"name":"demo","items":["a"]}'])
    result = await StructuredLLM(llm).complete([], schema=Result, agent_name="test")
    assert isinstance(result, Result)
    assert result.name == "demo"
    assert llm.calls[0]["response_format"]["type"] == "json_schema"


@pytest.mark.asyncio
async def test_schema_owned_normalization_is_applied():
    llm = FakeLLM([
        '{"complexity":"simple","entities":{"store_count":30},'
        '"metrics":[{"name":"turnover","value":4.2}]}'
    ])
    result = await StructuredLLM(llm).complete([], schema=ScenarioIntent, agent_name="scenario_intent")
    assert result.entities == [{"type": "store_count", "value": 30}]
    assert result.metrics == {"turnover": 4.2}


@pytest.mark.asyncio
async def test_markdown_and_leading_text_are_parsed():
    assert StructuredLLM.parse_json_object('```json\n{"name":"a","items":[]}\n```')["name"] == "a"
    assert StructuredLLM.parse_json_object('结果如下： {"name":"b","items":[]} 完成')["name"] == "b"


def test_multiple_json_values_are_rejected():
    with pytest.raises(ValueError, match="多个 JSON"):
        StructuredLLM.parse_json_object('{"name":"a","items":[]} {"name":"b"}')


def test_top_level_array_is_rejected():
    with pytest.raises(ValueError, match="顶层 JSON 必须是对象"):
        StructuredLLM.parse_json_object('[{"name":"a","items":[]}]')


@pytest.mark.asyncio
async def test_validation_failure_is_repaired_once():
    llm = FakeLLM([
        '{"name":"demo","items":"a"}',
        '{"name":"demo","items":["a"]}',
    ])
    result = await StructuredLLM(llm, max_repairs=1).complete([], schema=Result, agent_name="test")
    assert result.items == ["a"]
    assert len(llm.calls) == 2
    assert "校验错误" in llm.calls[1]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_second_invalid_response_raises_unified_error():
    llm = FakeLLM(['{"items":"a"}', '{"items":"b"}'])
    with pytest.raises(StructuredOutputError) as captured:
        await StructuredLLM(llm, max_repairs=1).complete([], schema=Result, agent_name="test")
    assert captured.value.stage == "validation"
    assert captured.value.attempts == 2


@pytest.mark.asyncio
async def test_unsupported_json_schema_falls_back_and_is_cached():
    unsupported = LLMError(
        "unsupported response_format",
        error_kind="http",
        status_code=400,
        response_body="json_schema response_format is unsupported",
    )
    llm = FakeLLM([unsupported, '{"name":"a","items":[]}', '{"name":"b","items":[]}'])
    structured = StructuredLLM(llm, mode="auto")
    assert (await structured.complete([], schema=Result, agent_name="test")).name == "a"
    assert (await structured.complete([], schema=Result, agent_name="test")).name == "b"
    assert [call["response_format"]["type"] for call in llm.calls] == [
        "json_schema", "json_object", "json_object"
    ]


@pytest.mark.asyncio
async def test_transport_error_is_not_repaired():
    llm = FakeLLM([LLMError("timeout", error_kind="network")])
    with pytest.raises(StructuredOutputError) as captured:
        await StructuredLLM(llm).complete([], schema=Result, agent_name="test")
    assert captured.value.stage == "transport"
    assert len(llm.calls) == 1
