from __future__ import annotations

import pytest

from app.harness.agents.manufacturing_agents import OrchestratorAgent, VerifierAgent
from app.harness.manufacturing_schemas import AnalysisPlan, AnalysisTask, EvidenceArtifact, TaskResult
from app.harness.task_executor import ManufacturingTaskExecutor, build_default_task_registry


class EmptyKnowledge:
    def __init__(self):
        self.calls = []

    async def execute(self, skill, **kwargs):
        self.calls.append((skill, kwargs))
        return []


class CaptureLLM:
    api_key = "sk-test"

    def __init__(self):
        self.messages = []

    async def complete(self, messages, **kwargs):
        self.messages = messages
        return "这是基于专业知识给出的正常分析建议。"


@pytest.mark.asyncio
async def test_no_knowledge_match_is_completed_not_failed():
    knowledge = EmptyKnowledge()
    plan = AnalysisPlan(tasks=[AnalysisTask(
        task_id="knowledge_search", title="检索", objective="检索", allowed_skills=["retrieve"]
    )])
    results = await ManufacturingTaskExecutor(
        build_default_task_registry(knowledge), knowledge
    ).execute(plan, {"query": "医院门诊流程优化"})
    assert results[0].status == "completed"
    assert results[0].data["retrieval_status"] == "no_match"
    report = VerifierAgent().verify(results)
    assert report["passed"] is True
    assert report["citation_status"] == "not_applicable"
    assert report["retrieval_status"] == "no_match"


@pytest.mark.asyncio
async def test_lead_generated_retrieve_task_is_also_optional():
    knowledge = EmptyKnowledge()
    plan = AnalysisPlan(tasks=[AnalysisTask(
        task_id="task_001", title="检索", objective="查找资料", allowed_skills=["retrieve"]
    )])
    results = await ManufacturingTaskExecutor(
        build_default_task_registry(knowledge), knowledge
    ).execute(plan, {"query": "医院流程优化", "top_k": 3, "context": {}})
    assert results[0].status == "completed"
    assert results[0].data["retrieval_status"] == "no_match"
    assert knowledge.calls[0][1]["query"] == "医院流程优化"


@pytest.mark.asyncio
async def test_retrieval_error_is_not_exposed_to_answer_llm():
    results = [TaskResult(
        task_id="knowledge_search", status="failed", error="private vector timeout",
        data={"retrieval_status": "error"},
    )]
    verification = VerifierAgent().verify(results)
    assert verification["passed"] is True
    assert verification["citation_status"] == "not_available"
    llm = CaptureLLM()
    solution = await OrchestratorAgent().synthesize_async(
        "医院门诊等待时间如何优化", results, verification, llm=llm
    )
    prompt = llm.messages[-1]["content"]
    assert "private vector timeout" not in prompt
    assert solution["executive_summary"] == "这是基于专业知识给出的正常分析建议。"


@pytest.mark.asyncio
async def test_source_requirement_is_only_enabled_when_user_asks_for_sources():
    llm = CaptureLLM()
    orchestrator = OrchestratorAgent()
    results = [TaskResult(
        task_id="knowledge_search", status="completed",
        data={"retrieval_status": "no_match", "hit_count": 0},
    )]
    verification = VerifierAgent().verify(results)
    await orchestrator.synthesize_async("医院门诊等待时间如何优化", results, verification, llm=llm)
    assert '"source_required": false' in llm.messages[-1]["content"]
    await orchestrator.synthesize_async("请根据文献来源分析医院门诊等待时间", results, verification, llm=llm)
    assert '"source_required": true' in llm.messages[-1]["content"]


@pytest.mark.asyncio
async def test_valid_evidence_is_preserved_for_llm_and_response():
    artifact = EvidenceArtifact(
        claim="分时预约可以改善等待", source_id="doc-1", chunk_id="chunk-1",
        page_start=2, excerpt="采用分时预约优化患者到达分布。",
    )
    results = [TaskResult(
        task_id="knowledge_search", status="completed", artifacts=[artifact],
        data={"retrieval_status": "available", "hit_count": 1},
    )]
    verification = VerifierAgent().verify(results)
    llm = CaptureLLM()
    solution = await OrchestratorAgent().synthesize_async("如何减少等待", results, verification, llm=llm)
    assert verification["citation_status"] == "valid"
    assert solution["citations"][0]["chunk_id"] == "chunk-1"
    assert "采用分时预约优化患者到达分布" in llm.messages[-1]["content"]
