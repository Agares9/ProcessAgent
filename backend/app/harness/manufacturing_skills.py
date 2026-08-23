"""Whitelisted skills for controlled access to the manufacturing knowledge base."""
from __future__ import annotations

from typing import Any

from app.llm.embeddings import EmbeddingClient
from app.retrieval.vector_store import VectorStore
from app.storage.store import DataStore


class ManufacturingSkillAccess:
    """Skill gateway; callers never receive the underlying store or vector client."""

    ALLOWED_SKILLS = {
        "search_manufacturing_knowledge",
        "search_case_studies",
        "get_document_evidence",
        "get_enterprise_profile",
        "get_factory_process_map",
    }

    def __init__(self, store: DataStore, vector_store: VectorStore, embeddings: EmbeddingClient) -> None:
        self._store = store
        self._vectors = vector_store
        self._embeddings = embeddings

    async def execute(self, skill: str, **kwargs: Any) -> Any:
        if skill not in self.ALLOWED_SKILLS:
            raise PermissionError(f"skill not allowed: {skill}")
        return await getattr(self, skill)(**kwargs)

    async def search_manufacturing_knowledge(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        return await self._search(query, top_k=top_k)

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
