"""Controlled Plan-and-Execute runtime for manufacturing analysis tasks."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Awaitable, Callable

from app.harness.manufacturing_schemas import AnalysisPlan, AnalysisTask, TaskResult

TaskHandler = Callable[[AnalysisTask, dict[str, Any]], Awaitable[TaskResult]]


class TaskRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, TaskHandler] = {}

    def register(self, task_id: str, handler: TaskHandler) -> None:
        self._handlers[task_id] = handler

    def get(self, task_id: str) -> TaskHandler | None:
        return self._handlers.get(task_id)


class ManufacturingTaskExecutor:
    """Execute only registered tasks and only the Skills declared by each task."""

    def __init__(self, registry: TaskRegistry, skill_gateway: Any, max_parallel: int = 4) -> None:
        self.registry = registry
        self.skill_gateway = skill_gateway
        self.max_parallel = max_parallel

    async def execute(self, plan: AnalysisPlan, context: dict[str, Any]) -> list[TaskResult]:
        pending = {task.task_id: task for task in plan.tasks}
        completed: dict[str, TaskResult] = {}
        results: list[TaskResult] = []
        while pending:
            ready = [
                task for task in pending.values()
                if all(dep in completed for dep in task.dependencies)
            ]
            if not ready:
                for task in pending.values():
                    results.append(TaskResult(
                        task_id=task.task_id, status="failed",
                        error="计划存在循环依赖或未满足的任务依赖",
                    ))
                break
            ready.sort(key=lambda task: (task.priority, task.task_id))
            for start in range(0, len(ready), self.max_parallel):
                batch = ready[start:start + self.max_parallel]
                batch_results = await asyncio.gather(*(self._run_one(task, context, completed) for task in batch))
                for task, result in zip(batch, batch_results):
                    completed[task.task_id] = result
                    results.append(result)
                    pending.pop(task.task_id, None)
        return results

    async def _run_one(
        self, task: AnalysisTask, context: dict[str, Any], completed: dict[str, TaskResult]
    ) -> TaskResult:
        handler = self.registry.get(task.task_id)
        if handler is None:
            return TaskResult(task_id=task.task_id, status="failed", error="任务未注册")
        task_context = {
            **context,
            "dependencies": {key: value.model_dump() for key, value in completed.items() if key in task.dependencies},
            "allowed_skills": list(task.allowed_skills),
        }
        try:
            return await asyncio.wait_for(handler(task, task_context), timeout=task.timeout_seconds)
        except asyncio.TimeoutError:
            return TaskResult(task_id=task.task_id, status="failed", error="任务执行超时")
        except Exception as exc:  # noqa: BLE001
            return TaskResult(task_id=task.task_id, status="failed", error=str(exc))


def build_default_task_registry(skill_gateway: Any) -> TaskRegistry:
    registry = TaskRegistry()

    async def knowledge_search(task: AnalysisTask, context: dict[str, Any]) -> TaskResult:
        query = str(context.get("query", task.objective))
        hits = await skill_gateway.execute("search_manufacturing_knowledge", query=query, top_k=5)
        from app.harness.manufacturing_schemas import EvidenceArtifact
        artifacts = [EvidenceArtifact(
            claim=hit.get("excerpt", "")[:200], value=hit.get("score"), source_id=hit.get("doc_id", ""),
            chunk_id=hit.get("chunk_id", ""), page_start=hit.get("page_start"), page_end=hit.get("page_end"),
            excerpt=hit.get("excerpt", ""), visibility=hit.get("visibility", "enterprise_private"),
        ) for hit in hits]
        return TaskResult(task_id=task.task_id, status="completed" if hits else "failed",
                          summary=f"检索到 {len(hits)} 条知识证据", artifacts=artifacts)

    async def applicability_check(task: AnalysisTask, context: dict[str, Any]) -> TaskResult:
        dependency = context.get("dependencies", {}).get("knowledge_search", {})
        artifacts = dependency.get("artifacts", [])
        return TaskResult(
            task_id=task.task_id, status="completed" if artifacts else "skipped",
            summary="候选措施需要结合企业基线复核" if artifacts else "缺少检索证据",
            artifacts=artifacts, assumptions=["当前未提供企业实测基线"],
            missing_information=context.get("missing_information", []),
        )

    registry.register("knowledge_search", knowledge_search)
    registry.register("applicability_check", applicability_check)
    return registry
