#!/usr/bin/env python
"""
add_custom_news.py

自動下載並解析 wenchiehlee-investment/MOPS 上的新聞 Markdown 檔案，
將其格式化為專案的 Google Alerts 快照 JSON，並自動跑完 analyze 分析生成報告。

特點:
    - 自動對比 Watchlist (公司代號與名稱)。
    - 自動從網址或檔名中提取日期與公司代號。
    - 智慧過濾：若來源為「經濟日報」且記者為「王郁倫」或「吳凱中」，會自動將新聞標註為 6 星書籤。

使用方法:
    python add_custom_news.py <GITHUB_URL> [--no-analyze]
"""

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import subprocess

# 載入專案模組
sys.path.append(str(Path(__file__).parent))
from src.companies.watchlist import load_companies


def to_raw_url(github_url: str) -> str:
    """將 GitHub 網頁 URL 轉換為原始 (raw) 內容 URL。"""
    if "github.com" in github_url and "/blob/" in github_url:
        raw_url = github_url.replace("github.com", "raw.githubusercontent.com")
        raw_url = raw_url.replace("/blob/", "/")
        return raw_url
    return github_url


def download_content(url: str) -> str:
    """下載網址內容。"""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req) as response:
        return response.read().decode("utf-8")


def parse_date_to_iso(date_str: str) -> str:
    """解析日期字串為 YYYY-MM-DD 格式。"""
    # 嘗試匹配 YYYY/MM/DD 或 YYYY-MM-DD
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", date_str)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 嘗試匹配 YYYY年MM月DD日
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_str)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ""


def parse_news_markdown(md_content: str):
    """解析 Markdown 中的標題、來源、記者、日期、網址與內文。"""
    lines = md_content.splitlines()
    title = ""
    source = ""
    reporter = ""
    date_raw = ""
    url = ""
    
    # 找標題
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            break
            
    # 正則匹配 metadata
    metadata_patterns = {
        "source": [r"\*\*來源\*\*\s*[:：]\s*(.*)", r"來源\s*[:：]\s*(.*)"],
        "reporter": [r"\*\*記者\*\*\s*[:：]\s*(.*)", r"記者\s*[:：]\s*(.*)"],
        "date": [r"\*\*日期\*\*\s*[:：]\s*(.*)", r"日期\s*[:：]\s*(.*)"],
        "url": [r"\*\*URL\*\*\s*[:::：]\s*(.*)", r"\*\*原文\*\*\s*[:：]\s*(.*)", r"URL\s*[:：]\s*(.*)", r"原文\s*[:：]\s*(.*)"]
    }
    
    for key, patterns in metadata_patterns.items():
        val = ""
        for pattern in patterns:
            for line in lines:
                m = re.search(pattern, line)
                if m:
                    val = m.group(1).strip()
                    break
            if val:
                break
        if key == "source":
            source = val
        elif key == "reporter":
            reporter = val
        elif key == "date":
            date_raw = val
        elif key == "url":
            url = val

    # 提取內文作為 summary
    body_lines = []
    in_body = False
    for line in lines:
        if line.strip() == "---":
            in_body = True
            continue
        if in_body:
            body_lines.append(line)
            
    if not body_lines:
        for line in lines:
            if line.startswith("# ") or any(re.search(pat, line) for pats in metadata_patterns.values() for pat in pats) or line.strip() == "---":
                continue
            body_lines.append(line)
            
    summary = "\n".join(body_lines).strip()
    return title, source, reporter, date_raw, url, summary


def main():
    if len(sys.argv) < 2:
        print("錯誤：請提供 GitHub 新聞 URL。")
        print("範例：python add_custom_news.py https://github.com/wenchiehlee-investment/MOPS/blob/main/downloads/2357/News/2026-03-06_udn_asus-ai-server-tier2-csp.md")
        sys.exit(1)
        
    github_url = sys.argv[1]
    no_analyze = "--no-analyze" in sys.argv
    
    # 1. 解析 stock_id 與公司名稱
    stock_id = ""
    # 從網址中尋找 "/downloads/xxxx/" 的結構
    m_stock = re.search(r"/downloads/(\d{4})/", github_url)
    if m_stock:
        stock_id = m_stock.group(1)
        
    companies = load_companies()
    company = next((c for c in companies if c.stock_id == stock_id), None)
    
    if not company:
        print(f"錯誤：在觀察名單中找不到代號 {stock_id} 的公司。")
        sys.exit(1)
        
    print(f"發現公司：{company.name} ({company.stock_id})")
    
    # 2. 下載並解析新聞
    raw_url = to_raw_url(github_url)
    print(f"正在從 {raw_url} 下載新聞...")
    try:
        md_content = download_content(raw_url)
    except Exception as e:
        print(f"下載失敗：{e}")
        sys.exit(1)
        
    title, source, reporter, date_raw, url, summary = parse_news_markdown(md_content)
    
    if not title or not url:
        print("錯誤：無法成功解析標題或原文 URL，請檢查 Markdown 格式。")
        sys.exit(1)
        
    # 3. 處理日期
    date_iso = parse_date_to_iso(date_raw)
    if not date_iso:
        # 如果欄位沒寫，嘗試從 GitHub 檔名尋找日期
        m_date = re.search(r"(\d{4}-\d{2}-\d{2})", github_url)
        if m_date:
            date_iso = m_date.group(1)
        else:
            m_date2 = re.search(r"(\d{8})", github_url)
            if m_date2:
                d = m_date2.group(1)
                date_iso = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
            else:
                date_iso = datetime.now().strftime("%Y-%m-%d")
                print(f"警告：無法解析日期，預設使用今天：{date_iso}")
                
    print(f"解析新聞：")
    print(f"  標題：{title}")
    print(f"  日期：{date_iso}")
    print(f"  來源：{source}")
    print(f"  記者：{reporter or '(無)'}")
    print(f"  網址：{url}")
    
    # 4. 建立 Entry 物件
    entry = {
        "id": url,
        "title": title,
        "link": url,
        "published": f"{date_iso}T12:00:00Z", # 使用 UTC 12 點為預設值
        "summary": summary,
        "stock_id": company.stock_id,
        "name": company.name,
        "fetched_at": datetime.now(timezone.utc).isoformat()
    }
    
    # 5. 合併至快照 JSON
    DATA_DIR = Path(__file__).parent / "data"
    alert_dir = DATA_DIR / "alerts" / date_iso
    alert_dir.mkdir(parents=True, exist_ok=True)
    json_path = alert_dir / f"{company.stock_id}.json"
    
    entries = []
    if json_path.exists():
        with open(json_path, encoding="utf-8") as f:
            try:
                entries = json.load(f)
            except json.JSONDecodeError:
                entries = []
                
    # 避開重複
    exists = any(e.get("link") == url or e.get("id") == url for e in entries)
    if not exists:
        entries.append(entry)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        print(f"✅ 成功將新聞寫入快照：{json_path}")
    else:
        print("該新聞已存在於快照中，跳過寫入。")

    # 5.1 智慧判定與人工標註 (若為經濟日報的王郁倫/吳凱中，直接自動標記為 6 星書籤)
    BEST_REPORTERS = ["王郁倫", "吳凱中"]
    BEST_SOURCES = ["經濟日報"]
    
    is_best_reporter = any(r in reporter for r in BEST_REPORTERS) if reporter else False
    is_best_source = any(s in source for s in BEST_SOURCES) if source else False
    
    cli_path = Path(__file__).parent / "cli.py"
    
    if is_best_reporter and is_best_source:
        print(f"\n💡 智慧過濾：偵測到此新聞由優質記者 ({reporter}) 發表於 {source}，自動指派為 6 星書籤！")
        label_reason = f"{source}優質報導 ({reporter})"
        subprocess.run([
            sys.executable, str(cli_path), "label",
            company.stock_id, date_iso, url, "6",
            "--reason", label_reason
        ])
        
    # 6. 自動執行分析
    if not no_analyze:
        print("\n正在自動執行情緒分析與報告生成...")
        result = subprocess.run([
            sys.executable, str(cli_path), "analyze",
            "--date", date_iso,
            "--stock-id", company.stock_id,
            "--force"
        ])
        if result.returncode == 0:
            print(f"✅ 分析報告已生成在：data/reports/{date_iso}/{company.stock_id}.md")
        else:
            print("❌ 分析失敗，請查看上方日誌。")


if __name__ == "__main__":
    main()
