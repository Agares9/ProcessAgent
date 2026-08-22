from __future__ import annotations

import json

import pytest

from app.config import Settings
from app.llm.embeddings import EmbeddingClient
from app.pipeline.manufacturing_importer import import_prepared_documents, prepare_dataset
from app.retrieval.vector_store import MemoryVectorStore
from app.storage.store import MemoryStore


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")


def test_prepare_dataset_joins_manifest_and_filters_status(tmp_path):
    _write_json(tmp_path / "source" / "manifests" / "ok.json", {
        "doc_id": "ok", "title": "案例", "doc_type": "doe_case", "extraction_status": "extracted"
    })
    _write_json(tmp_path / "source" / "manifests" / "ocr.json", {
        "doc_id": "ocr", "title": "待OCR", "extraction_status": "needs_ocr"
    })
    _write_jsonl(tmp_path / "source" / "chunks" / "data.jsonl", [
        {"chunk_id": "ok-1", "doc_id": "ok", "text": "节能案例", "review_status": "approved"},
        {"chunk_id": "ok-2", "doc_id": "ok", "text": "待审核", "review_status": "pending"},
        {"chunk_id": "ocr-1", "doc_id": "ocr", "text": "扫描内容", "review_status": "approved"},
    ])

    prepared, report = prepare_dataset(tmp_path)
    assert len(prepared) == 1
    assert prepared[0].manifest["doc_id"] == "ok"
    assert len(prepared[0].chunks) == 1
    assert report.accepted_chunks == 1
    assert report.to_dict()["issue_counts"] == {"not_extracted": 1}


@pytest.mark.asyncio
async def test_import_is_idempotent_and_writes_searchable_vectors(tmp_path):
    _write_json(tmp_path / "manifests" / "case.json", {
        "doc_id": "case", "title": "压缩空气节能", "doc_type": "doe_case",
        "extraction_status": "extracted", "industry": "制造业", "process": "compressed air"
    })
    _write_jsonl(tmp_path / "chunks" / "case.jsonl", [
        {"chunk_id": "case-1", "doc_id": "case", "text": "降低压缩空气泄漏率", "review_status": "approved"}
    ])
    prepared, report = prepare_dataset(tmp_path)
    store = MemoryStore()
    vectors = MemoryVectorStore()
    embeddings = EmbeddingClient(Settings(embedding_provider="hash", embedding_dim=128), relay=None)

    await import_prepared_documents(prepared, report, store, vectors, embeddings)
    second_report = prepare_dataset(tmp_path)[1]
    await import_prepared_documents(prepared, second_report, store, vectors, embeddings)

    assert await store.count("documents") == 1
    assert await store.count("chunks") == 1
    assert await vectors.count() == 1
    doc = await store.get_document("case")
    assert doc["doc_type"] == "case_study"
    assert doc["tenant_id"] == "tenant_public"
