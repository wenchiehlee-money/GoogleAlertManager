"""讀取股票觀察名單 CSV，回傳 Company dataclass 列表。"""

import csv
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
FOCUS_CSV = ROOT / "StockID_TWSE_TPEX_focus.csv"
OBSERVATION_CSV = ROOT / "StockID_TWSE_TPEX.csv"


@dataclass
class Company:
    stock_id: str       # e.g. "2330"
    name: str           # e.g. "台積電"
    list_type: str      # "focus" | "observation"
    rss_url: str = field(default="")


def _read_csv(path: Path) -> list[tuple[str, str]]:
    """讀取 CSV，回傳 (stock_id, name) 列表，兼容有無 header。"""
    results = []
    if not path.exists():
        return results
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 2:
                continue
            stock_id, name = row[0].strip(), row[1].strip()
            # 跳過 header 列（非數字開頭）
            if not stock_id or not stock_id[0].isdigit():
                continue
            results.append((stock_id, name))
    return results


def load_companies(focus_only: bool = True) -> list[Company]:
    """讀取 CSV，回傳 Company 列表。

    focus_only=True（預設）：僅回傳專注清單。
    focus_only=False：回傳全部（focus + observation）。
    """
    companies: list[Company] = []
    seen_ids: set[str] = set()

    for stock_id, name in _read_csv(FOCUS_CSV):
        if stock_id not in seen_ids:
            companies.append(Company(stock_id=stock_id, name=name, list_type="focus"))
            seen_ids.add(stock_id)

    if not focus_only:
        for stock_id, name in _read_csv(OBSERVATION_CSV):
            if stock_id not in seen_ids:
                companies.append(Company(stock_id=stock_id, name=name, list_type="observation"))
                seen_ids.add(stock_id)

    return companies
