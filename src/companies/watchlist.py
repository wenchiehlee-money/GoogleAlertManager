"""讀取股票觀察名單 CSV，回傳 Company dataclass 列表。"""

import csv
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
FOCUS_CSV = ROOT / "StockID_TWSE_TPEX_focus.csv"
OBSERVATION_CSV = ROOT / "StockID_TWSE_TPEX.csv"
# US "concept stock" tickers -- a SEPARATE file from FOCUS_CSV/OBSERVATION_CSV
# on purpose. Those two are downloaded wholesale from the external
# Selenium-Actions.Auction repo by `cli.py update-list` (see
# skill-google-alert-fetch), which overwrites them completely on every run.
# Per skill-stock-universe-onboarding, foreign tickers never belong in that
# TW-focused source anyway, so this file lives outside that overwrite path
# and is populated separately from ConceptStocks/raw_conceptstock_company_
# metadata.csv (see TW-institutional-research/SOURCE_POLICY.md's "US Ticker
# Coverage" for the same source-of-truth rule applied there).
US_FOCUS_CSV = ROOT / "StockID_US_focus.csv"


@dataclass
class Company:
    stock_id: str       # e.g. "2330" (TW) or "TSM" (US)
    name: str           # e.g. "台積電"
    list_type: str      # "focus" | "observation"
    market: str = field(default="TW")  # "TW" | "US"
    rss_url: str = field(default="")


def _read_csv(path: Path) -> list[tuple[str, str]]:
    """讀取 stock_id,name 格式的觀察名單 CSV。"""
    rows: list[tuple[str, str]] = []
    if not path.exists():
        return rows
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 2:
                continue
            stock_id = row[0].strip()
            name = row[1].strip()
            if not stock_id or not stock_id[0].isdigit():
                continue
            rows.append((stock_id, name))
    return rows


def load_companies(focus_only: bool = True) -> list[Company]:
    """讀取 CSV，回傳 Company 列表。

    focus_only=True（預設）：僅回傳專注清單。
    focus_only=False：回傳全部（focus + observation）。

    只回傳台股（TW）公司，跟既有行為一致。美股請另外呼叫
    `load_us_companies()` -- 刻意不合併進這個函式的預設輸出，因為既有呼叫端
    （RSS fetch 等）尚未驗證能正確處理非數字 ticker（見 US_FOCUS_CSV 的
    註解）。
    """
    companies: list[Company] = []
    seen_ids: set[str] = set()

    for stock_id, name in _read_csv(FOCUS_CSV):
        if stock_id not in seen_ids:
            companies.append(Company(stock_id=stock_id, name=name, list_type="focus", market="TW"))
            seen_ids.add(stock_id)

    if not focus_only:
        for stock_id, name in _read_csv(OBSERVATION_CSV):
            if stock_id not in seen_ids:
                companies.append(Company(stock_id=stock_id, name=name, list_type="observation", market="TW"))
                seen_ids.add(stock_id)

    return companies


def _read_us_csv(path: Path) -> list[tuple[str, str]]:
    """讀取 ticker,name 格式的美股清單 CSV -- 跟 `_read_csv()` 幾乎一樣，
    唯一差異是不套用 `stock_id[0].isdigit()` 過濾（美股 ticker 是英文字母，
    套用該過濾會把整份清單濾空）。台股的 `_read_csv()`/`load_companies()`
    保持原樣不受影響。"""
    rows: list[tuple[str, str]] = []
    if not path.exists():
        return rows
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # header row ("代號,名稱") -- no isdigit() filter here to skip it implicitly
        for row in reader:
            if len(row) < 2:
                continue
            ticker = row[0].strip()
            name = row[1].strip()
            if not ticker:
                continue
            rows.append((ticker, name))
    return rows


def load_us_companies() -> list[Company]:
    """讀取 `StockID_US_focus.csv`（見該常數上方註解：獨立於 `cli.py
    update-list` 的覆蓋範圍之外），回傳美股 Company 列表。

    每個 Company 的 `rss_url` 留空 -- 美股 ticker 要用什麼策略抓 Google
    Alert RSS（跟台股用同一套 URL 產生邏輯是否適用）尚未確認，此函式不猜測，
    呼叫端（`fetcher.py` 等）目前也還沒接上這份清單。"""
    companies: list[Company] = []
    for ticker, name in _read_us_csv(US_FOCUS_CSV):
        companies.append(Company(stock_id=ticker, name=name, list_type="focus", market="US"))
    return companies
