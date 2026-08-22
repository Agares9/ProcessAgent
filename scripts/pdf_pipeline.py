#!/usr/bin/env python3
"""Conservative PDF extraction pipeline for the manufacturing knowledge base.

The command never edits source PDFs. It extracts text with PyMuPDF, records a
page for every output paragraph, and only offers OCR for pages with no useful
text. OCR is intentionally an explicit opt-in (``--ocr-command``).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF
except ImportError as exc:  # pragma: no cover - exercised in dependency checks
    raise SystemExit("PyMuPDF is required: python -m pip install -r requirements.txt") from exc


CASE_FIELDS = ["行业", "工艺", "工厂/设备背景", "改造前基线", "改造措施", "参数条件",
               "能耗/物耗", "节能量", "减排量", "投资额", "回收期", "产能和质量影响",
               "适用条件", "限制", "来源页码"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def language(text: str) -> str:
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cjk and latin and 0.35 <= cjk / max(latin, 1) <= 2.8:
        return "zh-en"
    return "zh" if cjk >= latin else "en"


def useful(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[-\s]?)?(?:1\d{10}|0\d{2,3}[-\s]?\d{7,8}(?:[-\s]\d{1,6})?)(?!\d)")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")


def clean_contact_text(text: str) -> str:
    """Remove direct contact details from indexable text, retaining names.

    The unmodified page text remains in parsed/*.json for auditability.
    """
    kept = []
    skipping_address_continuation = False
    for original in text.splitlines():
        line = original.strip()
        if not line:
            kept.append("")
            continue
        # Administrative/contact and promotional noise is excluded from index text.
        if re.match(r"^(?:联系人|联系|电话|传真|手机|邮\s*箱|电子邮箱|网址|网站|网\s*站|地\s*址|地址|通讯地址|作者|编制|审核|校对|主编)\s*[:：]", line, re.I):
            continue
        if re.match(r"^(?:案例技术企业|技术企业|联系人单位|申报单位)\s*[:：]", line, re.I):
            continue
        if re.match(r"^(?:联系我们|家园的模样|节能推广之歌|版权所有|目录|Contents?)", line, re.I) or "节能推广之歌" in line:
            continue
        if re.fullmatch(r"[—\-_=~·•\s]+", line) or re.fullmatch(r"\d{1,4}", line):
            continue
        compact_label = re.sub(r"\s+", "", line)
        if skipping_address_continuation and (original[:1].isspace() or not line):
            if not line:
                skipping_address_continuation = False
            continue
        if re.match(r"^(?:网站|网址|地址|联系地址|邮箱|电子邮箱)[:：]", compact_label, re.I):
            skipping_address_continuation = compact_label.startswith(("地址", "联系地址"))
            continue
        if re.match(r"^地\s*址\s*[:：]", line):
            skipping_address_continuation = True
            continue
        line = EMAIL_RE.sub("", line)
        line = PHONE_RE.sub("", line)
        line = re.sub(r"https?://\S+|www\.\S+", "", line, flags=re.I)
        line = re.sub(r"^(?:网\s*站|网\s*址|地\s*址|联系地址|邮\s*箱|电子邮箱|联系我们)\s*[:：]?\s*$", "", line, flags=re.I)
        # Names left by a stripped contact line, e.g. ``张三：`` or ``王  蔓``.
        if re.fullmatch(r"[\u3400-\u9fff]{2,4}\s*[:：]", line):
            continue
        if re.match(r"^（?原[：:、]?", line) and re.search(r"公司|有限公司", line):
            continue
        if re.search(r"(?:工业园|开发区|大厦|街道|创新智汇园).*(?:栋|号|层)", line) and not re.search(r"(?:设备|装置|系统|工艺|参数|管径|压力|温度)", line):
            continue
        # A line containing only a number/contact fragment is not useful evidence.
        if not line.strip() or (re.fullmatch(r"[\d\s()+\-]+", line.strip()) and len(re.findall(r"\d", line)) >= 5):
            continue
        kept.append(line.rstrip())
    return "\n".join(kept)


def source_type(path: Path) -> str:
    joined = str(path.parent).lower()
    if "bref" in joined or "eu" in joined:
        return "industry_reference"
    if any(x in joined for x in ("生态环境", "工信部", "发改委")):
        return "government_technical_document"
    return "technical_document"


def guess_industry(path: Path) -> str:
    text = path.name.lower()
    terms = {"钢铁": "钢铁", "化工": "化工合成", "chemical": "chemical", "汽车": "汽车",
             "铸造": "铸造", "电镀": "电镀", "纺织": "纺织", "锅炉": "能源管理",
             "energy": "energy management", "cooling": "能源管理", "metal": "金属加工"}
    return next((v for k, v in terms.items() if k in text), "制造业")


def extract(path: Path, ocr_command: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    doc = fitz.open(path)
    pages: list[dict[str, Any]] = []
    ocr_pages = []
    for number, page in enumerate(doc, 1):
        raw = page.get_text("text") or ""
        text = raw.strip()
        parser = "pymupdf"
        if len(useful(text)) < 20:
            ocr_pages.append(number)
            if ocr_command:
                command = shlex.split(ocr_command) + [str(path), str(number)]
                result = subprocess.run(command, capture_output=True, text=True, check=False)
                if result.returncode == 0 and result.stdout.strip():
                    text, parser = result.stdout.strip(), "ocr"
        pages.append({"page": number, "raw_text": raw, "text": text, "parser": parser})
    density = sum(1 for p in pages if len(re.findall(r"\t| {3,}|\|", p["raw_text"])) >= 4)
    meta = {"page_count": len(doc), "ocr_pages": ocr_pages, "table_pages": density,
            "has_tables": density >= max(1, len(pages) // 10)}
    return pages, meta


def headings(text: str) -> list[str]:
    found = []
    for line in text.splitlines():
        line = line.strip()
        if len(line) > 80 or re.search(r"(?:电话|手机|邮箱|网址|地址)\s*[:：]", line):
            continue
        if re.match(r"^(?:第[一二三四五六七八九十百]+[章节部分]|\d+(?:\.\d+)+\s+|[一二三四五六七八九十]+[、.]\s*|#{1,6}\s+)", line):
            found.append(re.sub(r"^#+\s*", "", line))
    return found


def markdown(path: Path, pages: list[dict[str, Any]], manifest: dict[str, Any]) -> str:
    front = "---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in manifest.items()) + "\n---\n\n"
    body = [front, f"# {manifest['title']}\n"]
    for item in pages:
        body.extend([f"\n<!-- page: {item['page']} -->\n", clean_contact_text(item["text"]) or "[NO_TEXT: OCR required]", "\n"])
    return "".join(body)


def chunks(pages: list[dict[str, Any]], manifest: dict[str, Any], target: int = 2800) -> list[dict[str, Any]]:
    result = []
    for item in pages:
        text = clean_contact_text(item["text"])
        if not text:
            continue
        paragraphs = [x.strip() for x in re.split(r"\n{2,}|(?<=。)\s+", text) if x.strip()]
        current: list[str] = []
        size = 0
        for paragraph in paragraphs:
            if current and size + len(paragraph) > target:
                result.append(chunk_record("\n\n".join(current), item["page"], manifest))
                # Roughly 100-150 Chinese/English tokens, retained across boundaries.
                overlap = current[-1][-500:]
                current, size = [overlap], len(overlap)
            current.append(paragraph)
            size += len(paragraph)
        if current:
            result.append(chunk_record("\n\n".join(current), item["page"], manifest))
    return result


def chunk_record(text: str, page: int, manifest: dict[str, Any]) -> dict[str, Any]:
    return {"chunk_id": f"{manifest['doc_id']}-p{page}-{hashlib.sha1(text.encode()).hexdigest()[:10]}",
            "doc_id": manifest["doc_id"], "text": text, "page_start": page, "page_end": page,
            "section": headings(text)[0] if headings(text) else None, "language": manifest["language"],
            "industry": manifest["industry"], "process": manifest["process"],
            "source_url": manifest["source_url"], "evidence_level": "source_document",
            "review_status": "pending"}


def process(path: Path, out: Path, ocr_command: str | None) -> dict[str, Any]:
    digest = sha256(path)
    pages, facts = extract(path, ocr_command)
    text = "\n".join(p["text"] for p in pages)
    doc_id = digest[:16]
    manifest = {"doc_id": doc_id, "file_name": path.name, "title": path.stem,
                "language": language(text), "source_type": source_type(path), "source_org": path.parent.name,
                "source_url": None, "industry": guess_industry(path), "process": "未人工确认",
                "published_at": None, "retrieved_at": datetime.now(timezone.utc).date().isoformat(),
                "license": "未人工确认", "sha256": digest, "parser": "pymupdf",
                "page_count": facts["page_count"], "extraction_status": "needs_ocr" if facts["ocr_pages"] else "extracted",
                "review_status": "pending", "ocr_pages": facts["ocr_pages"], "has_tables": facts["has_tables"],
                "table_pages": facts["table_pages"], "case_fields": {key: None for key in CASE_FIELDS}}
    (out / "parsed").mkdir(parents=True, exist_ok=True); (out / "normalized").mkdir(parents=True, exist_ok=True)
    (out / "chunks").mkdir(parents=True, exist_ok=True); (out / "manifests").mkdir(parents=True, exist_ok=True)
    (out / "parsed" / f"{doc_id}.json").write_text(json.dumps({"manifest": manifest, "pages": pages}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "normalized" / f"{doc_id}.md").write_text(markdown(path, pages, manifest), encoding="utf-8")
    (out / "manifests" / f"{doc_id}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "chunks" / f"{doc_id}.jsonl").open("w", encoding="utf-8") as stream:
        for chunk in chunks(pages, manifest): stream.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--input", type=Path, default=Path("文档"))
    parser.add_argument("--sample", action="store_true", help="process up to 3 zh, 3 en, and 2 likely scans")
    parser.add_argument("--output", type=Path, default=Path("manufacturing-data"))
    parser.add_argument("--run-log", default="run-log.json", help="name of the processing log under --output")
    parser.add_argument("--ocr-command", help="explicit command receiving PDF path and page number")
    args = parser.parse_args()
    files = [p for p in args.files if p.suffix.lower() == ".pdf"]
    if args.sample:
        candidates = sorted(args.input.rglob("*.pdf"))
        selected: list[Path] = []
        buckets: dict[str, list[Path]] = {"zh": [], "en": [], "scan": []}
        for p in candidates:
            try:
                probe = fitz.open(p)
                first = (probe[0].get_text("text") if len(probe) else "").strip()
                probe.close()
            except Exception:
                continue
            if len(useful(first)) < 20:
                buckets["scan"].append(p)
            else:
                buckets["zh" if language(first).startswith("zh") else "en"].append(p)
        for bucket, count in (("zh", 3), ("en", 3), ("scan", 2)):
            selected.extend(buckets[bucket][:count])
        files = selected
    if not files:
        parser.error("pass PDF files explicitly or use --sample; refusing to process the entire corpus")
    for directory in ("raw", "parsed", "normalized", "chunks", "manifests", "reviewed", "rejected"):
        (args.output / directory).mkdir(parents=True, exist_ok=True)
    manifests: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for path in files:
        try:
            manifests.append(process(path, args.output, args.ocr_command))
        except Exception as exc:  # parsing failures must be visible, never silently skipped
            failures.append({"file_name": path.name, "path": str(path), "error": repr(exc)})
    (args.output / "rejected").mkdir(parents=True, exist_ok=True)
    for failure in failures:
        name = hashlib.sha1(failure["path"].encode()).hexdigest()[:16]
        (args.output / "rejected" / f"{name}.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
    hashes = Counter(item["sha256"] for item in manifests)
    quality = {"short_or_empty": [item["doc_id"] for item in manifests if item["extraction_status"] == "needs_ocr"],
               "ocr_pages": {item["doc_id"]: item["ocr_pages"] for item in manifests if item["ocr_pages"]},
               "table_documents": [item["doc_id"] for item in manifests if item["has_tables"]],
               "duplicate_sha256": [digest for digest, count in hashes.items() if count > 1],
               "missing_source_or_license": [item["doc_id"] for item in manifests if not item["source_url"] or item["license"] == "未人工确认"]}
    (args.output / args.run_log).write_text(json.dumps({"files": manifests, "failures": failures, "quality": quality}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"processed": len(manifests), "rejected": len(failures), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
