"""Command-line interface for GoogleAlertManager（股票觀察名單驅動版）。"""

import io
import logging
import subprocess
import sys

# Windows 終端預設 cp1252，強制改為 UTF-8 以輸出中文
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import date, datetime, timedelta, timezone

from src.config import today_taipei
from pathlib import Path

import click

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@click.group()
def cli():
    """GoogleAlertManager — 股票觀察名單 × Google Alerts × Claude 分析。"""


def _google_alert_skill_script() -> Path:
    return (
        Path(__file__).parent
        / "skills"
        / "common"
        / "skill-google-alert-fetch"
        / "scripts"
        / "google_alert_fetch.py"
    )


def _run_google_alert_skill(*args: str) -> None:
    script = _google_alert_skill_script()
    if not script.exists():
        click.echo(f"找不到 Google Alert fetch skill script: {script}", err=True)
        sys.exit(1)
    subprocess.run(
        [sys.executable, str(script), "--repo-root", str(Path(__file__).parent), *args],
        check=True,
    )


@cli.command("update-list")
def update_list():
    """下載最新 CSV 觀察名單。"""
    _run_google_alert_skill("update-list")


@cli.command("list-companies")
def list_companies():
    """列出所有觀察名單公司（含清單類型與 Google Alert 狀態）。"""
    from src.alerts.manager import get_rss_map
    from src.companies.watchlist import load_companies

    companies = load_companies()
    if not companies:
        click.echo("找不到公司清單，請先執行 update-list。")
        return

    try:
        rss_map = get_rss_map()
    except Exception as e:
        click.echo(f"[警告] 無法取得 Google Alert 狀態：{e}", err=True)
        rss_map = {}

    click.echo(f"共 {len(companies)} 家公司：\n")
    click.echo(f"{'代號':<8} {'名稱':<12} {'類型':<8} {'Alert'}")
    click.echo("-" * 50)
    for c in companies:
        list_label = "⭐ 專注" if c.list_type == "focus" else "   觀察"
        if not rss_map:
            has_alert = "(未連線)"
        else:
            has_alert = "✓ RSS 已設定" if c.stock_id in rss_map else "✗ 未建立"
        click.echo(f"{c.stock_id:<8} {c.name:<12} {list_label:<8} {has_alert}")


@cli.command()
def sync():
    """依公司名單同步 Google Alerts（建立缺少的、刪除多餘的）。"""
    from src.alerts.manager import sync_alerts
    result = sync_alerts()
    click.echo(f"建立 : {', '.join(result['created']) or '(無)'}")
    click.echo(f"刪除 : {', '.join(result['deleted']) or '(無)'}")
    click.echo(f"保留 : {len(result['unchanged'])} 家")


@cli.command()
def fetch():
    """立即抓取所有公司 RSS feeds 並儲存新 entries。"""
    from src.alerts.fetcher import fetch_all
    from src.companies.watchlist import load_companies

    companies = load_companies()
    if not companies:
        click.echo("找不到公司清單，請先執行 update-list。")
        sys.exit(1)

    results = fetch_all(companies)
    total = sum(results.values())
    for stock_id, count in results.items():
        click.echo(f"  {stock_id}: {count} 篇新文章")
    click.echo(f"合計新增：{total} 篇")


@cli.command()
@click.option("--date", "day_str", default=None, help="分析日期 (YYYY-MM-DD)，預設今天")
@click.option("--stock-id", "stock_id", default=None, help="僅分析指定股票代碼")
@click.option("--force", is_flag=True, default=False, help="強制重新分析，忽略已存在的報告")
def analyze(day_str: str | None, stock_id: str | None, force: bool):
    """針對每家公司進行 LLM 情緒分析 + Gemini 文章評分，產出 Markdown 報告。"""
    from src.analysis import llm
    from src.companies.watchlist import load_companies
    from src.storage.json_store import load_entries_by_stock_id
    from src.storage.markdown_writer import (
        read_report_summary,
        summarize_llm_result,
        write_company_report,
        write_daily_summary,
    )
    from src.storage.scores_store import load_scores, update_scores

    day = date.fromisoformat(day_str) if day_str else today_taipei()
    companies = load_companies()
    if not companies:
        click.echo("找不到公司清單，請先執行 update-list。")
        sys.exit(1)

    # 篩選特定公司
    if stock_id:
        companies = [c for c in companies if c.stock_id == stock_id]
        if not companies:
            click.echo(f"找不到股票代碼 {stock_id}。")
            sys.exit(1)

    entries_by_id = load_entries_by_stock_id(day)
    if not entries_by_id and not day_str:
        # 今天沒資料，自動 fallback 到最近一天有資料的日期
        from src.config import ALERTS_DATA_DIR
        available = sorted(
            [d for d in ALERTS_DATA_DIR.iterdir() if d.is_dir() and d.name != day.isoformat()],
            key=lambda d: d.name,
            reverse=True,
        )
        if available:
            fallback = date.fromisoformat(available[0].name)
            click.echo(f"找不到 {day} 的 entries，改用最近一天 {fallback}。")
            day = fallback
            entries_by_id = load_entries_by_stock_id(day)
    if not entries_by_id:
        click.echo(f"找不到 {day} 的 entries，請先執行 fetch。")
        sys.exit(1)

    generated_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S CST")
    all_scores = load_scores()
    company_reports = []

    from src.config import REPORTS_DIR

    for company in companies:
        entries = entries_by_id.get(company.stock_id, [])
        if not entries:
            click.echo(f"  {company.stock_id} {company.name}: 無資料，跳過")
            continue

        # 已有報告就跳過 LLM，但仍納入每日 summary，避免 partial run 覆蓋整天彙整。
        report_path = REPORTS_DIR / str(day) / f"{company.stock_id}.md"
        if report_path.exists() and not stock_id and not force:
            click.echo(f"  {company.stock_id} {company.name}: 報告已存在，納入彙整")
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

        click.echo(f"  分析+評分 {company.stock_id} {company.name}（{len(entries)} 篇）…")
        try:
            llm_result, new_scores = llm.analyze_and_score(company, entries)
        except Exception as e:
            click.echo(f"    LLM 失敗，跳過：{e}", err=True)
            continue
        update_scores(new_scores)
        all_scores = load_scores()  # 重新載入，確保 manual 標記不被覆蓋

        # 統計高分文章數（score >= 4）
        top_count = sum(1 for s in new_scores.values() if s.get("score", 0) >= 4)
        click.echo(f"    高分文章（≥4）：{top_count} 篇")

        path = write_company_report(company, day, entries, llm_result, generated_at, scores=all_scores)
        click.echo(f"    -> {path}")

        # 立即 commit，確保中途失敗也不遺失
        subprocess.run(
            ["git", "add", str(path)],
            check=False, capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"chore: report {company.stock_id} {day}"],
            check=False, capture_output=True,
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
        click.echo(f"\n彙整報告：{summary_path}")


@cli.command("update-readme")
def update_readme():
    """更新 README.md 的報告彙整表格（近 7 天）。"""
    _run_google_alert_skill("update-readme")


@cli.command("sync-stale")
def sync_stale():
    """處理 GitHub Issues 中標記為 [STALE] 或 [RATING] 的報告請求。"""
    import json
    import os
    import re

    def run_gh(args: list[str], check: bool = False) -> subprocess.CompletedProcess:
        return subprocess.run(["gh", *args], capture_output=True, text=True, check=check)

    def ensure_label(name: str, color: str, description: str) -> None:
        subprocess.run(
            ["gh", "label", "create", name, "--color", color, "--description", description],
            check=False,
            capture_output=True,
            text=True,
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
        allowed = {
            author.strip()
            for author in allowed_authors.split(",")
            if author.strip()
        }
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
        # 搜尋標題含有 [STALE] 或 [RATING] 的 open issues
        cmd = [
            "gh", "issue", "list",
            "--search", "[STALE] OR [RATING] in:title",
            "--json", "number,title,body,author",
            "--state", "open",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        issues = json.loads(res.stdout)
        if not issues:
            click.echo("無待處理的請求。")
            return

        for issue in issues:
            num, txt = issue["number"], issue["title"]

            if not is_allowed_author(issue):
                mark_invalid(
                    num,
                    "此 issue 的作者不在允許清單中，因此未自動處理。",
                )
                click.echo(f"跳過未授權作者的 Issue: {txt}")
                continue
            
            if "[STALE]" in txt:
                # 格式：[STALE] stock_id YYYY-MM-DD
                parts = txt.replace("[STALE]", "").strip().split()
                if len(parts) < 2 or not valid_day(parts[1]):
                    mark_invalid(num, "格式錯誤。請使用：`[STALE] stock_id YYYY-MM-DD`")
                    click.echo(f"跳過格式錯誤的 STALE Issue: {txt}")
                    continue

                stock_id, day_str = parts[0], parts[1]
                click.echo(f"處理過時標記：{stock_id} ({day_str})")
                result = subprocess.run(
                    [
                        sys.executable,
                        "cli.py",
                        "analyze",
                        "--date",
                        day_str,
                        "--stock-id",
                        stock_id,
                        "--force",
                    ],
                    check=False,
                )
                if result.returncode == 0:
                    add_label(num, "stale-refresh")
                    add_label(num, "processed")
                    close_issue(num, "✅ 報告已重新產生。")
                else:
                    add_label(num, "processing-failed")
                    comment(
                        num,
                        "自動重新產生報告失敗，請查看 GitHub Actions logs。",
                    )
            
            elif "[RATING]" in txt:
                # 格式：[RATING] stock_id YYYY-MM-DD entry_id score
                parts = txt.replace("[RATING]", "").strip().split()
                if len(parts) < 4 or not valid_day(parts[1]):
                    mark_invalid(
                        num,
                        "格式錯誤。請使用：`[RATING] stock_id YYYY-MM-DD entry_id score`",
                    )
                    click.echo(f"跳過格式錯誤的 RATING Issue: {txt}")
                    continue

                stock_id, day_str, entry_id, score_text = parts[0], parts[1], parts[2], parts[3]
                try:
                    score = int(score_text)
                except ValueError:
                    mark_invalid(num, "分數格式錯誤。`score` 必須是 1 到 6 的整數。")
                    click.echo(f"跳過分數格式錯誤的 RATING Issue: {txt}")
                    continue
                if score < 1 or score > 6:
                    mark_invalid(num, "分數範圍錯誤。`score` 必須是 1 到 6 的整數。")
                    click.echo(f"跳過分數範圍錯誤的 RATING Issue: {txt}")
                    continue

                # 從內文中擷取 Reason。格式：... Reason: 理由內容
                reason = ""
                body = issue.get("body", "") or ""
                if "Reason:" in body:
                    reason = body.split("Reason:", 1)[1].strip()
                
                click.echo(
                    f"處理重評請求：{stock_id} {entry_id} -> {score} (理由: {reason})"
                )
                
                # 執行標註指令，帶上理由
                label_cmd = [
                    sys.executable,
                    "cli.py",
                    "label",
                    stock_id,
                    day_str,
                    entry_id,
                    str(score),
                ]
                if reason:
                    label_cmd.extend(["--reason", reason])
                label_result = subprocess.run(label_cmd, check=False)
                if label_result.returncode != 0:
                    add_label(num, "processing-failed")
                    comment(
                        num,
                        "自動標註文章分數失敗，請查看 GitHub Actions logs。",
                    )
                    continue
                
                # 重新產生報告以反映變更
                analyze_result = subprocess.run(
                    [
                        sys.executable,
                        "cli.py",
                        "analyze",
                        "--date",
                        day_str,
                        "--stock-id",
                        stock_id,
                        "--force",
                    ],
                    check=False,
                )
                if analyze_result.returncode == 0:
                    add_label(num, "rating-feedback")
                    add_label(num, "processed")
                    reason_suffix = f"理由：{reason}" if reason else "未提供理由。"
                    close_issue(
                        num,
                        f"✅ 文章已重新評分為 {score} 分並更新報表。"
                        f"AI 已學習此偏好。{reason_suffix}",
                    )
                else:
                    add_label(num, "processing-failed")
                    comment(
                        num,
                        "文章分數已標註，但重新產生報告失敗，"
                        "請查看 GitHub Actions logs。",
                    )
            
            else:
                click.echo(f"跳過格式錯誤的 Issue: {txt}")
    except Exception as e:
        click.echo(f"執行 sync-stale 失敗：{e}", err=True)


@cli.command("export-rss")
def export_rss():
    """將目前 Google Alert RSS URLs 匯出至 config/rss_urls.json（供 CI 環境使用）。"""
    import json

    from src.alerts.manager import get_rss_map

    rss_map = get_rss_map()
    output_path = Path(__file__).parent / "config" / "rss_urls.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(rss_map, f, ensure_ascii=False, indent=2)
    click.echo(f"已匯出 {len(rss_map)} 個 RSS URLs 至 {output_path}")
    click.echo("請記得將此檔案 git commit 後再推送，以供 GitHub Actions 使用。")


@cli.command()
def run():
    """啟動背景排程（定期 fetch + 每日 analyze）。"""
    from src.scheduler import start
    click.echo("啟動排程器… 按 Ctrl+C 停止。")
    start()


@cli.command("label")
@click.argument("stock_id")
@click.argument("day_str")
@click.argument("entry_id")
@click.argument("score", type=int)
@click.option("--reason", help="標註理由")
def label(stock_id: str, day_str: str, entry_id: str, score: int, reason: str | None):
    """人工標註文章分數，供 AI 學習偏好。"""
    import json
    from src.storage.scores_store import update_scores
    
    # 1. 尋找原始文章內容
    DATA_DIR = Path(__file__).parent / "data"
    alert_path = DATA_DIR / "alerts" / day_str / f"{stock_id}.json"
    if not alert_path.exists():
        click.echo(f"找不到文章：{alert_path}")
        return
        
    with open(alert_path, encoding="utf-8") as f:
        entries = json.load(f)
        
    target = next((e for e in entries if e.get("id") == entry_id), None)
    if not target:
        click.echo(f"在 {alert_path} 中找不到 ID 為 {entry_id} 的文章。")
        return
        
    # 2. 儲存至 scores.json (source='manual')
    update_scores({
        entry_id: {
            "score": score,
            "reason": reason or target.get("title", ""),
            "source": "manual",
            "scored_at": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S CST")
        }
    })
    
    # 3. 儲存至 user_preferences.json (Few-shot 範例，用於當前 Prompt)
    pref_path = DATA_DIR / "user_preferences.json"
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
        "reason": reason
    })
    prefs = prefs[-50:]
    with open(pref_path, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)
        
    # 4. 儲存至 training_data.jsonl (長期訓練數據，用於未來微調 Fine-tuning)
    train_path = DATA_DIR / "training_data.jsonl"
    train_entry = {
        "timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "context": {
            "stock_id": stock_id,
            "company_name": target.get("name", "")
        },
        "input": {
            "title": target.get("title", ""),
            "summary": target.get("summary", "")
        },
        "label": {
            "score": score,
            "reason": reason
        }
    }
    with open(train_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(train_entry, ensure_ascii=False) + "\n")
        
    # 5. 處理書籤清單 (6 分文章)
    from src.storage.markdown_writer import write_bookmarks_page
    bookmark_path = DATA_DIR / "bookmarks.json"
    bookmarks = []
    if bookmark_path.exists():
        with open(bookmark_path, encoding="utf-8") as f:
            try:
                bookmarks = json.load(f)
            except json.JSONDecodeError:
                bookmarks = []

    # 移除舊的相同 entry
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
            "marked_at": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S CST")
        })

    with open(bookmark_path, "w", encoding="utf-8") as f:
        json.dump(bookmarks, f, ensure_ascii=False, indent=2)

    # 重新渲染 bookmarks.md
    bm_page_path = write_bookmarks_page(bookmarks)
    click.echo(f"已更新書籤清單網頁：{bm_page_path}")

    # 自動 Git 提交書籤檔案
    subprocess.run(
        ["git", "add", str(bookmark_path), str(bm_page_path)],
        check=False, capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", f"chore: update bookmarks for {stock_id}"],
        check=False, capture_output=True,
    )

    click.echo(f"✅ 成功：文章已標註並存入訓練數據集 (data/training_data.jsonl)。")
    click.echo(f"AI 將在下次分析時學習此偏好，且此數據可用於未來模型微調。")


if __name__ == "__main__":
    cli()
