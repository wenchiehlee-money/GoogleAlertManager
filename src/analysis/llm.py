"""以 LLM 針對每家公司進行情緒分析與投資建議。

底層使用 `llm` library（支援 Gemini key 輪轉 + Codex-API-Server fallback）。
"""

import logging

from llm import LLMClient

logger = logging.getLogger(__name__)

MAX_TOKENS = 8192

_client: LLMClient | None = None


def _get_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient(app_name="GoogleAlertManager")
    return _client


# ── prompt builders ───────────────────────────────────────────────────────────


def _analysis_items(entries: list[dict]) -> str:
    lines = []
    for e in entries:
        title = e.get("title", "")
        summary = e.get("summary", "")[:300]
        published = e.get("published", "")
        lines.append(f"- [{published}] {title}\n  {summary}")
    return "\n".join(lines) if lines else "（無文章）"


def _score_items(entries: list[dict]) -> str:
    lines = []
    for i, e in enumerate(entries):
        lines.append(
            f"[{i}] id={e.get('id', str(i))}\n"
            f"    標題: {e.get('title', '')}\n"
            f"    摘要: {e.get('summary', '')[:200]}"
        )
    return "\n".join(lines)


# ── public API ────────────────────────────────────────────────────────────────


def analyze_company(company, entries: list[dict], competitor_context: str = "") -> str:
    """對單一公司進行分析，回傳結構化 Markdown 結論。"""
    if not entries:
        return f"_近期無 {company.name}（{company.stock_id}）的相關新聞。_"

    competitor_block = f"\n{competitor_context}\n" if competitor_context else ""

    prompt = f"""\
以下是關於 **{company.name}（股票代碼：{company.stock_id}）** 的最新新聞/文章：

{_analysis_items(entries)}
{competitor_block}
請根據上述文章{"與競爭同業財務比較" if competitor_context else ""}，用繁體中文提供以下分析：

## 1. 近期動態摘要
（條列式，3-5 點重點）

## 2. 利多/利空判斷
- **利多因素**：（列出正面因素，附理由）
- **利空因素**：（列出負面因素，附理由）
- **整體傾向**：利多 / 利空 / 中性（擇一，並說明主要依據）

## 3. 投資建議方向
從以下選項擇一，並說明理由：
- **買進**：具體說明進場理由與目標
- **持有**：說明繼續持有的依據
- **觀察**：說明需要觀察的關鍵指標
- **迴避**：說明風險與迴避原因

> 注意：此分析僅供參考，不構成投資建議。
"""
    logger.info("Analyzing %s (%s) with %d entries", company.name, company.stock_id, len(entries))
    return _get_client().generate(prompt, max_tokens=MAX_TOKENS)


def _get_user_preferences_prompt() -> str:
    """載入使用者的人工標註範例，作為 Few-shot Learning 參考。"""
    import json
    from pathlib import Path
    pref_path = Path("data") / "user_preferences.json"
    if not pref_path.exists():
        return ""
    
    try:
        with open(pref_path, encoding="utf-8") as f:
            prefs = json.load(f)
        if not prefs:
            return ""
        
        lines = ["### 使用者評分偏好範例 (請優先參考此標準)："]
        # 只取最近 10 則作為範例，避免 Prompt 過長
        for p in prefs[-10:]:
            lines.append(f"- 標題: {p['title']}")
            lines.append(f"  摘要: {p['summary'][:100]}...")
            lines.append(f"  評分: {p['score']} 分 (理由: {p.get('reason') or '無'})")
        return "\n".join(lines) + "\n"
    except Exception as e:
        logger.warning(f"無法載入使用者偏好：{e}")
        return ""


_SCORING_CRITERIA_PROMPT = """\
評分標準（0-6 整數）：
- 6 分【🔖 6分書籤/極高價值】：來自「工商時報」或「經濟日報」之報導，或極具長期參考與策略價值的必讀標竿文章（自動歸檔至 bookmarks.md 精選書籤頁）。
- 5 分【關鍵決策/重大事件】：官方財報/營收公告、重大併購、核心產品突破、高層異動、重大法律/政策變動。
- 4 分【重要業務/實質消息】：產能擴建/新廠投產、大客戶訂單確切消息、權威法人報告（目標價/評等顯著調整）。
- 3 分【參考價值/產業趨勢】：總體產業趨勢、法說會前展望預測、一般個股籌碼/技術面分析報導。
- 2 分【一般性提及/周邊報導】：僅文章末尾或列表中提及股票名稱/代號，無實質個股深入分析。
- 1 分【幾乎無關/重複資訊】：內容偏離主題、舊聞重複刊登、軟體自動產生的行情列表/行情圖摘要。
- 0 分【完全無關/垃圾/廣告】：詐騙/LINE飆股廣告、同名誤載、內容農場罐頭貼文、垃圾導流頁面。

評分特別注意事項：
1. 權威財經媒體（6分書籤）：凡來自「工商時報」或「經濟日報」（包含標題、摘要或連結含有 工商時報、經濟日報、ctee、money.udn）的文章，一律直接給予 6 分。
2. 內容農場/重複報導：若為多家內容農場轉載之同一公關稿且無原創觀點，上限降至 2-3 分。
3. 垃圾/廣告過濾：標題或摘要含「飆股」、「社團/LINE」、「親愛的朋友」、「投信掃貨鎖碼」等罐頭推銷語，一律給 0-1 分。
4. 嚴格扣分：僅條列股票代號而未有實質營運/財務分析者，最高僅給 2 分。
"""

TIER1_MEDIA_KEYWORDS = ["工商時報", "經濟日報", "ctee.com.tw", "money.udn.com"]


def _apply_source_scoring_rules(entries: list[dict], scores: dict[str, dict]) -> dict[str, dict]:
    """將來自『工商時報』或『經濟日報』的文章優先提升為 6 分書籤。"""
    entry_map = {e.get("id"): e for e in entries if "id" in e}
    for eid, sdata in scores.items():
        entry = entry_map.get(eid)
        if not entry:
            continue
        text_to_check = f"{entry.get('title', '')} {entry.get('summary', '')} {entry.get('link', '')}"
        if any(kw in text_to_check for kw in TIER1_MEDIA_KEYWORDS):
            sdata["score"] = 6
            if not sdata.get("reason"):
                sdata["reason"] = "權威媒體 (工商時報/經濟日報)"
            elif "工商時報" not in sdata["reason"] and "經濟日報" not in sdata["reason"]:
                sdata["reason"] += " (工商時報/經濟日報 6分書籤)"
    return scores


def analyze_and_score(company, entries: list[dict], competitor_context: str = "") -> tuple[str, dict[str, dict]]:
    """合併分析與評分為單次 API 呼叫，回傳 (analysis_text, scores)。"""
    if not entries:
        return f"_近期無 {company.name}（{company.stock_id}）的相關新聞。_", {}

    user_prefs = _get_user_preferences_prompt()
    competitor_block = f"\n{competitor_context}\n" if competitor_context else ""

    prompt = f"""\
以下是關於 **{company.name}（股票代碼：{company.stock_id}）** 的最新新聞/文章：

{_analysis_items(entries)}
{competitor_block}
{user_prefs}

請用繁體中文完成以下兩項任務，以 JSON 格式回傳：

### 任務一：公司分析
提供 Markdown 格式的分析（存入 "analysis" 欄位），若上方提供了競爭同業財務比較，請在判斷利多/利空與投資建議時納入考量：
## 1. 近期動態摘要（條列式，3-5 點重點）
## 2. 利多/利空判斷（利多因素、利空因素、整體傾向：利多/利空/中性）
## 3. 投資建議方向（買進/持有/觀察/迴避，擇一並說明）
> 注意：此分析僅供參考，不構成投資建議。

### 任務二：文章評分
對以下 {len(entries)} 篇文章逐一評分（存入 "scores" 欄位）：

{_SCORING_CRITERIA_PROMPT}

文章列表：
{_score_items(entries)}

回傳格式：
{{"analysis": "<Markdown 分析文字>", "scores": [{{"id": "<原始id>", "score": <0-6整數>, "reason": "<15字內評分理由>"}}]}}
"""

    score_tokens = max(MAX_TOKENS, len(entries) * 160 + MAX_TOKENS)
    logger.info("Analyzing+scoring %s (%s) with %d entries in 1 call", company.name, company.stock_id, len(entries))
    data = _get_client().generate_json(prompt, max_tokens=score_tokens)

    if not isinstance(data, dict):
        return str(data), {}

    analysis = data.get("analysis", "")
    scores = {
        item["id"]: {"score": item["score"], "reason": item.get("reason", "")}
        for item in data.get("scores", [])
        if "id" in item and "score" in item
    }
    scores = _apply_source_scoring_rules(entries, scores)
    return analysis, scores


def score_entries(company, entries: list[dict]) -> dict[str, dict]:
    """對每篇文章評分 0-6。"""
    if not entries:
        return {}

    prompt = f"""\
針對 **{company.name}（{company.stock_id}）** 的投資決策，請對以下 {len(entries)} 篇文章逐一評分：

{_SCORING_CRITERIA_PROMPT}

文章列表：
{_score_items(entries)}

請回傳 JSON 陣列，每篇文章一個物件：
[{{"id": "<原始id>", "score": <0-6整數>, "reason": "<15字內理由>"}}]
"""
    score_tokens = max(4096, len(entries) * 160)
    results = _get_client().generate_json(prompt, max_tokens=score_tokens)

    if not isinstance(results, list):
        return {}
    scores = {
        item["id"]: {"score": item["score"], "reason": item.get("reason", "")}
        for item in results
        if "id" in item and "score" in item
    }
    scores = _apply_source_scoring_rules(entries, scores)
    return scores


def summarize(entries: list[dict]) -> str:
    """舊版 summarize 介面保留，用於 scheduler 向後兼容。"""
    if not entries:
        return "_今日無新 Alert 資料。_"

    lines = []
    for e in entries:
        name = e.get("name", e.get("stock_id", ""))
        title = e.get("title", "")
        summary = e.get("summary", "")[:200]
        lines.append(f"- [{name}] {title} — {summary}")

    prompt = f"""\
以下是今日 Google Alert 收集到的股票相關文章清單：

{chr(10).join(lines)}

請根據這些文章，用繁體中文提供：
1. **主要趨勢**（3-5 點，條列式）
2. **值得關注的個股**（最多 3 則，說明原因）
3. **整體市場觀察**（1-3 點建議）
"""
    return _get_client().generate(prompt, max_tokens=MAX_TOKENS)
