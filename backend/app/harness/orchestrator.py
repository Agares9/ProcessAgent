"""企业场景编排入口兼容导出。"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class ScenarioOrchestratorFacade:
    """统一企业场景入口；实际流程由 CLI/Web 共用的 pipeline 提供。"""

    def __init__(self, pipeline: Callable[..., Awaitable[dict[str, Any]]]) -> None:
        self._pipeline = pipeline

    async def run(self, query: str, *, top_k: int = 5, profile: dict | None = None,
                  use_llm: bool = True, session_id: str = "", user_id: str = "") -> dict[str, Any]:
        result = await self._pipeline(query, top_k, profile, use_llm, session_id, user_id)
        if isinstance(result, dict):
            intent = result.get("intent") or {}
            orchestration = dict(result.get("orchestration") or {})
            orchestration.update({
                "version": "scenario.v1",
                "entrypoint": "ScenarioOrchestratorFacade",
                "industry": intent.get("industry", ""),
                "domain": intent.get("domain", ""),
                "business_domain": intent.get("business_domain", ""),
                "scenario_type": intent.get("scenario_type", ""),
                "matched_skills": result.get("matched_skills", []),
            })
            result["orchestration"] = orchestration
        return result


ManufacturingOrchestratorFacade = ScenarioOrchestratorFacade
