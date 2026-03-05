"""產生每家公司 Markdown 報告及每日彙整報告。"""

from datetime import date
from pathlib import Path

from jinja2 import BaseLoader, Environment

from src.config import REPORTS_DIR

_COMPANY_TEMPLATE = """\
# {{ name }}（{{ stock_id }}）分析報告 — {{ date }}

**清單類型**：{{ list_type }}

## 文章統計

- 總文章數：{{ entry_count }}
- 主要來源：
{% for domain, count in top_domains %}
<details>
<summary>{{ domain }} ({{ count }})</summary>

{% for title, url in domain_urls.get(domain, []) %}- [{{ title }}]({{ url }})
{% endfor %}
</details>
{% endfor %}

## LLM 分析結論

{{ llm_result }}

---
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
) -> str:
    """輸出單一公司報告至 data/reports/YYYY-MM-DD/{stock_id}.md。

    回傳檔案路徑。
    """
    from src.analysis.stats import analyze
    stat_result = analyze(entries, stock_id=company.stock_id)
    top_domains = stat_result.top_domains[:5]

    env = Environment(loader=BaseLoader())
    template = env.from_string(_COMPANY_TEMPLATE)
    content = template.render(
        name=company.name,
        stock_id=company.stock_id,
        list_type="專注清單" if company.list_type == "focus" else "觀察清單",
        date=day.isoformat(),
        entry_count=len(entries),
        top_domains=top_domains,
        domain_urls=stat_result.domain_urls,
        llm_result=llm_result,
        generated_at=generated_at,
    )

    company_dir = _get_company_dir(day)
    report_path = company_dir / f"{company.stock_id}.md"
    report_path.write_text(content, encoding="utf-8")
    return str(report_path)


def write_daily_summary(
    day: date,
    company_reports: list[dict],
    generated_at: str,
) -> str:
    """彙整所有公司報告至 data/reports/YYYY-MM-DD-summary.md。

    company_reports 每項須含：stock_id, name, list_type, summary 欄位。
    回傳檔案路徑。
    """
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
