"""Controlled Plan-and-Execute runtime for manufacturing analysis tasks."""
from __future__ import annotations

import asyncio
import re
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

    async def skill_task(task: AnalysisTask, context: dict[str, Any]) -> TaskResult:
        """Generic adapter for deterministic Skills registered by LeadAgent."""
        skill_map = {
            "case_study_search": "search_case_studies",
            "parameter_extraction": "extract_process_parameters",
            "applicability_analysis": "check_applicability",
            "option_comparison": "compare_technical_options",
            "financial_analysis": "calculate_project_financials",
            "energy_analysis": "calculate_energy_savings",
            "carbon_analysis": "calculate_emission_reduction",
            "citation_check": "verify_citations",
            "constraint_check": "check_constraint_compliance",
        }
        skill = task.input_data.get("skill") or skill_map.get(task.task_id) or (task.allowed_skills[0] if task.allowed_skills else "")
        if not skill:
            return TaskResult(task_id=task.task_id, status="failed", error="任务未声明 Skill")
        kwargs = dict(task.input_data.get("kwargs") or {})
        if skill == "extract_process_parameters":
            kwargs.setdefault("text", context.get("query", ""))
        elif skill == "check_applicability":
            kwargs.setdefault("option", context.get("query", ""))
            kwargs.setdefault("context", context)
        elif skill == "calculate_energy_savings":
            source = _dependency_data(context)
            kwargs.setdefault("baseline_kwh", source.get("baseline_kwh"))
            kwargs.setdefault("saving_rate", source.get("saving_rate"))
            query = str(context.get("query", ""))
            if kwargs.get("baseline_kwh") is None:
                kwargs["baseline_kwh"] = _number_after(query, ("基线能耗", "基线电耗", "用电量", "能耗"), ("万度", "度", "kWh"))
            if kwargs.get("saving_rate") is None:
                rate = _number_after(query, ("节能率", "降低", "下降"), ("%", "％"))
                kwargs["saving_rate"] = rate / 100 if rate is not None else None
        elif skill == "calculate_emission_reduction":
            source = _dependency_data(context)
            kwargs.setdefault("saved_kwh", source.get("saved_kwh"))
            kwargs.setdefault("emission_factor", source.get("emission_factor", 0.5703))
        elif skill == "calculate_project_financials":
            source = _dependency_data(context)
            kwargs.setdefault("investment", source.get("investment"))
            kwargs.setdefault("annual_saving", source.get("annual_saving"))
            kwargs.setdefault("annual_operating_cost", source.get("annual_operating_cost", 0.0))
            query = str(context.get("query", ""))
            kwargs["investment"] = kwargs.get("investment") or _number_after(query, ("投资", "预算", "投入"), ("万元", "万", "元"))
            kwargs["annual_saving"] = kwargs.get("annual_saving") or _number_after(query, ("年节省", "每年节省", "年度节省", "年收益"), ("万元", "万", "元"))
        elif skill == "verify_citations":
            kwargs.setdefault("claims", _dependency_artifacts(context))
        elif skill == "check_constraint_compliance":
            kwargs.setdefault("proposal", _dependency_data(context))
            kwargs.setdefault("constraints", context.get("constraints", {}))
        required = {
            "calculate_energy_savings": ("baseline_kwh", "saving_rate"),
            "calculate_emission_reduction": ("saved_kwh",),
            "calculate_project_financials": ("investment", "annual_saving"),
        }.get(skill, ())
        missing = [key for key in required if kwargs.get(key) is None]
        if missing:
            return TaskResult(task_id=task.task_id, status="skipped", summary="缺少计算输入", missing_information=missing)
        try:
            value = await skill_gateway.execute(skill, **kwargs)
            data = value if isinstance(value, dict) else {"value": value}
            prior_sources = []
            for dependency in (context.get("dependencies") or {}).values():
                prior_sources.extend(dependency.get("data", {}).get("source_chain", []))
            if prior_sources:
                data.setdefault("source_chain", list(dict.fromkeys(prior_sources)))
            if data.get("source_type"):
                data.setdefault("source_chain", []).append(data["source_type"])
            return TaskResult(
                task_id=task.task_id, status="completed", summary=f"Skill {skill} 执行完成", data=data,
                data_schema=str(data.get("data_schema", f"{skill}.v1")),
                sources=[str(x) for x in data.get("source_ids", [])] if isinstance(data, dict) else [],
            )
        except Exception as exc:  # noqa: BLE001
            return TaskResult(task_id=task.task_id, status="failed", error=str(exc))

    registry.register("knowledge_search", knowledge_search)
    registry.register("applicability_check", applicability_check)
    for task_id in (
        "case_study_search", "parameter_extraction", "applicability_analysis", "option_comparison",
        "financial_analysis", "energy_analysis", "carbon_analysis",
        "citation_check", "constraint_check",
    ):
        registry.register(task_id, skill_task)
    return registry


def _dependency_data(context: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for result in (context.get("dependencies") or {}).values():
        merged.update(result.get("data") or {})
    return merged


def _dependency_artifacts(context: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for result in (context.get("dependencies") or {}).values():
        artifacts.extend(result.get("artifacts") or [])
    return artifacts


def _number_after(text: str, labels: tuple[str, ...], units: tuple[str, ...]) -> float | None:
    """Parse a number near a business label and normalize common Chinese units."""
    label = next((x for x in labels if x in text), None)
    if not label:
        return None
    match = re.search(re.escape(label) + r"[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?)\s*(万元|万度|MWh|kWh|MW|kW|kg|吨|千克|吨|t|度|元|万|%|％)?", text, re.I)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2) or ""
    return _normalize_unit(value, unit)


def _normalize_unit(value: float, unit: str, target: str | None = None) -> float:
    """Normalize common manufacturing units to calculation base units."""
    factors = {
        "元": 1.0, "万": 10000.0, "万元": 10000.0,
        "度": 1.0, "kWh": 1.0, "MWh": 1000.0, "万度": 10000.0,
        "kg": 1.0, "千克": 1.0, "t": 1000.0, "吨": 1000.0,
        "kW": 1.0, "MW": 1000.0, "千瓦": 1.0,
        "%": 0.01, "％": 0.01,
    }
    return value * factors.get(unit, 1.0)
