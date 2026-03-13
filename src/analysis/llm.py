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


def analyze_company(company, entries: list[dict]) -> str:
    """對單一公司進行分析，回傳結構化 Markdown 結論。"""
    if not entries:
        return f"_近期無 {company.name}（{company.stock_id}）的相關新聞。_"

    prompt = f"""\
以下是關於 **{company.name}（股票代碼：{company.stock_id}）** 的最新新聞/文章：

{_analysis_items(entries)}

請根據上述文章，用繁體中文提供以下分析：

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


def analyze_and_score(company, entries: list[dict]) -> tuple[str, dict[str, dict]]:
    """合併分析與評分為單次 API 呼叫，回傳 (analysis_text, scores)。"""
    if not entries:
        return f"_近期無 {company.name}（{company.stock_id}）的相關新聞。_", {}

    prompt = f"""\
以下是關於 **{company.name}（股票代碼：{company.stock_id}）** 的最新新聞/文章：

{_analysis_items(entries)}

請用繁體中文完成以下兩項任務，以 JSON 格式回傳：

### 任務一：公司分析
提供 Markdown 格式的分析（存入 "analysis" 欄位）：
## 1. 近期動態摘要（條列式，3-5 點重點）
## 2. 利多/利空判斷（利多因素、利空因素、整體傾向：利多/利空/中性）
## 3. 投資建議方向（買進/持有/觀察/迴避，擇一並說明）
> 注意：此分析僅供參考，不構成投資建議。

### 任務二：文章評分
對以下 {len(entries)} 篇文章逐一評分（存入 "scores" 欄位）：
評分標準（0-5）：5=關鍵決策性資訊、4=重要業務資訊、3=有參考價值、2=一般性提及、1=幾乎無關、0=完全無關/垃圾

{_score_items(entries)}

回傳格式：
{{"analysis": "<Markdown 分析文字>", "scores": [{{"id": "<原始id>", "score": <0-5>, "reason": "<15字內>"}}]}}
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
    return analysis, scores


def score_entries(company, entries: list[dict]) -> dict[str, dict]:
    """對每篇文章評分 0-5。"""
    if not entries:
        return {}

    prompt = f"""\
針對 **{company.name}（{company.stock_id}）** 的投資決策，請對以下 {len(entries)} 篇文章逐一評分：

評分標準（0-5）：
- 5：關鍵決策性資訊（財報、重大合約、技術突破、經營層異動）
- 4：重要業務/產業資訊（市場份額、新產品、重要客戶消息）
- 3：有參考價值的市場新聞
- 2：一般性提及，資訊量少
- 1：幾乎無關或重複
- 0：完全無關/垃圾/廣告

文章列表：
{_score_items(entries)}

請回傳 JSON 陣列，每篇文章一個物件：
[{{"id": "<原始id>", "score": <0-5整數>, "reason": "<15字內理由>"}}]
"""
    score_tokens = max(4096, len(entries) * 160)
    results = _get_client().generate_json(prompt, max_tokens=score_tokens)

    if not isinstance(results, list):
        return {}
    return {
        item["id"]: {"score": item["score"], "reason": item.get("reason", "")}
        for item in results
        if "id" in item and "score" in item
    }


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
