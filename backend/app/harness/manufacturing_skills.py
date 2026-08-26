"""Whitelisted skills for controlled access to the manufacturing knowledge base."""
from __future__ import annotations

from typing import Any
import re

from app.llm.embeddings import EmbeddingClient
from app.retrieval.vector_store import VectorStore
from app.storage.store import DataStore
from app.harness.domain_skills import DOMAIN_HANDLERS


class ManufacturingSkillAccess:
    """Skill gateway; callers never receive the underlying store or vector client."""

    ALLOWED_SKILLS = {
        "retrieve", "understand", "analyze", "compare", "calculate", "optimize", "check", "verify",
        "search_manufacturing_knowledge",
        "search_case_studies",
        "get_document_evidence",
        "get_enterprise_profile",
        "get_factory_process_map",
        "extract_process_parameters", "check_applicability", "compare_technical_options",
        "calculate_project_financials", "calculate_energy_savings", "calculate_emission_reduction",
        "verify_citations", "check_constraint_compliance",
        "search_knowledge", "extract_metrics", "compare_options",
        "analyze_retail_inventory", "analyze_store_operations",
        "analyze_transport_routes", "calculate_transport_cost",
    }

    def __init__(self, store: DataStore, vector_store: VectorStore, embeddings: EmbeddingClient) -> None:
        self._store = store
        self._vectors = vector_store
        self._embeddings = embeddings

    async def execute(self, skill: str, **kwargs: Any) -> Any:
        operation = kwargs.pop("operation", None) or kwargs.get("analysis_type") or kwargs.get("calculation_type") or kwargs.get("optimization_type")
        domain = kwargs.pop("domain", None)
        if domain and domain not in DOMAIN_HANDLERS and kwargs.get("industry"):
            domain = f"{kwargs['industry']}_{domain}"
        if domain in DOMAIN_HANDLERS and skill in {"analyze", "understand", "calculate", "optimize", "check", "verify"}:
            return DOMAIN_HANDLERS[domain](kwargs)
        core_dispatch = {
            "retrieve": "search_knowledge", "understand": "extract_process_parameters" if operation == "process_parameters" else "extract_metrics",
            "analyze": "check_applicability" if operation in {None, "applicability"} else None, "compare": "compare_options",
            "check": "check_constraint_compliance", "verify": "verify_citations",
        }
        if skill == "analyze" and core_dispatch["analyze"] is None:
            return {"analysis_type": operation, "result": "需要领域处理器提供该分析类型", "missing": ["领域分析规则"], "data_schema": "analysis.v1"}
        if skill == "calculate":
            skill = {"energy_savings": "calculate_energy_savings", "emission_reduction": "calculate_emission_reduction", "financials": "calculate_project_financials", "transport_cost": "calculate_transport_cost"}.get(kwargs.pop("calculation_type", "financials"), "calculate_project_financials")
        else:
            skill = core_dispatch.get(skill, skill)
        if skill not in self.ALLOWED_SKILLS:
            raise PermissionError(f"skill not allowed: {skill}")
        return await getattr(self, skill)(**kwargs)

    async def search_manufacturing_knowledge(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        return await self._search(query, top_k=top_k)

    async def search_knowledge(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        return await self._search(query, top_k=top_k)

    async def extract_metrics(self, text: str) -> dict[str, Any]:
        return {"metrics": {}, "missing": ["业务指标"], "source_type": "user_input", "source_text": text, "data_schema": "metrics.v1"}

    async def compare_options(self, options: list[dict[str, Any]], criteria: dict[str, float] | None = None) -> dict[str, Any]:
        return await self.compare_technical_options(options, criteria)

    async def analyze_retail_inventory(self, **kwargs: Any) -> dict[str, Any]:
        return {"industry": "retail", "analysis": "需要库存、销量、补货周期和缺货率数据", "missing": ["库存量", "销量", "补货周期"], "data_schema": "retail_inventory.v1"}

    async def analyze_store_operations(self, **kwargs: Any) -> dict[str, Any]:
        return {"industry": "retail", "analysis": "需要门店客流、转化率、坪效和毛利数据", "missing": ["客流", "转化率", "坪效"], "data_schema": "store_operations.v1"}

    async def analyze_transport_routes(self, **kwargs: Any) -> dict[str, Any]:
        return {"industry": "transport", "analysis": "需要路线里程、时效、装载率和油耗数据", "missing": ["里程", "装载率", "油耗"], "data_schema": "transport_routes.v1"}

    async def calculate_transport_cost(self, distance: float = 0, fuel_rate: float = 0, fuel_price: float = 0, **kwargs: Any) -> dict[str, Any]:
        cost = float(distance) * float(fuel_rate) * float(fuel_price)
        return {"distance": float(distance), "fuel_rate": float(fuel_rate), "fuel_price": float(fuel_price), "fuel_cost": cost, "unit": "CNY", "data_schema": "transport_cost.v1"}

    async def search_case_studies(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        hits = await self._search(query, top_k=max(top_k * 3, 10))
        return [hit for hit in hits if hit.get("doc_type") == "case_study"][:top_k]

    async def _search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        vector = await self._embeddings.embed_query(query)
        hits = await self._vectors.search(vector, top_k=top_k)
        output: list[dict[str, Any]] = []
        for hit in hits:
            chunk = await self._store.get("chunks", hit.get("id", ""))
            if not chunk:
                continue
            doc = await self._store.get_document(str(hit.get("doc_id", "")))
            metadata = chunk.get("metadata") or {}
            output.append({
                "chunk_id": chunk.get("_id", ""), "doc_id": chunk.get("doc_id", ""),
                "doc_title": (doc or {}).get("title", ""), "score": hit.get("score", 0.0),
                "page_start": metadata.get("page_start"), "page_end": metadata.get("page_end"),
                "process": metadata.get("process", ""), "evidence_level": metadata.get("evidence_level", "F"),
                "excerpt": chunk.get("content", ""), "visibility": "enterprise_private",
            })
        return output

    async def get_document_evidence(self, chunk_id: str) -> dict[str, Any] | None:
        chunk = await self._store.get("chunks", chunk_id)
        if not chunk:
            return None
        doc = await self._store.get_document(chunk.get("doc_id", ""))
        metadata = chunk.get("metadata") or {}
        return {
            "chunk_id": chunk.get("_id", ""), "doc_id": chunk.get("doc_id", ""),
            "doc_title": (doc or {}).get("title", ""), "page_start": metadata.get("page_start"),
            "page_end": metadata.get("page_end"), "excerpt": chunk.get("content", ""),
            "visibility": "enterprise_private",
        }

    async def get_enterprise_profile(self, workspace_id: str = "default_company") -> dict[str, Any]:
        return {"workspace_id": workspace_id, "source": "configured_profile", "facts": []}

    async def get_factory_process_map(self, workspace_id: str = "default_company") -> dict[str, Any]:
        return {"workspace_id": workspace_id, "factories": [], "processes": []}

    async def extract_process_parameters(self, text: str) -> dict[str, Any]:
        patterns = {
            "temperature": r"温度[^0-9]{0,8}([0-9]+(?:\.[0-9]+)?)\s*(°C|℃|摄氏度)?",
            "pressure": r"压力[^0-9]{0,8}([0-9]+(?:\.[0-9]+)?)\s*(MPa|kPa|bar)?",
            "power_kw": r"功率[^0-9]{0,8}([0-9]+(?:\.[0-9]+)?)\s*(kW|千瓦)?",
            "cycle_time_s": r"(?:周期|循环时间|节拍)[^0-9]{0,8}([0-9]+(?:\.[0-9]+)?)\s*(秒|s)?",
            "energy_kwh": r"(?:电耗|用电量|能耗)[^0-9]{0,8}([0-9]+(?:\.[0-9]+)?)\s*(kWh|度)?",
        }
        values = {}
        for name, pattern in patterns.items():
            match = re.search(pattern, text, re.I)
            if match:
                values[name] = {"value": float(match.group(1)), "unit": match.group(2) or ""}
        processes = [p for p in ("机加工", "注塑", "焊接", "装配", "化工合成", "压缩空气", "蒸汽") if p in text]
        return {"processes": processes, "parameters": values, "missing": [] if values else ["工艺参数"], "source_type": "user_input", "source_text": text, "data_schema": "process_parameters.v1"}

    async def check_applicability(self, option: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        text = str(context)
        blockers = []
        if not text.strip():
            blockers.append("缺少工艺或设备上下文")
        if "预算" in text and "预算" not in option:
            blockers.append("需要核对预算约束")
        return {"applicable": not blockers, "conditions": ["需通过现场数据验证"], "limitations": blockers, "confidence": 0.6 if not blockers else 0.3}

    async def compare_technical_options(self, options: list[dict[str, Any]], criteria: dict[str, float] | None = None) -> dict[str, Any]:
        criteria = criteria or {"saving": 0.4, "cost": 0.25, "risk": 0.2, "fit": 0.15}
        ranked = []
        for item in options:
            score = sum(float(item.get(key, 0)) * weight for key, weight in criteria.items())
            ranked.append({**item, "score": round(score, 4)})
        ranked.sort(key=lambda x: x["score"], reverse=True)
        return {"options": ranked, "recommended_option": ranked[0].get("name") if ranked else None, "criteria": criteria}

    async def calculate_project_financials(self, investment: float, annual_saving: float, annual_operating_cost: float = 0.0) -> dict[str, Any]:
        net = float(annual_saving) - float(annual_operating_cost)
        return {"investment": float(investment), "annual_gross_saving": float(annual_saving), "annual_net_saving": net, "payback_years": round(float(investment) / net, 2) if net > 0 else None, "source_type": "calculation", "formula": "investment / (annual_saving - annual_operating_cost)", "inputs": {"investment": float(investment), "annual_saving": float(annual_saving), "annual_operating_cost": float(annual_operating_cost)}, "data_schema": "financials.v1"}

    async def calculate_energy_savings(self, baseline_kwh: float, saving_rate: float) -> dict[str, Any]:
        saved = float(baseline_kwh) * float(saving_rate)
        return {"baseline_kwh": float(baseline_kwh), "saving_rate": float(saving_rate), "saved_kwh": saved, "remaining_kwh": float(baseline_kwh) - saved, "unit": "kWh", "source_type": "calculation", "formula": "baseline_kwh * saving_rate", "inputs": {"baseline_kwh": float(baseline_kwh), "saving_rate": float(saving_rate)}, "data_schema": "energy_savings.v1"}

    async def calculate_emission_reduction(self, saved_kwh: float, emission_factor: float = 0.5703) -> dict[str, Any]:
        return {"saved_kwh": float(saved_kwh), "emission_factor": float(emission_factor), "reduced_kgco2e": float(saved_kwh) * float(emission_factor), "reduced_tco2e": float(saved_kwh) * float(emission_factor) / 1000, "unit": "tCO2e", "source_type": "calculation", "formula": "saved_kwh * emission_factor / 1000", "inputs": {"saved_kwh": float(saved_kwh), "emission_factor": float(emission_factor)}, "data_schema": "emission_reduction.v1"}

    async def verify_citations(self, claims: list[dict[str, Any]]) -> dict[str, Any]:
        errors = []
        for i, claim in enumerate(claims):
            if not claim.get("source_id") or not claim.get("chunk_id"):
                errors.append(f"claim[{i}] 缺少 source_id 或 chunk_id")
            if not claim.get("excerpt"):
                errors.append(f"claim[{i}] 缺少摘录")
        return {"passed": not errors, "errors": errors, "checked": len(claims)}

    async def check_constraint_compliance(self, proposal: dict[str, Any], constraints: dict[str, Any]) -> dict[str, Any]:
        violations = []
        if constraints.get("max_investment") is not None and proposal.get("investment", 0) > constraints["max_investment"]:
            violations.append("超过最大投资额")
        if constraints.get("max_payback_years") is not None and proposal.get("payback_years") is not None and proposal["payback_years"] > constraints["max_payback_years"]:
            violations.append("超过目标回收期")
        return {"compliant": not violations, "violations": violations}
