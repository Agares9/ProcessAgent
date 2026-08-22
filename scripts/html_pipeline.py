#!/usr/bin/env python3
"""Extract saved Chinese announcement HTML into auditable Markdown/JSONL."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from pdf_pipeline import clean_contact_text, guess_industry, language, source_type


def read_html(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("gb18030", "gbk", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table_markdown(table) -> str:
    rows = []
    for tr in table.find_all("tr"):
        cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)).replace("|", "\\|") for c in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    out.extend("| " + " | ".join(row) + " |" for row in rows[1:])
    return "\n".join(out)


def extract(path: Path) -> tuple[dict, str, list[str]]:
    soup = BeautifulSoup(read_html(path), "html.parser")
    title_node = soup.select_one(".newstitle h2") or soup.find("title")
    title = title_node.get_text(" ", strip=True) if title_node else path.stem
    date_node = soup.select_one(".newstitle span")
    published = date_node.get_text(" ", strip=True) if date_node else None
    content = soup.select_one("#newsContent") or soup.body or soup
    blocks: list[str] = []
    tables: list[str] = []
    # Tables can be nested several levels deep in Word-exported HTML.
    for table in content.find_all("table"):
        rendered = table_markdown(table)
        if rendered:
            tables.append(rendered)
        table.decompose()
    for child in content.find_all(["p", "div"], recursive=False):
        text = child.get_text(" ", strip=True)
        if text:
            blocks.append(text)
    if not blocks and not tables:
        blocks = [content.get_text("\n", strip=True)]
    cleaned = [clean_contact_text(block) for block in blocks]
    cleaned = [block for block in cleaned if block.strip()]
    body = "\n\n".join(cleaned)
    if tables:
        body += ("\n\n" if body else "") + "\n\n".join(tables)
    manifest = {
        "doc_id": sha256(path)[:16], "file_name": path.name, "title": title,
        "language": language(body), "source_type": source_type(path), "source_org": path.parent.name,
        "source_url": None, "industry": guess_industry(path), "process": "未人工确认",
        "published_at": published, "retrieved_at": datetime.now(timezone.utc).date().isoformat(),
        "license": "未人工确认", "sha256": sha256(path), "parser": "beautifulsoup+gb18030",
        "page_count": None, "extraction_status": "extracted", "review_status": "pending",
        "has_tables": bool(tables), "table_count": len(tables),
    }
    return manifest, body, tables


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path("manufacturing-data-html"))
    args = parser.parse_args()
    for directory in ("parsed", "normalized", "chunks", "manifests", "reviewed", "rejected"):
        (args.output / directory).mkdir(parents=True, exist_ok=True)
    manifests = []
    for path in args.files:
        try:
            manifest, body, _ = extract(path)
            doc_id = manifest["doc_id"]
            front = "---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in manifest.items()) + "\n---\n\n"
            (args.output / "normalized" / f"{doc_id}.md").write_text(front + f"# {manifest['title']}\n\n" + body + "\n", encoding="utf-8")
            (args.output / "manifests" / f"{doc_id}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            (args.output / "parsed" / f"{doc_id}.html").write_text(read_html(path), encoding="utf-8")
            paragraphs = [p.strip() for p in re.split(r"\n{2,}", body) if p.strip()]
            with (args.output / "chunks" / f"{doc_id}.jsonl").open("w", encoding="utf-8") as out:
                for index, paragraph in enumerate(paragraphs):
                    out.write(json.dumps({"chunk_id": f"{doc_id}-{index:04d}", "doc_id": doc_id, "text": paragraph,
                                          "page_start": None, "page_end": None, "section": None,
                                          "language": manifest["language"], "industry": manifest["industry"],
                                          "process": manifest["process"], "source_url": None,
                                          "evidence_level": "source_document", "review_status": "pending"}, ensure_ascii=False) + "\n")
            manifests.append(manifest)
        except Exception as exc:
            (args.output / "rejected" / f"{path.stem}.json").write_text(json.dumps({"file_name": path.name, "error": repr(exc)}, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "run-log.json").write_text(json.dumps({"files": manifests}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"processed": len(manifests), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
