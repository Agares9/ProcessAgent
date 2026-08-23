"""Manufacturing workflow agents; no domain-specific permanent expert agents."""
from __future__ import annotations

import re
import json
from typing import Any

from app.harness.manufacturing_schemas import (
    AnalysisPlan,
    AnalysisTask,
    EnterpriseContext,
    ManufacturingIntent,
)
from app.llm.client import ChatMessage, LLMClient


class ManufacturingIntentAgent:
    """Extract a conservative manufacturing intent without inventing enterprise facts."""

    def infer(self, query: str, context: str = "") -> ManufacturingIntent:
        text = query.strip()
        lower = text.lower()
        objectives: list[str] = []
        mappings = {
            "降碳": "reduce_emissions", "碳排": "reduce_emissions", "节能": "reduce_energy",
            "能耗": "reduce_energy", "成本": "reduce_cost", "质量": "improve_quality",
            "良率": "improve_yield", "产能": "increase_capacity", "瓶颈": "remove_bottleneck",
            "设备": "improve_equipment", "工艺": "optimize_process", "合规": "check_compliance",
        }
        for keyword, objective in mappings.items():
            if keyword in text or keyword in lower:
                if objective not in objectives:
                    objectives.append(objective)
        processes = [p for p in ("机加工", "注塑", "焊接", "装配", "化工合成", "压缩空气", "蒸汽") if p in text]
        industries = [p for p in ("钢铁", "汽车", "电子", "化工", "包装", "建材") if p in text]
        constraints = re.findall(r"(?:不超过|低于|达到|在)\s*[^，。；;]+", text)
        missing = []
        if any(item in objectives for item in ("reduce_energy", "reduce_emissions", "reduce_cost")):
            missing.extend(["基线能耗", "产量和运行周期"])
        if "质量" in text or "良率" in text:
            missing.extend(["缺陷率或良率", "关键工艺参数"])
        return ManufacturingIntent(
            intent_type=objectives[0] if objectives else "general_manufacturing",
            objectives=objectives,
            industries=industries,
            processes=processes,
            constraints=constraints,
            requested_outputs=["问题分析", "候选措施", "实施建议"],
            missing_information=sorted(set(missing)),
            needs_clarification=bool(missing),
            confidence=0.7 if objectives else 0.4,
            raw={"source": "deterministic_fallback", "query": query, "context": context[:500]},
        )

    async def infer_async(self, query: str, llm: LLMClient | None = None, context: str = "") -> ManufacturingIntent:
        if llm is None or not llm.api_key:
            return self.infer(query, context)
        prompt = ("你是制造业意图识别助手，只输出JSON。字段：intent_type, objectives, industries, "
                  "processes, materials, equipment, constraints, requested_outputs, missing_information, "
                  f"needs_clarification, confidence。\n用户问题：{query}\n上下文：{context[:2000]}")
        try:
            data = await llm.complete_json([ChatMessage.system("严谨、保守，不得虚构企业事实。"), ChatMessage.user(prompt)], temperature=0.0)
            return ManufacturingIntent.model_validate(data)
        except Exception:
            return self.infer(query, context)


class EnterpriseContextAgent:
    """Build context from user-provided facts; private retrieval is injected by Skills later."""

    def build(self, query: str, intent: ManufacturingIntent, profile: dict[str, Any] | None = None) -> EnterpriseContext:
        profile = profile or {}
        company = profile.get("company_name") or profile.get("company")
        facts = []
        if company:
            from app.harness.manufacturing_schemas import ContextFact
            facts.append(ContextFact(name="company_name", value=company, source_type="user_input", confidence=0.9))
        return EnterpriseContext(
            workspace_id=str(profile.get("workspace_id", "default_company")),
            company_name=company,
            industries=sorted(set(intent.industries + list(profile.get("industries", [])))),
            processes=sorted(set(intent.processes + list(profile.get("processes", [])))),
            current_problems=[query],
            constraints=intent.constraints + list(profile.get("constraints", [])),
            facts=facts,
            missing_information=list(intent.missing_information),
        )


class LeadAgent:
    """Create a validated plan; roles are task labels, not permanent expert Agents."""

    def plan(self, intent: ManufacturingIntent, context: EnterpriseContext) -> AnalysisPlan:
        tasks = [
            AnalysisTask(
                task_id="knowledge_search", title="检索制造业知识", objective="检索相关标准、指南和案例",
                role="evidence_search", priority=1,
                allowed_skills=["search_manufacturing_knowledge", "search_case_studies", "get_document_evidence"],
                completion_criteria=["返回带文档和页码的证据"],
            ),
            AnalysisTask(
                task_id="applicability_check", title="分析适用条件", objective="判断候选措施与当前问题的适用性",
                role="applicability_analysis", priority=2, dependencies=["knowledge_search"],
                allowed_skills=["check_applicability", "compare_technical_options"],
                completion_criteria=["列出适用条件和限制"],
            ),
        ]
        return AnalysisPlan(tasks=tasks, assumptions=context.assumptions, missing_information=context.missing_information)

    async def plan_async(self, intent: ManufacturingIntent, context: EnterpriseContext, llm: LLMClient | None = None) -> AnalysisPlan:
        if llm is None or not llm.api_key:
            return self.plan(intent, context)
        prompt = ("你是制造业LeadAgent，只输出JSON对象{tasks:[...]}。每个任务字段：task_id,title,objective,role,"
                  "priority,dependencies,allowed_skills,completion_criteria。只能使用检索和适用性Skills，"
                  f"不得创建固定专业Agent。\n意图：{intent.model_dump_json()}\n上下文：{context.model_dump_json()}")
        try:
            data = await llm.complete_json([ChatMessage.system("只输出合法JSON。"), ChatMessage.user(prompt)], temperature=0.0)
            tasks = data.get("tasks", []) if isinstance(data, dict) else []
            plan = AnalysisPlan.model_validate({"tasks": tasks, "assumptions": context.assumptions, "missing_information": context.missing_information})
            allowed = {"search_manufacturing_knowledge", "search_case_studies", "get_document_evidence", "check_applicability", "compare_technical_options"}
            for task in plan.tasks:
                task.allowed_skills = [skill for skill in task.allowed_skills if skill in allowed]
            return plan
        except Exception:
            return self.plan(intent, context)


class VerifierAgent:
    """Deterministic evidence gate before synthesis."""

    def verify(self, results: list[Any]) -> dict[str, Any]:
        issues: list[str] = []
        citation_errors: list[str] = []
        for result in results:
            seen_chunks: set[str] = set()
            if getattr(result, "status", "") == "failed":
                issues.append(f"task_failed:{getattr(result, 'task_id', '')}")
            for artifact in getattr(result, "artifacts", []) or []:
                if isinstance(artifact, dict):
                    chunk_id = artifact.get("chunk_id", "")
                    source_id = artifact.get("source_id", "")
                    excerpt = artifact.get("excerpt", "")
                    page_start = artifact.get("page_start")
                else:
                    chunk_id = getattr(artifact, "chunk_id", "")
                    source_id = getattr(artifact, "source_id", "")
                    excerpt = getattr(artifact, "excerpt", "")
                    page_start = getattr(artifact, "page_start", None)
                if not source_id:
                    citation_errors.append(f"missing_source:{getattr(result, 'task_id', '')}")
                if not chunk_id:
                    citation_errors.append(f"missing_chunk:{getattr(result, 'task_id', '')}")
                if not excerpt.strip():
                    citation_errors.append(f"empty_excerpt:{chunk_id or source_id}")
                if page_start is not None and (not isinstance(page_start, int) or page_start < 1):
                    citation_errors.append(f"invalid_page:{chunk_id or source_id}")
                if chunk_id and chunk_id in seen_chunks:
                    citation_errors.append(f"duplicate_evidence:{chunk_id}")
                if chunk_id:
                    seen_chunks.add(chunk_id)
        issues.extend(citation_errors)
        passed = not issues
        score = 1.0 if passed else max(0.0, 1.0 - min(len(issues) * 0.2, 1.0))
        return {
            "passed": passed, "score": score, "issues": issues,
            "citation_errors": citation_errors,
            "required_revisions": issues,
        }


class ExecutiveSynthesisAgent:
    """Keep synthesis input to verified task results and explicit assumptions."""

    def synthesize(self, query: str, results: list[Any], verification: dict[str, Any]) -> dict[str, Any]:
        return {
            "executive_summary": "" if not verification.get("passed") else "已完成受控分析，等待填充经验证据。",
            "problem_definition": query,
            "findings": [r.model_dump() if hasattr(r, "model_dump") else r for r in results],
            "missing_data": [],
            "assumptions": [],
            "citations": [],
        }

    async def synthesize_async(self, query: str, results: list[Any], verification: dict[str, Any], llm: LLMClient | None = None) -> dict[str, Any]:
        if llm is None or not llm.api_key or not verification.get("passed"):
            return self.synthesize(query, results, verification)
        evidence = [r.model_dump() if hasattr(r, "model_dump") else r for r in results]
        prompt = ("你是制造业管理层方案汇总Agent，只输出JSON，字段：executive_summary, problem_definition, "
                  "findings, recommended_actions, implementation_roadmap, risks_and_constraints, missing_data, "
                  f"assumptions, citations。不得把外部案例效果写成企业实际结果。\n问题：{query}\n"
                  f"验证：{json.dumps(verification, ensure_ascii=False)}\n分析：{json.dumps(evidence, ensure_ascii=False)[:18000]}")
        try:
            data = await llm.complete_json([ChatMessage.system("只输出合法JSON，不输出推理过程。"), ChatMessage.user(prompt)])
            return data if isinstance(data, dict) else self.synthesize(query, results, verification)
        except Exception:
            return self.synthesize(query, results, verification)
