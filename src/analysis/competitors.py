"""讀取 My-TW-Coverage 同步過來的競爭同業財務資料（data/competitors/{stock_id}_competitors.json）。"""

import json
import logging

from src.config import COMPETITORS_DIR

logger = logging.getLogger(__name__)

_RELATIONSHIP_LABEL = {
    "target": "本公司",
    "odm_peer": "ODM同業",
}


def load_competitor_data(stock_id: str) -> dict | None:
    """讀取單一股票的競爭同業 JSON，檔案不存在或格式錯誤時回傳 None。"""
    path = COMPETITORS_DIR / f"{stock_id}_competitors.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("無法讀取競爭同業資料 %s：%s", path, e)
        return None


def _latest_period_rows(rows: list[dict]) -> list[dict]:
    """每家公司只取最新一期「有完整財報數字」的資料。

    同一個 period（如 2026Q2）可能同時存在多筆列：月營收預估（有 revenue 無 profit）、
    財報公布日佔位列（revenue/profit 皆空）、正式財報（revenue/profit 皆有值）。
    只有最後一種才算「有完整財報」，否則會選到全空的佔位列。
    """
    latest: dict[str, dict] = {}
    for row in rows:
        stock = row.get("stock")
        period = row.get("period") or ""
        if not stock or not period or not row.get("revenue") or not row.get("profit"):
            continue
        existing = latest.get(stock)
        if existing is None or period > (existing.get("period") or ""):
            latest[stock] = row
    return sorted(
        latest.values(),
        key=lambda r: (r.get("relationship_type") != "target", r.get("stock", "")),
    )


def build_llm_context(data: dict | None) -> str:
    """給 LLM prompt 使用的精簡文字摘要（僅取最新一期）。"""
    if not data or not data.get("rows"):
        return ""
    latest_rows = _latest_period_rows(data["rows"])
    if not latest_rows:
        return ""

    lines = ["### 競爭同業財務比較（最新一季，資料來源：My-TW-Coverage）："]
    for row in latest_rows:
        label = _RELATIONSHIP_LABEL.get(row.get("relationship_type"), row.get("relationship_type", "同業"))
        lines.append(
            f"- {row.get('company')}（{row.get('stock')}，{label}）{row.get('period')}："
            f"營收 {row.get('revenue')}（YoY {row.get('revenue_yoy_pct')}），"
            f"淨利 {row.get('profit')}（YoY {row.get('profit_yoy_pct')}），"
            f"毛利率 {row.get('gross_margin_pct')}，P/E {row.get('pe_range')}"
        )
    lines.append(f"\n（同業資料時間：{data.get('as_of', '')}）")
    return "\n".join(lines)


def build_markdown_table(data: dict | None) -> str:
    """給報告直接顯示用的 markdown 表格（固定格式，不經過 LLM）。"""
    if not data or not data.get("rows"):
        return ""
    latest_rows = _latest_period_rows(data["rows"])
    if not latest_rows:
        return ""

    header = (
        "| 股票代碼 | 公司 | 關係 | 期間 | 營收 | YoY | 淨利 | YoY | 毛利率 | P/E |\n"
        "| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |"
    )
    body_lines = []
    for row in latest_rows:
        label = _RELATIONSHIP_LABEL.get(row.get("relationship_type"), row.get("relationship_type", "同業"))
        body_lines.append(
            f"| {row.get('stock')} | {row.get('company')} | {label} | {row.get('period')} | "
            f"{row.get('revenue')} | {row.get('revenue_yoy_pct')} | {row.get('profit')} | "
            f"{row.get('profit_yoy_pct')} | {row.get('gross_margin_pct')} | {row.get('pe_range')} |"
        )
    footer = f"\n*資料來源：My-TW-Coverage，更新時間：{data.get('as_of', '')}*"
    return "\n".join([header, *body_lines]) + footer
