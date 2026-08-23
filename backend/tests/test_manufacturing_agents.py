from __future__ import annotations

from app.harness.agents.manufacturing_agents import (
    EnterpriseContextAgent,
    LeadAgent,
    ManufacturingIntentAgent,
)


def test_manufacturing_intent_extracts_objectives_and_missing_data():
    intent = ManufacturingIntentAgent().infer("我们希望降低汽车工厂压缩空气能耗并减少碳排")
    assert "reduce_energy" in intent.objectives
    assert "reduce_emissions" in intent.objectives
    assert "压缩空气" in intent.processes
    assert intent.needs_clarification is True


def test_context_keeps_private_workspace_and_does_not_invent_facts():
    intent = ManufacturingIntentAgent().infer("注塑质量问题如何改善？")
    context = EnterpriseContextAgent().build(
        "注塑质量问题如何改善？", intent, {"workspace_id": "default_company", "company_name": "示例公司"}
    )
    assert context.workspace_id == "default_company"
    assert context.company_name == "示例公司"
    assert context.baseline_metrics == {}
    assert context.missing_information


def test_lead_agent_creates_dependency_plan_with_skill_allowlist():
    intent = ManufacturingIntentAgent().infer("降低能耗")
    context = EnterpriseContextAgent().build("降低能耗", intent)
    plan = LeadAgent().plan(intent, context)
    assert [task.task_id for task in plan.tasks] == ["knowledge_search", "applicability_check"]
    assert plan.tasks[1].dependencies == ["knowledge_search"]
    assert "search_case_studies" in plan.tasks[0].allowed_skills
