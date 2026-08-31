"""Manufacturing workflow agents; no domain-specific permanent expert agents."""
from __future__ import annotations

import re
import json
from typing import Any

from app.harness.manufacturing_schemas import (
    AnalysisPlan,
    AnalysisPlanDraft,
    AnalysisTask,
    EnterpriseContext,
    ManufacturingIntent,
    ScenarioIntent,
)
from app.llm.client import ChatMessage, LLMClient
from app.llm.structured import StructuredLLM


class ScenarioIntentAgent:
    """Extract a conservative manufacturing intent without inventing enterprise facts."""

    def infer(self, query: str, context: str = "") -> ScenarioIntent:
        text = query.strip()
        lower = text.lower()
        if any(k in text for k in ("你能做什么", "你会什么", "你的功能", "你是谁", "你是什么助手")):
            return ScenarioIntent(intent_type="capability_query", industry="general", domain="capability", business_domain="general", scenario_type="capability", response_mode="capability_info", complexity="simple", confidence=0.99, raw={"source": "deterministic_fallback", "query": query})
        if text in {"你好", "您好", "嗨", "hello", "hi"}:
            return ScenarioIntent(intent_type="chitchat", industry="general", domain="general_chat", business_domain="general", scenario_type="chat", response_mode="boundary_redirect", complexity="simple", confidence=0.99, raw={"source": "deterministic_fallback", "query": query})
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
        complexity_score = 0
        if len(text) > 80:
            complexity_score += 1
        if len(objectives) > 1 or len(constraints) > 1:
            complexity_score += 1
        if any(token in text for token in ("预算", "回收期", "投资", "多家工厂", "路线图", "对比", "优化方案")):
            complexity_score += 2
        complexity = "complex" if complexity_score >= 3 else "standard" if complexity_score >= 1 else "simple"
        # Generic industry hints are intentionally small and extensible; detailed
        # routing belongs to registered Skills rather than permanent expert agents.
        industry = "manufacturing"
        business_domain = "general"
        for marker, value in (("门店", "retail"), ("库存", "retail"), ("车辆", "transport"), ("路线", "transport"), ("运输", "transport"), ("财务", "finance"), ("现金流", "finance"), ("GMP", "pharma"), ("药品", "pharma"), ("能源资产", "energy"), ("施工", "construction")):
            if marker in text:
                industry = value
                break
        if industry == "retail":
            business_domain = "inventory" if "库存" in text else "store"
        elif industry == "transport":
            business_domain = "route" if "路线" in text else "fleet"
        elif industry == "finance":
            business_domain = "risk_compliance" if any(x in text for x in ("风险", "合规", "审计")) else "operations"
        elif industry == "pharma":
            business_domain = "compliance" if any(x in text for x in ("GMP", "法规", "审计")) else "quality"
        elif industry == "energy":
            business_domain = "emissions" if any(x in text for x in ("排放", "碳")) else "asset"
        elif industry == "construction":
            business_domain = "safety" if any(x in text for x in ("安全", "隐患")) else "project"
        return ScenarioIntent(
            intent_type=objectives[0] if objectives else "general_manufacturing",
            industry=industry, domain="manufacturing" if industry == "manufacturing" else industry, business_domain=business_domain, scenario_type="optimization", response_mode="analysis",
            complexity=complexity,
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

    async def infer_async(
        self, query: str, structured_llm: StructuredLLM | None = None, context: str = ""
    ) -> ScenarioIntent:
        if structured_llm is None:
            raise RuntimeError("ScenarioIntentAgent 必须使用 StructuredLLM")
        prompt = ("你是通用企业场景意图识别助手，只输出一个 JSON 对象，不要 Markdown。字段：industry, domain, business_domain, scenario_type, response_mode(analysis|capability_info|boundary_redirect), intent_type, complexity(simple|standard|complex), objectives, industries, entities, metrics, "
                  "processes, materials, equipment, constraints, requested_outputs, missing_information, "
                  f"needs_clarification, confidence。complexity由你根据问题范围、目标数量、约束、预算和是否需要多步骤决策判断。\n用户问题：{query}\n上下文：{context[:2000]}")
        result = await structured_llm.complete(
            [ChatMessage.system("严谨、保守，不得虚构企业事实。严格遵守字段类型。"), ChatMessage.user(prompt)],
            schema=ScenarioIntent,
            agent_name="scenario_intent",
            temperature=0.0,
        )
        result.raw = {"source": "structured_llm"}
        return result


class ManufacturingIntentAgent(ScenarioIntentAgent):
    """Backward-compatible manufacturing entry point."""


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
            industry=intent.industry,
            domain=intent.business_domain,
            scenario_type=intent.scenario_type,
            industries=sorted(set(intent.industries + list(profile.get("industries", [])))),
            entities=list(intent.entities) + list(profile.get("entities", [])),
            metrics=dict(intent.metrics) | dict(profile.get("metrics", {})),
            processes=sorted(set(intent.processes + list(profile.get("processes", [])))),
            current_problems=[query],
            constraints=intent.constraints + list(profile.get("constraints", [])),
            facts=facts,
            missing_information=list(intent.missing_information),
        )


class LeadAgent:
    """Create a validated plan; roles are task labels, not permanent expert Agents."""

    def plan(self, intent: ManufacturingIntent, context: EnterpriseContext) -> AnalysisPlan:
        industry = getattr(intent, "industry", "manufacturing")
        tasks = [
            AnalysisTask(
                task_id="knowledge_search", title=f"检索{industry}相关知识", objective="检索相关标准、指南和案例",
                role="evidence_search", priority=1,
                allowed_skills=["retrieve", "search_case_studies", "get_document_evidence"], input_data={"skill": "retrieve"},
                completion_criteria=["返回带文档和页码的证据"],
            ),
            AnalysisTask(
                task_id="applicability_check", title="分析适用条件", objective="判断候选措施与当前问题的适用性",
                role="applicability_analysis", priority=2, dependencies=["knowledge_search"],
                allowed_skills=["analyze", "compare", "check_applicability", "compare_technical_options"], input_data={"skill": "analyze"},
                completion_criteria=["列出适用条件和限制"],
            ),
        ]
        return AnalysisPlan(tasks=tasks, assumptions=context.assumptions, missing_information=context.missing_information)

    async def plan_async(
        self, intent: ManufacturingIntent, context: EnterpriseContext,
        structured_llm: StructuredLLM | None = None,
    ) -> AnalysisPlan:
        if structured_llm is None:
            raise RuntimeError("LeadAgent 必须使用 StructuredLLM")
        prompt = ("你是通用企业场景 LeadAgent，只输出JSON对象{tasks:[...]}。每个任务字段：task_id,title,objective,role,"
                  "priority,dependencies,allowed_skills,completion_criteria。allowed_skills 必须严格使用 JSON Schema 中的 Skill 枚举值，"
                  f"不得创建固定专业Agent。\n意图：{intent.model_dump_json()}\n上下文：{context.model_dump_json()}")
        draft = await structured_llm.complete(
            [ChatMessage.system("只输出符合字段类型的合法 JSON。"), ChatMessage.user(prompt)],
            schema=AnalysisPlanDraft,
            agent_name="lead_plan",
            temperature=0.0,
        )
        return AnalysisPlan(
            tasks=draft.tasks,
            assumptions=context.assumptions,
            missing_information=context.missing_information,
        )


class VerifierAgent:
    """Deterministic evidence gate before synthesis."""

    def verify(self, results: list[Any]) -> dict[str, Any]:
        execution_issues: list[str] = []
        citation_errors: list[str] = []
        retrieval_states: list[str] = []
        evidence_count = 0
        for result in results:
            seen_chunks: set[str] = set()
            data = getattr(result, "data", {}) or {}
            if data.get("retrieval_status"):
                retrieval_states.append(str(data["retrieval_status"]))
            if getattr(result, "status", "") == "failed":
                execution_issues.append(f"task_failed:{getattr(result, 'task_id', '')}")
            for artifact in getattr(result, "artifacts", []) or []:
                evidence_count += 1
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
        if "available" in retrieval_states or evidence_count:
            retrieval_status = "available"
        elif "error" in retrieval_states:
            retrieval_status = "error"
        elif "no_match" in retrieval_states:
            retrieval_status = "no_match"
        else:
            retrieval_status = "not_requested"
        citation_status = (
            "invalid" if citation_errors else
            "valid" if evidence_count else
            "not_available" if retrieval_status == "error" else
            "not_applicable"
        )
        passed = not citation_errors
        score = 1.0 if passed else max(0.0, 1.0 - min(len(citation_errors) * 0.2, 1.0))
        issues = execution_issues + citation_errors
        return {
            "passed": passed, "score": score, "issues": issues,
            "citation_errors": citation_errors,
            "citation_status": citation_status,
            "retrieval_status": retrieval_status,
            "evidence_count": evidence_count,
            "execution_issues": execution_issues,
            "required_revisions": citation_errors,
        }


class OrchestratorAgent:
    """Unified deterministic orchestration facade and evidence-grounded answer layer."""

    @staticmethod
    def _valid_evidence(results: list[Any]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        seen: set[str] = set()
        for result in results:
            for artifact in getattr(result, "artifacts", []) or []:
                item = artifact.model_dump() if hasattr(artifact, "model_dump") else dict(artifact)
                chunk_id = str(item.get("chunk_id") or "")
                if not item.get("source_id") or not chunk_id or not str(item.get("excerpt") or "").strip():
                    continue
                if chunk_id in seen:
                    continue
                seen.add(chunk_id)
                evidence.append(item)
        return evidence

    @staticmethod
    def _analysis_results(results: list[Any]) -> list[dict[str, Any]]:
        output = []
        for result in results:
            item = result.model_dump() if hasattr(result, "model_dump") else dict(result)
            if item.get("status") != "completed" or item.get("task_id") in {"knowledge_search", "citation_check"}:
                continue
            data = dict(item.get("data") or {})
            data.pop("execution", None)
            output.append({
                "task_id": item.get("task_id"),
                "summary": item.get("summary", ""),
                "data": data,
                "assumptions": item.get("assumptions") or [],
                "missing_information": item.get("missing_information") or [],
            })
        return output

    @staticmethod
    def _source_required(query: str) -> bool:
        return any(term in query for term in (
            "根据知识库", "依据知识库", "根据内部资料", "依据内部资料", "根据文献", "文献来源",
            "提供来源", "给出来源", "引用来源", "引用标准", "根据标准", "依据标准",
        ))

    def synthesize(self, query: str, results: list[Any], verification: dict[str, Any]) -> dict[str, Any]:
        findings = []
        citations = []
        for result in results:
            item = result.model_dump() if hasattr(result, "model_dump") else result
            for artifact in item.get("artifacts", []):
                findings.append({"finding": artifact.get("claim", "")[:300], "evidence": artifact.get("excerpt", "")[:1200], "source_id": artifact.get("source_id", ""), "chunk_id": artifact.get("chunk_id", ""), "page": artifact.get("page_start")})
                citations.append(artifact)
        return {
            "executive_summary": "已根据问题信息形成初步分析和可执行建议。",
            "problem_definition": query,
            "findings": findings,
            "recommended_actions": ["先确认工艺、设备和能耗基线，再按证据适用条件筛选改造措施。"],
            "implementation_roadmap": ["第一步：补齐现场基线数据。", "第二步：对候选措施做适用性和投资回收期评估。"],
            "risks_and_constraints": ["文档案例结果不能直接视为当前企业的实际节能结果。"],
            "missing_data": ["具体工艺环节", "能耗基线", "设备和运行周期"],
            "assumptions": ["当前未提供完整企业现场数据"],
            "citations": citations,
        }

    async def synthesize_async(self, query: str, results: list[Any], verification: dict[str, Any], llm: LLMClient | None = None) -> dict[str, Any]:
        if llm is None or not llm.api_key:
            return self.synthesize(query, results, verification)
        evidence = self._valid_evidence(results)
        answer_context = {
            "query": query,
            "analysis_results": self._analysis_results(results),
            "evidence": evidence,
            "evidence_status": "available" if evidence else "none",
            "source_required": self._source_required(query),
        }
        prompt = (
            "你是通用企业场景分析助手。请优先直接解决用户的问题，用自然、清晰的中文回答，不要输出JSON，"
            "不要机械填充固定报告模板。知识库资料只是可选参考，不是回答前提。\n"
            "规则：\n"
            "1. evidence 中有相关资料时，可以结合资料分析；使用其中事实、数字或案例时必须标注来源。\n"
            "2. evidence 为空时，直接基于你的专业知识正常回答，不要把缺少资料描述为系统失败或不完整回答。\n"
            "3. 除非 source_required=true，否则不要提及知识库、检索状态、证据检索失败或等待知识库恢复。\n"
            "4. source_required=true 且 evidence 为空时，应明确无法满足可核验来源要求，但仍可把一般专业分析单独说明。\n"
            "5. 不得虚构企业现场数据；缺少现场数据时，可以给出常见原因、分析方法、实施建议和需要补充的数据。\n"
            "6. 外部案例数字不能直接当作当前企业结果；无关证据不要使用。\n"
            f"回答上下文：{json.dumps(answer_context, ensure_ascii=False)[:18000]}"
        )
        try:
            content = await llm.complete([ChatMessage.system("你是流畅、严谨的企业场景回答助手。只输出最终回答，不输出JSON和推理过程。"), ChatMessage.user(prompt)], temperature=0.3)
            if not content.strip():
                return self.synthesize(query, results, verification)
            return {"executive_summary": content, "problem_definition": query, "findings": [], "recommended_actions": [], "implementation_roadmap": [], "risks_and_constraints": [], "missing_data": [], "assumptions": [], "citations": evidence}
        except Exception:
            raise
