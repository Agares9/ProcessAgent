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
    ScenarioIntent,
)
from app.llm.client import ChatMessage, LLMClient


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

    async def infer_async(self, query: str, llm: LLMClient | None = None, context: str = "") -> ScenarioIntent:
        if llm is None or not llm.api_key:
            return self.infer(query, context)
        prompt = ("你是通用企业场景意图识别助手，只输出JSON。字段：industry, domain, business_domain, scenario_type, response_mode(analysis|capability_info|boundary_redirect), intent_type, complexity(simple|standard|complex), objectives, industries, entities, metrics, "
                  "processes, materials, equipment, constraints, requested_outputs, missing_information, "
                  f"needs_clarification, confidence。complexity由你根据问题范围、目标数量、约束、预算和是否需要多步骤决策判断。\n用户问题：{query}\n上下文：{context[:2000]}")
        try:
            data = await llm.complete_json([ChatMessage.system("严谨、保守，不得虚构企业事实。"), ChatMessage.user(prompt)], temperature=0.0)
            return ScenarioIntent.model_validate(data)
        except Exception:
            return self.infer(query, context)


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

    async def plan_async(self, intent: ManufacturingIntent, context: EnterpriseContext, llm: LLMClient | None = None) -> AnalysisPlan:
        if llm is None or not llm.api_key:
            return self.plan(intent, context)
        prompt = ("你是通用企业场景 LeadAgent，只输出JSON对象{tasks:[...]}。每个任务字段：task_id,title,objective,role,"
                  "priority,dependencies,allowed_skills,completion_criteria。只能使用检索和适用性Skills，"
                  f"不得创建固定专业Agent。\n意图：{intent.model_dump_json()}\n上下文：{context.model_dump_json()}")
        try:
            data = await llm.complete_json([ChatMessage.system("只输出合法JSON。"), ChatMessage.user(prompt)], temperature=0.0)
            tasks = data.get("tasks", []) if isinstance(data, dict) else []
            plan = AnalysisPlan.model_validate({"tasks": tasks, "assumptions": context.assumptions, "missing_information": context.missing_information})
            allowed = {"retrieve", "understand", "analyze", "compare", "calculate", "optimize", "check", "verify", "search_manufacturing_knowledge", "search_case_studies", "get_document_evidence", "check_applicability", "compare_technical_options", "extract_process_parameters", "calculate_project_financials", "calculate_energy_savings", "calculate_emission_reduction", "verify_citations", "check_constraint_compliance"}
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


class OrchestratorAgent:
    """Unified deterministic orchestration facade and evidence-grounded answer layer."""

    def synthesize(self, query: str, results: list[Any], verification: dict[str, Any]) -> dict[str, Any]:
        findings = []
        citations = []
        for result in results:
            item = result.model_dump() if hasattr(result, "model_dump") else result
            for artifact in item.get("artifacts", []):
                findings.append({"finding": artifact.get("claim", "")[:300], "evidence": artifact.get("excerpt", "")[:1200], "source_id": artifact.get("source_id", ""), "chunk_id": artifact.get("chunk_id", ""), "page": artifact.get("page_start")})
                citations.append(artifact)
        return {
            "executive_summary": "未通过证据校验，暂不输出确定性结论。" if not verification.get("passed") else "已基于检索到的相关资料形成初步分析，具体措施仍需结合现场数据验证。",
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
        if llm is None or not llm.api_key or not verification.get("passed"):
            return self.synthesize(query, results, verification)
        evidence = [r.model_dump() if hasattr(r, "model_dump") else r for r in results]
        prompt = ("你是通用企业场景证据增强回答Agent。请直接用自然、清晰的中文回答用户，不要输出JSON，不要套用固定报告模板。"
                  "请根据问题复杂度自适应决定回答长度，简单问题简洁回答，复杂问题再展开方案。"
                  f"assumptions, citations。根据问题复杂度和用户需求自适应决定回答长度和章节：简单定义问题简洁回答，标准问题给出分点分析，复杂决策问题才给出完整方案。不要为了填模板虚构章节或内容；空数组必须保持为空。每条事实发现说明证据、适用条件或限制；不得把外部案例效果写成企业实际结果，引用必须包含source_id、chunk_id和页码。\n问题：{query}\n"
                  f"验证：{json.dumps(verification, ensure_ascii=False)}\n原始证据和任务结果：{json.dumps(evidence, ensure_ascii=False)[:18000]}\n"
                  "由你负责理解问题、取舍内容和组织自然流畅的回答，不要机械复述文档或填充固定模板。"
                  "不要单独输出固定标题‘如需进一步细化：’；如果确实有助于下一轮对话，可以自然地说明需要补充的信息。"
                  "本地文档只作为事实证据和边界：案例数字必须标明为案例，不能直接当作当前企业结果；证据与问题不相关时不要使用。"
                  "重要结论尽量标注来源编号或文档信息；没有证据支持的内容明确说明不确定性。")
        try:
            content = await llm.complete([ChatMessage.system("你是流畅、严谨的企业场景回答助手。只输出最终回答，不输出JSON和推理过程。"), ChatMessage.user(prompt)], temperature=0.3)
            if not content.strip():
                return self.synthesize(query, results, verification)
            return {"executive_summary": content, "problem_definition": query, "findings": [], "recommended_actions": [], "implementation_roadmap": [], "risks_and_constraints": [], "missing_data": [], "assumptions": [], "citations": []}
        except Exception:
            return self.synthesize(query, results, verification)
