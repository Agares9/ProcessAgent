from __future__ import annotations

import pytest

from app.storage.store import SQLiteStore
from app.config import Settings
from app.deps import build_container


@pytest.mark.asyncio
async def test_sqlite_store_persists_and_filters_documents(tmp_path):
    path = tmp_path / "processagent.db"
    store = SQLiteStore(str(path))
    await store.upsert("documents", {"_id": "d1", "status": "active", "count": 1})
    await store.upsert("documents", {"_id": "d2", "status": "draft", "count": 0})

    reopened = SQLiteStore(str(path))
    assert (await reopened.get("documents", "d1"))["status"] == "active"
    assert [row["_id"] for row in await reopened.find("documents", {"status": "active"})] == ["d1"]
    assert await reopened.count("documents") == 2

    updated = await reopened.increment("documents", "d1", "count", 2)
    assert updated["count"] == 3
    await reopened.delete("documents", "d2")
    assert await reopened.count("documents") == 1


def test_container_builds_without_mongo_for_local_sqlite(tmp_path):
    container = build_container(Settings(
        storage_mode="sqlite",
        sqlite_path=str(tmp_path / "local.db"),
        vector_backend="memory",
        embedding_provider="hash",
        reranker_enabled=False,
        pi_agent_enabled=False,
    ))
    assert isinstance(container.store, SQLiteStore)
    assert container.mongo is None
