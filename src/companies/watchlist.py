"""讀取股票觀察名單 CSV，回傳 Company dataclass 列表。"""

import importlib.util
import sys
from functools import cache
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).parent.parent.parent
FOCUS_CSV = ROOT / "StockID_TWSE_TPEX_focus.csv"
OBSERVATION_CSV = ROOT / "StockID_TWSE_TPEX.csv"
SKILL_SCRIPT = (
    ROOT
    / "skills"
    / "common"
    / "skill-google-alert-fetch"
    / "scripts"
    / "google_alert_fetch.py"
)


@dataclass
class Company:
    stock_id: str       # e.g. "2330"
    name: str           # e.g. "台積電"
    list_type: str      # "focus" | "observation"
    rss_url: str = field(default="")


@cache
def _skill_module() -> ModuleType:
    """Load the skill implementation so CSV parsing has one source of truth."""
    module_name = "google_alert_fetch_skill"
    spec = importlib.util.spec_from_file_location(module_name, SKILL_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Google Alert fetch skill script: {SKILL_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _read_csv(path: Path) -> list[tuple[str, str]]:
    return [(company.stock_id, company.name) for company in _skill_module().read_company_csv(path)]


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
