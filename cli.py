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


@cli.command("update-list")
def update_list():
    """執行 Get觀察名單.py 下載最新 CSV 觀察名單。"""
    script = Path(__file__).parent / "Get觀察名單.py"
    if not script.exists():
        click.echo("找不到 Get觀察名單.py", err=True)
        sys.exit(1)
    subprocess.run([sys.executable, str(script)], check=True)


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
def analyze(day_str: str | None, stock_id: str | None):
    """針對每家公司進行 LLM 情緒分析 + Gemini 文章評分，產出 Markdown 報告。"""
    from src.analysis import llm
    from src.companies.watchlist import load_companies
    from src.storage.json_store import load_entries_by_stock_id
    from src.storage.markdown_writer import write_company_report, write_daily_summary
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

        # 已有報告就跳過（避免重複呼叫 LLM）
        report_path = REPORTS_DIR / str(day) / f"{company.stock_id}.md"
        if report_path.exists() and not stock_id:
            click.echo(f"  {company.stock_id} {company.name}: 報告已存在，跳過")
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

        summary_lines = [l for l in llm_result.splitlines() if l.strip()]
        summary = summary_lines[0] if summary_lines else ""

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
    import json
    import re
    from datetime import timedelta

    today = today_taipei()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]

    alerts_dir = Path(__file__).parent / "data" / "alerts"
    reports_dir = Path(__file__).parent / "data" / "reports"
    scores_file = Path(__file__).parent / "data" / "scores.json"

    scores: dict[str, dict] = {}
    if scores_file.exists():
        with open(scores_file, encoding="utf-8") as f:
            scores = json.load(f)

    # 收集各股票各日文章數 + 高分文章
    stocks: dict[str, dict] = {}
    for day in days:
        day_dir = alerts_dir / day.isoformat()
        if not day_dir.exists():
            continue
        for json_file in sorted(day_dir.glob("*.json")):
            stock_id = json_file.stem
            with open(json_file, encoding="utf-8") as f:
                entries = json.load(f)
            name = entries[0].get("name", stock_id) if entries else stock_id
            if stock_id not in stocks:
                stocks[stock_id] = {"name": name, "counts": {}, "top_counts": {}, "latest_report": None}
            stocks[stock_id]["counts"][day] = len(entries)
            # 高分文章數（score >= 4）
            top = sum(1 for e in entries if scores.get(e.get("id", ""), {}).get("score", -1) >= 4)
            if top:
                stocks[stock_id]["top_counts"][day] = top

    # 找最新報告連結
    for stock_id in stocks:
        for day in reversed(days):
            if (reports_dir / day.isoformat() / f"{stock_id}.md").exists():
                stocks[stock_id]["latest_report"] = day
                break

    # 建立表格
    day_cols = " | ".join(d.strftime("%m/%d") for d in days)
    lines = [
        f"| 代號 | 名稱 | {day_cols} | ⭐≥4 | 最新報告 |",
        "| --- | --- |" + " :---: |" * 7 + " :---: | --- |",
    ]
    for stock_id, info in sorted(stocks.items()):
        counts = " | ".join(str(info["counts"].get(d, "-")) for d in days)
        total_top = sum(info["top_counts"].values())
        top_str = str(total_top) if total_top else "-"
        if info["latest_report"]:
            d = info["latest_report"]
            link = f"[{d.isoformat()}](data/reports/{d.isoformat()}/{stock_id}.md)"
        else:
            link = "-"
        lines.append(f"| {stock_id} | {info['name']} | {counts} | {top_str} | {link} |")

    table = "\n".join(lines)
    marker_s = "<!-- REPORT_TABLE_START -->"
    marker_e = "<!-- REPORT_TABLE_END -->"
    new_block = f"{marker_s}\n\n## 報告彙整（近 7 天）\n\n{table}\n\n{marker_e}"

    readme = Path(__file__).parent / "README.md"
    content = readme.read_text(encoding="utf-8")
    if marker_s in content:
        content = re.sub(f"{re.escape(marker_s)}.*?{re.escape(marker_e)}", new_block, content, flags=re.DOTALL)
    else:
        content = content.rstrip() + "\n\n" + new_block + "\n"
    readme.write_text(content, encoding="utf-8")
    click.echo(f"README.md 已更新，共 {len(stocks)} 支股票")


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


if __name__ == "__main__":
    cli()
