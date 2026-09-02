"""讀取 My-TW-Coverage 同步過來的競爭同業財務資料（data/competitors/{stock_id}_competitors.json）。"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone

from src.config import COMPETITORS_DIR

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))

# 資料新鮮度門檻：超過此時數視為 stale（My-TW-Coverage 為每日同步，48h ≈ 漏過一次同步週期）。
STALE_AFTER_HOURS = 48

_RELATIONSHIP_LABEL = {
    "target": "本公司",
    "odm_peer": "ODM同業",
}

# skill-theme-competitor-analysis（biztrends.TW）定義的 relationship_type 集合。
# 若同步進來的資料出現集合外的值，代表兩邊 schema 已經走樣，需要人工核對。
KNOWN_RELATIONSHIP_TYPES = {
    "target",
    "brand_competitor",
    "chip_competitor",
    "foundry_competitor",
    "odm_peer",
    "server_peer",
    "supplier_or_component",
    "product_peer",
}

# (raw 欄位, 顯示名稱, 是否用 +/- 號)
# 注意：底層 `profit`/`profit_yoy_pct` 來自 skill-theme-competitor-analysis 的
# 獲利金額_億_營業_利益（營業利益），不是稅後淨利；真正的稅後淨利是 `net_profit`。
_RANKING_METRICS = [
    ("revenue_yoy_pct_raw", "營收YoY", True),
    ("profit_yoy_pct_raw", "營業利益YoY", True),
    ("net_profit_yoy_pct_raw", "淨利YoY", True),
    ("gross_margin_pct_raw", "毛利率", False),
    ("net_margin_pct_raw", "淨利率", False),
]

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


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


def _parse_as_of(as_of: str) -> datetime | None:
    """解析 `as_of` 欄位（例："2026-08-25 03:30 CST"）為台北時區 datetime。"""
    if not as_of:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})", as_of.strip())
    if not match:
        return None
    try:
        naive = datetime.strptime(f"{match.group(1)} {match.group(2)}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return naive.replace(tzinfo=TZ_TAIPEI)


def check_data_health(data: dict | None, max_age_hours: int = STALE_AFTER_HOURS) -> dict:
    """檢查競爭同業資料的新鮮度與 schema 一致性（不呼叫 LLM，純本地檢查）。

    回傳 {"stale": bool, "age_hours": float | None, "issues": list[str]}。
    `issues` 為人類可讀的問題描述，空清單代表資料健康。
    此檢查僅針對「已同步進來的資料」把關（是否過期、schema 是否偏移），
    不會、也無法重新執行 skill-theme-competitor-analysis 本身（該 skill 依賴
    biztrends.TW 的原始資料檔，不在本 repo 內）。
    """
    issues: list[str] = []
    if not data:
        return {"stale": False, "age_hours": None, "issues": []}

    as_of_raw = data.get("as_of", "")
    parsed = _parse_as_of(as_of_raw)
    age_hours: float | None = None
    stale = False
    if parsed is None:
        issues.append(f"缺少或無法解析 as_of 時間戳（原始值：{as_of_raw!r}）")
    else:
        age_hours = (datetime.now(TZ_TAIPEI) - parsed).total_seconds() / 3600
        if age_hours > max_age_hours:
            stale = True
            issues.append(f"資料已 {age_hours:.0f} 小時未更新（門檻 {max_age_hours} 小時），可能落後最新財報/同業變動")

    rows = data.get("rows") or []
    if not rows:
        issues.append("rows 為空")
    unknown_types = sorted({r.get("relationship_type") for r in rows if r.get("relationship_type") not in KNOWN_RELATIONSHIP_TYPES})
    if unknown_types:
        issues.append(f"出現未知 relationship_type（與 skill-theme-competitor-analysis 定義不一致）：{unknown_types}")

    return {"stale": stale, "age_hours": age_hours, "issues": issues}


def build_health_note(health: dict) -> str:
    """把 check_data_health() 的結果轉成一行 Markdown 警示文字，健康時回傳空字串。"""
    issues = health.get("issues") or []
    if not issues:
        return ""
    return "> ⚠️ **競爭同業資料狀態提醒**：" + "；".join(issues)


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


def _strip_wikilinks(text: str) -> str:
    return _WIKILINK_RE.sub(r"\1", text or "")


def _rank_by(rows: list[dict], key: str) -> list[dict]:
    ranked = [r for r in rows if isinstance(r.get(key), (int, float))]
    return sorted(ranked, key=lambda r: r[key], reverse=True)


def build_ranking_highlights(data: dict | None) -> str:
    """固定式排名重點（不經 LLM，直接用 *_raw 數值計算），指出本公司在每項指標的同業排名。"""
    if not data or not data.get("rows"):
        return ""
    latest_rows = _latest_period_rows(data["rows"])
    target = next((r for r in latest_rows if r.get("relationship_type") == "target"), None)
    if target is None or len(latest_rows) < 2:
        return ""

    lines = []
    for key, label, signed in _RANKING_METRICS:
        ranked = _rank_by(latest_rows, key)
        if len(ranked) < 2:
            continue
        rank = next((i for i, r in enumerate(ranked, 1) if r.get("stock") == target.get("stock")), None)
        if rank is None:
            continue
        leader = ranked[0]
        fmt = (lambda v: f"{v:+.1f}%") if signed else (lambda v: f"{v:.1f}%")
        if leader.get("stock") == target.get("stock"):
            lines.append(f"- {label}最高：**本公司**（{fmt(leader[key])}），領先其餘 {len(ranked) - 1} 家同業")
        else:
            lines.append(
                f"- {label}最高：{leader.get('company')}（{fmt(leader[key])}）；"
                f"本公司排名第 {rank}/{len(ranked)}（{fmt(target[key])}）"
            )
    if not lines:
        return ""
    return "**同業排名重點**（依最新一期財報數字自動計算，非 LLM 生成）：\n" + "\n".join(lines)


def build_llm_context(data: dict | None) -> str:
    """給 LLM prompt 使用的精簡文字摘要（僅取最新一期），含公司定位描述與排名重點。"""
    if not data or not data.get("rows"):
        return ""
    latest_rows = _latest_period_rows(data["rows"])
    if not latest_rows:
        return ""

    lines = ["### 競爭同業財務比較（最新一季，資料來源：My-TW-Coverage）："]

    business_summary = _strip_wikilinks(data.get("business_summary", ""))
    if business_summary:
        lines.append(f"公司定位與差異化：{business_summary}\n")

    for row in latest_rows:
        label = _RELATIONSHIP_LABEL.get(row.get("relationship_type"), row.get("relationship_type", "同業"))
        lines.append(
            f"- {row.get('company')}（{row.get('stock')}，{label}）{row.get('period')}："
            f"營收 {row.get('revenue')}（YoY {row.get('revenue_yoy_pct')}），"
            f"營業利益 {row.get('profit')}（YoY {row.get('profit_yoy_pct')}），"
            f"淨利 {row.get('net_profit')}（YoY {row.get('net_profit_yoy_pct')}），"
            f"毛利率 {row.get('gross_margin_pct')}，營業利益率 {row.get('operating_margin_pct')}，"
            f"淨利率 {row.get('net_margin_pct')}，P/E {row.get('pe_range')}"
        )

    ranking = build_ranking_highlights(data)
    if ranking:
        lines.append(f"\n{ranking}")

    lines.append(
        "\n請針對上述**每一家**同業逐一比較本公司的相對表現（不要只挑1-2家舉例），"
        "並在分析中明確指出本公司在成長性、獲利能力、估值上相對同業的排名與差異化優劣勢。"
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
        "| 股票代碼 | 公司 | 關係 | 期間 | 營收 | YoY | 營業利益 | YoY | 淨利 | YoY | 毛利率 | 營業利益率 | 淨利率 | P/E |\n"
        "| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    )
    body_lines = []
    for row in latest_rows:
        label = _RELATIONSHIP_LABEL.get(row.get("relationship_type"), row.get("relationship_type", "同業"))
        body_lines.append(
            f"| {row.get('stock')} | {row.get('company')} | {label} | {row.get('period')} | "
            f"{row.get('revenue')} | {row.get('revenue_yoy_pct')} | {row.get('profit')} | "
            f"{row.get('profit_yoy_pct')} | {row.get('net_profit')} | {row.get('net_profit_yoy_pct')} | "
            f"{row.get('gross_margin_pct')} | {row.get('operating_margin_pct')} | {row.get('net_margin_pct')} | "
            f"{row.get('pe_range')} |"
        )
    footer = f"\n*資料來源：My-TW-Coverage，更新時間：{data.get('as_of', '')}*"
    table = "\n".join([header, *body_lines]) + footer

    ranking = build_ranking_highlights(data)
    if ranking:
        table += f"\n\n{ranking}"
    return table
