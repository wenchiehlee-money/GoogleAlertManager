#!/usr/bin/env python3
"""Check competitive-group names against the cross-theme canonical name registry."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def find_root() -> Path:
    for candidate in (Path.cwd(), *Path.cwd().parents):
        if (candidate / "data" / "themes").is_dir() and (candidate / "skills" / "skill-theme-competitor-groups-curate").is_dir():
            return candidate
    raise SystemExit("Cannot find My-TW-Coverage root. Run from the repository root.")


ROOT = find_root()
SKILL_DIR = ROOT / "skills" / "skill-theme-competitor-groups-curate"


def main() -> int:
    registry_path = SKILL_DIR / "references" / "canonical_group_names.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    alias_to_canonical: dict[str, str] = {}
    for canonical, definition in registry.items():
        alias_to_canonical[canonical] = canonical
        for alias in definition.get("aliases", []):
            alias_to_canonical[str(alias)] = canonical

    findings: list[str] = []
    seen: dict[str, list[str]] = {}
    for path in sorted((ROOT / "data" / "themes").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for group in data.get("competitive_groups", []) or []:
            name = str(group.get("name") or "").strip()
            if not name:
                continue
            seen.setdefault(name, []).append(path.name)
            canonical = alias_to_canonical.get(name)
            if canonical and name != canonical:
                findings.append(f"{path.name}: group name {name!r} is an alias; use canonical {canonical!r}")

    if findings:
        print("競爭群組名稱檢查失敗：")
        print("\n".join(f"- {line}" for line in findings))
        return 1

    print(f"競爭群組名稱檢查通過：掃描 {len(seen)} 個不同名稱，沒有使用已登錄 alias。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
