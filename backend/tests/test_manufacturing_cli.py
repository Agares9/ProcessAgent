from __future__ import annotations

import pytest

from scripts.run_manufacturing_agents import run


@pytest.mark.asyncio
async def test_cli_workflow_contract(monkeypatch):
    async def fake_search(self, skill, **kwargs):
            return [{
                "chunk_id": "c1", "doc_id": "d1", "source_id": "d1", "score": 0.9,
            "page_start": 4, "page_end": 4, "excerpt": "压缩空气节能案例",
            "visibility": "enterprise_private",
        }]

    monkeypatch.setattr("app.harness.manufacturing_skills.ManufacturingSkillAccess.execute", fake_search)
    # The test validates the orchestration contract without loading the local model.
    result = await run("如何降低压缩空气能耗")
    assert result["intent"]["objectives"]
    assert result["plan"]["tasks"][1]["dependencies"] == ["knowledge_search"]
    assert result["verification"]["passed"] is True
