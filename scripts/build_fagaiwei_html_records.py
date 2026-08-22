#!/usr/bin/env python3
"""Create RAG-ready technical case records from the few Fagaiwei HTML tables."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from html_pipeline import read_html


def cell_text(cell) -> str:
    return re.sub(r"\s+", " ", cell.get_text(" ", strip=True))


def record_id(technology: str, project: str) -> str:
    return hashlib.sha1(f"{technology}|{project}".encode("utf-8")).hexdigest()[:16]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("文档/发改委和国家节能中心"))
    parser.add_argument("--output", type=Path, default=Path("manufacturing-data/fagaiwei"))
    args = parser.parse_args()

    sources: dict[str, dict] = {}
    records: dict[str, dict] = {}
    for path in sorted(args.input.glob("*.html")):
        soup = BeautifulSoup(read_html(path), "html.parser")
        content = soup.select_one("#newsContent")
        if not content:
            continue
        # Different browser saves of the same page may have different assets but identical content.
        content_hash = hashlib.sha256(str(content).encode("utf-8")).hexdigest()
        if content_hash in sources:
            sources[content_hash]["file_names"].append(path.name)
            continue
        title_node = soup.select_one(".newstitle h2") or soup.find("title")
        sources[content_hash] = {
            "doc_id": hashlib.sha256(path.read_bytes()).hexdigest()[:16],
            "title": title_node.get_text(" ", strip=True) if title_node else path.stem,
            "file_names": [path.name],
        }
        source = sources[content_hash]
        for table_index, table in enumerate(content.find_all("table"), 1):
            for row_index, row in enumerate(table.find_all("tr"), 1):
                cells = [cell_text(cell) for cell in row.find_all(["th", "td"])]
                if len(cells) < 2 or not cells[0].isdigit():
                    continue
                values = cells[1:]
                if len(values) >= 3:
                    company, technology, project = values[:3]
                elif len(values) == 2:
                    company, technology, project = None, values[0], values[1]
                else:
                    continue
                if not technology or not project:
                    continue
                rid = record_id(technology, project)
                locator = {"type": "html_table", "table_index": table_index, "row_index": row_index}
                if rid in records:
                    records[rid]["source_locators"].append({"doc_id": source["doc_id"], **locator})
                    continue
                records[rid] = {
                    "record_id": rid,
                    "doc_id": source["doc_id"],
                    "doc_type": "case_study",
                    "record_type": "technology_case",
                    "technology_name": technology,
                    "application_project": project,
                    "company": company,
                    "industry": [], "process": [], "equipment": [], "parameters": [],
                    "baseline": None, "measure": None, "energy_saving": None,
                    "emission_reduction": None, "investment": None, "payback": None,
                    "applicability": None, "limitations": None,
                    "evidence_level": "C", "review_status": "pending",
                    "license_status": "internal_retrieval_needs_confirmation",
                    "source_document": source["title"],
                    "source_locators": [{"doc_id": source["doc_id"], **locator}],
                }

    records_dir = args.output / "records"
    chunks_dir = args.output / "chunks"
    records_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records.values(), key=lambda item: item["record_id"])
    with (records_dir / "technology_cases.jsonl").open("w", encoding="utf-8") as stream:
        for item in ordered:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")
    with (chunks_dir / "technology_cases.jsonl").open("w", encoding="utf-8") as stream:
        for item in ordered:
            text = f"技术名称：{item['technology_name']}\n应用项目：{item['application_project']}"
            if item["company"]:
                text += f"\n公司：{item['company']}"
            chunk = {
                "chunk_id": f"{item['record_id']}-chunk-01", "record_id": item["record_id"],
                "doc_id": item["doc_id"], "text": text, "doc_type": "case_study",
                "record_type": "technology_case", "language": "zh", "industry": [],
                "process": [], "evidence_level": "C", "review_status": "pending",
                "license_status": "internal_retrieval_needs_confirmation",
                "source_document": item["source_document"], "source_locators": item["source_locators"],
            }
            stream.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    index_manifest = {"collection": "technology_case_chunks", "input_files": ["chunks/technology_cases.jsonl"],
                      "production_filter": {"review_status": "approved"},
                      "excluded": ["chunks/<doc_id>.jsonl"], "record_count": len(ordered),
                      "source_page_count": len(sources)}
    (args.output / "index-manifest.json").write_text(json.dumps(index_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"records": len(ordered), "source_pages": len(sources)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
