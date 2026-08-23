import pytest
import math

from app.harness.manufacturing_schemas import AnalysisPlan, AnalysisTask, TaskResult
from app.harness.task_executor import ManufacturingTaskExecutor, build_default_task_registry


class FakeSkills:
    async def execute(self, skill, **kwargs):
        if skill == "extract_process_parameters":
            return {"baseline_kwh": 1000.0, "saving_rate": 0.2, "data_schema": "process_parameters.v1"}
        if skill == "calculate_energy_savings":
            saved = kwargs["baseline_kwh"] * kwargs["saving_rate"]
            return {"saved_kwh": saved, "baseline_kwh": kwargs["baseline_kwh"], "saving_rate": kwargs["saving_rate"], "data_schema": "energy_savings.v1"}
        if skill == "calculate_emission_reduction":
            return {"reduced_tco2e": kwargs["saved_kwh"] * kwargs["emission_factor"] / 1000, "data_schema": "emission_reduction.v1"}
        return {"data_schema": f"{skill}.v1"}


@pytest.mark.asyncio
async def test_structured_data_flows_through_dependency_chain():
    plan = AnalysisPlan(tasks=[
        AnalysisTask(task_id="parameter_extraction", title="参数", objective="参数", allowed_skills=["extract_process_parameters"]),
        AnalysisTask(task_id="energy_analysis", title="节能", objective="节能", dependencies=["parameter_extraction"], allowed_skills=["calculate_energy_savings"]),
        AnalysisTask(task_id="carbon_analysis", title="碳排", objective="碳排", dependencies=["energy_analysis"], allowed_skills=["calculate_emission_reduction"]),
    ])
    results = await ManufacturingTaskExecutor(build_default_task_registry(FakeSkills()), FakeSkills()).execute(plan, {"query": "测试"})
    assert [r.status for r in results] == ["completed", "completed", "completed"]
    assert results[1].data["saved_kwh"] == 200
    assert math.isclose(results[2].data["reduced_tco2e"], 0.11406)


@pytest.mark.asyncio
async def test_financial_inputs_parse_from_query():
    class FinancialSkills:
        async def execute(self, skill, **kwargs):
            return {"payback_years": kwargs["investment"] / kwargs["annual_saving"], "data_schema": "financials.v1"}

    plan = AnalysisPlan(tasks=[AnalysisTask(
        task_id="financial_analysis", title="财务", objective="财务", allowed_skills=["calculate_project_financials"]
    )])
    result = (await ManufacturingTaskExecutor(build_default_task_registry(FinancialSkills()), FinancialSkills()).execute(
        plan, {"query": "预算300万元，每年节省180万元"}
    ))[0]
    assert result.status == "completed"
    assert result.data["payback_years"] == 300 / 180
