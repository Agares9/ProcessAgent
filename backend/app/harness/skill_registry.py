"""通用核心 Skill 与行业领域注册表。"""
from __future__ import annotations

CORE_SKILLS = ("retrieve", "understand", "analyze", "compare", "calculate", "optimize", "check", "verify")

DOMAIN_REGISTRY = {
    "manufacturing_process": {"industry": "manufacturing", "skills": ("understand", "analyze", "calculate"), "metrics": ("产量", "良率", "节拍", "单位能耗")},
    "manufacturing_equipment": {"industry": "manufacturing", "skills": ("understand", "analyze", "optimize"), "metrics": ("开机率", "故障率", "停机时间")},
    "retail_inventory": {"industry": "retail", "skills": ("understand", "analyze", "optimize"), "metrics": ("库存周转率", "缺货率", "库存金额")},
    "retail_store": {"industry": "retail", "skills": ("understand", "analyze", "compare"), "metrics": ("客流", "转化率", "坪效", "毛利")},
    "transport_fleet": {"industry": "transport", "skills": ("understand", "analyze", "optimize"), "metrics": ("油耗", "装载率", "车辆利用率")},
    "transport_route": {"industry": "transport", "skills": ("understand", "calculate", "optimize"), "metrics": ("里程", "运输成本", "准时率")},
    "pharma_quality": {"industry": "pharma", "skills": ("understand", "analyze", "verify"), "metrics": ("批次合格率", "偏差率", "CAPA")},
    "pharma_compliance": {"industry": "pharma", "skills": ("retrieve", "check", "verify"), "metrics": ("法规条款", "审计发现")},
    "energy_asset": {"industry": "energy", "skills": ("understand", "analyze", "optimize"), "metrics": ("负荷", "能效", "可用率")},
    "energy_emissions": {"industry": "energy", "skills": ("retrieve", "calculate", "verify"), "metrics": ("排放量", "排放因子", "减排量")},
    "construction_project": {"industry": "construction", "skills": ("understand", "analyze", "optimize"), "metrics": ("进度", "工程量", "预算")},
    "construction_safety": {"industry": "construction", "skills": ("retrieve", "check", "verify"), "metrics": ("隐患数", "事故率", "整改率")},
    "finance_operations": {"industry": "finance", "skills": ("understand", "analyze", "calculate", "compare"), "metrics": ("收入", "成本", "利润", "现金流", "ROI")},
    "finance_risk_compliance": {"industry": "finance", "skills": ("retrieve", "analyze", "check", "verify"), "metrics": ("风险敞口", "违约率", "资本充足率", "合规项")},
}

def get_domain(domain: str) -> dict:
    return DOMAIN_REGISTRY.get(domain, {"industry": "general", "skills": CORE_SKILLS, "metrics": ()})
