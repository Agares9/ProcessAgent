from __future__ import annotations

import pytest

from app.harness.agents.manufacturing_agents import ScenarioIntentAgent
from app.harness.domain_skills import DOMAIN_HANDLERS
from app.harness.manufacturing_schemas import AnalysisPlan, AnalysisTask, EnterpriseContext, TaskResult
from app.harness.skill_matcher import ScenarioSkillMatcher
from app.harness.task_executor import ManufacturingTaskExecutor, build_default_task_registry


@pytest.mark.parametrize(("query", "industry", "business_domain"), [
    ("门店库存周转率低", "retail", "inventory"),
    ("运输路线油耗太高", "transport", "route"),
    ("财务风险合规检查", "finance", "risk_compliance"),
])
def test_scenario_routes_once(query, industry, business_domain):
    intent = ScenarioIntentAgent().infer(query)
    assert intent.industry == industry
    assert intent.business_domain == business_domain
    matched = ScenarioSkillMatcher().match(query, intent)
    assert matched

def test_capability_response_is_industry_neutral():
    intent = ScenarioIntentAgent().infer("你能做什么")
    assert intent.industry == "general"
    assert intent.business_domain == "general"


class Gateway:
    async def execute(self, skill, **kwargs):
        if skill == "analyze" and kwargs.get("domain") == "inventory":
            return DOMAIN_HANDLERS["retail_inventory"]({"average_inventory": 100, "sales": 250})
        raise AssertionError(f"unexpected skill: {skill} {kwargs}")


@pytest.mark.asyncio
async def test_core_skill_reaches_domain_handler():
    plan = AnalysisPlan(tasks=[AnalysisTask(
        task_id="domain_analysis", title="库存分析", objective="库存分析",
        allowed_skills=["analyze"], input_data={"skill": "analyze"},
    )])
    context = {"query": "库存周转", "context": {"industry": "retail", "domain": "inventory"}}
    results = await ManufacturingTaskExecutor(
        build_default_task_registry(Gateway()), Gateway()
    ).execute(plan, context)
    assert results[0].status == "completed"
    assert results[0].data["metrics"]["turnover"] == 2.5
