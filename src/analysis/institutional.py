"""讀取法人研究情報同步過來的資料（尚無上游同步管線，見下方說明）。

資料來源設計為比照 src/analysis/competitors.py 的模式：由來源 repo 自己的
workflow push 一份精簡 JSON 進來，本檔案只負責讀取與組 prompt/報告文字，
不會、也無法主動呼叫對應的 skill 重新產生資料。

尚待建立的上游同步（目前完全沒有資料進來，以下所有函式在檔案不存在時皆
優雅降級為空字串/None，不會中斷報告流程）：

- data/institutional_reports/{stock_id}.json
  ← skill-institutional-tw-report-research（來源 repo：TW-institutional-research）
  券商評等/目標價/EPS 修正/法人籌碼 flow 的精簡快照。

- data/institutional_thesis/{stock_id}.json
  ← skill-institutional-thesis-research（來源 repo：TW-institutional-investment-theses）
  五大機構投資論點的精簡快照。

下方 JSON schema 為初版提案，實際同步管線建立後如欄位不同，調整這裡的
load_*/build_* 即可，不影響呼叫端（llm.py / markdown_writer.py）的介面。
"""

import json
import logging

from src.config import INSTITUTIONAL_REPORTS_DIR, INSTITUTIONAL_THESIS_DIR

logger = logging.getLogger(__name__)

_STANCE_LABEL = {
    "bullish": "偏多",
    "bearish": "偏空",
    "neutral": "中性",
}


def load_institutional_report(stock_id: str) -> dict | None:
    """讀取單一股票的法人研究報告快照，檔案不存在或格式錯誤時回傳 None。"""
    path = INSTITUTIONAL_REPORTS_DIR / f"{stock_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("無法讀取法人研究報告資料 %s：%s", path, e)
        return None


def load_institutional_thesis(stock_id: str) -> dict | None:
    """讀取單一股票的機構投資論點快照，檔案不存在或格式錯誤時回傳 None。"""
    path = INSTITUTIONAL_THESIS_DIR / f"{stock_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("無法讀取機構投資論點資料 %s：%s", path, e)
        return None


def _format_rating_distribution(dist: dict) -> str:
    parts = [f"{k}: {v}" for k, v in dist.items() if v]
    return "、".join(parts) if parts else ""


def build_llm_context(report: dict | None, thesis: dict | None) -> str:
    """給 LLM prompt 使用的精簡文字摘要。兩份資料都沒有時回傳空字串（no-op）。"""
    if not report and not thesis:
        return ""

    lines = ["### 法人研究情報（來源：TW-institutional-research / TW-institutional-investment-theses）："]

    if report:
        dist = report.get("rating_distribution") or {}
        if dist:
            lines.append(f"評等分布：{_format_rating_distribution(dist)}")

        tp = report.get("target_price_range") or {}
        if tp:
            lines.append(
                f"目標價區間：{tp.get('low', '-')} ~ {tp.get('high', '-')}（中位數 {tp.get('median', '-')}）"
            )

        for r in report.get("recent_reports", [])[:5]:
            rating_change = ""
            if r.get("rating_previous") and r.get("rating_previous") != r.get("rating"):
                rating_change = f"（前次：{r['rating_previous']}）"
            tp_change = ""
            if r.get("target_price_previous") and r.get("target_price_previous") != r.get("target_price"):
                tp_change = f"（前次：{r['target_price_previous']}）"
            lines.append(
                f"- {r.get('publisher', '未知券商')}（{r.get('report_date', '')}）："
                f"評等 {r.get('rating', '-')}{rating_change}，"
                f"目標價 {r.get('target_price', '-')}{tp_change}"
                + (f"，EPS修正 {r['eps_revision']}" if r.get("eps_revision") else "")
                + (f"｜{r['thesis']}" if r.get("thesis") else "")
            )

        divergence = report.get("view_flow_divergence")
        if divergence:
            lines.append(f"\n法人觀點與籌碼流向分歧：{divergence}")

    if thesis:
        theses = thesis.get("theses", [])
        if theses:
            lines.append("\n機構投資論點：")
            for t in theses:
                stance = _STANCE_LABEL.get(t.get("stance"), t.get("stance", "-"))
                lines.append(f"- {t.get('institution', '未知機構')}（{stance}）：{t.get('summary', '')}")

    lines.append(
        "\n請將上述法人評等/目標價動能與機構論點，與新聞內容交叉比對；"
        "當新聞情緒與法人評等/目標價方向明顯不一致時，在分析中明確指出分歧。"
    )
    return "\n".join(lines)


def build_markdown_table(report: dict | None, thesis: dict | None) -> str:
    """給報告直接顯示用的 markdown（固定格式，不經過 LLM）。兩份資料都沒有時回傳空字串。"""
    if not report and not thesis:
        return ""

    blocks = []

    if report and report.get("recent_reports"):
        header = (
            "| 券商/機構 | 日期 | 評等 | 目標價 | EPS修正 |\n"
            "| :--- | :---: | :---: | ---: | :---: |"
        )
        rows = []
        for r in report["recent_reports"]:
            rating = r.get("rating", "-")
            if r.get("rating_previous") and r["rating_previous"] != rating:
                rating = f"{rating}（前：{r['rating_previous']}）"
            tp = r.get("target_price", "-")
            if r.get("target_price_previous") and r["target_price_previous"] != tp:
                tp = f"{tp}（前：{r['target_price_previous']}）"
            rows.append(
                f"| {r.get('publisher', '-')} | {r.get('report_date', '-')} | {rating} | "
                f"{tp} | {r.get('eps_revision', '-')} |"
            )
        footer = f"\n*資料來源：TW-institutional-research，更新時間：{report.get('as_of', '')}*"
        blocks.append("\n".join([header, *rows]) + footer)

    if thesis and thesis.get("theses"):
        header = "| 機構 | 立場 | 論點 |\n| :--- | :---: | :--- |"
        rows = [
            f"| {t.get('institution', '-')} | {_STANCE_LABEL.get(t.get('stance'), t.get('stance', '-'))} | "
            f"{t.get('summary', '-')} |"
            for t in thesis["theses"]
        ]
        footer = f"\n*資料來源：TW-institutional-investment-theses，更新時間：{thesis.get('as_of', '')}*"
        blocks.append("\n".join([header, *rows]) + footer)

    return "\n\n".join(blocks)
