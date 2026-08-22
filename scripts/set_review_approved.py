#!/usr/bin/env python3
"""Mark generated knowledge-base JSON records as approved on explicit request."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def update(value):
    count = 0
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "review_status":
                value[key] = "approved"
                count += 1
            else:
                count += update(child)
    elif isinstance(value, list):
        for child in value:
            count += update(child)
    return count


def main() -> None:
    root = Path("manufacturing-data")
    files = [p for p in root.rglob("*.json") if "rejected" not in p.parts]
    files += [p for p in root.rglob("*.jsonl") if "rejected" not in p.parts]
    changed_files = changed_values = 0
    for path in sorted(set(files)):
        original = path.read_text(encoding="utf-8")
        if path.suffix == ".jsonl":
            rows = [json.loads(line) for line in original.splitlines() if line.strip()]
            count = sum(update(row) for row in rows)
            updated = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else "")
        else:
            data = json.loads(original)
            count = update(data)
            updated = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        if count:
            path.write_text(updated, encoding="utf-8")
            changed_files += 1
            changed_values += count
    audit = {"updated_at": datetime.now(timezone.utc).isoformat(), "status": "approved",
             "changed_files": changed_files, "changed_values": changed_values,
             "note": "Explicit user instruction; extraction_status and OCR flags were not changed."}
    (root / "approval-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    main()
