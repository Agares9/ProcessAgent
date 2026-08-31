from __future__ import annotations

from types import SimpleNamespace

import pytest

import web_app
from app.llm.errors import StructuredOutputError


@pytest.mark.asyncio
async def test_web_returns_safe_structured_error(monkeypatch):
    async def fail(*args, **kwargs):
        raise StructuredOutputError(
            agent="scenario_intent", schema_name="ScenarioIntent", stage="validation",
            attempts=2, errors=[{"msg": "secret validation detail"}], trace_id="trace-test",
            raw_excerpt="private model output",
        )

    monkeypatch.setattr(web_app, "run_cli_workflow", fail)
    app = {
        "container": SimpleNamespace(settings=SimpleNamespace(hybrid_topk=5)),
        "tasks": {"task-1": {"status": "running"}},
    }
    await web_app.run_chat_task(app, "task-1", "question", "session-1", "user-1")
    task = app["tasks"]["task-1"]
    assert task["status"] == "failed"
    assert task["error_code"] == "structured_output_invalid"
    assert task["result"]["answer"] == "意图识别模型返回格式不符合要求，请重试。"
    assert "private model output" not in str(task)
