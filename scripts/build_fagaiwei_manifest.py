#!/usr/bin/env python3
"""Build a combined, explicit collection manifest for Fagaiwei PDF/HTML data."""
import json
from pathlib import Path


def main() -> None:
    root = Path("manufacturing-data/fagaiwei")
    pdf = json.loads((root / "pdf-run-log.json").read_text(encoding="utf-8"))
    docs = []
    for item in pdf["files"]:
        docs.append({"doc_id": item["doc_id"], "doc_type": "case_study" if "案例" in item["title"] else "technical_reference",
                     "title": item["title"], "collection": "pdf_documents", "review_status": item["review_status"],
                     "extraction_status": item["extraction_status"], "has_tables": item["has_tables"],
                     "ocr_pages": item["ocr_pages"]})
    html_ids = set()
    records = root / "records" / "technology_cases.jsonl"
    if records.exists():
        for line in records.read_text(encoding="utf-8").splitlines():
            if line.strip(): html_ids.add(json.loads(line)["doc_id"])
    for doc_id in sorted(html_ids):
        docs.append({"doc_id": doc_id, "doc_type": "case_catalog", "title": None,
                     "collection": "technology_case_chunks", "review_status": "pending",
                     "extraction_status": "extracted"})
    result = {"name": "fagaiwei", "collections": ["pdf_documents", "technology_case_records", "technology_case_chunks"],
              "production_rule": {"review_status": "approved"},
              "documents": docs,
              "notes": ["parsed/ is authoritative raw extraction", "HTML generic chunks are excluded from production indexing", "records/technology_cases.jsonl is the normalized HTML case collection"]}
    (root / "collection-manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"documents": len(docs), "output": str(root / "collection-manifest.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
