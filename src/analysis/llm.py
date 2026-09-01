"""以 LLM 針對每家公司進行情緒分析與投資建議。

底層使用 `llm` library。備援鏈為 codex（CLI 橋接，經 skill-llm-api-server 執行
gemini-cli）→ gemini（直接呼叫 Gemini API，多把 key 輪轉）→ mlx（本地推論）。
CLI 橋接與直接 API 都固定使用 gemini-2.5-flash，只是呼叫路徑不同；CODEX_API_URL/
CODEX_API_KEY 未設定時 codex provider 會被自動跳過，直接退回 gemini。
"""

import logging

from llm import LLMClient

from src.config import today_taipei

logger = logging.getLogger(__name__)

MAX_TOKENS = 8192
DEFAULT_MODEL = "gemini-2.5-flash"

_client: LLMClient | None = None


def _get_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient(
            providers=["codex", "gemini", "mlx"],
            model=DEFAULT_MODEL,
            app_name="GoogleAlertManager",
        )
    return _client


# ── prompt builders ───────────────────────────────────────────────────────────


MANUAL_EXCLUDE_MAX_SCORE = 1  # 人工標記 <= 此分數（幾乎無關/舊聞重複）不納入分析摘要


def _filter_for_analysis(entries: list[dict], known_scores: dict[str, dict] | None) -> list[dict]:
    """排除已被人工標記為低分（幾乎無關/舊聞）的文章，避免影響摘要與利多利空判斷。

    僅過濾 source='manual' 的標記，避免每日 LLM 自動評分的雜訊誤刪正常文章。
    """
    if not known_scores:
        return entries
    return [
        e
        for e in entries
        if not (
            known_scores.get(e.get("id", ""), {}).get("source") == "manual"
            and known_scores.get(e.get("id", ""), {}).get("score", 99) <= MANUAL_EXCLUDE_MAX_SCORE
        )
    ]


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
            f"    RSS 發布時間: {e.get('published', '（無）')}\n"
            f"    標題: {e.get('title', '')}\n"
            f"    摘要: {e.get('summary', '')[:200]}"
        )
    return "\n".join(lines)


# ── public API ────────────────────────────────────────────────────────────────


def analyze_company(
    company, entries: list[dict], competitor_context: str = "", known_scores: dict[str, dict] | None = None
) -> str:
    """對單一公司進行分析，回傳結構化 Markdown 結論。"""
    if not entries:
        return f"_近期無 {company.name}（{company.stock_id}）的相關新聞。_"

    analysis_entries = _filter_for_analysis(entries, known_scores)
    competitor_block = f"\n{competitor_context}\n" if competitor_context else ""

    prompt = f"""\
今日日期：{today_taipei().isoformat()}（判斷新聞時效性時請以此為基準）

以下是關於 **{company.name}（股票代碼：{company.stock_id}）** 的最新新聞/文章：

{_analysis_items(analysis_entries)}
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
5. 內容日期核實（RSS 發布時間不可盡信）：Google Alert 的「RSS 發布時間」有時只是 Google 重新索引/轉載的時間，
   不代表新聞真正首次發生的時間。請主動比對標題與摘要裡的時間線索（提到的展會/活動名稱、財報季別「如 2026Q1」、
   明確日期、「昨日」「上週」等相對時間用語），若內容明顯指向已經過去許久的事件（例如提到已結束數月的電腦展、
   已公布完畢的舊季財報、已過期的展會/法說會時程），即使 RSS 發布時間看起來是最近，仍應視為舊聞，比照第 1 分
   「幾乎無關/重複資訊」處理，並在 reason 註明「疑似舊聞：內容指向 {實際推估時間}」。無法判斷時維持原有標準評分，
   不要過度推測。
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


def analyze_and_score(
    company, entries: list[dict], competitor_context: str = "", known_scores: dict[str, dict] | None = None
) -> tuple[str, dict[str, dict]]:
    """合併分析與評分為單次 API 呼叫，回傳 (analysis_text, scores)。

    `known_scores`（通常是既有的 data/scores.json）用於在建立「近期動態摘要／利多利空判斷」
    的 prompt 時，排除已被人工標記為幾乎無關/舊聞的文章，避免結論被過時消息誤導；
    文章評分（任務二）仍涵蓋全部 entries，不受影響。
    """
    if not entries:
        return f"_近期無 {company.name}（{company.stock_id}）的相關新聞。_", {}

    analysis_entries = _filter_for_analysis(entries, known_scores)
    user_prefs = _get_user_preferences_prompt()
    competitor_block = f"\n{competitor_context}\n" if competitor_context else ""

    prompt = f"""\
今日日期：{today_taipei().isoformat()}（判斷新聞時效性時請以此為基準）

以下是關於 **{company.name}（股票代碼：{company.stock_id}）** 的最新新聞/文章：

{_analysis_items(analysis_entries)}
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
今日日期：{today_taipei().isoformat()}（判斷新聞時效性時請以此為基準）

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
