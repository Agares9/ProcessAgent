"""基于行业元数据的动态 Skill 匹配；保留制造业兼容入口。"""
from __future__ import annotations

from app.harness.manufacturing_schemas import ManufacturingIntent, ScenarioIntent
from app.harness.skill_registry import DOMAIN_REGISTRY, get_domain


class ScenarioSkillMatcher:
    """Match shared skills plus registered industry skills without expert agents."""

    CORE_SKILLS = ("retrieve", "understand", "analyze", "compare", "calculate", "optimize", "check", "verify")
    LEGACY_ALIASES = {
        "search_manufacturing_knowledge": "retrieve", "search_knowledge": "retrieve", "search_case_studies": "retrieve",
        "get_document_evidence": "retrieve", "extract_process_parameters": "understand", "extract_metrics": "understand",
        "check_applicability": "analyze", "compare_technical_options": "compare", "compare_options": "compare",
        "calculate_project_financials": "calculate", "calculate_energy_savings": "calculate", "calculate_emission_reduction": "calculate",
        "calculate_transport_cost": "calculate", "check_constraint_compliance": "check", "verify_citations": "verify",
    }

    @classmethod
    def canonicalize(cls, skills: list[str]) -> list[str]:
        """Convert legacy implementation names to the stable public contract."""
        return list(dict.fromkeys(cls.LEGACY_ALIASES.get(skill, skill) for skill in skills))

    _industry_skills: dict[str, list[str]] = {
        "retail": ["analyze_retail_inventory", "analyze_store_operations"],
        "transport": ["analyze_transport_routes", "calculate_transport_cost"],
    }

    @classmethod
    def register_industry_skills(cls, industry: str, skills: list[str]) -> None:
        cls._industry_skills[industry] = list(dict.fromkeys(skills))

    def match(self, query: str, intent: ScenarioIntent) -> list[str]:
        domain_name = f"{getattr(intent, 'industry', 'general')}_{getattr(intent, 'business_domain', 'general')}"
        domain = get_domain(domain_name) if domain_name in DOMAIN_REGISTRY else {"skills": ()}
        skills = list(self._industry_skills.get(intent.industry, []))
        skills.extend(domain.get("skills", ()))
        if intent.industry == "manufacturing":
            skills.append("search_manufacturing_knowledge")
        else:
            skills.append("search_knowledge")
        if intent.complexity in {"standard", "complex"}:
            skills.extend(["search_case_studies", "check_applicability"])
        if intent.complexity == "complex":
            skills.append("extract_metrics")
        text = f"{query} {' '.join(intent.objectives)} {' '.join(intent.constraints)}"
        if any(k in text for k in ("能耗", "节能", "电耗", "能源", "油耗", "reduce_energy")):
            skills.append("calculate_energy_savings")
        if any(k in text for k in ("碳排", "降碳", "碳达峰", "碳中和", "reduce_emissions")):
            skills.append("calculate_emission_reduction")
        if any(k in text for k in ("预算", "投资", "回收期", "成本", "费用", "payback")):
            skills.append("calculate_project_financials")
        if any(k in text for k in ("对比", "比较", "方案", "option")) and intent.complexity != "simple":
            skills.append("compare_options")
        if intent.constraints:
            skills.append("check_constraint_compliance")
        skills.append("verify_citations")
        return self.canonicalize(skills)


class ManufacturingSkillMatcher:
    def match(self, query: str, intent: ManufacturingIntent) -> list[str]:
        # Delegate shared routing while retaining the historical skill names.
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
