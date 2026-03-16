"""以 stock_id 為 key 讀寫 alert entries JSON 檔案。"""

import json
from datetime import date
from pathlib import Path

from src.config import ALERTS_DATA_DIR, today_taipei


def _today_dir() -> Path:
    today = today_taipei().isoformat()
    path = ALERTS_DATA_DIR / today
    path.mkdir(parents=True, exist_ok=True)
    return path


def _file_for(stock_id: str, day: date | None = None) -> Path:
    if day is None:
        return _today_dir() / f"{stock_id}.json"
    return ALERTS_DATA_DIR / day.isoformat() / f"{stock_id}.json"


def load_entries(stock_id: str, day: date | None = None) -> list[dict]:
    path = _file_for(stock_id, day)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_entries(stock_id: str, entries: list[dict], day: date | None = None) -> None:
    path = _file_for(stock_id, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def load_all_entries_for_date(day: date) -> list[dict]:
    """載入指定日期所有公司的 entries。"""
    day_dir = ALERTS_DATA_DIR / day.isoformat()
    if not day_dir.exists():
        return []
    entries: list[dict] = []
    for json_file in day_dir.glob("*.json"):
        with open(json_file, encoding="utf-8") as f:
            entries.extend(json.load(f))
    return entries


def load_entries_by_stock_id(day: date) -> dict[str, list[dict]]:
    """載入指定日期所有公司的 entries，以 stock_id 為 key。"""
    day_dir = ALERTS_DATA_DIR / day.isoformat()
    if not day_dir.exists():
        return {}
    result: dict[str, list[dict]] = {}
    for json_file in day_dir.glob("*.json"):
        stock_id = json_file.stem
        with open(json_file, encoding="utf-8") as f:
            result[stock_id] = json.load(f)
    return result
