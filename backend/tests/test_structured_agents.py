from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.harness.agents.manufacturing_agents import LeadAgent, ScenarioIntentAgent
from app.harness.manufacturing_schemas import (
    AnalysisPlanDraft,
    AnalysisTaskDraft,
    EnterpriseContext,
    ScenarioIntent,
)


class FakeStructuredLLM:
    def __init__(self):
        self.calls = []

    async def complete(self, messages, *, schema, agent_name, temperature=0.0):
        self.calls.append((schema, agent_name))
        if schema is ScenarioIntent:
            return ScenarioIntent(
                industry="retail", domain="retail", business_domain="inventory",
                complexity="standard", objectives=["reduce_cost"],
            )
        return AnalysisPlanDraft(tasks=[AnalysisTaskDraft(
            task_id="knowledge_search", title="检索", objective="查找证据",
            allowed_skills=["retrieve"], completion_criteria=["返回证据"],
        )])


@pytest.mark.asyncio
async def test_trial_agents_use_structured_llm_and_keep_trusted_context():
    structured = FakeStructuredLLM()
    intent = await ScenarioIntentAgent().infer_async("库存成本上升", structured_llm=structured)
    context = EnterpriseContext(
        assumptions=["用户确认的假设"], missing_information=["补货周期"]
    )
    plan = await LeadAgent().plan_async(intent, context, structured_llm=structured)
    assert structured.calls == [(ScenarioIntent, "scenario_intent"), (AnalysisPlanDraft, "lead_plan")]
    assert intent.raw == {"source": "structured_llm"}
    assert plan.assumptions == ["用户确认的假设"]
    assert plan.missing_information == ["补货周期"]


def test_analysis_plan_draft_rejects_unknown_skills():
    with pytest.raises(ValueError, match="allowed_skills"):
        AnalysisPlanDraft.model_validate({"tasks": [{
            "task_id": "bad", "title": "bad", "objective": "bad", "allowed_skills": ["invent_skill"]
        }]})


def test_trial_agents_cannot_call_complete_json_directly():
    path = Path(__file__).resolve().parents[1] / "app/harness/agents/manufacturing_agents.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    direct_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "complete_json"
    ]
    assert direct_calls == []
