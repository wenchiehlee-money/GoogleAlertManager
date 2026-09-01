#!/usr/bin/env python3
from pathlib import Path
import json, sys

ROOT = Path(__file__).resolve().parents[3]
SKILL = Path(__file__).resolve().parents[1]
errors, warnings = [], []

meta = SKILL / "metadata.json"
if not meta.exists():
    errors.append("Missing metadata.json")
else:
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        for key in ("name", "description", "category", "version", "source"):
            if not data.get(key): errors.append(f"metadata missing {key}")
        if "<owner>" in data.get("source", ""):
            warnings.append("Replace <owner> placeholder before registry publication")
    except Exception as exc:
        errors.append(f"Invalid metadata.json: {exc}")

for name in ("README.md", "AGENTS.md", "SOURCE_POLICY.md", "DATA_MODEL.md", "RESEARCH_WORKFLOW.md", "INFERENCE_FRAMEWORK.md"):
    if not (ROOT / name).exists(): errors.append(f"Missing {name}")

ignore = ROOT / ".gitignore"
if not ignore.exists() or "raw/" not in ignore.read_text(encoding="utf-8"):
    warnings.append("raw/ should be git-ignored")

for w in warnings: print("WARNING:", w)
for e in errors: print("ERROR:", e)
if errors: sys.exit(1)
print("OK" if not warnings else "OK with warnings")
