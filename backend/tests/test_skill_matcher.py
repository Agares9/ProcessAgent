from app.harness.skill_matcher import ManufacturingSkillMatcher
from app.harness.manufacturing_schemas import ManufacturingIntent


def test_simple_matcher_is_small():
    intent = ManufacturingIntent(intent_type="general_manufacturing", complexity="simple")
    skills = ManufacturingSkillMatcher().match("什么是注塑工艺", intent)
    assert skills == ["search_manufacturing_knowledge", "verify_citations"]


def test_complex_matcher_adds_targeted_skills():
    intent = ManufacturingIntent(
        intent_type="reduce_energy", complexity="complex", objectives=["reduce_energy"],
        constraints=["预算不超过300万元"],
    )
    skills = ManufacturingSkillMatcher().match("比较方案并计算预算回收期和碳排", intent)
    assert "calculate_energy_savings" in skills
    assert "calculate_project_financials" in skills
    assert "calculate_emission_reduction" in skills
    assert "compare_technical_options" in skills
    assert "check_constraint_compliance" in skills
