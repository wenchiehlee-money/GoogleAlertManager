---
name: skill-google-alert-fetch
description: >-
  Operate and maintain the GoogleAlertManager Google Alerts fetch pipeline: refresh
  Selenium-Actions.Auction watchlist CSVs, sync Google Alert RSS subscriptions, export fallback RSS
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
- Watchlist refresh wrapper: `Get觀察名單.py`
- CLI entrypoint: `cli.py`
- Skill implementation script: `skills/common/skill-google-alert-fetch/scripts/google_alert_fetch.py`
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

This delegates to the bundled skill script, which downloads both CSVs from Selenium-Actions.Auction. Direct script form:

```bash
python skills/common/skill-google-alert-fetch/scripts/google_alert_fetch.py update-list
```

3. Verify README/list consistency when the user asks about the watchlist:

```bash
python skills/common/skill-google-alert-fetch/scripts/google_alert_fetch.py check-readme
```

Use `--json` when structured output is useful.

4. Fetch alert entries:

```bash
uv run python cli.py fetch
```

`fetch` uses live Google Alerts through `GOOGLE_ALERT_EMAIL` and `GOOGLE_ALERT_PASSWORD`. If live auth/listing fails, it falls back to `config/rss_urls.json`.

5. Update the README table:

```bash
uv run python cli.py update-readme
```

This delegates to the bundled skill script. Direct script form:

```bash
python skills/common/skill-google-alert-fetch/scripts/google_alert_fetch.py update-readme
```

The implementation initializes rows from `StockID_TWSE_TPEX_focus.csv` and only fills counts for those IDs.

6. Stage the full data surface that may have changed:

```bash
git add data/alerts/ README.md StockID_TWSE_TPEX.csv StockID_TWSE_TPEX_focus.csv
```

For analyze/report workflows also include:

```bash
git add data/reports/ data/scores.json paths.js README.md StockID_TWSE_TPEX.csv StockID_TWSE_TPEX_focus.csv
```

`data/competitors/{stock_id}_competitors.json` is a separate data surface: it is synced in daily from `My-TW-Coverage` (via that repo's `sync_to_googlealertmanager.yml`, pushed directly to `main`), not written by `cli.py analyze`. `analyze` only reads it if present (`src/analysis/competitors.py`) to add a "競爭同業比較" section and feed peer context into the LLM prompt; a missing file for a given stock is a normal no-op, not an error. Don't stage it manually — it arrives via its own push.

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

## Star Rating & Article Scoring Criteria

Article ratings (0-6 stars) drive high-score selection (score ≥ 4 ⭐) and bookmark archiving:

- **6 Stars (🔖 6分書籤/極高價值)**: Articles from **工商時報** (Commercial Times, `ctee.com.tw`) or **經濟日報** (Economic Daily News, `money.udn.com`), exceptional long-term reference articles, and user manual bookmarks (automatically archived to `data/reports/bookmarks.md`).
- **5 Stars (⭐5 關鍵決策/重大事件)**: Official earnings announcements, M&A, major contracts, leadership changes, major regulatory shifts.
- **4 Stars (⭐4 重要業務/實質消息)**: Factory expansions, key product line releases, confirmed top-tier client orders, institutional target price upgrades.
- **3 Stars (⭐3 參考價值/產業趨勢)**: Broader industry trend reports, pre-earnings previews, general technical/chip flow updates.
- **2 Stars (⭐2 一般性提及/周邊報導)**: Mere mention of stock code/name in list or footer without in-depth analysis.
- **1 Star (⭐1 幾乎無關/重複資訊)**: Duplicate press releases, outdated news reposts, auto-generated daily stock table snippets.
- **0 Stars (○ 完全無關/垃圾/廣告)**: Spam/LINE stock group promotions, content farm templates, misidentified stock names.

Special Scoring & Priority Rules:
1. **Tier-1 Financial Media Boost (6 Stars)**: Articles originating from **工商時報** or **經濟日報** (identified via title, summary, or domain `ctee.com.tw` / `money.udn.com`) are automatically rated **6 stars**.
2. **Content Farm / Syndicated News**: Reposted press releases without original analysis are capped at 2-3 points.
3. **Spam & Stock Group Filtering**: Articles containing clickbait/spam phrases ("飆股", "LINE群", "親愛的朋友") are capped at 0-1 points.
4. **List-Only Mention**: Articles merely listing stock IDs without fundamental analysis receive a maximum of 2 points.



## Failure Modes

- Empty fetch result plus auth warning: verify secrets or run `export-rss` locally and commit `config/rss_urls.json`.
- README contains extra or missing rows: run `python skills/common/skill-google-alert-fetch/scripts/google_alert_fetch.py check-readme`, then update README through the same script/CLI.
- New focus stock has `-` counts: expected until RSS exists and entries are fetched for that ID.
- Workflow updates README but not CSV: add both `StockID_TWSE_TPEX.csv` and `StockID_TWSE_TPEX_focus.csv` to the workflow commit step.
- `sync` deletes alerts outside focus list by design; inspect the focus CSV before running it.

