#!/usr/bin/env python3
"""GoogleAlertManager watchlist and README maintenance helpers.

This script is bundled with skills/common/skill-google-alert-fetch so the skill's
SOP and the repository automation share the same implementation.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE_URL = "https://raw.githubusercontent.com/wenchiehlee/Selenium-Actions.Auction/refs/heads/main/"
WATCHLIST_FILES = [
    ("%E8%A7%80%E5%AF%9F%E5%90%8D%E5%96%AE.csv", "StockID_TWSE_TPEX.csv"),
    ("%E5%B0%88%E6%B3%A8%E5%90%8D%E5%96%AE.csv", "StockID_TWSE_TPEX_focus.csv"),
]
REPORT_TABLE_START = "<!-- REPORT_TABLE_START -->"
REPORT_TABLE_END = "<!-- REPORT_TABLE_END -->"
TZ_TAIPEI = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class Company:
    stock_id: str
    name: str


def today_taipei() -> date:
    return datetime.now(TZ_TAIPEI).date()


def resolve_repo_root(repo_root: str | Path | None = None) -> Path:
    if repo_root:
        return Path(repo_root).expanduser().resolve()
    return Path.cwd().resolve()


def read_focus_companies(repo_root: Path) -> list[Company]:
    return read_company_csv(repo_root / "StockID_TWSE_TPEX_focus.csv")


def read_company_csv(path: Path) -> list[Company]:
    companies: list[Company] = []
    if not path.exists():
        return companies
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 2:
                continue
            stock_id = row[0].strip()
            name = row[1].strip()
            if not stock_id or not stock_id[0].isdigit():
                continue
            companies.append(Company(stock_id=stock_id, name=name))
    return companies


def update_watchlist(repo_root: Path) -> list[Path]:
    saved: list[Path] = []
    for remote_name, local_name in WATCHLIST_FILES:
        url = BASE_URL + remote_name
        dest = repo_root / local_name
        print(f"Downloading {local_name}...")
        urllib.request.urlretrieve(url, dest)
        print(f"  -> saved to {dest}")
        saved.append(dest)
    return saved


def parse_readme_rows(readme_path: Path) -> list[Company]:
    if not readme_path.exists():
        return []
    content = readme_path.read_text(encoding="utf-8")
    block = re.search(
        rf"{re.escape(REPORT_TABLE_START)}(.*?){re.escape(REPORT_TABLE_END)}",
        content,
        re.S,
    )
    if not block:
        return []
    rows: list[Company] = []
    for line in block.group(1).splitlines():
        if not line.startswith("| "):
            continue
        if line.startswith("| 名稱") or ":---:" in line:
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) >= 2:
            rows.append(Company(stock_id=parts[1], name=parts[0]))
    return rows


def check_readme_consistency(repo_root: Path) -> dict[str, object]:
    focus = read_focus_companies(repo_root)
    rows = parse_readme_rows(repo_root / "README.md")
    focus_ids = [company.stock_id for company in focus]
    row_ids = [company.stock_id for company in rows]
    return {
        "focus_count": len(focus_ids),
        "readme_count": len(row_ids),
        "missing_from_readme": [
            {"stock_id": company.stock_id, "name": company.name}
            for company in focus
            if company.stock_id not in row_ids
        ],
        "extra_in_readme": [
            {"stock_id": company.stock_id, "name": company.name}
            for company in rows
            if company.stock_id not in focus_ids
        ],
        "order_same": focus_ids == row_ids,
    }


def _load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_readme_table(repo_root: Path, today: date | None = None) -> tuple[str, int]:
    current_day = today or today_taipei()
    days = [current_day - timedelta(days=i) for i in range(7)]

    alerts_dir = repo_root / "data" / "alerts"
    reports_dir = repo_root / "data" / "reports"
    scores = _load_json(repo_root / "data" / "scores.json", {})

    companies = read_focus_companies(repo_root)
    stocks: dict[str, dict] = {
        company.stock_id: {"name": company.name, "counts": {}, "top_counts": {}}
        for company in companies
    }

    for day in reversed(days):
        day_dir = alerts_dir / day.isoformat()
        if not day_dir.exists():
            continue
        for json_file in sorted(day_dir.glob("*.json")):
            stock_id = json_file.stem
            if stock_id not in stocks:
                continue
            entries = _load_json(json_file, [])
            stocks[stock_id]["counts"][day] = len(entries)
            top = sum(
                1
                for entry in entries
                if scores.get(entry.get("id", ""), {}).get("score", -1) >= 4
            )
            if top:
                stocks[stock_id]["top_counts"][day] = top

    day_headers = []
    for day in days:
        summary_file = f"{day.isoformat()}-summary.md"
        if (reports_dir / summary_file).exists():
            day_headers.append(f"[{day.strftime('%m/%d')}](data/reports/{summary_file})")
        else:
            day_headers.append(day.strftime("%m/%d"))

    header_cols = ["名稱", "代號", day_headers[0], day_headers[1], *day_headers[2:]]
    lines = [
        "| " + " | ".join(header_cols) + " |",
        "| " + " :---: |" * len(header_cols),
    ]

    for stock_id, info in stocks.items():
        row_data = [info["name"], stock_id]
        for day in days:
            count = info["counts"].get(day, "-")
            top = info["top_counts"].get(day, 0)
            report_path = reports_dir / day.isoformat() / f"{stock_id}.md"

            if count != "-" and report_path.exists():
                link_all = f"data/reports/{day.isoformat()}/{stock_id}.md"
                general = count - top if isinstance(count, int) else 0
                top_anchor = urllib.parse.quote(f"⭐-高分精選文章-score-≥-4-{top}")
                general_anchor = urllib.parse.quote(f"📊-文章統計與來源-含一般文章-{general}")
                if top > 0:
                    label = f"[{general}]({link_all}?id={general_anchor}) ([{top}]({link_all}?id={top_anchor}))"
                else:
                    label = f"[{general}]({link_all}?id={general_anchor})"
            else:
                general = count - top if isinstance(count, int) and isinstance(top, int) else count
                label = f"{general}({top})" if top > 0 else str(general)
            row_data.append(label)
        lines.append(f"| {' | '.join(row_data)} |")

    return "\n".join(lines), len(stocks)


def update_readme(repo_root: Path, today: date | None = None) -> int:
    table, stock_count = build_readme_table(repo_root, today=today)
    new_block = (
        f"{REPORT_TABLE_START}\n\n"
        "## 報告彙整（近 7 天）\n\n"
        f"{table}\n\n"
        f"{REPORT_TABLE_END}"
    )

    readme_path = repo_root / "README.md"
    content = readme_path.read_text(encoding="utf-8")
    if REPORT_TABLE_START in content:
        content = re.sub(
            rf"{re.escape(REPORT_TABLE_START)}.*?{re.escape(REPORT_TABLE_END)}",
            new_block,
            content,
            flags=re.DOTALL,
        )
    else:
        content = content.rstrip() + "\n\n" + new_block + "\n"
    readme_path.write_text(content, encoding="utf-8", newline="\n")
    return stock_count


def _print_consistency(result: dict[str, object]) -> None:
    print("focus_count", result["focus_count"])
    print("readme_count", result["readme_count"])
    print("missing_from_readme", result["missing_from_readme"])
    print("extra_in_readme", result["extra_in_readme"])
    print("order_same", result["order_same"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=None, help="GoogleAlertManager repo root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("update-list", help="Download watchlist CSV files")

    update_readme_parser = subparsers.add_parser("update-readme", help="Update README report table")
    update_readme_parser.add_argument("--today", default=None, help="Override today as YYYY-MM-DD")

    check_parser = subparsers.add_parser("check-readme", help="Check README rows against focus CSV")
    check_parser.add_argument("--json", action="store_true", help="Print JSON result")

    args = parser.parse_args(argv)
    repo_root = resolve_repo_root(args.repo_root)

    if args.command == "update-list":
        update_watchlist(repo_root)
        return 0

    if args.command == "update-readme":
        override_today = date.fromisoformat(args.today) if args.today else None
        stock_count = update_readme(repo_root, today=override_today)
        print(f"README.md 已更新，共 {stock_count} 支股票")
        return 0

    if args.command == "check-readme":
        result = check_readme_consistency(repo_root)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            _print_consistency(result)
        ok = (
            result["focus_count"] == result["readme_count"]
            and not result["missing_from_readme"]
            and not result["extra_in_readme"]
            and result["order_same"] is True
        )
        return 0 if ok else 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
