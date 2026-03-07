"""以 Gemini API 針對每家公司進行情緒分析與投資建議。"""

import logging
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from src.config import get_env

logger = logging.getLogger(__name__)

MODEL = "gemini-2.0-flash"
MAX_TOKENS = 8192

_RETRY_DELAYS = [5, 15, 30]  # 秒，最多重試 3 次


def _client():
    return genai.Client(api_key=get_env("GEMINI_API_KEY"))


def _generate_with_retry(client, **kwargs):
    """呼叫 generate_content，遇到 503/429 時以 exponential backoff 重試。"""
    import re

    last_exc = None
    for i, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            logger.warning("Gemini API 重試，%d 秒後重試（第 %d 次）…", delay, i)
            time.sleep(delay)
        try:
            return client.models.generate_content(**kwargs)
        except genai_errors.ServerError as e:
            if e.code == 503:
                last_exc = e
                continue
            raise
        except genai_errors.ClientError as e:
            if e.code == 429:
                # 嘗試從錯誤訊息取得建議等待秒數
                suggested = 60
                m = re.search(r"retry[^\d]+(\d+)", str(e), re.IGNORECASE)
                if m:
                    suggested = int(m.group(1)) + 5
                wait = max(delay, suggested)
                logger.warning("Gemini API 429 quota，%d 秒後重試（第 %d 次）…", wait, i + 1)
                time.sleep(wait)
                last_exc = e
                continue
            raise
    raise last_exc


def _build_company_prompt(company, entries: list[dict]) -> str:
    items = []
    for e in entries:
        title = e.get("title", "")
        summary = e.get("summary", "")[:300]
        published = e.get("published", "")
        items.append(f"- [{published}] {title}\n  {summary}")
    items_text = "\n".join(items) if items else "（無文章）"

    return f"""\
以下是關於 **{company.name}（股票代碼：{company.stock_id}）** 的最新新聞/文章：

{items_text}

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


def analyze_company(company, entries: list[dict]) -> str:
    """對單一公司進行 Gemini 分析，回傳結構化 Markdown 結論。"""
    if not entries:
        return f"_近期無 {company.name}（{company.stock_id}）的相關新聞。_"

    client = _client()
    prompt = _build_company_prompt(company, entries)

    logger.info("Analyzing %s (%s) with %d entries", company.name, company.stock_id, len(entries))
    response = _generate_with_retry(
        client,
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=MAX_TOKENS),
    )
    return response.text


def score_entries(company, entries: list[dict]) -> dict[str, dict]:
    """用 Gemini 對每篇文章評分 0-5。回傳 {entry_id: {score, reason}}。

    評分標準：
      5 = 關鍵決策性資訊（財報、重大合約、技術突破、經營層異動）
      4 = 重要業務/產業資訊（市場份額、新產品、重要客戶）
      3 = 有參考價值的市場新聞
      2 = 一般性提及，資訊量少
      1 = 幾乎無關或重複
      0 = 完全無關/垃圾/廣告
    """
    import json as _json

    if not entries:
        return {}

    client = _client()
    items = []
    for i, e in enumerate(entries):
        items.append(
            f"[{i}] id={e['id']}\n"
            f"    標題: {e.get('title', '')}\n"
            f"    摘要: {e.get('summary', '')[:200]}\n"
            f"    發布: {e.get('published', '')}"
        )
    items_text = "\n\n".join(items)

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
{items_text}

請回傳 JSON 陣列，每篇文章一個物件：
[{{"id": "<原始id>", "score": <0-5整數>, "reason": "<15字內理由>"}}]
"""

    # 每篇約 80 token，保留 2 倍緩衝
    score_tokens = max(4096, len(entries) * 160)
    response = _generate_with_retry(
        client,
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=score_tokens,
        ),
    )

    try:
        results = _json.loads(response.text)
        return {
            item["id"]: {"score": item["score"], "reason": item.get("reason", "")}
            for item in results
            if "id" in item and "score" in item
        }
    except Exception as e:
        logger.warning("評分結果解析失敗：%s", e)
        return {}


def summarize(entries: list[dict]) -> str:
    """舊版 summarize 介面保留，用於 scheduler 向後兼容。"""
    if not entries:
        return "_今日無新 Alert 資料。_"

    client = _client()
    items = []
    for e in entries:
        name = e.get("name", e.get("stock_id", ""))
        title = e.get("title", "")
        summary = e.get("summary", "")[:200]
        items.append(f"- [{name}] {title} — {summary}")
    items_text = "\n".join(items)

    prompt = f"""\
以下是今日 Google Alert 收集到的股票相關文章清單：

{items_text}

請根據這些文章，用繁體中文提供：
1. **主要趨勢**（3-5 點，條列式）
2. **值得關注的個股**（最多 3 則，說明原因）
3. **整體市場觀察**（1-3 點建議）
"""
    response = _generate_with_retry(
        client,
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=MAX_TOKENS),
    )
    return response.text
