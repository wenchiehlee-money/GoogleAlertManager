---
name: skill-google-alert-fetch
description: >-
  Operate and maintain the GoogleAlertManager Google Alerts fetch pipeline: refresh
  GoPublic watchlist CSVs, sync Google Alert RSS subscriptions, export fallback RSS
  URLs, fetch RSS entries, update README report tables from the focus CSV, inspect
  GitHub Actions runs, and commit/push refreshed alert data and watchlist files.
  Use when the user asks to update GoogleAlertManager alerts, fetch Google Alerts,
  refresh the stock watchlist, reconcile README with StockID_TWSE_TPEX_focus.csv,
  or debug the fetch/analyze workflows.
---

# Google Alert Fetch Skill

This skill covers the `GoogleAlertManager` repo and its Google Alerts data pipeline. Work from the repo root unless the user gives another path.

## Source Of Truth

- Focus list: `StockID_TWSE_TPEX_focus.csv`
- Observation list: `StockID_TWSE_TPEX.csv`
- Watchlist refresh script: `Get觀察名單.py`
- CLI entrypoint: `cli.py`
- RSS fallback map: `config/rss_urls.json`
- Alert output: `data/alerts/<YYYY-MM-DD>/<stock_id>.json`
- Report output: `data/reports/<YYYY-MM-DD>/`
- README table: `README.md` between `REPORT_TABLE_START` / `REPORT_TABLE_END`
- Workflows: `.github/workflows/fetch.yml`, `.github/workflows/analyze.yml`, `.github/workflows/issue-feedback.yml`

README rows must come from `StockID_TWSE_TPEX_focus.csv`, not from whatever historical alerts happen to exist. Historical data may contain stale stock IDs; do not treat that as the current watchlist.

## Standard Workflow

1. Check local state first:

```bash
git status --short
```

2. Refresh the watchlist CSVs:

```bash
uv run python cli.py update-list
```

This runs `Get觀察名單.py`, downloading both CSVs from GoPublic.

3. Verify README/list consistency when the user asks about the watchlist:

```bash
python3 - <<'PY'
import csv, re
from pathlib import Path
focus=[]
with open('StockID_TWSE_TPEX_focus.csv', encoding='utf-8-sig') as f:
    for row in csv.reader(f):
        if len(row) >= 2 and row[0].strip() and row[0].strip()[0].isdigit():
            focus.append((row[0].strip(), row[1].strip()))
readme = Path('README.md').read_text(encoding='utf-8')
block = re.search(r'<!-- REPORT_TABLE_START -->(.*?)<!-- REPORT_TABLE_END -->', readme, re.S)
rows=[]
if block:
    for line in block.group(1).splitlines():
        if line.startswith('| ') and not line.startswith('| 名稱') and ':---:' not in line:
            parts=[p.strip() for p in line.strip('|').split('|')]
            if len(parts) >= 2:
                rows.append((parts[1], parts[0]))
focus_ids=[sid for sid,_ in focus]
row_ids=[sid for sid,_ in rows]
print('focus_count', len(focus_ids))
print('readme_count', len(row_ids))
print('missing_from_readme', [(sid,n) for sid,n in focus if sid not in row_ids])
print('extra_in_readme', [(sid,n) for sid,n in rows if sid not in focus_ids])
print('order_same', focus_ids == row_ids)
PY
```

4. Fetch alert entries:

```bash
uv run python cli.py fetch
```

`fetch` uses live Google Alerts through `GOOGLE_ALERT_EMAIL` and `GOOGLE_ALERT_PASSWORD`. If live auth/listing fails, it falls back to `config/rss_urls.json`.

5. Update the README table:

```bash
uv run python cli.py update-readme
```

The current implementation should initialize rows from `load_companies()` / the focus CSV and only fill counts for those IDs.

6. Stage the full data surface that may have changed:

```bash
git add data/alerts/ README.md StockID_TWSE_TPEX.csv StockID_TWSE_TPEX_focus.csv
```

For analyze/report workflows also include:

```bash
git add data/reports/ data/scores.json README.md StockID_TWSE_TPEX.csv StockID_TWSE_TPEX_focus.csv
```

## Google Alert Subscription Maintenance

Use these commands only when the user asks to inspect or repair subscriptions:

```bash
uv run python cli.py list-companies
uv run python cli.py sync
uv run python cli.py export-rss
```

- `list-companies` reports which focus-list companies have RSS configured.
- `sync` creates missing Google Alerts and deletes alerts outside the current focus list.
- `export-rss` writes `config/rss_urls.json` so CI can fetch even when live Google auth fails.

## GitHub Actions Operations

The scheduled fetch workflow should run:

1. checkout
2. `uv sync`
3. `uv run python cli.py update-list`
4. `uv run python cli.py fetch`
5. `uv run python cli.py update-readme`
6. commit `data/alerts/`, `README.md`, and both watchlist CSVs

When changing workflows, confirm refreshed CSVs are staged; otherwise README can be updated from new CSVs in CI without committing the CSV source used to build it.

Useful checks:

```bash
gh workflow run fetch.yml
gh run list --workflow fetch.yml --limit 5
gh run watch <run-id> --exit-status
```

Use `gh` only when authenticated for `wenchiehlee-money/GoogleAlertManager`.

## Failure Modes

- Empty fetch result plus auth warning: verify secrets or run `export-rss` locally and commit `config/rss_urls.json`.
- README contains extra or missing rows: patch `update-readme` to use `load_companies()` as the row source, then regenerate README.
- New focus stock has `-` counts: expected until RSS exists and entries are fetched for that ID.
- Workflow updates README but not CSV: add both `StockID_TWSE_TPEX.csv` and `StockID_TWSE_TPEX_focus.csv` to the workflow commit step.
- `sync` deletes alerts outside focus list by design; inspect the focus CSV before running it.
