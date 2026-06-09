---
source: https://raw.githubusercontent.com/wenchiehlee-money/GoogleAlertManager/refs/heads/main/raw_column_definition_GAM.md
destination: https://raw.githubusercontent.com/wenchiehlee-money/biztrends.TW/refs/heads/main/definitions/raw_column_definition_GAM.md
---

# Raw CSV Column Definitions - GoogleAlertManager Repo

---

## google_alert_health_summary.csv (GoogleAlertManager Data & API Health Summary)
**No:** 70
**Source:** `data/reports/google_alert_health_summary.csv`
**Purpose:** Summarize alert crawlers and LLM analysis success rates to detect API issues or quota exhaustion.

### Column Definitions:

| Column | Type | Description |
|--------|------|-------------|
| `process_timestamp` | timestamp | Time when health metrics were computed (Taipei Time). |
| `latest_report_date` | date | The latest YYYY-MM-DD date directory containing processed files. |
| `total_focus_companies` | int | Total number of companies listed in the focus watchlist CSV. |
| `total_all_companies` | int | Total number of companies listed in the full watchlist CSV. |
| `active_alerts` | int | Number of focus companies that had google alert JSON files downloaded for the target date. |
| `success_reports` | int | Number of focus companies that successfully completed LLM analysis (MD files generated) for the target date. |
| `success_rate_pct` | float | Percentage of alerts successfully analyzed (`success_reports / active_alerts * 100`). |
| `total_articles_fetched` | int | Total number of raw articles fetched for all focus companies for the target date. |
| `high_value_articles` | int | Total number of articles rated 3-5 (useful signal) in scores.json for the target date. |
| `signal_to_noise_ratio_pct` | float | Percentage of articles rated 3-5 out of all fetched articles (`high_value_articles / total_articles_fetched * 100`). |
| `authority_score` | float | Percentage of articles fetched from Tier-1 authoritative domains (e.g., cnyes.com, commercialtimes.com). |
| `checked_at` | timestamp | Execution time of the health checker (same as `process_timestamp`). |

---
