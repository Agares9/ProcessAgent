#!/usr/bin/env python3
"""Supplement manifest metadata and existing chunk values without changing schema."""
from __future__ import annotations

import json
import re
from pathlib import Path


def infer(manifest: dict, category: str, source_root: Path) -> tuple[str, str, str, str]:
    title = manifest.get("title", "")
    name = f"{category} {title}".lower()
    if source_root.name == "doe":
        process = category if category in {"compressed air", "process heating", "project manufacturing", "steam"} else "industrial electrification"
        return "doe", "doe_case", "制造业", process
    if category == "fagaiwei":
        group, evidence = "fagaiwei", "C"
        if "实施指南" in title: doc_type, process = "technical_guideline", "节能降碳改造"
        elif "案例" in title or "目录" in title: doc_type, process = "case_catalog", "节能技术推广"
        else: doc_type, process = "technical_reference", "节能低碳"
        return group, doc_type, "能源管理", process
    if category == "gongxinbu":
        if "钢铁" in title: industry = "钢铁"
        elif "汽车" in title: industry = "汽车"
        elif "化工" in title: industry = "化工"
        elif "纺织" in title: industry = "纺织"
        elif "建材" in title: industry = "建材"
        elif "锅炉" in title or "余热" in title or "电机" in title: industry = "能源管理"
        else: industry = "制造业"
        process = "绿色设计" if "绿色设计" in title else "节能提效"
        return "gongxinbu", "technical_reference", industry, process
    if category == "shengtaihuanjingbu":
        industry = next((x for x in ("陶瓷", "铸造", "纺织", "矿物棉", "电镀", "玻璃", "炼焦", "火电", "涂料", "汽车", "氮肥", "锅炉", "屠宰", "家具", "印刷", "制革", "制糖", "制浆造纸", "农药") if x in title), "制造业")
        return "shengtaihuanjingbu", "pollution_control_guideline", industry, "污染防治"
    if category == "eubref":
        industry = "化工" if "chemical" in name or "organic" in name else ("钢铁" if "steel" in name or "ferrous" in name else "制造业")
        return "eubref", "bref", industry, "环境污染预防与控制"
    return category, manifest.get("doc_type", "technical_reference"), manifest.get("industry", "制造业"), manifest.get("process", "未人工确认")


def update_chunks(chunk_dir: Path, industry: str, process: str, evidence: str) -> int:
    changed = 0
    for path in chunk_dir.glob("*.jsonl"):
        lines = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            item = json.loads(line)
            if item.get("industry") in (None, "", "制造业") and industry != "制造业": item["industry"] = industry; changed += 1
            if item.get("process") in (None, "", "未人工确认") and process != "未人工确认": item["process"] = process; changed += 1
            if item.get("evidence_level") in (None, "source_document"): item["evidence_level"] = evidence; changed += 1
            lines.append(json.dumps(item, ensure_ascii=False))
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return changed


def main() -> None:
    root = Path("manufacturing-data")
    manifest_count = chunk_changes = 0
    for path in sorted(root.rglob("manifests/*.json")):
        category = path.parents[2].name if path.parents[2].name == "doe" else path.parents[1].name
        subcategory = path.parents[1].name if category == "doe" else category
        manifest = json.loads(path.read_text(encoding="utf-8"))
        group, doc_type, industry, process = infer(manifest, subcategory if category == "doe" else category, root / category)
        manifest.update({"source_group": group, "doc_type": doc_type, "industry": industry,
                         "process": process, "evidence_level": "D" if group == "doe" else ("E" if group == "eubref" else "C"),
                         "source_path": str(Path("文档") / ("美国DOE" if group == "doe" else "欧盟BREF" if group == "eubref" else "发改委和国家节能中心" if group == "fagaiwei" else "工信部" if group == "gongxinbu" else "生态环境部") / manifest.get("file_name", "")),
                         "metadata_status": "machine_supplemented_needs_review"})
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest_count += 1
        # Find the sibling chunk directories, including DOE category subdirectories.
        for chunk_dir in (path.parents[1] / "chunks",):
            if chunk_dir.exists(): chunk_changes += update_chunks(chunk_dir, industry, process, manifest["evidence_level"])
    # Markdown manifest directory uses a separate name.
    for path in sorted(root.glob("*/md-manifests/*.json")):
        category = path.parents[1].name
        manifest = json.loads(path.read_text(encoding="utf-8"))
        group, doc_type, industry, process = infer(manifest, category, root / category)
        manifest.update({"source_group": group, "doc_type": doc_type, "industry": industry, "process": process,
                         "evidence_level": "C", "metadata_status": "machine_supplemented_needs_review"})
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest_count += 1
        chunk_changes += update_chunks(path.parents[1] / "md-chunks", industry, process, "C")
    print(json.dumps({"manifests_updated": manifest_count, "chunk_values_updated": chunk_changes}, ensure_ascii=False))


if __name__ == "__main__":
    main()
