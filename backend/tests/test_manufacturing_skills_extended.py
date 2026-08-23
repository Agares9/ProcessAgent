import pytest

from app.harness.manufacturing_skills import ManufacturingSkillAccess


@pytest.mark.asyncio
async def test_extended_skills_without_backends():
    skills = ManufacturingSkillAccess(None, None, None)
    params = await skills.execute("extract_process_parameters", text="注塑温度220℃，压力80 MPa，功率180 kW")
    assert params["parameters"]["temperature"]["value"] == 220
    assert params["source_type"] == "user_input"
    finance = await skills.execute("calculate_project_financials", investment=100, annual_saving=60, annual_operating_cost=10)
    assert finance["payback_years"] == 2.0
    assert finance["source_type"] == "calculation"
    assert "investment /" in finance["formula"]
    energy = await skills.execute("calculate_energy_savings", baseline_kwh=1000, saving_rate=0.2)
    carbon = await skills.execute("calculate_emission_reduction", saved_kwh=energy["saved_kwh"], emission_factor=0.5)
    assert carbon["reduced_tco2e"] == 0.1
    comparison = await skills.execute("compare_technical_options", options=[{"name": "A", "saving": 1}, {"name": "B", "saving": 2}])
    assert comparison["recommended_option"] == "B"
    citations = await skills.execute("verify_citations", claims=[{"source_id": "d", "chunk_id": "c", "excerpt": "e"}])
    assert citations["passed"] is True
    constraints = await skills.execute("check_constraint_compliance", proposal={"investment": 120}, constraints={"max_investment": 100})
    assert constraints["compliant"] is False
