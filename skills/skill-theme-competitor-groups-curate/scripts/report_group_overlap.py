#!/usr/bin/env python3
"""Report cross-theme competitor-group overlap as a Markdown table.

The default metric is Jaccard overlap: intersection tickers divided by union tickers.
Group pairs with the same name are already canonicalized and are omitted by default.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path


@dataclass(frozen=True)
class Group:
    theme: str
    name: str
    tickers: frozenset[str]


def find_root() -> Path:
    for candidate in (Path.cwd(), *Path.cwd().parents):
        if (candidate / "data" / "themes").is_dir() and (candidate / "scripts" / "build_themes.py").is_file():
            return candidate
    raise SystemExit("Cannot find My-TW-Coverage root. Run from the repository root.")


def load_groups(root: Path) -> list[Group]:
    groups: list[Group] = []
    for path in sorted((root / "data" / "themes").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for raw in data.get("competitive_groups", []) or []:
            name = str(raw.get("name") or "").strip()
            tickers = frozenset(str(t).strip() for t in raw.get("tickers", []) or [] if str(t).strip())
            if name and tickers:
                groups.append(Group(path.stem, name, tickers))
    return groups


def markdown_report(groups: list[Group], threshold: float, include_same_name: bool) -> tuple[str, int]:
    rows: list[tuple[float, int, Group, Group, frozenset[str]]] = []
    for left, right in combinations(groups, 2):
        if left.theme == right.theme:
            continue
        if not include_same_name and left.name == right.name:
            continue
        intersection = left.tickers & right.tickers
        union = left.tickers | right.tickers
        coverage = len(intersection) / len(union)
        if coverage > threshold:
            rows.append((coverage, len(intersection), left, right, intersection))

    rows.sort(key=lambda row: (-row[0], -row[1], row[2].name, row[3].name))
    lines = [
        "| Group A | Group B | 小組覆蓋率 | 交集／聯集 | 交集公司 |",
        "|---|---|---:|---:|---|",
    ]
    for coverage, intersection_count, left, right, intersection in rows:
        lines.append(
            f"| `{left.name}`（{left.theme}） | `{right.name}`（{right.theme}） | "
            f"**{coverage:.0%}** | {intersection_count} / {len(left.tickers | right.tickers)} | "
            f"{', '.join(sorted(intersection))} |"
        )
    if not rows:
        lines.append(f"| （無跨 theme、不同名稱且 > {threshold:.0%} 的配對） |  |  |  |  |")
    return "\n".join(lines), len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=float, default=0.30, help="Report pairs with Jaccard overlap strictly above this value (default: 0.30).")
    parser.add_argument("--include-same-name", action="store_true", help="Include pairs whose group names are already identical.")
    parser.add_argument("--root", type=Path, help="My-TW-Coverage root; defaults to auto-detection.")
    args = parser.parse_args()
    if not 0 <= args.threshold < 1:
        parser.error("--threshold must be >= 0 and < 1")
    root = args.root.resolve() if args.root else find_root()
    report, count = markdown_report(load_groups(root), args.threshold, args.include_same_name)
    print(f"Jaccard 小組覆蓋率：交集公司數 ÷ 聯集公司數；門檻 > {args.threshold:.0%}")
    print()
    print(report)
    print()
    print(f"符合配對數：{count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
