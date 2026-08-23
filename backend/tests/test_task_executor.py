from __future__ import annotations

import asyncio

import pytest

from app.harness.manufacturing_schemas import AnalysisPlan, AnalysisTask, TaskResult
from app.harness.task_executor import ManufacturingTaskExecutor, TaskRegistry


@pytest.mark.asyncio
async def test_executor_runs_same_priority_in_parallel_and_dependencies_afterward():
    registry = TaskRegistry()
    events: list[str] = []

    async def first(task, context):
        events.append(task.task_id + ":start")
        await asyncio.sleep(0.02)
        events.append(task.task_id + ":end")
        return TaskResult(task_id=task.task_id, status="completed")

    async def dependent(task, context):
        assert "a" in context["dependencies"] and "b" in context["dependencies"]
        assert events[-1] in {"a:end", "b:end"}
        return TaskResult(task_id=task.task_id, status="completed")

    registry.register("a", first)
    registry.register("b", first)
    registry.register("c", dependent)
    plan = AnalysisPlan(tasks=[
        AnalysisTask(task_id="a", title="A", objective="A", priority=1),
        AnalysisTask(task_id="b", title="B", objective="B", priority=1),
        AnalysisTask(task_id="c", title="C", objective="C", priority=2, dependencies=["a", "b"]),
    ])
    results = await ManufacturingTaskExecutor(registry, object()).execute(plan, {})
    assert [item.task_id for item in results] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_executor_isolates_unregistered_task():
    plan = AnalysisPlan(tasks=[AnalysisTask(task_id="missing", title="x", objective="x")])
    results = await ManufacturingTaskExecutor(TaskRegistry(), object()).execute(plan, {})
    assert results[0].status == "failed"
    assert results[0].error == "任务未注册"
