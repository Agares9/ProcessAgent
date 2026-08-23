"""Run the five-agent manufacturing workflow from the command line."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.config import Settings
from app.harness.agents.manufacturing_agents import (
    EnterpriseContextAgent,
    ExecutiveSynthesisAgent,
    LeadAgent,
    ManufacturingIntentAgent,
    VerifierAgent,
)
from app.harness.manufacturing_skills import ManufacturingSkillAccess
from app.harness.manufacturing_schemas import TaskResult
from app.llm.embeddings import EmbeddingClient
from app.retrieval.vector_store import ChromaVectorStore
from app.storage.store import SQLiteStore


async def run(query: str, top_k: int = 5, profile: dict | None = None) -> dict:
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

    intent = ManufacturingIntentAgent().infer(query)
    context = EnterpriseContextAgent().build(query, intent, profile)
    plan = LeadAgent().plan(intent, context)
    results: list[TaskResult] = []

    for task in sorted(plan.tasks, key=lambda item: (item.priority, item.task_id)):
        if task.task_id == "knowledge_search":
            hits = await skills.execute("search_manufacturing_knowledge", query=query, top_k=top_k)
            results.append(TaskResult(
                task_id=task.task_id, status="completed" if hits else "failed",
                summary=f"检索到 {len(hits)} 条知识证据", artifacts=[{
                    "claim": hit["excerpt"][:160], "value": hit["score"],
                    "source_id": hit["doc_id"], "chunk_id": hit["chunk_id"],
                    "page_start": hit["page_start"], "page_end": hit["page_end"],
                    "excerpt": hit["excerpt"], "visibility": hit["visibility"],
                } for hit in hits], missing_information=context.missing_information,
            ))
        elif task.task_id == "applicability_check":
            previous = next((item for item in results if item.task_id == "knowledge_search"), None)
            artifacts = previous.artifacts if previous else []
            results.append(TaskResult(
                task_id=task.task_id, status="completed" if artifacts else "skipped",
                summary="基于检索证据保留候选措施，适用性需结合企业基线复核",
                artifacts=artifacts, assumptions=["当前未提供企业实测基线"],
                missing_information=context.missing_information,
            ))

    verification = VerifierAgent().verify(results)
    solution = ExecutiveSynthesisAgent().synthesize(query, results, verification)
    return {
        "query": query, "intent": intent.model_dump(), "context": context.model_dump(),
        "plan": plan.model_dump(), "results": [item.model_dump() for item in results],
        "verification": verification, "solution": solution,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ProcessAgent manufacturing agents locally")
    parser.add_argument("query", help="制造业问题")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--profile", type=Path, help="企业上下文 JSON 文件")
    parser.add_argument("--output", type=Path, help="保存完整 JSON 结果")
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding="utf-8")) if args.profile else None
    result = asyncio.run(run(args.query, args.top_k, profile))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "intent": result["intent"], "plan": result["plan"],
        "verification": result["verification"], "solution": result["solution"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
