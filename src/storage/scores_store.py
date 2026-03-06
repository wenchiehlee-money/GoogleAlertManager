"""讀寫 data/scores.json — 以 entry id 為 key 的 Gemini 評分儲存。"""

import json

from src.config import DATA_DIR

SCORES_FILE = DATA_DIR / "scores.json"


def load_scores() -> dict[str, dict]:
    if not SCORES_FILE.exists():
        return {}
    with open(SCORES_FILE, encoding="utf-8") as f:
        return json.load(f)


def update_scores(new_scores: dict[str, dict]) -> None:
    """合併新評分至現有 scores.json。

    規則：
    - source='manual' 的條目永遠不被覆蓋（人工標記優先）
    - 其餘條目以新評分覆蓋舊值
    """
    existing = load_scores()
    for entry_id, score_data in new_scores.items():
        if existing.get(entry_id, {}).get("source") == "manual":
            continue  # 保護人工標記
        existing[entry_id] = score_data
    SCORES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
