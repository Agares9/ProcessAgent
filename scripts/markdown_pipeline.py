#!/usr/bin/env python3
"""Normalize existing Markdown references into RAG-ready, pending chunks."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from pdf_pipeline import clean_contact_text, guess_industry, language


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current = "正文"
    buf: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if match:
            if buf:
                sections.append((current, "\n".join(buf).strip()))
                buf = []
            current = match.group(1)
        else:
            buf.append(line)
    if buf:
        sections.append((current, "\n".join(buf).strip()))
    return [(section, body) for section, body in sections if body]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path("manufacturing-data/gongxinbu"))
    args = parser.parse_args()
    for name in ("parsed-md", "normalized-md", "md-manifests", "md-chunks", "reviewed", "rejected"):
        (args.output / name).mkdir(parents=True, exist_ok=True)
    manifests = []
    for path in args.files:
        digest = sha256(path)
        doc_id = digest[:16]
        raw = path.read_text(encoding="utf-8", errors="replace")
        title_match = re.search(r"^#\s+(.+)$", raw, re.M)
        title = title_match.group(1).strip() if title_match else path.stem
        body = clean_contact_text(raw)
        sections = split_sections(body)
        industry = next((x for x in ("钢铁", "汽车", "电器电子", "包装", "日化") if x in title), "制造业")
        manifest = {"doc_id": doc_id, "doc_type": "technical_reference", "record_type": "green_design_reference",
                    "file_name": path.name, "title": title, "language": language(body), "source_type": "government_technical_document",
                    "source_org": "工信部", "source_url": None, "industry": [industry], "process": ["绿色设计"],
                    "published_at": None, "retrieved_at": datetime.now(timezone.utc).date().isoformat(),
                    "license": "internal_retrieval_needs_confirmation", "sha256": digest, "parser": "markdown",
                    "extraction_status": "extracted", "review_status": "pending", "evidence_level": "C"}
        (args.output / "parsed-md" / path.name).write_text(raw, encoding="utf-8")
        front = "---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in manifest.items()) + "\n---\n\n"
        (args.output / "normalized-md" / f"{doc_id}.md").write_text(front + body.strip() + "\n", encoding="utf-8")
        (args.output / "md-manifests" / f"{doc_id}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        with (args.output / "md-chunks" / f"{doc_id}.jsonl").open("w", encoding="utf-8") as stream:
            for index, (section, content) in enumerate(sections):
                if len(content) < 40:
                    continue
                text = f"主题：{title}\n章节：{section}\n\n{content}"
                chunk = {"chunk_id": f"{doc_id}-md-{index:04d}", "doc_id": doc_id, "record_id": f"{doc_id}-ref",
                         "text": text, "doc_type": "technical_reference", "record_type": "green_design_reference",
                         "language": manifest["language"], "industry": manifest["industry"], "process": manifest["process"],
                         "section": section, "evidence_level": "C", "review_status": "pending",
                         "license_status": manifest["license"], "source_document": title}
                stream.write(json.dumps(chunk, ensure_ascii=False) + "\n")
        manifests.append(manifest)
    (args.output / "md-run-log.json").write_text(json.dumps({"files": manifests}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"processed": len(manifests), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
