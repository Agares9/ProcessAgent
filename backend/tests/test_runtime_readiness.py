from __future__ import annotations

import builtins
from types import SimpleNamespace

import httpx
import pytest

from app.main import app, validate_knowledge_runtime, validate_llm_runtime
from app.llm.embeddings import EmbeddingClient


class FakeLLM:
    async def complete(self, messages, **kwargs):
        return "OK"


class FakeEmbeddings:
    async def embed_query(self, text):
        return [0.0, 1.0]


class FakeStore:
    def __init__(self, chunks):
        self.chunks = chunks

    async def list_active_chunks(self):
        return self.chunks


class FakeVectors:
    def __init__(self, count):
        self.value = count
        self.searched = False

    async def count(self):
        return self.value

    async def search(self, vector, top_k=1):
        self.searched = True
        return []


@pytest.mark.asyncio
async def test_llm_is_a_mandatory_startup_dependency():
    runtime = SimpleNamespace(
        settings=SimpleNamespace(
            deepseek_api_key="",
            deepseek_base_url="https://api.deepseek.com",
            deepseek_model="deepseek-chat",
            startup_llm_timeout=1,
        ),
        llm=FakeLLM(),
    )
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        await validate_llm_runtime(runtime)


@pytest.mark.asyncio
async def test_llm_startup_check_accepts_a_working_model():
    runtime = SimpleNamespace(
        settings=SimpleNamespace(
            deepseek_api_key="sk-test",
            deepseek_base_url="https://api.deepseek.com",
            deepseek_model="deepseek-chat",
            startup_llm_timeout=1,
        ),
        llm=FakeLLM(),
    )
    await validate_llm_runtime(runtime)


@pytest.mark.asyncio
async def test_knowledge_runtime_checks_embedding_and_vector_count():
    vectors = FakeVectors(count=1)
    runtime = SimpleNamespace(
        settings=SimpleNamespace(require_knowledge_base=True),
        embeddings=FakeEmbeddings(),
        store=FakeStore([{"_id": "chunk-1"}]),
        vector_store=vectors,
    )
    details = await validate_knowledge_runtime(runtime)
    assert details == {"active_chunks": 1, "vectors": 1, "embedding_dim": 2}
    assert vectors.searched is True


@pytest.mark.asyncio
async def test_empty_required_knowledge_base_blocks_startup():
    runtime = SimpleNamespace(
        settings=SimpleNamespace(require_knowledge_base=True),
        embeddings=FakeEmbeddings(),
        store=FakeStore([]),
        vector_store=FakeVectors(count=0),
    )
    with pytest.raises(RuntimeError, match="知识库为空"):
        await validate_knowledge_runtime(runtime)


@pytest.mark.asyncio
async def test_hash_embedding_cannot_mark_runtime_ready():
    runtime = SimpleNamespace(
        settings=SimpleNamespace(require_knowledge_base=True, embedding_provider="hash"),
        embeddings=FakeEmbeddings(),
        store=FakeStore([{"_id": "chunk-1"}]),
        vector_store=FakeVectors(count=1),
    )
    with pytest.raises(RuntimeError, match="hash Embedding"):
        await validate_knowledge_runtime(runtime)


def test_local_embedding_missing_dependency_fails_closed(monkeypatch):
    original_import = builtins.__import__

    def import_without_sentence_transformers(name, *args, **kwargs):
        if name == "sentence_transformers":
            raise ImportError("not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_sentence_transformers)
    client = EmbeddingClient(SimpleNamespace(
        embedding_provider="local",
        embedding_model="BAAI/bge-small-zh-v1.5",
        embedding_dim=512,
        embedding_local_only=True,
    ))

    with pytest.raises(RuntimeError, match="禁止回退"):
        client._local_embed(["启动检查"])


@pytest.mark.asyncio
async def test_readyz_reflects_runtime_state():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        app.state.readiness = {"status": "not_ready", "error": "llm"}
        failed = await client.get("/readyz")
        assert failed.status_code == 503
        app.state.readiness = {"status": "ready", "components": {"llm": "ready"}}
        ready = await client.get("/readyz")
        assert ready.status_code == 200
