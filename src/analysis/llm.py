"""以 Gemini API 針對每家公司進行情緒分析與投資建議。"""

import logging

from google import genai
from google.genai import types

from src.config import get_env

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"
MAX_TOKENS = 8192


def _client():
    return genai.Client(api_key=get_env("GEMINI_API_KEY"))


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
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=MAX_TOKENS),
    )
    return response.text


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
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=MAX_TOKENS),
    )
    return response.text
