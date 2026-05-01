"""產生每家公司 Markdown 報告及每日彙整報告。"""

from datetime import date
from pathlib import Path

from jinja2 import BaseLoader, Environment

from src.config import REPORTS_DIR

_STARS = ["○", "⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]

_COMPANY_TEMPLATE = """\
# {{ name }}（{{ stock_id }}）分析報告 — {{ date }}

**清單類型**：{{ list_type }}
**當日總文章數**：{{ entry_count }}

## ⭐ 高分精選文章 (Score ≥ 4) ({{ top_entries|length }})
{% if top_entries %}
{% for e in top_entries %}- {{ e.stars }} [{{ e.title }}]({{ e.url }}){% if e.reason %} — *{{ e.reason }}*{% endif %}
{% endfor %}
{% else %}
*（今日無高分文章）*
{% endif %}

## 📊 文章統計與來源 (含一般文章) ({{ general_count }})

- 一般文章數：{{ general_count }}
{% for e in general_entries_enriched %}
- {{ e.stars }} [{{ e.title }}]({{ e.url }}){% if e.reason %} — *{{ e.reason }}*{% endif %}
{% endfor %}

## LLM 分析結論

{{ llm_result }}

## 🛠️ 管理與更新

| 方式 | 動作 |
| :--- | :--- |
| **排程更新** | [🚩 標記為過時 (預約下次更新)](https://github.com/wenchiehlee-money/GoogleAlertManager/issues/new?title=[STALE]+{{ stock_id }}+{{ date }}&body=此報告內容已過時，請在下次排程任務中強制重新產生。%0A%0A---%0A*請勿修改標題，系統將自動處理此更新。*) |
| **立即更新** | [![Update Report](https://img.shields.io/badge/GitHub_Actions-Run_Update-blue?style=for-the-badge&logo=github)](https://github.com/wenchiehlee-money/GoogleAlertManager/actions/workflows/analyze.yml) <br> *(點擊後按 `Run workflow`，輸入 `{{ date }}` 與 `{{ stock_id }}`)* |
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

[詳細報告]({{ report.stock_id }}.md)

---
{% endfor %}

*報告產生時間：{{ generated_at }}*
"""


def _get_company_dir(day: date) -> Path:
    company_dir = REPORTS_DIR / day.isoformat()
    company_dir.mkdir(parents=True, exist_ok=True)
    return company_dir


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
    for e in entries:
        s = scores.get(e.get("id", ""), {})
        score_val = s.get("score", -1)
        if score_val >= 4:
            top_entries.append({
                "stars": _STARS[score_val] if 0 <= score_val <= 5 else "",
                "title": e.get("title", ""),
                "url": e.get("link", ""),
                "reason": s.get("reason", ""),
                "score": score_val
            })
        else:
            general_entries.append(e)
    top_entries.sort(key=lambda x: x["score"], reverse=True)

    # 2. 準備一般文章列表 (平鋪並排序)
    general_entries_enriched = []
    for e in general_entries:
        s = scores.get(e.get("id", ""), {})
        score_val = s.get("score", -1)
        general_entries_enriched.append({
            "stars": _STARS[score_val] if 0 <= score_val <= 5 else "",
            "title": e.get("title", ""),
            "url": e.get("link", ""),
            "reason": s.get("reason", ""),
            "score": score_val
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
    return str(summary_path)
