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
    """合併新評分至現有 scores.json（保留已有評分，新評分覆蓋舊值）。"""
    existing = load_scores()
    existing.update(new_scores)
    SCORES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
