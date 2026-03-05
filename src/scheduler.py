"""APScheduler 背景排程：定期 fetch + 每日 analyze。"""

import logging
import time
from datetime import date, datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from src.alerts.fetcher import fetch_all
from src.analysis import llm
from src.companies.watchlist import load_companies
from src.config import load_config
from src.storage.json_store import load_entries_by_stock_id
from src.storage.markdown_writer import write_company_report, write_daily_summary

logger = logging.getLogger(__name__)


def run_fetch() -> None:
    logger.info("Scheduler: starting fetch")
    companies = load_companies()
    results = fetch_all(companies)
    for stock_id, count in results.items():
        logger.info("  %s: %d new entries", stock_id, count)


def run_analyze() -> None:
    logger.info("Scheduler: starting analysis")
    today = date.today()
    companies = load_companies()
    entries_by_id = load_entries_by_stock_id(today)
    if not entries_by_id:
        logger.info("No entries for today, skipping analysis")
        return

    generated_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S CST")
    company_reports = []

    for company in companies:
        entries = entries_by_id.get(company.stock_id, [])
        if not entries:
            continue
        llm_result = llm.analyze_company(company, entries)
        write_company_report(company, today, entries, llm_result, generated_at)

        summary_lines = [l for l in llm_result.splitlines() if l.strip()]
        company_reports.append({
            "stock_id": company.stock_id,
            "name": company.name,
            "list_type": company.list_type,
            "entry_count": len(entries),
            "summary": summary_lines[0] if summary_lines else "",
        })

    if company_reports:
        path = write_daily_summary(today, company_reports, generated_at)
        logger.info("Daily summary saved: %s", path)


def start() -> None:
    config = load_config()
    schedule_cfg = config.get("schedule", {})
    fetch_hours: int = schedule_cfg.get("fetch_interval_hours", 4)
    report_time: str = schedule_cfg.get("report_time", "23:55")
    hour, minute = map(int, report_time.split(":"))

    scheduler = BackgroundScheduler()
    scheduler.add_job(run_fetch, "interval", hours=fetch_hours, id="fetch")
    scheduler.add_job(run_analyze, "cron", hour=hour, minute=minute, id="analyze")
    scheduler.start()

    logger.info(
        "Scheduler started — fetch every %dh, report at %s",
        fetch_hours,
        report_time,
    )

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler stopped")
