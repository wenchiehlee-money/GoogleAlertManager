#!/usr/bin/env python3
import csv
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
ALERTS_DIR = REPO_ROOT / "data" / "alerts"
REPORTS_DIR = REPO_ROOT / "data" / "reports"
SCORES_JSON = REPO_ROOT / "data" / "scores.json"
HEALTH_SUMMARY_CSV = REPORTS_DIR / "google_alert_health_summary.csv"

TAIPEI_TZ = timezone(timedelta(hours=8))

# Authority Domains
AUTHORITY_DOMAINS = {
    "cnyes.com", "chinatimes.com", "udn.com", "moneydj.com", 
    "yahoo.com", "reuters.com", "technews.tw", "wealth.com.tw", 
    "businesstoday.com.tw", "commercialtimes.com"
}

def get_latest_date():
    if not ALERTS_DIR.exists():
        return None
    subdirs = [d.name for d in ALERTS_DIR.iterdir() if d.is_dir()]
    valid_dates = []
    for d in subdirs:
        try:
            datetime.strptime(d, "%Y-%m-%d")
            valid_dates.append(d)
        except ValueError:
            pass
    if not valid_dates:
        return None
    valid_dates.sort()
    return valid_dates[-1]

def is_authoritative(link):
    if not link:
        return False
    try:
        parsed = urlparse(link)
        domain = parsed.netloc.lower()
        return any(domain == auth or domain.endswith("." + auth) for auth in AUTHORITY_DOMAINS)
    except Exception:
        return False

def main():
    print("=== Generating GoogleAlertManager Data Health Summary ===")
    
    if not REPORTS_DIR.exists():
        os.makedirs(REPORTS_DIR, exist_ok=True)

    # 1. Get watchlist counts
    focus_csv = REPO_ROOT / "StockID_TWSE_TPEX_focus.csv"
    total_focus_companies = 0
    if focus_csv.exists():
        try:
            with open(focus_csv, "r", encoding="utf-8") as f:
                total_focus_companies = sum(1 for line in f) - 1
        except Exception as e:
            print(f"Warning: Failed to read {focus_csv.name}: {e}")

    all_csv = REPO_ROOT / "StockID_TWSE_TPEX.csv"
    total_all_companies = 0
    if all_csv.exists():
        try:
            with open(all_csv, "r", encoding="utf-8") as f:
                total_all_companies = sum(1 for line in f) - 1
        except Exception as e:
            print(f"Warning: Failed to read {all_csv.name}: {e}")

    print(f"Total Focus Companies: {total_focus_companies}")
    print(f"Total All Companies: {total_all_companies}")

    # 2. Identify latest date directory
    latest_date = get_latest_date()
    
    # Check if a custom date is provided as an argument
    if len(sys.argv) > 1:
        custom_date = sys.argv[1]
        try:
            datetime.strptime(custom_date, "%Y-%m-%d")
            latest_date = custom_date
            print(f"Using custom date from argument: {latest_date}")
        except ValueError:
            print(f"Warning: Invalid date argument format '{custom_date}'. Expected YYYY-MM-DD.")

    if not latest_date:
        latest_date = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d")
        print(f"No alert directories found. Fallback to today: {latest_date}")
    else:
        print(f"Target date identified: {latest_date}")

    # 3. Load scores.json
    scores_db = {}
    if SCORES_JSON.exists():
        try:
            with open(SCORES_JSON, "r", encoding="utf-8") as f:
                scores_db = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load {SCORES_JSON.name}: {e}")

    # 4. Scan alert JSONs for metrics
    day_alerts_dir = ALERTS_DIR / latest_date
    day_reports_dir = REPORTS_DIR / latest_date

    active_alerts = 0
    if day_alerts_dir.exists():
        active_alerts = len(list(day_alerts_dir.glob("*.json")))

    success_reports = 0
    if day_reports_dir.exists():
        report_files = [f for f in day_reports_dir.glob("*.md") if not f.name.endswith("-top.md")]
        success_reports = len(report_files)

    success_rate_pct = 100.0
    if active_alerts > 0:
        success_rate_pct = round((success_reports / active_alerts * 100), 2)
    elif active_alerts == 0 and success_reports > 0:
        success_rate_pct = 100.0
    elif active_alerts == 0 and success_reports == 0:
        success_rate_pct = 0.0

    print(f"Active Alerts (JSON count): {active_alerts}")
    print(f"Success Reports (MD count): {success_reports}")
    print(f"Success Rate: {success_rate_pct}%")

    # 5. Extract SNR and Source Authority from crawled articles
    total_articles_fetched = 0
    high_value_articles = 0
    authoritative_articles = 0

    if day_alerts_dir.exists():
        for json_file in day_alerts_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    articles = json.load(f)
                    if isinstance(articles, list):
                        for art in articles:
                            total_articles_fetched += 1
                            
                            # Check authority
                            link = art.get("link")
                            if is_authoritative(link):
                                authoritative_articles += 1
                            
                            # Check score in scores.json
                            art_id = art.get("id")
                            if art_id in scores_db:
                                score_val = scores_db[art_id].get("score", -1)
                                if score_val >= 3:
                                    high_value_articles += 1
            except Exception as e:
                print(f"Warning: Failed to read articles from {json_file.name}: {e}")

    signal_to_noise_ratio_pct = 0.0
    if total_articles_fetched > 0:
        signal_to_noise_ratio_pct = round((high_value_articles / total_articles_fetched * 100), 2)

    authority_score = 0.0
    if total_articles_fetched > 0:
        authority_score = round((authoritative_articles / total_articles_fetched * 100), 2)

    print(f"Total Articles Fetched: {total_articles_fetched}")
    print(f"High-Value Articles (score >= 3): {high_value_articles}")
    print(f"Authoritative Articles: {authoritative_articles}")
    print(f"Signal-to-Noise Ratio: {signal_to_noise_ratio_pct}%")
    print(f"Authority Score: {authority_score}%")

    now = datetime.now(TAIPEI_TZ)
    checked_at = now.isoformat()
    process_timestamp = checked_at

    summary_data = {
        "process_timestamp": process_timestamp,
        "latest_report_date": latest_date,
        "total_focus_companies": total_focus_companies,
        "total_all_companies": total_all_companies,
        "active_alerts": active_alerts,
        "success_reports": success_reports,
        "success_rate_pct": success_rate_pct,
        "total_articles_fetched": total_articles_fetched,
        "high_value_articles": high_value_articles,
        "signal_to_noise_ratio_pct": signal_to_noise_ratio_pct,
        "authority_score": authority_score,
        "checked_at": checked_at
    }

    fieldnames = [
        "process_timestamp",
        "latest_report_date",
        "total_focus_companies",
        "total_all_companies",
        "active_alerts",
        "success_reports",
        "success_rate_pct",
        "total_articles_fetched",
        "high_value_articles",
        "signal_to_noise_ratio_pct",
        "authority_score",
        "checked_at"
    ]

    with open(HEALTH_SUMMARY_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(summary_data)

    print(f"Successfully generated health summary at {HEALTH_SUMMARY_CSV}")

if __name__ == "__main__":
    main()
