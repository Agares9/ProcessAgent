"""MediX-style dynamic Skill matching for manufacturing questions."""
from __future__ import annotations

from app.harness.manufacturing_schemas import ManufacturingIntent


class ManufacturingSkillMatcher:
    def match(self, query: str, intent: ManufacturingIntent) -> list[str]:
        skills = ["search_manufacturing_knowledge"]
        if intent.complexity in {"standard", "complex"}:
            skills.append("search_case_studies")
            skills.append("check_applicability")
        if intent.complexity == "complex":
            skills.append("extract_process_parameters")
        text = f"{query} {' '.join(intent.objectives)} {' '.join(intent.constraints)}"
        if any(k in text for k in ("能耗", "节能", "电耗", "能源", "reduce_energy")):
            skills.append("calculate_energy_savings")
        if any(k in text for k in ("碳排", "降碳", "碳达峰", "碳中和", "reduce_emissions")):
            skills.append("calculate_emission_reduction")
        if any(k in text for k in ("预算", "投资", "回收期", "成本", "payback")):
            skills.append("calculate_project_financials")
        if any(k in text for k in ("对比", "比较", "方案", "option")) and intent.complexity != "simple":
            skills.append("compare_technical_options")
        if intent.constraints:
            skills.append("check_constraint_compliance")
        skills.append("verify_citations")
        return list(dict.fromkeys(skills))
