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
| `checked_at` | timestamp | Execution time of the health checker (same as `process_timestamp`). |

---
