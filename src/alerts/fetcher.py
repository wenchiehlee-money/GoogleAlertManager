"""以 stock_id 為 key 抓取 Google Alert RSS feeds。"""

import json
import logging
from datetime import datetime, timezone

import feedparser

from src.alerts.manager import get_rss_map
from src.companies.watchlist import Company, load_companies
from src.config import ROOT
from src.storage.json_store import load_entries, save_entries

logger = logging.getLogger(__name__)


def _parse_entry(entry: dict, company: Company) -> dict:
    return {
        "id": entry.get("id") or entry.get("link", ""),
        "title": entry.get("title", ""),
        "link": entry.get("link", ""),
        "published": entry.get("published", ""),
        "summary": entry.get("summary", ""),
        "stock_id": company.stock_id,
        "name": company.name,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _load_rss_urls_from_file() -> dict[str, str]:
    """從 config/rss_urls.json 讀取 RSS URL 映射（CI 環境 / 離線備用）。"""
    rss_file = ROOT / "config" / "rss_urls.json"
    if not rss_file.exists():
        return {}
    with open(rss_file, encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if v}


def fetch_all(companies: list[Company] | None = None) -> dict[str, int]:
    """抓取所有公司的 RSS feeds 並儲存新 entries。

    回傳 stock_id -> 新增 entry 數量 的映射。
    優先使用 Google Alerts，若驗證失敗則 fallback 到 config/rss_urls.json。
    """
    if companies is None:
        companies = load_companies()

    try:
        rss_map = get_rss_map()
    except Exception as e:
        logger.warning("Google Alerts 無法連線（%s），改用 config/rss_urls.json", e)
        rss_map = _load_rss_urls_from_file()
        if not rss_map:
            logger.error("config/rss_urls.json 為空，請先執行 export-rss 或設定 Google Alerts 憑證")
            return {}
    results: dict[str, int] = {}

    for company in companies:
        rss_url = rss_map.get(company.stock_id, "")
        if not rss_url:
            logger.warning("No RSS URL for %s (%s)", company.name, company.stock_id)
            results[company.stock_id] = 0
            continue

        feed = feedparser.parse(rss_url)
        existing = load_entries(company.stock_id)
        existing_ids = {e["id"] for e in existing}

        new_entries = []
        for entry in feed.entries:
            parsed = _parse_entry(entry, company)
            if parsed["id"] not in existing_ids:
                new_entries.append(parsed)

        if new_entries:
            save_entries(company.stock_id, existing + new_entries)
            logger.info("Saved %d new entries for %s (%s)", len(new_entries), company.name, company.stock_id)
        else:
            logger.info("No new entries for %s (%s)", company.name, company.stock_id)

        results[company.stock_id] = len(new_entries)

    return results
