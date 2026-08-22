#!/usr/bin/env python3
"""Create bilingual navigation and BAT translation work items for BREF PDFs.

This does not translate full BREFs. English source text remains authoritative;
Chinese summaries and terminology make Chinese retrieval practical. BAT items are
separate translation/review units so values, units and conditions are not guessed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


DOCS = {
    "Common Waste Gas Management in Chemical Sector": ("化工行业共性废气管理与处理", "覆盖化工生产过程的有组织与无组织废气控制，重点包括排放源识别、泄漏控制、收集与处理系统、监测及环境管理。", ["化工废气", "无组织排放", "泄漏检测与修复", "废气收集", "BAT"]),
    "Energy Efficiency": ("能源效率", "提供跨行业的能源管理、系统优化、能效监测和最佳可行技术评估框架，适用于工业装置及公用工程系统。", ["能源效率", "能源管理系统", "能效监测", "系统优化", "BAT"]),
    "Ferrous Metals Processing Industry": ("黑色金属加工行业", "涵盖钢铁后续加工中的表面处理、轧制、酸洗、涂覆等过程，关注能源和水资源消耗、废水、废气与工艺排放控制。", ["黑色金属加工", "轧制", "酸洗", "表面处理", "BAT"]),
    "Food, Drink and Milk Industries": ("食品、饮料和乳制品行业", "适用于食品、饮料和乳制品的原料处理及加工，重点关注废水排放、能源和水耗、清洗消毒及资源效率。", ["食品加工", "废水", "清洗消毒", "水耗", "BAT"]),
    "Industrial Cooling Systems": ("工业冷却系统", "涵盖一次通过式、循环式及蒸发式冷却系统，关注取排水、热污染、冷却水化学处理、微生物控制和能效。", ["工业冷却", "循环冷却水", "热污染", "冷却塔", "BAT"]),
    "Iron and Steel Production ": ("钢铁生产", "覆盖烧结、焦化、高炉、炼钢、铸造和轧制相关工序，重点是大气排放、能源效率、原料利用、副产物回收和水管理。", ["钢铁生产", "烧结", "高炉", "炼钢", "BAT"]),
    "Large Volume Organic Chemicals": ("大宗有机化学品生产", "覆盖连续化大宗有机化学品生产及相关炉窑燃烧，重点关注废气与废水排放、能源和水效率、残渣最小化与回收。", ["大宗有机化学品", "连续化生产", "废气治理", "资源效率", "BAT"]),
    "Non-ferrous Metals Industries": ("有色金属工业", "覆盖有色金属冶炼与加工中的原料处理、熔炼、精炼和烟气净化，重点关注粉尘、二氧化硫、重金属排放和能源利用。", ["有色金属", "冶炼", "烟气净化", "重金属", "BAT"]),
    "Surface Treatment of Metals and Plastics": ("金属和塑料表面处理", "涵盖电镀、化学处理和相关表面处理过程，重点关注槽液管理、废水、废气、重金属、资源回收及能耗。", ["电镀", "表面处理", "重金属", "槽液管理", "BAT"]),
    "Waste Treatment": ("废物处理", "覆盖危险和非危险废物的接收、贮存、预处理、物化处理和废气废水控制，强调环境管理与全过程风险控制。", ["废物处理", "危险废物", "预处理", "废气治理", "BAT"]),
}

TERMS = {
    "BAT": "最佳可行技术", "BAT conclusions": "最佳可行技术结论", "BAT-AEL": "与最佳可行技术相关的排放水平",
    "emission limit value": "排放限值", "environmental management system": "环境管理体系",
    "fugitive emissions": "无组织排放", "waste gas": "废气", "waste water": "废水",
    "resource efficiency": "资源效率", "energy efficiency": "能源效率", "monitoring": "监测",
    "integrated pollution prevention and control": "综合污染预防与控制",
}


def main() -> None:
    root = Path("manufacturing-data/eubref")
    nav_dir = root / "zh-navigation"
    nav_dir.mkdir(parents=True, exist_ok=True)
    summaries, bat_items = [], []
    for manifest_path in sorted((root / "manifests").glob("*.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        title = manifest["title"]
        zh_title, summary, keywords = DOCS.get(title, (title, "待人工补充中文技术摘要。", ["BAT", "BREF"]))
        summaries.append({"doc_id": manifest["doc_id"], "title_en": title, "title_zh": zh_title,
                          "summary_zh": summary, "keywords_zh": keywords, "terms_zh": TERMS,
                          "review_status": "pending", "translation_scope": "summary_and_bat_only"})
        parsed = json.loads((root / "parsed" / f"{manifest['doc_id']}.json").read_text(encoding="utf-8"))
        for page in parsed["pages"]:
            text = page["text"]
            if re.search(r"\bBAT\s+\d+\b|\bBAT conclusions\b", text, re.I):
                bat_items.append({"bat_item_id": f"{manifest['doc_id']}-p{page['page']}", "doc_id": manifest["doc_id"],
                                  "page": page["page"], "title_en": title, "title_zh": zh_title,
                                  "text_en": text, "translation_zh": None,
                                  "translation_status": "needs_translation_and_review", "review_status": "pending",
                                  "evidence_level": "E"})
    with (nav_dir / "bref_summaries_zh.jsonl").open("w", encoding="utf-8") as stream:
        for item in summaries: stream.write(json.dumps(item, ensure_ascii=False) + "\n")
    with (nav_dir / "bat_translation_worklist.jsonl").open("w", encoding="utf-8") as stream:
        for item in bat_items: stream.write(json.dumps(item, ensure_ascii=False) + "\n")
    index = {"documents": len(summaries), "bat_candidate_pages": len(bat_items),
             "retrieval_fields": ["text_en", "summary_zh", "keywords_zh", "terms_zh"],
             "production_rule": {"review_status": "approved"},
             "note": "BAT translations are intentionally blank until reviewed; do not infer numeric requirements from summaries."}
    (nav_dir / "README.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(index, ensure_ascii=False))


if __name__ == "__main__":
    main()
