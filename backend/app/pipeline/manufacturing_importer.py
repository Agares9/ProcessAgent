"""Import preprocessed manufacturing manifests and chunks into local RAG stores."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.llm.embeddings import EmbeddingClient
from app.retrieval.vector_store import VectorStore
from app.storage.store import DataStore

PUBLIC_TENANT_ID = "tenant_public"
PUBLIC_SCOPE_ID = "public_manufacturing"

DOC_TYPE_MAP = {
    "doe_case": "case_study",
    "case": "case_study",
    "case_study": "case_study",
    "standard": "standard",
    "regulation": "regulation",
    "policy": "regulation",
    "announcement": "regulation",
    "bref": "technical_guide",
    "bat": "technical_guide",
    "technical_document": "technical_guide",
    "technical_guide": "technical_guide",
    "vendor_manual": "vendor_manual",
    "paper": "paper",
    "patent": "patent",
    "enterprise_sop": "enterprise_sop",
    "energy_audit": "energy_audit",
    "carbon_inventory": "carbon_inventory",
    "esg_report": "esg_report",
}


@dataclass
class ImportIssue:
    kind: str
    source: str
    detail: str


@dataclass
class ImportReport:
    manifest_files: int = 0
    chunk_files: int = 0
    discovered_documents: int = 0
    accepted_documents: int = 0
    accepted_chunks: int = 0
    skipped_documents: int = 0
    skipped_chunks: int = 0
    imported_documents: int = 0
    imported_chunks: int = 0
    issues: list[ImportIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["issue_counts"] = {}
        for issue in self.issues:
            counts = result["issue_counts"]
            counts[issue.kind] = counts.get(issue.kind, 0) + 1
        return result


@dataclass
class PreparedDocument:
    manifest: dict[str, Any]
    chunks: list[dict[str, Any]]


def normalize_doc_type(manifest: dict[str, Any]) -> str:
    candidates = [
        str(manifest.get("doc_type") or "").lower(),
        str(manifest.get("source_type") or "").lower(),
        str(manifest.get("source_group") or "").lower(),
    ]
    joined = " ".join(candidates)
    for key, normalized in DOC_TYPE_MAP.items():
        if key in joined:
            return normalized
    return "technical_guide"


def prepare_dataset(source: Path, limit_documents: int = 0) -> tuple[list[PreparedDocument], ImportReport]:
    source = source.resolve()
    report = ImportReport()
    manifests: dict[str, dict[str, Any]] = {}

    manifest_files = sorted(
        path for path in source.rglob("*.json")
        if path.parent.name in {"manifests", "md-manifests"}
    )
    report.manifest_files = len(manifest_files)
    for path in manifest_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            report.issues.append(ImportIssue("invalid_manifest", str(path), str(exc)))
            continue
        doc_id = str(data.get("doc_id") or "").strip()
        if not doc_id:
            report.issues.append(ImportIssue("manifest_without_doc_id", str(path), "missing doc_id"))
            continue
        data["_manifest_path"] = str(path)
        if doc_id in manifests:
            report.issues.append(ImportIssue("duplicate_manifest", str(path), doc_id))
            continue
        manifests[doc_id] = data

    chunks_by_doc: dict[str, list[dict[str, Any]]] = {}
    seen_chunk_ids: set[str] = set()
    chunk_files = sorted(
        path for path in source.rglob("*.jsonl")
        if path.parent.name in {"chunks", "md-chunks"}
    )
    report.chunk_files = len(chunk_files)
    for path in chunk_files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            report.issues.append(ImportIssue("unreadable_chunk_file", str(path), str(exc)))
            continue
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as exc:
                report.skipped_chunks += 1
                report.issues.append(ImportIssue("invalid_chunk_json", f"{path}:{line_number}", str(exc)))
                continue
            chunk_id = str(chunk.get("chunk_id") or "").strip()
            doc_id = str(chunk.get("doc_id") or "").strip()
            text = str(chunk.get("text") or "").strip()
            if not chunk_id or not doc_id or not text:
                report.skipped_chunks += 1
                report.issues.append(
                    ImportIssue("invalid_chunk_fields", f"{path}:{line_number}", "chunk_id/doc_id/text required")
                )
                continue
            if chunk_id in seen_chunk_ids:
                report.skipped_chunks += 1
                report.issues.append(ImportIssue("duplicate_chunk", f"{path}:{line_number}", chunk_id))
                continue
            seen_chunk_ids.add(chunk_id)
            chunk["_chunk_path"] = str(path)
            chunks_by_doc.setdefault(doc_id, []).append(chunk)

    report.discovered_documents = len(set(manifests) | set(chunks_by_doc))
    prepared: list[PreparedDocument] = []
    for doc_id in sorted(set(manifests) | set(chunks_by_doc)):
        manifest = manifests.get(doc_id)
        chunks = chunks_by_doc.get(doc_id, [])
        if manifest is None:
            report.skipped_documents += 1
            report.skipped_chunks += len(chunks)
            report.issues.append(ImportIssue("missing_manifest", doc_id, f"{len(chunks)} chunks skipped"))
            continue
        if manifest.get("extraction_status") != "extracted":
            report.skipped_documents += 1
            report.skipped_chunks += len(chunks)
            report.issues.append(
                ImportIssue("not_extracted", manifest["_manifest_path"], str(manifest.get("extraction_status")))
            )
            continue
        approved = [chunk for chunk in chunks if chunk.get("review_status") == "approved"]
        report.skipped_chunks += len(chunks) - len(approved)
        if not approved:
            report.skipped_documents += 1
            report.issues.append(ImportIssue("no_approved_chunks", manifest["_manifest_path"], doc_id))
            continue
        prepared.append(PreparedDocument(manifest=manifest, chunks=approved))
        if limit_documents and len(prepared) >= limit_documents:
            break

    report.accepted_documents = len(prepared)
    report.accepted_chunks = sum(len(item.chunks) for item in prepared)
    return prepared, report


async def import_prepared_documents(
    prepared: list[PreparedDocument],
    report: ImportReport,
    store: DataStore,
    vector_store: VectorStore,
    embeddings: EmbeddingClient,
    batch_size: int = 32,
) -> ImportReport:
    now = datetime.now(timezone.utc).isoformat()
    for item in prepared:
        manifest = item.manifest
        doc_id = str(manifest["doc_id"])
        texts = [str(chunk["text"]) for chunk in item.chunks]
        vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            vectors.extend(await embeddings.embed(texts[start:start + batch_size]))
        if len(vectors) != len(item.chunks):
            raise ValueError(f"embedding count mismatch for {doc_id}")

        await vector_store.delete_by_doc(doc_id)
        await store.delete_chunks_by_doc(doc_id)
        stored_chunks: list[dict[str, Any]] = []
        for index, (chunk, vector) in enumerate(zip(item.chunks, vectors)):
            chunk_id = str(chunk["chunk_id"])
            content = str(chunk["text"])
            metadata = {
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
                "section": chunk.get("section"),
                "language": chunk.get("language") or manifest.get("language") or "",
                "industry": chunk.get("industry") or manifest.get("industry") or "",
                "process": chunk.get("process") or manifest.get("process") or "",
                "source_url": chunk.get("source_url") or manifest.get("source_url"),
                "evidence_level": chunk.get("evidence_level") or manifest.get("evidence_level") or "F",
                "review_status": "approved",
                "tenant_id": PUBLIC_TENANT_ID,
            }
            stored_chunks.append({
                "_id": chunk_id,
                "doc_id": doc_id,
                "dept_id": PUBLIC_SCOPE_ID,
                "tenant_id": PUBLIC_TENANT_ID,
                "chunk_index": index,
                "section_path": [metadata["section"]] if metadata["section"] else [],
                "section_title": metadata["section"] or "",
                "content": content,
                "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "char_count": len(content),
                "embedding_id": chunk_id,
                "keywords": [],
                "metadata": metadata,
            })
            vector_metadata = {
                "doc_id": doc_id,
                "dept_id": PUBLIC_SCOPE_ID,
                "tenant_id": PUBLIC_TENANT_ID,
                "chunk_index": index,
                "doc_type": normalize_doc_type(manifest),
                "language": str(metadata["language"]),
                "industry": str(metadata["industry"]),
                "process": str(metadata["process"]),
                "evidence_level": str(metadata["evidence_level"]),
            }
            await vector_store.add(chunk_id, vector, vector_metadata)

        await store.insert_chunks(stored_chunks)
        source = {key: value for key, value in manifest.items() if not key.startswith("_")}
        await store.insert_document({
            "_id": doc_id,
            "dept_id": PUBLIC_SCOPE_ID,
            "tenant_id": PUBLIC_TENANT_ID,
            "title": manifest.get("title") or manifest.get("file_name") or doc_id,
            "doc_type": normalize_doc_type(manifest),
            "version": str(manifest.get("version") or "1.0"),
            "status": "active",
            "effective_date": manifest.get("effective_date") or manifest.get("published_at"),
            "expiry_date": manifest.get("expiry_date"),
            "source": source,
            "tags": [value for value in [manifest.get("industry"), manifest.get("process")] if value],
            "chunk_count": len(stored_chunks),
            "vector_status": "ready",
            "applicable_scope": ["public"],
            "created_at": now,
            "updated_at": now,
        })
        report.imported_documents += 1
        report.imported_chunks += len(stored_chunks)
    return report
