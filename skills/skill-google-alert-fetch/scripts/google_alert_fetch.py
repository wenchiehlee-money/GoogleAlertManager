#!/usr/bin/env python3
"""GoogleAlertManager watchlist and README maintenance helpers.

This script is bundled with skills/common/skill-google-alert-fetch so the skill's
SOP and the repository automation share the same implementation.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

BASE_URL = "https://raw.githubusercontent.com/wenchiehlee/Selenium-Actions.Auction/refs/heads/main/"
WATCHLIST_FILES = [
    ("%E8%A7%80%E5%AF%9F%E5%90%8D%E5%96%AE.csv", "StockID_TWSE_TPEX.csv"),
    ("%E5%B0%88%E6%B3%A8%E5%90%8D%E5%96%AE.csv", "StockID_TWSE_TPEX_focus.csv"),
]
REPORT_TABLE_START = "<!-- REPORT_TABLE_START -->"
REPORT_TABLE_END = "<!-- REPORT_TABLE_END -->"
TZ_TAIPEI = timezone(timedelta(hours=8))
MAX_LLM_ENTRY_INPUT = 40


def today_taipei() -> date:
    return datetime.now(TZ_TAIPEI).date()


def resolve_repo_root(repo_root: str | Path | None = None) -> Path:
    if repo_root:
        return Path(repo_root).expanduser().resolve()
    return Path.cwd().resolve()


def _ensure_src_importable(repo_root: Path) -> None:
    """Make `src` (the app's library package) importable regardless of CWD.

    The skill script is the single implementation of every workflow step
    described in SKILL.md; it reuses `src` rather than reimplementing it.
    """
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


def read_focus_companies(repo_root: Path) -> list:
    """回傳專注清單公司（重用 src.companies.watchlist，避免重複解析 CSV）。"""
    _ensure_src_importable(repo_root)
    from src.companies.watchlist import load_companies

    return load_companies(focus_only=True)


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


class ReadmeRow(NamedTuple):
    stock_id: str
    name: str


def parse_readme_rows(readme_path: Path) -> list[ReadmeRow]:
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
    rows: list[ReadmeRow] = []
    for line in block.group(1).splitlines():
        if not line.startswith("| "):
            continue
        if line.startswith("| 名稱") or ":---:" in line:
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) >= 2:
            rows.append(ReadmeRow(stock_id=parts[1], name=parts[0]))
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


def cmd_list_companies(repo_root: Path) -> int:
    _ensure_src_importable(repo_root)
    from src.alerts.manager import get_rss_map
    from src.companies.watchlist import load_companies

    companies = load_companies()
    if not companies:
        print("找不到公司清單，請先執行 update-list。")
        return 0

    try:
        rss_map = get_rss_map()
    except Exception as e:
        print(f"[警告] 無法取得 Google Alert 狀態：{e}", file=sys.stderr)
        rss_map = {}

    print(f"共 {len(companies)} 家公司：\n")
    print(f"{'代號':<8} {'名稱':<12} {'類型':<8} {'Alert'}")
    print("-" * 50)
    for c in companies:
        list_label = "⭐ 專注" if c.list_type == "focus" else "   觀察"
        if not rss_map:
            has_alert = "(未連線)"
        else:
            has_alert = "✓ RSS 已設定" if c.stock_id in rss_map else "✗ 未建立"
        print(f"{c.stock_id:<8} {c.name:<12} {list_label:<8} {has_alert}")
    return 0


def cmd_sync(repo_root: Path) -> int:
    _ensure_src_importable(repo_root)
    from src.alerts.manager import sync_alerts

    result = sync_alerts()
    print(f"建立 : {', '.join(result['created']) or '(無)'}")
    print(f"刪除 : {', '.join(result['deleted']) or '(無)'}")
    print(f"保留 : {len(result['unchanged'])} 家")
    return 0


def cmd_fetch(repo_root: Path) -> int:
    _ensure_src_importable(repo_root)
    from src.alerts.fetcher import fetch_all
    from src.companies.watchlist import load_companies

    companies = load_companies()
    if not companies:
        print("找不到公司清單，請先執行 update-list。")
        return 1

    results = fetch_all(companies)
    total = sum(results.values())
    for stock_id, count in results.items():
        print(f"  {stock_id}: {count} 篇新文章")
    print(f"合計新增：{total} 篇")
    return 0


def cmd_export_rss(repo_root: Path) -> int:
    _ensure_src_importable(repo_root)
    from src.alerts.manager import get_rss_map

    rss_map = get_rss_map()
    output_path = repo_root / "config" / "rss_urls.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(rss_map, f, ensure_ascii=False, indent=2)
    print(f"已匯出 {len(rss_map)} 個 RSS URLs 至 {output_path}")
    print("請記得將此檔案 git commit 後再推送，以供 GitHub Actions 使用。")
    return 0


def cmd_analyze(repo_root: Path, day_str: str | None, stock_id: str | None, force: bool) -> int:
    _ensure_src_importable(repo_root)
    import subprocess as sp

    from src.analysis import llm
    from src.analysis.competitors import build_llm_context, build_markdown_table, load_competitor_data
    from src.companies.watchlist import load_companies
    from src.config import today_taipei as src_today_taipei
    from src.storage.json_store import load_entries_by_stock_id
    from src.storage.markdown_writer import (
        read_report_summary,
        summarize_llm_result,
        write_company_report,
        write_daily_summary,
    )
    from src.storage.scores_store import load_scores, update_scores

    day = date.fromisoformat(day_str) if day_str else src_today_taipei()
    companies = load_companies()
    if not companies:
        print("找不到公司清單，請先執行 update-list。")
        return 1

    if stock_id:
        companies = [c for c in companies if c.stock_id == stock_id]
        if not companies:
            print(f"找不到股票代碼 {stock_id}。")
            return 1

    entries_by_id = load_entries_by_stock_id(day)
    if not entries_by_id and not day_str:
        from src.config import ALERTS_DATA_DIR

        available = sorted(
            [d for d in ALERTS_DATA_DIR.iterdir() if d.is_dir() and d.name != day.isoformat()],
            key=lambda d: d.name,
            reverse=True,
        )
        if available:
            fallback = date.fromisoformat(available[0].name)
            print(f"找不到 {day} 的 entries，改用最近一天 {fallback}。")
            day = fallback
            entries_by_id = load_entries_by_stock_id(day)
    if not entries_by_id:
        print(f"找不到 {day} 的 entries，請先執行 fetch。")
        return 1

    generated_at = datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d %H:%M:%S CST")
    all_scores = load_scores()
    company_reports = []

    from src.config import REPORTS_DIR

    for company in companies:
        entries = entries_by_id.get(company.stock_id, [])
        if not entries:
            print(f"  {company.stock_id} {company.name}: 無資料，跳過")
            continue

        report_path = REPORTS_DIR / str(day) / f"{company.stock_id}.md"
        if report_path.exists() and not stock_id and not force:
            print(f"  {company.stock_id} {company.name}: 報告已存在，納入彙整")
            top_count = sum(
                1
                for e in entries
                if all_scores.get(e.get("id", ""), {}).get("score", -1) >= 4
            )
            company_reports.append({
                "stock_id": company.stock_id,
                "name": company.name,
                "list_type": company.list_type,
                "entry_count": len(entries),
                "top_count": top_count,
                "summary": read_report_summary(report_path),
            })
            continue

        print(f"  分析+評分 {company.stock_id} {company.name}（{len(entries)} 篇）…")
        llm_entries = entries
        if len(entries) > MAX_LLM_ENTRY_INPUT:
            llm_entries = entries[:MAX_LLM_ENTRY_INPUT]
            print(f"    LLM 輸入限制為最新 {MAX_LLM_ENTRY_INPUT} / {len(entries)} 篇，避免 prompt 過長")

        competitor_data = load_competitor_data(company.stock_id)
        competitor_context = build_llm_context(competitor_data)
        competitor_table = build_markdown_table(competitor_data)

        try:
            llm_result, new_scores = llm.analyze_and_score(
                company, llm_entries, competitor_context, known_scores=all_scores
            )
        except Exception as e:
            print(f"    合併分析+評分失敗，改用純分析：{e}", file=sys.stderr)
            try:
                llm_result = llm.analyze_company(
                    company, llm_entries, competitor_context, known_scores=all_scores
                )
                new_scores = {}
            except Exception as fallback_error:
                print(f"    LLM 失敗，跳過：{fallback_error}", file=sys.stderr)
                continue
        update_scores(new_scores)
        all_scores = load_scores()

        top_count = sum(1 for s in new_scores.values() if s.get("score", 0) >= 4)
        print(f"    高分文章（≥4）：{top_count} 篇")

        path = write_company_report(
            company, day, entries, llm_result, generated_at,
            scores=all_scores, competitor_table=competitor_table,
        )
        print(f"    -> {path}")

        sp.run(["git", "add", str(path)], check=False, capture_output=True, cwd=repo_root)
        sp.run(
            ["git", "commit", "-m", f"chore: report {company.stock_id} {day}"],
            check=False, capture_output=True, cwd=repo_root,
        )

        summary = summarize_llm_result(llm_result)
        company_reports.append({
            "stock_id": company.stock_id,
            "name": company.name,
            "list_type": company.list_type,
            "entry_count": len(entries),
            "top_count": top_count,
            "summary": summary,
        })

    if company_reports and not stock_id:
        summary_path = write_daily_summary(day, company_reports, generated_at)
        print(f"\n彙整報告：{summary_path}")
    return 0


def cmd_label(
    repo_root: Path, stock_id: str, day_str: str, entry_id: str, score: int, reason: str | None
) -> int:
    _ensure_src_importable(repo_root)
    import subprocess as sp

    from src.storage.scores_store import update_scores

    data_dir = repo_root / "data"
    alert_path = data_dir / "alerts" / day_str / f"{stock_id}.json"
    if not alert_path.exists():
        print(f"找不到文章：{alert_path}")
        return 1

    with open(alert_path, encoding="utf-8") as f:
        entries = json.load(f)

    target = next((e for e in entries if e.get("id") == entry_id), None)
    if not target:
        print(f"在 {alert_path} 中找不到 ID 為 {entry_id} 的文章。")
        return 1

    update_scores({
        entry_id: {
            "score": score,
            "reason": reason or target.get("title", ""),
            "source": "manual",
            "scored_at": datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d %H:%M:%S CST"),
        }
    })

    pref_path = data_dir / "user_preferences.json"
    prefs = []
    if pref_path.exists():
        with open(pref_path, encoding="utf-8") as f:
            prefs = json.load(f)

    prefs = [p for p in prefs if p["id"] != entry_id]
    prefs.append({
        "id": entry_id,
        "title": target.get("title", ""),
        "summary": target.get("summary", "")[:200],
        "score": score,
        "reason": reason,
    })
    prefs = prefs[-50:]
    with open(pref_path, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)

    train_path = data_dir / "training_data.jsonl"
    train_entry = {
        "timestamp": datetime.now(TZ_TAIPEI).isoformat(),
        "context": {"stock_id": stock_id, "company_name": target.get("name", "")},
        "input": {"title": target.get("title", ""), "summary": target.get("summary", "")},
        "label": {"score": score, "reason": reason},
    }
    with open(train_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(train_entry, ensure_ascii=False) + "\n")

    from src.storage.markdown_writer import write_bookmarks_page

    bookmark_path = data_dir / "bookmarks.json"
    bookmarks = []
    if bookmark_path.exists():
        with open(bookmark_path, encoding="utf-8") as f:
            try:
                bookmarks = json.load(f)
            except json.JSONDecodeError:
                bookmarks = []

    bookmarks = [b for b in bookmarks if b["id"] != entry_id]
    if score == 6:
        bookmarks.append({
            "id": entry_id,
            "stock_id": stock_id,
            "name": target.get("name", ""),
            "title": target.get("title", ""),
            "link": target.get("link", ""),
            "published": target.get("published", ""),
            "summary": target.get("summary", "")[:200],
            "reason": reason or target.get("title", ""),
            "marked_at": datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d %H:%M:%S CST"),
        })

    with open(bookmark_path, "w", encoding="utf-8") as f:
        json.dump(bookmarks, f, ensure_ascii=False, indent=2)

    bm_page_path = write_bookmarks_page(bookmarks)
    print(f"已更新書籤清單網頁：{bm_page_path}")

    sp.run(["git", "add", str(bookmark_path), str(bm_page_path)], check=False, capture_output=True, cwd=repo_root)
    sp.run(["git", "commit", "-m", f"chore: update bookmarks for {stock_id}"], check=False, capture_output=True, cwd=repo_root)

    print("✅ 成功：文章已標註並存入訓練數據集 (data/training_data.jsonl)。")
    print("AI 將在下次分析時學習此偏好，且此數據可用於未來模型微調。")
    return 0


def _self_invoke(repo_root: Path, *args: str) -> "subprocess.CompletedProcess[str]":
    """Re-run this script as a subprocess (used by sync-stale to reuse analyze/label)."""
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--repo-root", str(repo_root), *args],
        check=False,
    )


def cmd_sync_stale(repo_root: Path) -> int:
    import os

    def run_gh(args: list[str], check: bool = False) -> subprocess.CompletedProcess:
        return subprocess.run(["gh", *args], capture_output=True, text=True, check=check)

    def ensure_label(name: str, color: str, description: str) -> None:
        subprocess.run(
            ["gh", "label", "create", name, "--color", color, "--description", description],
            check=False, capture_output=True, text=True,
        )

    def add_label(issue_number: int, label: str) -> None:
        run_gh(["issue", "edit", str(issue_number), "--add-label", label])

    def comment(issue_number: int, body: str) -> None:
        run_gh(["issue", "comment", str(issue_number), "--body", body])

    def close_issue(issue_number: int, message: str) -> None:
        run_gh(["issue", "close", str(issue_number), "--comment", message])

    def mark_invalid(issue_number: int, message: str) -> None:
        add_label(issue_number, "invalid-input")
        comment(issue_number, message)

    def is_allowed_author(issue: dict) -> bool:
        allowed_authors = os.getenv("ISSUE_FEEDBACK_ALLOWED_AUTHORS", "wenchiehlee-money")
        allowed = {a.strip() for a in allowed_authors.split(",") if a.strip()}
        author = issue.get("author", {}).get("login", "")
        return not allowed or author in allowed

    def valid_day(day_str: str) -> bool:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", day_str))

    ensure_label("processed", "0E8A16", "Processed by issue feedback automation")
    ensure_label("rating-feedback", "1D76DB", "Manual rating feedback for AI learning")
    ensure_label("stale-refresh", "5319E7", "Request to refresh stale report output")
    ensure_label("invalid-input", "D93F0B", "Issue input did not match the automation format")
    ensure_label("processing-failed", "B60205", "Automation attempted the request but failed")

    try:
        cmd = [
            "gh", "issue", "list",
            "--search", "[STALE] OR [RATING] in:title",
            "--json", "number,title,body,author",
            "--state", "open",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        issues = json.loads(res.stdout)
        if not issues:
            print("無待處理的請求。")
            return 0

        for issue in issues:
            num, txt = issue["number"], issue["title"]

            if not is_allowed_author(issue):
                mark_invalid(num, "此 issue 的作者不在允許清單中，因此未自動處理。")
                print(f"跳過未授權作者的 Issue: {txt}")
                continue

            if "[STALE]" in txt:
                parts = txt.replace("[STALE]", "").strip().split()
                if len(parts) < 2 or not valid_day(parts[1]):
                    mark_invalid(num, "格式錯誤。請使用：`[STALE] stock_id YYYY-MM-DD`")
                    print(f"跳過格式錯誤的 STALE Issue: {txt}")
                    continue

                stock_id, day_str = parts[0], parts[1]
                print(f"處理過時標記：{stock_id} ({day_str})")
                result = _self_invoke(repo_root, "analyze", "--date", day_str, "--stock-id", stock_id, "--force")
                if result.returncode == 0:
                    add_label(num, "stale-refresh")
                    add_label(num, "processed")
                    close_issue(num, "✅ 報告已重新產生。")
                else:
                    add_label(num, "processing-failed")
                    comment(num, "自動重新產生報告失敗，請查看 GitHub Actions logs。")

            elif "[RATING]" in txt:
                parts = txt.replace("[RATING]", "").strip().split()
                if len(parts) < 4 or not valid_day(parts[1]):
                    mark_invalid(num, "格式錯誤。請使用：`[RATING] stock_id YYYY-MM-DD entry_id score`")
                    print(f"跳過格式錯誤的 RATING Issue: {txt}")
                    continue

                stock_id, day_str, entry_id, score_text = parts[0], parts[1], parts[2], parts[3]
                try:
                    score = int(score_text)
                except ValueError:
                    mark_invalid(num, "分數格式錯誤。`score` 必須是 1 到 6 的整數。")
                    print(f"跳過分數格式錯誤的 RATING Issue: {txt}")
                    continue
                if score < 1 or score > 6:
                    mark_invalid(num, "分數範圍錯誤。`score` 必須是 1 到 6 的整數。")
                    print(f"跳過分數範圍錯誤的 RATING Issue: {txt}")
                    continue

                reason = ""
                body = issue.get("body", "") or ""
                if "Reason:" in body:
                    reason = body.split("Reason:", 1)[1].strip()

                print(f"處理重評請求：{stock_id} {entry_id} -> {score} (理由: {reason})")

                label_args = ["label", stock_id, day_str, entry_id, str(score)]
                if reason:
                    label_args.extend(["--reason", reason])
                label_result = _self_invoke(repo_root, *label_args)
                if label_result.returncode != 0:
                    add_label(num, "processing-failed")
                    comment(num, "自動標註文章分數失敗，請查看 GitHub Actions logs。")
                    continue

                analyze_result = _self_invoke(
                    repo_root, "analyze", "--date", day_str, "--stock-id", stock_id, "--force"
                )
                if analyze_result.returncode == 0:
                    add_label(num, "rating-feedback")
                    add_label(num, "processed")
                    reason_suffix = f"理由：{reason}" if reason else "未提供理由。"
                    close_issue(num, f"✅ 文章已重新評分為 {score} 分並更新報表。AI 已學習此偏好。{reason_suffix}")
                else:
                    add_label(num, "processing-failed")
                    comment(num, "文章分數已標註，但重新產生報告失敗，請查看 GitHub Actions logs。")

            else:
                print(f"跳過格式錯誤的 Issue: {txt}")
        return 0
    except Exception as e:
        print(f"執行 sync-stale 失敗：{e}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=None, help="GoogleAlertManager repo root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("update-list", help="Download watchlist CSV files")

    update_readme_parser = subparsers.add_parser("update-readme", help="Update README report table")
    update_readme_parser.add_argument("--today", default=None, help="Override today as YYYY-MM-DD")

    check_parser = subparsers.add_parser("check-readme", help="Check README rows against focus CSV")
    check_parser.add_argument("--json", action="store_true", help="Print JSON result")

    subparsers.add_parser("list-companies", help="List watchlist companies and their Alert status")
    subparsers.add_parser("sync", help="Sync Google Alerts to match the watchlist")
    subparsers.add_parser("fetch", help="Fetch RSS entries for all companies")
    subparsers.add_parser("export-rss", help="Export current Google Alert RSS URLs to config/rss_urls.json")

    analyze_parser = subparsers.add_parser("analyze", help="Run LLM analysis + scoring, write reports")
    analyze_parser.add_argument("--date", dest="day_str", default=None, help="分析日期 (YYYY-MM-DD)")
    analyze_parser.add_argument("--stock-id", dest="stock_id", default=None, help="僅分析指定股票代碼")
    analyze_parser.add_argument("--force", action="store_true", default=False, help="強制重新分析")

    label_parser = subparsers.add_parser("label", help="Manually label an article's score")
    label_parser.add_argument("stock_id")
    label_parser.add_argument("day_str")
    label_parser.add_argument("entry_id")
    label_parser.add_argument("score", type=int)
    label_parser.add_argument("--reason", default=None)

    subparsers.add_parser("sync-stale", help="Process [STALE]/[RATING] GitHub issue requests")

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

    if args.command == "list-companies":
        return cmd_list_companies(repo_root)

    if args.command == "sync":
        return cmd_sync(repo_root)

    if args.command == "fetch":
        return cmd_fetch(repo_root)

    if args.command == "export-rss":
        return cmd_export_rss(repo_root)

    if args.command == "analyze":
        return cmd_analyze(repo_root, args.day_str, args.stock_id, args.force)

    if args.command == "label":
        return cmd_label(repo_root, args.stock_id, args.day_str, args.entry_id, args.score, args.reason)

    if args.command == "sync-stale":
        return cmd_sync_stale(repo_root)

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    import io as _io

    # Windows 終端預設 cp1252，強制改為 UTF-8 以輸出中文
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
        sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    raise SystemExit(main())
