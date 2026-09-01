"""一次性清理歷史重複 alert entries。

背景：src/alerts/fetcher.py 過去的跨日去重邏輯有 bug（只跟「當天」已存檔的 entries
比對，未涵蓋歷史所有日期），導致同一篇文章（尤其是 Google Alert RSS 滾動視窗裡
停留較久的舊文章）可能連續多天被誤判為「新」而重複寫入 data/alerts/{date}/{stock_id}.json。

此腳本依日期由舊到新掃描 data/alerts/，對每支股票的每個 entry id 只保留「最早出現的
那一天」，之後日期裡重複的同一 id 會從該天的檔案移除。

用法：
    python scripts/dedupe_historical_alerts.py --dry-run   # 只印出會異動的檔案，不寫入
    python scripts/dedupe_historical_alerts.py --apply     # 實際寫回檔案

不會動 data/scores.json（依 id 存放，去重不影響既有評分）；也不會重新產生任何
data/reports/ 下的歷史報告——那些報告是否需要針對受影響日期重新分析，由使用者另外決定。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
ALERTS_DIR = ROOT / "data" / "alerts"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="只印出報告，不寫入檔案")
    group.add_argument("--apply", action="store_true", help="實際寫回去重後的檔案")
    args = parser.parse_args()

    if not ALERTS_DIR.exists():
        print(f"找不到 {ALERTS_DIR}", file=sys.stderr)
        return 1

    day_dirs = sorted(d for d in ALERTS_DIR.iterdir() if d.is_dir())

    seen_ids: dict[str, set[str]] = {}
    touched_files = 0
    total_removed = 0
    per_stock_removed: dict[str, int] = {}

    for day_dir in day_dirs:
        for json_file in sorted(day_dir.glob("*.json")):
            stock_id = json_file.stem
            with open(json_file, encoding="utf-8") as f:
                entries = json.load(f)

            known = seen_ids.setdefault(stock_id, set())
            kept = []
            removed = []
            for e in entries:
                eid = e.get("id", "")
                if eid and eid in known:
                    removed.append(e)
                else:
                    kept.append(e)
                    if eid:
                        known.add(eid)

            if removed:
                touched_files += 1
                total_removed += len(removed)
                per_stock_removed[stock_id] = per_stock_removed.get(stock_id, 0) + len(removed)
                rel = json_file.relative_to(ROOT)
                titles = "; ".join(e.get("title", "")[:40] for e in removed[:3])
                more = f" (+{len(removed) - 3} more)" if len(removed) > 3 else ""
                print(f"{'[DRY-RUN] ' if args.dry_run else ''}{rel}: 移除 {len(removed)} 筆重複 -> {titles}{more}")

                if args.apply:
                    with open(json_file, "w", encoding="utf-8") as f:
                        json.dump(kept, f, ensure_ascii=False, indent=2)

    print()
    print(f"受影響檔案數：{touched_files}")
    print(f"移除的重複 entries 總數：{total_removed}")
    print(f"受影響股票數：{len(per_stock_removed)}")
    if per_stock_removed:
        top = sorted(per_stock_removed.items(), key=lambda x: x[1], reverse=True)[:10]
        print("重複最多的前 10 支股票：")
        for stock_id, count in top:
            print(f"  {stock_id}: {count} 筆")

    if args.dry_run:
        print("\n這是 dry-run，未寫入任何檔案。加 --apply 才會實際清理。")
    else:
        print("\n已寫回去重後的檔案。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
