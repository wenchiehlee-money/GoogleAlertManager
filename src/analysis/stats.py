"""針對每家公司的 alert entries 進行統計分析。"""

import re
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass
class StatsResult:
    stock_id: str = ""
    entry_count: int = 0
    top_words: list[tuple[str, int]] = field(default_factory=list)
    top_domains: list[tuple[str, int]] = field(default_factory=list)
    # 向後兼容舊版（全關鍵字統計）
    keyword_counts: dict[str, int] = field(default_factory=dict)


_STOPWORDS = {
    # English
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "of", "for",
    "is", "are", "was", "were", "be", "been", "by", "with", "this", "that",
    "it", "as", "from", "but", "not", "have", "has", "had", "do", "does",
    # Chinese particles
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没",
    "看", "好", "自己", "这",
}


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


def analyze(entries: list[dict], top_n: int = 10, stock_id: str = "") -> StatsResult:
    """計算文章數、高頻詞彙、主要來源域名。"""
    word_counter: Counter = Counter()
    domain_counter: Counter = Counter()
    keyword_counts: Counter = Counter()

    for entry in entries:
        # 向後兼容：舊版 entries 用 keyword，新版用 stock_id/name
        key = entry.get("stock_id") or entry.get("keyword", "unknown")
        keyword_counts[key] += 1

        text = f"{entry.get('title', '')} {entry.get('summary', '')}"
        word_counter.update(_tokenize(text))

        link = entry.get("link", "")
        if link:
            try:
                domain = urlparse(link).netloc
                if domain:
                    domain_counter[domain] += 1
            except Exception:
                pass

    return StatsResult(
        stock_id=stock_id,
        entry_count=len(entries),
        top_words=word_counter.most_common(top_n),
        top_domains=domain_counter.most_common(top_n),
        keyword_counts=dict(keyword_counts.most_common()),
    )
