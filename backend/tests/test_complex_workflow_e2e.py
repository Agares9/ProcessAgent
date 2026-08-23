import pytest

from app.harness.manufacturing_schemas import AnalysisPlan, AnalysisTask
from app.harness.task_executor import ManufacturingTaskExecutor, build_default_task_registry
from app.harness.skill_matcher import ManufacturingSkillMatcher
from app.harness.manufacturing_schemas import ManufacturingIntent
from scripts.run_manufacturing_agents import merge_intent_entities


class E2ESkills:
    async def execute(self, skill, **kwargs):
        if skill in {"search_manufacturing_knowledge", "search_case_studies"}:
            return [{"doc_id": "doc1", "chunk_id": "chunk1", "excerpt": "e", "score": 0.9, "page_start": 1, "page_end": 1}]
        if skill == "extract_process_parameters":
            return {"baseline_kwh": 1_000_000, "saving_rate": 0.15, "investment": 3_000_000, "annual_saving": 1_800_000}
        if skill == "calculate_energy_savings":
            return {"saved_kwh": kwargs["baseline_kwh"] * kwargs["saving_rate"]}
        if skill == "calculate_emission_reduction":
            return {"reduced_tco2e": kwargs["saved_kwh"] * 0.5703 / 1000}
        return {"checked": True}


@pytest.mark.asyncio
async def test_complex_parallel_and_dependency_workflow():
    plan = AnalysisPlan(tasks=[
        AnalysisTask(task_id="knowledge_search", title="知识", objective="知识"),
        AnalysisTask(task_id="case_study_search", title="案例", objective="案例"),
        AnalysisTask(task_id="parameter_extraction", title="参数", objective="参数", dependencies=["knowledge_search"], allowed_skills=["extract_process_parameters"]),
        AnalysisTask(task_id="energy_analysis", title="节能", objective="节能", dependencies=["parameter_extraction"], allowed_skills=["calculate_energy_savings"]),
        AnalysisTask(task_id="carbon_analysis", title="碳排", objective="碳排", dependencies=["energy_analysis"], allowed_skills=["calculate_emission_reduction"]),
    ])
    results = await ManufacturingTaskExecutor(build_default_task_registry(E2ESkills()), E2ESkills()).execute(plan, {"query": "复杂制造改造方案"})
    assert all(item.status == "completed" for item in results)
    assert results[-1].data["reduced_tco2e"] > 0


def test_multi_turn_entities_merge():
    intent = ManufacturingIntent(intent_type="general_manufacturing", processes=["注塑"], equipment=["180kW注塑机"])
    merge_intent_entities(intent, {"industries": ["汽车零部件"], "factories": ["苏州工厂"], "processes": ["装配"]})
    assert intent.industries == ["汽车零部件"]
    assert intent.processes == ["装配", "注塑"]
