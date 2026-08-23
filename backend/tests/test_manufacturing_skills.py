from __future__ import annotations

import pytest

from app.config import Settings
from app.harness.manufacturing_skills import ManufacturingSkillAccess
from app.llm.embeddings import EmbeddingClient
from app.retrieval.vector_store import MemoryVectorStore
from app.storage.store import MemoryStore


@pytest.mark.asyncio
async def test_skill_gateway_returns_evidence_without_exposing_store():
    store = MemoryStore()
    vectors = MemoryVectorStore()
    embeddings = EmbeddingClient(Settings(embedding_provider="hash", embedding_dim=128), relay=None)
    await store.insert_document({"_id": "doc1", "title": "压缩空气案例", "status": "active"})
    await store.insert_chunks([{
        "_id": "chunk1", "doc_id": "doc1", "content": "压缩空气系统节能改造案例",
        "metadata": {"page_start": 3, "page_end": 3, "process": "compressed air", "evidence_level": "C"},
    }])
    vector = await embeddings.embed_query("压缩空气节能")
    await vectors.add("chunk1", vector, {"doc_id": "doc1", "doc_type": "case_study"})
    gateway = ManufacturingSkillAccess(store, vectors, embeddings)
    hits = await gateway.execute("search_manufacturing_knowledge", query="压缩空气节能", top_k=1)
    assert hits[0]["chunk_id"] == "chunk1"
    assert hits[0]["page_start"] == 3
    with pytest.raises(PermissionError):
        await gateway.execute("delete_database", collection="documents")
