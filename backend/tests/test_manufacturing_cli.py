from __future__ import annotations

import pytest

from scripts.run_manufacturing_agents import run


@pytest.mark.asyncio
async def test_cli_workflow_contract(monkeypatch, fresh_container):
    async def fake_search(self, skill, **kwargs):
            return [{
                "chunk_id": "c1", "doc_id": "d1", "source_id": "d1", "score": 0.9,
            "page_start": 4, "page_end": 4, "excerpt": "压缩空气节能案例",
            "visibility": "enterprise_private",
        }]

    monkeypatch.setattr("app.harness.manufacturing_skills.ManufacturingSkillAccess.execute", fake_search)
    async def deterministic_intent(self, query, structured_llm=None, context=""):
        return self.infer(query, context)

    async def deterministic_plan(self, intent, context, structured_llm=None):
        return self.plan(intent, context)

    async def deterministic_answer(self, query, results, verification, llm=None):
        return self.synthesize(query, results, verification)

    monkeypatch.setattr("app.harness.agents.manufacturing_agents.ManufacturingIntentAgent.infer_async", deterministic_intent)
    monkeypatch.setattr("app.harness.agents.manufacturing_agents.LeadAgent.plan_async", deterministic_plan)
    monkeypatch.setattr("app.harness.agents.manufacturing_agents.OrchestratorAgent.synthesize_async", deterministic_answer)
    monkeypatch.setattr(fresh_container.settings, "deepseek_api_key", "sk-test")
    monkeypatch.setattr(fresh_container.llm, "api_key", "sk-test")
    monkeypatch.setattr(
        "scripts.run_manufacturing_agents.build_container",
        lambda settings: (_ for _ in ()).throw(AssertionError("shared runtime was not reused")),
    )
    result = await run("如何降低压缩空气能耗", runtime=fresh_container)
    assert result["intent"]["objectives"]
    assert result["plan"]["tasks"][1]["dependencies"] == ["knowledge_search"]
    assert result["verification"]["passed"] is True
    traces = await fresh_container.store.find("traces", {"session_id": "cli-session", "user_id": "cli-user"})
    assert len(traces) == 1
    assert traces[0]["answer"] == result["answer"]
    assert traces[0]["retrieval_status"] == "available"
