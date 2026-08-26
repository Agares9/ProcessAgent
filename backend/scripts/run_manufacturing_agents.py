"""Run the five-agent manufacturing workflow from the command line."""
from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path

from app.config import Settings
from app.harness.agents.manufacturing_agents import (
    EnterpriseContextAgent,
    OrchestratorAgent,
    LeadAgent,
    ManufacturingIntentAgent,
    VerifierAgent,
)
from app.harness.manufacturing_skills import ManufacturingSkillAccess
from app.harness.task_executor import ManufacturingTaskExecutor, build_default_task_registry
from app.llm.embeddings import EmbeddingClient
from app.llm.deepseek import DeepSeekClient
from app.config import get_settings
from app.retrieval.vector_store import ChromaVectorStore
from app.storage.store import SQLiteStore
from app.storage.redis_store import MemorySessionStore
from app.memory.working import WorkingMemory
from app.memory.episodic import EpisodicMemory
from app.memory.user_semantic import UserSemanticMemory
from app.memory.organization import OrganizationMemory
from app.memory.learning import LearningMemory
from app.memory.context_builder import MemoryContextBuilder
from app.harness.manufacturing_schemas import AnalysisPlan, AnalysisTask
from app.harness.skill_matcher import ScenarioSkillMatcher
from app.harness.orchestrator import ScenarioOrchestratorFacade


def route_scope(query: str) -> str:
    """Deterministic safety gate before manufacturing retrieval."""
    manufacturing_terms = ("制造", "工厂", "车间", "产线", "设备", "工艺", "注塑", "机加工", "焊接", "装配", "化工", "能耗", "节能", "碳排", "质量", "良率", "生产")
    out_of_scope_terms = ("天气", "股票", "旅游", "写诗", "歌词", "做饭", "足球")
    if any(term in query for term in out_of_scope_terms) and not any(term in query for term in manufacturing_terms):
        return "out_of_scope"
    return "in_scope"


def merge_intent_entities(intent, previous_entities: dict) -> None:
    """Merge prior confirmed conversation entities into the current intent in place."""
    for field in ("objectives", "industries", "processes", "materials", "equipment", "constraints", "requested_outputs", "missing_information"):
        current = getattr(intent, field)
        prior = previous_entities.get(field, []) if isinstance(previous_entities, dict) else []
        if isinstance(current, list) and isinstance(prior, list):
            setattr(intent, field, list(dict.fromkeys(prior + current)))
    if previous_entities.get("intent_type") and intent.intent_type == "general_manufacturing":
        intent.intent_type = previous_entities["intent_type"]


async def run(query: str, top_k: int = 5, profile: dict | None = None, use_llm: bool = False,
              session_id: str = "cli-session", user_id: str = "cli-user") -> dict:
    scope = route_scope(query)
    if scope in {"out_of_scope", "general_chat", "capability"}:
        capability_answer = (
            "我可以帮助分析制造、零售、运输、医药、能源、建筑、金融等企业场景。"
            "具体包括：检索相关知识和案例，提取实体与指标，判断方案适用性，"
            "比较候选方案，计算成本、收益、能源和风险指标，并给出实施建议和所需补充数据。"
            "你可以直接描述一个业务问题，我会先基于已有资料回答，信息不足时再追问必要条件。"
        )
        return {
            "query": query,
            "route": {"scope": scope, "response_mode": "capability_info" if scope == "capability" else "boundary_redirect", "reason": "未进入企业场景知识库"},
            "answer": capability_answer if scope == "capability" else ("你好，我可以协助分析企业经营、生产、供应链、风险和合规问题。请告诉我需要解决的具体场景。" if scope == "general_chat" else "这个问题不属于当前企业场景范围。你可以描述制造、零售、运输、医药、能源、建筑或金融相关问题。"),
        }
    settings = Settings(
        storage_mode="sqlite", sqlite_path="../local-data/processagent.db",
        vector_backend="chroma", chroma_path="../local-data/chroma",
        embedding_provider="local", embedding_model="BAAI/bge-small-zh-v1.5",
        embedding_dim=512, reranker_enabled=False,
    )
    store = SQLiteStore(settings.sqlite_path)
    vectors = ChromaVectorStore(path=settings.chroma_path)
    embeddings = EmbeddingClient(settings, relay=None)
    skills = ManufacturingSkillAccess(store, vectors, embeddings)

    # CLI uses an in-process session store; production can replace it with Redis.
    session_store = MemorySessionStore()
    working = WorkingMemory(session_store, ttl=1800, max_history=10)
    episodic = EpisodicMemory(store, event_days=90, summary_days=180)
    memory_builder = MemoryContextBuilder(
        store, working, episodic, UserSemanticMemory(store),
        OrganizationMemory(store), LearningMemory(store),
        max_chars=6000, user_limit=8, org_limit=8, recent_limit=10,
    )
    await working.append_message(session_id, "user", query)
    await episodic.append_event(session_id, user_id, "user_message", query)
    memory_context = await memory_builder.build(session_id, user_id, query, include_organization=False)
    memory_prompt = memory_context.prompt_text()
    intent_memory_prompt = memory_context.intent_prompt_text()

    llm = DeepSeekClient(get_settings()) if use_llm else None
    intent_agent = ManufacturingIntentAgent()
    intent = await intent_agent.infer_async(query, llm=llm, context=intent_memory_prompt)
    # A classifier must not let a stale capability response override a clearly
    # manufacturing-shaped current turn. Compare with the deterministic parser
    # as a generic consistency check, without maintaining domain keyword lists.
    if llm is not None and intent.domain != "manufacturing":
        baseline = intent_agent.infer(query, context=intent_memory_prompt)
        has_current_facts = bool(baseline.industries or baseline.processes or baseline.equipment or baseline.objectives)
        if baseline.domain == "manufacturing" and has_current_facts:
            intent = baseline
    if intent.domain in {"capability", "general_chat", "out_of_scope"}:
        answer = ("我可以帮助分析制造、零售、运输、医药、能源、建筑、金融等企业场景，并结合知识库给出措施、风险和实施建议。您可以直接描述一个业务问题。" if intent.domain == "capability" else "你好，我可以协助分析企业经营、生产、供应链、风险和合规问题。" if intent.domain == "general_chat" else "这个问题不属于当前企业场景范围。你可以描述制造、零售、运输、医药、能源、建筑或金融相关问题。")
        return {"query": query, "route": {"scope": intent.domain, "response_mode": intent.response_mode}, "intent": intent.model_dump(), "answer": answer}
    # Merge facts already confirmed in prior turns without requiring a separate profile.
    previous_entities = memory_context.session.get("entities") or {}
    merge_intent_entities(intent, previous_entities)
    if intent.missing_information:
        intent.needs_clarification = True
    complexity = intent.complexity
    context = EnterpriseContextAgent().build(query, intent, profile)
    if memory_prompt:
        context.assumptions.append("已注入历史会话记忆")
    if complexity == "simple":
        plan = AnalysisPlan(tasks=[AnalysisTask(
            task_id="knowledge_search", title="快速检索相关知识", objective="检索直接相关的标准和案例",
            role="evidence_search", priority=1,
            allowed_skills=["retrieve"], input_data={"skill": "retrieve"},
            completion_criteria=["返回相关证据"],
        )], assumptions=context.assumptions, missing_information=context.missing_information)
    else:
        plan = await LeadAgent().plan_async(intent, context, llm=llm)
    matched_skills = ScenarioSkillMatcher().match(query, intent)
    existing = {skill for task in plan.tasks for skill in task.allowed_skills}
    task_specs = {
        "understand": ("parameter_extraction", "提取业务指标和参数"),
        "analyze": ("applicability_analysis", "分析场景适用性"),
        "compare": ("option_comparison", "比较候选方案"),
        "calculate": ("financial_analysis", "计算经营与项目指标"),
        "check": ("constraint_check", "检查约束与合规"),
        "verify": ("citation_check", "验证证据与引用"),
        "extract_process_parameters": ("parameter_extraction", "提取工艺参数"),
        "check_applicability": ("applicability_analysis", "判断方案适用性"),
        "compare_technical_options": ("option_comparison", "比较技术方案"),
        "calculate_project_financials": ("financial_analysis", "计算项目财务收益"),
        "calculate_energy_savings": ("energy_analysis", "计算节能量"),
        "calculate_emission_reduction": ("carbon_analysis", "计算碳减排量"),
        "verify_citations": ("citation_check", "验证引用"),
        "check_constraint_compliance": ("constraint_check", "检查约束合规"),
    }
    for skill in matched_skills:
        if skill not in task_specs or skill in existing:
            continue
        task_id, title = task_specs[skill]
        deps = ["knowledge_search"] if task_id not in {"citation_check", "constraint_check"} else [t.task_id for t in plan.tasks]
        plan.tasks.append(AnalysisTask(
            task_id=task_id, title=title, objective=title, role="skill_analysis",
            priority=3, dependencies=deps, allowed_skills=[skill], input_data={"skill": skill},
            completion_criteria=["返回结构化结果"],
        ))
    executor = ManufacturingTaskExecutor(build_default_task_registry(skills), skills)
    results = await executor.execute(plan, {
        "query": query,
        "context": context.model_dump(),
        "missing_information": context.missing_information,
        "top_k": top_k,
    })

    verification = VerifierAgent().verify(results)
    solution = await OrchestratorAgent().synthesize_async(query, results, verification, llm=llm)
    await working.append_message(session_id, "assistant", solution.get("executive_summary", ""))
    await episodic.append_event(session_id, user_id, "assistant_answer", solution.get("executive_summary", ""))
    await working.set_summary(session_id, solution.get("executive_summary", ""))
    await episodic.update_summary(session_id, user_id, solution.get("executive_summary", ""), intent.model_dump())
    missing = list(dict.fromkeys(context.missing_information))
    response_mode = "answer_then_clarify" if missing else "complete_analysis"
    followup_map = {
        "用户具体需求领域": "您更关注生产、经营、供应链、能源、质量、风险还是合规？",
        "具体工艺环节": "目前重点是电芯制造、部件装配，还是废旧电池回收？",
        "能耗现状": "如果方便，可以提供单位产品能耗，或近期能耗变化幅度。",
        "基线能耗": "如果方便，可以提供近期月度用电量或单位产品能耗。",
        "产量和运行周期": "如果方便，可以提供月产量和设备年运行小时。",
    }
    return {
        "query": query, "route": {"scope": scope, "complexity": complexity, "response_mode": response_mode}, "intent": intent.model_dump(), "context": context.model_dump(),
        "matched_skills": matched_skills,
        "plan": plan.model_dump(), "results": [item.model_dump() for item in results],
        "verification": verification, "solution": solution,
        "follow_up_questions": [followup_map.get(item, f"如果方便，可以说明{item}。") for item in missing[:3]],
    }


async def run_with_progress(query: str, top_k: int, profile: dict | None, use_llm: bool,
                            session_id: str, user_id: str) -> dict:
    """Interactive CLI wrapper with elapsed time and coarse ETA feedback."""
    started = time.monotonic()
    task = asyncio.create_task(ScenarioOrchestratorFacade(run).run(query, top_k=top_k, profile=profile, use_llm=use_llm, session_id=session_id, user_id=user_id))
    estimates = {"simple": 20, "standard": 45, "complex": 90}
    stage = "正在识别意图和判断任务复杂度"
    shown = 0
    while not task.done():
        elapsed = int(time.monotonic() - started)
        # Before Intent returns, standard is the conservative estimate.
        estimate = estimates["standard"]
        progress = min(95, max(1, round(elapsed / estimate * 100)))
        if elapsed >= 15:
            stage = "多 Agent 正在并行检索和分析，请耐心等待"
        print(f"\r[处理中] {stage} | 已完成 {progress}% | 已用时 {elapsed}秒", end="", flush=True)
        shown += 1
        await asyncio.sleep(1)
    result = await task
    elapsed = int(time.monotonic() - started)
    print(f"\r[完成] 本轮耗时 {elapsed}s" + " " * 30)
    return result


def render_interactive_answer(result: dict) -> str:
    if result.get("answer"):
        return result["answer"]
    solution = result.get("solution") or {}
    sections = []
    if solution.get("executive_summary"):
        sections.append(solution["executive_summary"])
    findings = solution.get("findings") if isinstance(solution.get("findings"), list) else []
    actions = solution.get("recommended_actions") if isinstance(solution.get("recommended_actions"), list) else []
    roadmap = solution.get("implementation_roadmap")
    roadmap = roadmap if isinstance(roadmap, list) else ([roadmap] if roadmap else [])
    roadmap = [item for item in roadmap if (item if isinstance(item, str) else item.get('stage') or item.get('summary') or item.get('description'))]
    if findings:
        sections.append("\n主要发现：\n" + "\n".join(f"- {item if isinstance(item, str) else item.get('summary', item.get('claim', item.get('finding', '')))}" for item in findings[:5]))
    if actions:
        sections.append("\n建议措施：\n" + "\n".join(f"{i}. {item if isinstance(item, str) else item.get('title', item.get('action', item.get('summary', '')))}" for i, item in enumerate(actions[:5], 1)))
    if roadmap:
        sections.append("\n实施顺序：\n" + "\n".join(f"{i}. {item if isinstance(item, str) else item.get('stage', item.get('summary', item.get('description', '')))}" for i, item in enumerate(roadmap[:4], 1)))
    if solution.get("risks_and_constraints"):
        sections.append("\n注意事项：\n" + "\n".join(f"- {item}" for item in solution["risks_and_constraints"][:5]))
    return "\n".join(sections) or "本轮没有生成可展示的分析结果。"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ProcessAgent scenario agent locally")
    parser.add_argument("query", nargs="?", help="企业场景问题；省略后进入交互式对话")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--profile", type=Path, help="企业上下文 JSON 文件")
    parser.add_argument("--output", type=Path, help="保存完整 JSON 结果")
    parser.add_argument("--llm", action="store_true", help="使用配置的 DeepSeek 进行结构化推理")
    parser.add_argument("--session-id", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--user-id", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    import os
    session_id = args.session_id or os.getenv("PROCESSAGENT_SESSION_ID") or f"cli-{uuid.uuid4().hex[:10]}"
    user_id = args.user_id or os.getenv("PROCESSAGENT_USER_ID", "cli-user")
    use_llm = args.llm or os.getenv("PROCESSAGENT_USE_LLM", "true").lower() in {"1", "true", "yes"}
    profile = json.loads(args.profile.read_text(encoding="utf-8")) if args.profile else None
    if not args.query:
        print("ProcessAgent 企业场景分析助手")
        print("可帮助分析制造、零售、运输、医药、能源、建筑、金融等场景，并结合知识库给出措施、风险和实施建议。")
        print("您可以直接描述一个生产或管理问题；输入 exit 或 quit 退出。")
        while True:
            try:
                query = input("\n👤 用户> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not query:
                continue
            if query.lower() in {"exit", "quit", "退出"}:
                break
            result = asyncio.run(run_with_progress(query, args.top_k, profile, use_llm, session_id, user_id))
            print(f"\n🤖 助手>\n{render_interactive_answer(result)}")
            # Do not append a fixed follow-up section here. The orchestrator
            # answer is responsible for deciding whether missing information
            # is worth mentioning and how to phrase it naturally.
        return 0
    orchestrator = ScenarioOrchestratorFacade(run)
    result = asyncio.run(orchestrator.run(args.query, top_k=args.top_k, profile=profile, use_llm=use_llm, session_id=session_id, user_id=user_id))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if result.get("route", {}).get("scope") in {"out_of_scope", "general_chat", "capability"}:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({
            "route": result["route"], "intent": result["intent"], "plan": result["plan"],
            "verification": result["verification"], "solution": result["solution"],
            "follow_up_questions": result["follow_up_questions"],
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
