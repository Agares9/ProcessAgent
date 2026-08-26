"""轻量、可测试的领域分析函数；不依赖外部知识库。"""
from __future__ import annotations
from typing import Any

def _missing(data: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    return [k for k in keys if data.get(k) is None]

def manufacturing_process(data: dict[str, Any]) -> dict[str, Any]:
    m = _missing(data, ("output", "defect_rate"))
    return {"domain":"manufacturing_process", "metrics":{"good_output": (1-float(data.get("defect_rate",0)))*float(data.get("output",0)) if not m else None}, "missing":m, "data_schema":"manufacturing_process.v1"}

def manufacturing_equipment(data: dict[str, Any]) -> dict[str, Any]:
    m = _missing(data, ("runtime_hours", "downtime_hours"))
    return {"domain":"manufacturing_equipment", "metrics":{"availability": (float(data.get("runtime_hours",0))/(float(data.get("runtime_hours",0))+float(data.get("downtime_hours",0)))) if not m else None}, "missing":m, "data_schema":"manufacturing_equipment.v1"}

def retail_inventory(data: dict[str, Any]) -> dict[str, Any]:
    m = _missing(data, ("average_inventory", "sales"))
    return {"domain":"retail_inventory", "metrics":{"turnover": float(data.get("sales",0))/float(data.get("average_inventory",1)) if not m else None}, "missing":m, "data_schema":"retail_inventory.v1"}

def retail_store(data: dict[str, Any]) -> dict[str, Any]:
    m = _missing(data, ("transactions", "visitors"))
    return {"domain":"retail_store", "metrics":{"conversion_rate": float(data.get("transactions",0))/float(data.get("visitors",1)) if not m else None}, "missing":m, "data_schema":"retail_store.v1"}

def transport_fleet(data: dict[str, Any]) -> dict[str, Any]:
    m = _missing(data, ("loaded_distance", "total_distance"))
    return {"domain":"transport_fleet", "metrics":{"utilization": float(data.get("loaded_distance",0))/float(data.get("total_distance",1)) if not m else None}, "missing":m, "data_schema":"transport_fleet.v1"}

def transport_route(data: dict[str, Any]) -> dict[str, Any]:
    m = _missing(data, ("distance", "fuel_rate", "fuel_price"))
    return {"domain":"transport_route", "metrics":{"fuel_cost": float(data.get("distance",0))*float(data.get("fuel_rate",0))*float(data.get("fuel_price",0)) if not m else None}, "missing":m, "data_schema":"transport_route.v1"}

def pharma_quality(data: dict[str, Any]) -> dict[str, Any]:
    m = _missing(data, ("passed_batches", "total_batches"))
    return {"domain":"pharma_quality", "metrics":{"pass_rate": float(data.get("passed_batches",0))/float(data.get("total_batches",1)) if not m else None}, "missing":m, "data_schema":"pharma_quality.v1"}

def pharma_compliance(data: dict[str, Any]) -> dict[str, Any]:
    return {"domain":"pharma_compliance", "compliant": bool(data.get("evidence")), "missing": [] if data.get("evidence") else ["法规证据"], "data_schema":"pharma_compliance.v1"}

def energy_asset(data: dict[str, Any]) -> dict[str, Any]:
    m = _missing(data, ("useful_output", "energy_input"))
    return {"domain":"energy_asset", "metrics":{"efficiency": float(data.get("useful_output",0))/float(data.get("energy_input",1)) if not m else None}, "missing":m, "data_schema":"energy_asset.v1"}

def energy_emissions(data: dict[str, Any]) -> dict[str, Any]:
    m = _missing(data, ("energy", "emission_factor"))
    return {"domain":"energy_emissions", "metrics":{"emissions": float(data.get("energy",0))*float(data.get("emission_factor",0)) if not m else None}, "missing":m, "data_schema":"energy_emissions.v1"}

def construction_project(data: dict[str, Any]) -> dict[str, Any]:
    m = _missing(data, ("planned_progress", "actual_progress"))
    return {"domain":"construction_project", "metrics":{"schedule_variance": float(data.get("actual_progress",0))-float(data.get("planned_progress",0)) if not m else None}, "missing":m, "data_schema":"construction_project.v1"}

def construction_safety(data: dict[str, Any]) -> dict[str, Any]:
    return {"domain":"construction_safety", "risk_level":"high" if data.get("hazards",0)>0 else "normal", "missing":[], "data_schema":"construction_safety.v1"}

def finance_operations(data: dict[str, Any]) -> dict[str, Any]:
    m = _missing(data, ("revenue", "cost"))
    return {"domain":"finance_operations", "metrics":{"profit": float(data.get("revenue",0))-float(data.get("cost",0)) if not m else None}, "missing":m, "data_schema":"finance_operations.v1"}

def finance_risk_compliance(data: dict[str, Any]) -> dict[str, Any]:
    return {"domain":"finance_risk_compliance", "risk_level": data.get("risk_level", "unknown"), "compliant": bool(data.get("evidence")), "missing": [] if data.get("evidence") else ["合规证据"], "data_schema":"finance_risk_compliance.v1"}

DOMAIN_HANDLERS = {name: globals()[name] for name in tuple(DOMAIN_REGISTRY) if name in globals()} if False else {
    "manufacturing_process": manufacturing_process, "manufacturing_equipment": manufacturing_equipment,
    "retail_inventory": retail_inventory, "retail_store": retail_store, "transport_fleet": transport_fleet, "transport_route": transport_route,
    "pharma_quality": pharma_quality, "pharma_compliance": pharma_compliance, "energy_asset": energy_asset, "energy_emissions": energy_emissions,
    "construction_project": construction_project, "construction_safety": construction_safety,
    "finance_operations": finance_operations, "finance_risk_compliance": finance_risk_compliance,
}
