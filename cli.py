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
        / "skill-google-alert-fetch"
        / "scripts"
        / "google_alert_fetch.py"
    )


def _run_google_alert_skill(*args: str) -> None:
    script = _google_alert_skill_script()
    if not script.exists():
        click.echo(f"找不到 Google Alert fetch skill script: {script}", err=True)
        sys.exit(1)
    result = subprocess.run(
        [sys.executable, str(script), "--repo-root", str(Path(__file__).parent), *args],
        check=False,
    )
    if result.returncode != 0:
        sys.exit(result.returncode)


@cli.command("update-list")
def update_list():
    """下載最新 CSV 觀察名單。"""
    _run_google_alert_skill("update-list")


@cli.command("list-companies")
def list_companies():
    """列出所有觀察名單公司（含清單類型與 Google Alert 狀態）。"""
    _run_google_alert_skill("list-companies")


@cli.command()
def sync():
    """依公司名單同步 Google Alerts（建立缺少的、刪除多餘的）。"""
    _run_google_alert_skill("sync")


@cli.command()
def fetch():
    """立即抓取所有公司 RSS feeds 並儲存新 entries。"""
    _run_google_alert_skill("fetch")


@cli.command()
@click.option("--date", "day_str", default=None, help="分析日期 (YYYY-MM-DD)，預設今天")
@click.option("--stock-id", "stock_id", default=None, help="僅分析指定股票代碼")
@click.option("--force", is_flag=True, default=False, help="強制重新分析，忽略已存在的報告")
def analyze(day_str: str | None, stock_id: str | None, force: bool):
    """針對每家公司進行 LLM 情緒分析 + Gemini 文章評分，產出 Markdown 報告。"""
    extra = []
    if day_str:
        extra += ["--date", day_str]
    if stock_id:
        extra += ["--stock-id", stock_id]
    if force:
        extra += ["--force"]
    _run_google_alert_skill("analyze", *extra)


@cli.command("update-readme")
def update_readme():
    """更新 README.md 的報告彙整表格（近 7 天）。"""
    _run_google_alert_skill("update-readme")


@cli.command("sync-stale")
def sync_stale():
    """處理 GitHub Issues 中標記為 [STALE] 或 [RATING] 的報告請求。"""
    _run_google_alert_skill("sync-stale")


@cli.command("export-rss")
def export_rss():
    """將目前 Google Alert RSS URLs 匯出至 config/rss_urls.json（供 CI 環境使用）。"""
    _run_google_alert_skill("export-rss")


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
    extra = [stock_id, day_str, entry_id, str(score)]
    if reason:
        extra += ["--reason", reason]
    _run_google_alert_skill("label", *extra)


if __name__ == "__main__":
    cli()
