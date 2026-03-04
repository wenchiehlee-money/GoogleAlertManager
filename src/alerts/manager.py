"""以公司名單同步 Google Alerts（公司驅動）。"""

import logging
from typing import Any

from google_alerts import GoogleAlerts

from src.companies.watchlist import Company, load_companies
from src.config import get_env, load_config

logger = logging.getLogger(__name__)


def _client() -> GoogleAlerts:
    email = get_env("GOOGLE_ALERT_EMAIL")
    password = get_env("GOOGLE_ALERT_PASSWORD")
    ga = GoogleAlerts(email, password)
    ga.authenticate()
    return ga


def _alert_term(company: Company) -> str:
    return f'"{company.name}" "{company.stock_id}"'


def list_alerts() -> list[dict]:
    """回傳所有目前 Google Alerts（含 RSS URL）。"""
    return _client().list()


def get_rss_map() -> dict[str, str]:
    """回傳 stock_id -> rss_url 的映射（從 Google Alerts 取得）。

    利用 alert term 中的股票代碼識別對應公司。
    """
    alerts = list_alerts()
    rss_map: dict[str, str] = {}
    for alert in alerts:
        term: str = alert.get("term", "")
        rss_url: str = alert.get("rss_link", "")
        if not rss_url:
            continue
        # term 格式："{公司名}" "{股票代碼}"，取最後一個 token 去掉引號作為 stock_id
        parts = term.strip().split()
        if parts:
            stock_id = parts[-1].strip('"')
            rss_map[stock_id] = rss_url
    return rss_map


def sync_alerts() -> dict[str, list]:
    """比對公司名單與 Google Alerts，建立缺少的、刪除清單以外的。

    回傳 {created, deleted, unchanged} 公司名稱列表。
    """
    config = load_config()
    alert_options = config.get("alert_options", {})
    language = alert_options.get("language", "zh-TW")
    region = alert_options.get("region", "TW")
    how_often = alert_options.get("how_often", "as_it_happens")

    companies = load_companies()
    desired_terms = {_alert_term(c): c for c in companies}

    ga = _client()
    existing: list[dict[str, Any]] = ga.list()
    existing_by_term: dict[str, dict] = {a.get("term", ""): a for a in existing}

    created, deleted, unchanged = [], [], []

    # 建立缺少的
    for term, company in desired_terms.items():
        if term in existing_by_term:
            unchanged.append(company.name)
            logger.info("Alert already exists, skipping: %s", term)
        else:
            options = {
                "delivery": "RSS",
                "language": language,
                "region": region,
                "how_often": how_often,
            }
            ga.create(term, options)
            created.append(company.name)
            logger.info("Created alert: %s", term)

    # 刪除清單以外的
    for term, alert in existing_by_term.items():
        if term not in desired_terms:
            ga.delete(alert["id"])
            deleted.append(term)
            logger.info("Deleted alert not in watchlist: %s", term)

    return {"created": created, "deleted": deleted, "unchanged": unchanged}
