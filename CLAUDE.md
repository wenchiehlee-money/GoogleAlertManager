# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

GoogleAlertManager 是以**台灣股票觀察名單**為核心的自動化分析工具：
1. 從 GitHub 下載股票觀察名單 CSV（`Get觀察名單.py`）
2. 以每家公司建立對應的 Google Alert（RSS 投遞）
3. 定期抓取 RSS feed 並以 `stock_id` 為 key 儲存 JSON
4. 使用 Claude API 對每家公司進行情緒分析（利多/利空/投資建議）
5. 輸出每家公司獨立 Markdown 報告 + 每日彙整報告

## Commands

```bash
# 安裝依賴（推薦 uv）
uv sync
# or: pip install -e .

# 下載最新股票觀察名單 CSV
python Get觀察名單.py
python cli.py update-list   # 等同上面

# 列出所有觀察名單公司（含 Alert 狀態）
python cli.py list-companies

# 依公司名單同步 Google Alerts
python cli.py sync

# 立即抓取所有 RSS feeds
python cli.py fetch

# 分析指定公司或全部公司
python cli.py analyze --stock-id 2330
python cli.py analyze
python cli.py analyze --date 2026-03-04

# 啟動背景排程
python cli.py run

# 執行測試
pytest
pytest -v
```

## Architecture

```
StockID_TWSE_TPEX_focus.csv  ─┐
StockID_TWSE_TPEX.csv        ─┤→ watchlist.py (Company dataclass)
                               │         ↓
                         manager.py → Google Alerts (RSS delivery)
                                             ↓ RSS URLs
scheduler.py ──── fetcher.py ────→ json_store.py
                                   data/alerts/YYYY-MM-DD/{stock_id}.json
                                             ↓
                             stats.py + llm.py (Claude API per company)
                                             ↓
                             markdown_writer.py
                               → data/reports/YYYY-MM-DD/{stock_id}.md
                               → data/reports/YYYY-MM-DD-summary.md
```

### Key files

| File | Role |
|------|------|
| `Get觀察名單.py` | 從 GoPublic GitHub 下載兩份 CSV |
| `cli.py` | Click CLI（`update-list`, `list-companies`, `sync`, `fetch`, `analyze`, `run`）|
| `src/config.py` | 路徑/env 設定 |
| `src/companies/watchlist.py` | 讀取 CSV，回傳 `Company` dataclass 列表 |
| `src/alerts/manager.py` | Google Alert CRUD（公司驅動）|
| `src/alerts/fetcher.py` | 抓取 RSS，以 `stock_id` 儲存 |
| `src/storage/json_store.py` | 以 `stock_id` 為 key 讀寫 JSON |
| `src/storage/markdown_writer.py` | 每家公司報告 + 每日彙整 |
| `src/analysis/stats.py` | 文章數/域名統計 |
| `src/analysis/llm.py` | Claude 情緒分析（利多/利空/建議）|
| `src/scheduler.py` | APScheduler 排程 |
| `config/alerts.yaml` | 排程設定 + Alert 建立選項 |

### Data layout

```
data/
├── alerts/
│   └── 2026-03-04/
│       ├── 2330.json    ← 台積電 entries
│       └── 2454.json    ← 聯發科 entries
└── reports/
    ├── 2026-03-04/
    │   ├── 2330.md      ← 台積電個別報告
    │   └── 2454.md
    └── 2026-03-04-summary.md ← 當日彙整
```

### Company dataclass

```python
@dataclass
class Company:
    stock_id: str    # e.g. "2330"
    name: str        # e.g. "台積電"
    list_type: str   # "focus" | "observation"
    rss_url: str = ""
```

### Alert 關鍵字格式
- Search term = `{公司名} {股票代碼}`，例如 `台積電 2330`
- 使用 RSS 投遞

## Configuration

複製 `.env.example` 為 `.env` 並填入：
```
GOOGLE_ALERT_EMAIL=your@gmail.com
GOOGLE_ALERT_PASSWORD=yourpassword
ANTHROPIC_API_KEY=sk-ant-...
```

`config/alerts.yaml`（僅保留排程與 Alert 建立選項）：
```yaml
schedule:
  fetch_interval_hours: 4
  report_time: "23:55"

alert_options:
  language: "zh-TW"
  region: "TW"
  how_often: "as_it_happens"
```
