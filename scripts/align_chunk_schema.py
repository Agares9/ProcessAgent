#!/usr/bin/env python3
"""Align Markdown/HTML vector JSONL with the existing PDF chunk schema."""
from __future__ import annotations

import json
from pathlib import Path


FIELDS = ["chunk_id", "doc_id", "text", "page_start", "page_end", "section",
          "language", "industry", "process", "source_url", "evidence_level", "review_status"]


def scalar(value, default):
    if isinstance(value, list):
        return value[0] if value else default
    return value if value not in (None, "") else default


def align(path: Path) -> tuple[int, int]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    output = []
    changed = 0
    for line in lines:
        item = json.loads(line)
        aligned = {
            "chunk_id": item.get("chunk_id"),
            "doc_id": item.get("doc_id"),
            "text": item.get("text", ""),
            "page_start": item.get("page_start"),
            "page_end": item.get("page_end"),
            "section": item.get("section"),
            "language": item.get("language", "zh"),
            "industry": scalar(item.get("industry"), "制造业"),
            "process": scalar(item.get("process"), "未人工确认"),
            "source_url": item.get("source_url"),
            "evidence_level": item.get("evidence_level", "source_document"),
            "review_status": item.get("review_status", "pending"),
        }
        if list(item.keys()) != FIELDS or any(item.get(k) != aligned[k] for k in FIELDS):
            changed += 1
        output.append(json.dumps(aligned, ensure_ascii=False))
    path.write_text("\n".join(output) + ("\n" if output else ""), encoding="utf-8")
    return len(output), changed


def main() -> None:
    root = Path("manufacturing-data")
    targets = list(root.glob("*/md-chunks/*.jsonl")) + list(root.glob("*/chunks/technology_cases.jsonl"))
    # Generic HTML chunks are also normalized if present.
    targets += [p for p in root.glob("*/chunks/*.jsonl") if p.name not in {"technology_cases.jsonl"} and "fagaiwei" in str(p)]
    total = changed = 0
    for path in sorted(set(targets)):
        rows, edits = align(path)
        total += rows; changed += edits
        print(f"{path}: rows={rows}, aligned={edits}")
    print(json.dumps({"files": len(set(targets)), "rows": total, "aligned": changed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
