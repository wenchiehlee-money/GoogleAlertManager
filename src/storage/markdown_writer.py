"""產生每家公司 Markdown 報告及每日彙整報告。"""

from datetime import date
from pathlib import Path

from jinja2 import BaseLoader, Environment

from src.config import REPORTS_DIR

_STARS = ["○", "⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐", "🔖 6分書籤"]

def _get_rating_links(stock_id: str, day_str: str, entry_id: str) -> str:
    """產生 1-6 分的重評連結。"""
    base_url = "https://github.com/wenchiehlee-money/GoogleAlertManager/issues/new"
    links = []
    for s in range(1, 7):
        title = f"[RATING] {stock_id} {day_str} {entry_id} {s}"
        body = f"Change rating to {s} for AI learning.\nReason: "
        import urllib.parse
        params = urllib.parse.urlencode({"title": title, "body": body})
        links.append(f"[{s}]({base_url}?{params})")
    return " / ".join(links)


_COMPANY_TEMPLATE = """\
# {{ name }}（{{ stock_id }}）分析報告 — {{ date }}

**清單類型**：{{ list_type }}
**當日總文章數**：{{ entry_count }}

## ⭐ 高分精選文章 (Score ≥ 4) ({{ top_entries|length }})
{% if top_entries %}
{% for e in top_entries %}- {{ e.stars }} [{{ e.title }}]({{ e.url }}){% if e.reason %} — *{{ e.reason }}*{% endif %} <sup>修正：{{ e.rating_links }}</sup>
{% endfor %}
{% else %}
*（今日無高分文章）*
{% endif %}

## 📊 文章統計與來源 (含一般文章) ({{ general_count }})

- 一般文章數：{{ general_count }}
{% for e in general_entries_enriched %}
- {{ e.stars }} [{{ e.title }}]({{ e.url }}){% if e.reason %} — *{{ e.reason }}*{% endif %} <sup>修正：{{ e.rating_links }}</sup>
{% endfor %}

## LLM 分析結論

{{ llm_result }}

## 🛠️ 管理與更新

| 方式 | 動作 |
| :--- | :--- |
| **請求更新** | [一鍵建立更新請求 (GitHub Issue)](https://github.com/wenchiehlee-money/GoogleAlertManager/issues/new?title=[STALE]+{{ stock_id }}+{{ date }}&body=STALE+{{ stock_id }}+{{ date }}) |
| **立即執行** | [前往 GitHub Actions 頁面](https://github.com/wenchiehlee-money/GoogleAlertManager/actions/workflows/analyze.yml) <br> *(點擊 `Run workflow` 後，請手動輸入日期 `{{ date }}` 與代號 `{{ stock_id }}`)* |
| **本地更新** | 執行指令：`python cli.py analyze --date {{ date }} --stock-id {{ stock_id }} --force` |

---
*報告產生時間：{{ generated_at }}*
"""

_TOP_COMPANY_TEMPLATE = """\
# ⭐ {{ name }}（{{ stock_id }}）高品質報告 — {{ date }}

此報告僅收錄評分 **4 分以上** 的關鍵資訊。

## 🎯 關鍵文章列表
{% for e in top_entries %}
- {{ e.stars }} [{{ e.title }}]({{ e.url }})
  > **核心價值**：{{ e.reason }}

{% endfor %}

## 💡 快速分析結論
{{ llm_result }}

---
[查看完整報告 (含所有文章)]({{ stock_id }}.md)

*報告產生時間：{{ generated_at }}*
"""

_SUMMARY_TEMPLATE = """\
# 每日彙整報告 — {{ date }}

> 共分析 {{ total_companies }} 家公司，{{ total_entries }} 篇文章

{% for report in company_reports %}
## {{ report.name }}（{{ report.stock_id }}）{% if report.list_type == "focus" %} ⭐{% endif %}

{{ report.summary }}

[詳細報告]({{ date }}/{{ report.stock_id }}.md)

---
{% endfor %}

*報告產生時間：{{ generated_at }}*
"""


def _get_company_dir(day: date) -> Path:
    company_dir = REPORTS_DIR / day.isoformat()
    company_dir.mkdir(parents=True, exist_ok=True)
    return company_dir


def summarize_llm_result(llm_result: str) -> str:
    """取得每日 summary 中使用的單行摘要。"""
    summary_lines = [line for line in llm_result.splitlines() if line.strip()]
    return summary_lines[0] if summary_lines else ""


def read_report_summary(report_path: Path) -> str:
    """從既有公司報告取回每日 summary 使用的摘要。"""
    if not report_path.exists():
        return ""

    content = report_path.read_text(encoding="utf-8")
    marker = "## LLM 分析結論"
    llm_result = content.split(marker, 1)[1] if marker in content else content
    return summarize_llm_result(llm_result)


def write_company_report(
    company,
    day: date,
    entries: list[dict],
    llm_result: str,
    generated_at: str,
    scores: dict | None = None,
) -> str:
    """輸出完整報告及高品質報告至 data/reports/YYYY-MM-DD/。"""
    from src.analysis.stats import analyze
    scores = scores or {}

    # 1. 分離高分與一般文章
    top_entries = []
    general_entries = []
    day_str = day.isoformat()
    for e in entries:
        eid = e.get("id", "")
        s = scores.get(eid, {})
        score_val = s.get("score", -1)
        entry_data = {
            "stars": _STARS[score_val] if 0 <= score_val <= 6 else "",
            "title": e.get("title", ""),
            "url": e.get("link", ""),
            "reason": s.get("reason", ""),
            "score": score_val,
            "rating_links": _get_rating_links(company.stock_id, day_str, eid)
        }
        if score_val >= 4:
            top_entries.append(entry_data)
        else:
            general_entries.append(e) # 原始 entry 留給統計用
    top_entries.sort(key=lambda x: x["score"], reverse=True)

    # 2. 準備一般文章列表 (平鋪並排序)
    general_entries_enriched = []
    for e in general_entries:
        eid = e.get("id", "")
        s = scores.get(eid, {})
        score_val = s.get("score", -1)
        general_entries_enriched.append({
            "stars": _STARS[score_val] if 0 <= score_val <= 6 else "",
            "title": e.get("title", ""),
            "url": e.get("link", ""),
            "reason": s.get("reason", ""),
            "score": score_val,
            "rating_links": _get_rating_links(company.stock_id, day_str, eid)
        })
    general_entries_enriched.sort(key=lambda x: x["score"], reverse=True)

    env = Environment(loader=BaseLoader())
    company_dir = _get_company_dir(day)
    
    # 1. 寫入完整報告
    template = env.from_string(_COMPANY_TEMPLATE)
    content = template.render(
        name=company.name,
        stock_id=company.stock_id,
        list_type="專注清單" if company.list_type == "focus" else "觀察清單",
        date=day.isoformat(),
        entry_count=len(entries),
        general_count=len(general_entries),
        top_entries=top_entries,
        general_entries_enriched=general_entries_enriched,
        llm_result=llm_result,
        generated_at=generated_at,
    )
    report_path = company_dir / f"{company.stock_id}.md"
    report_path.write_text(content, encoding="utf-8")

    # 2. 寫入高品質報告 (如果有高分文章)
    if top_entries:
        top_template = env.from_string(_TOP_COMPANY_TEMPLATE)
        top_content = top_template.render(
            name=company.name,
            stock_id=company.stock_id,
            date=day.isoformat(),
            top_entries=top_entries,
            llm_result=llm_result,
            generated_at=generated_at,
        )
        top_path = company_dir / f"{company.stock_id}-top.md"
        top_path.write_text(top_content, encoding="utf-8")

    update_search_paths()
    return str(report_path)


def write_daily_summary(
    day: date,
    company_reports: list[dict],
    generated_at: str,
) -> str:
    """彙整所有公司報告至 data/reports/YYYY-MM-DD-summary.md。"""
    total_entries = sum(r.get("entry_count", 0) for r in company_reports)

    env = Environment(loader=BaseLoader())
    template = env.from_string(_SUMMARY_TEMPLATE)
    content = template.render(
        date=day.isoformat(),
        total_companies=len(company_reports),
        total_entries=total_entries,
        company_reports=company_reports,
        generated_at=generated_at,
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = REPORTS_DIR / f"{day.isoformat()}-summary.md"
    summary_path.write_text(content, encoding="utf-8")
    update_search_paths()
    return str(summary_path)


_BOOKMARKS_TEMPLATE = """# 🔖 精選書籤清單 (6分)

> 這裡收集了所有由使用者手樣標記為 6 分的最有價值資訊。

{% if bookmarks %}
| 日期 | 公司 | 標題與連結 | 標籤/理由 | 標記時間 |
| :---: | :--- | :--- | :--- | :---: |
{% for b in bookmarks %}| {{ b.published[:10] }} | {{ b.name }} ({{ b.stock_id }}) | [{{ b.title }}]({{ b.link }}) | {{ b.reason or "-" }} | {{ b.marked_at }} |
{% endfor %}
{% else %}
*（目前尚無已標記的書籤文章）*
{% endif %}
"""


def write_bookmarks_page(bookmarks: list[dict]) -> str:
    """將所有書籤清單內容寫入至 data/reports/bookmarks.md。"""
    # 依發布日期由新到舊排序
    sorted_bookmarks = sorted(bookmarks, key=lambda x: x.get("published", ""), reverse=True)
    env = Environment(loader=BaseLoader())
    template = env.from_string(_BOOKMARKS_TEMPLATE)
    content = template.render(bookmarks=sorted_bookmarks)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    bookmarks_path = REPORTS_DIR / "bookmarks.md"
    bookmarks_path.write_text(content, encoding="utf-8")
    update_search_paths()
    return str(bookmarks_path)


def update_search_paths() -> str:
    """搜尋 data/reports 底下所有的 md 檔案並生成 paths.js 給 Docsify 搜尋引擎使用。"""
    from src.config import ROOT
    import json
    import time
    
    reports_dir = ROOT / "data" / "reports"
    paths = ["/"] # 首頁
    
    if reports_dir.exists():
        # 尋找所有 .md 檔案
        for md_file in reports_dir.rglob("*.md"):
            # 轉換為相對於專案根目錄的相對路徑，並去除 .md 後綴
            rel_path = md_file.relative_to(ROOT).as_posix()
            if rel_path.endswith(".md"):
                rel_path = rel_path[:-3]
            
            paths.append("/" + rel_path)
            
    # 去除重複，並排序
    paths = sorted(list(set(paths)))
    
    paths_file = ROOT / "paths.js"
    timestamp = int(time.time())
    content = (
        f"window.DOCS_PATHS_TIMESTAMP = {timestamp};\n"
        f"window.DOCS_PATHS = {json.dumps(paths, ensure_ascii=False, indent=2)};\n"
    )
    paths_file.write_text(content, encoding="utf-8")
    return str(paths_file)
