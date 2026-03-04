"""Command-line interface for GoogleAlertManager（股票觀察名單驅動版）。"""

import logging
import subprocess
import sys
from datetime import date, datetime, timezone
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
    """針對每家公司進行 LLM 情緒分析，產出 Markdown 報告。"""
    from src.analysis import llm
    from src.companies.watchlist import load_companies
    from src.storage.json_store import load_entries_by_stock_id
    from src.storage.markdown_writer import write_company_report, write_daily_summary

    day = date.fromisoformat(day_str) if day_str else date.today()
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
    if not entries_by_id:
        click.echo(f"找不到 {day} 的 entries，請先執行 fetch。")
        sys.exit(1)

    generated_at = datetime.now(timezone.utc).isoformat()
    company_reports = []

    for company in companies:
        entries = entries_by_id.get(company.stock_id, [])
        if not entries:
            click.echo(f"  {company.stock_id} {company.name}: 無資料，跳過")
            continue

        click.echo(f"  分析 {company.stock_id} {company.name}（{len(entries)} 篇）…")
        llm_result = llm.analyze_company(company, entries)
        path = write_company_report(company, day, entries, llm_result, generated_at)
        click.echo(f"    -> {path}")

        # 擷取 LLM 結論首段作為彙整摘要
        summary_lines = [l for l in llm_result.splitlines() if l.strip()]
        summary = summary_lines[0] if summary_lines else ""

        company_reports.append({
            "stock_id": company.stock_id,
            "name": company.name,
            "list_type": company.list_type,
            "entry_count": len(entries),
            "summary": summary,
        })

    if company_reports and not stock_id:
        summary_path = write_daily_summary(day, company_reports, generated_at)
        click.echo(f"\n彙整報告：{summary_path}")


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
