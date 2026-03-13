"""Tests for src/analysis/llm.py — mocks LLMClient, no real API calls."""
import sys
import os

# 讓 test 能找到 llm library（本地路徑）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../llm"))

import pytest
from unittest.mock import MagicMock, patch


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def company():
    c = MagicMock()
    c.name = "台積電"
    c.stock_id = "2330"
    return c


@pytest.fixture
def entries():
    return [
        {"id": "e1", "title": "台積電法說會", "summary": "營收創新高", "published": "2026-03-13"},
        {"id": "e2", "title": "台積電擴廠", "summary": "美國鳳凰城廠投產", "published": "2026-03-12"},
    ]


@pytest.fixture
def mock_client():
    with patch("src.analysis.llm._client", None):
        with patch("src.analysis.llm.LLMClient") as MockClass:
            instance = MagicMock()
            MockClass.return_value = instance
            yield instance


# ── empty entries (no LLM call) ───────────────────────────────────────────────

def test_analyze_company_empty(company):
    from src.analysis.llm import analyze_company
    result = analyze_company(company, [])
    assert "近期無" in result
    assert company.name in result


def test_analyze_and_score_empty(company):
    from src.analysis.llm import analyze_and_score
    text, scores = analyze_and_score(company, [])
    assert "近期無" in text
    assert scores == {}


def test_score_entries_empty(company):
    from src.analysis.llm import score_entries
    assert score_entries(company, []) == {}


def test_summarize_empty():
    from src.analysis.llm import summarize
    assert "無新" in summarize([])


# ── prompt builders ───────────────────────────────────────────────────────────

def test_analysis_items_format(entries):
    from src.analysis.llm import _analysis_items
    out = _analysis_items(entries)
    assert "台積電法說會" in out
    assert "2026-03-13" in out


def test_score_items_format(entries):
    from src.analysis.llm import _score_items
    out = _score_items(entries)
    assert "id=e1" in out
    assert "台積電法說會" in out


def test_score_items_missing_id():
    from src.analysis.llm import _score_items
    # 不應 crash，fallback 用 index
    out = _score_items([{"title": "無 id 文章", "summary": "test"}])
    assert "id=0" in out


def test_analysis_items_empty():
    from src.analysis.llm import _analysis_items
    assert _analysis_items([]) == "（無文章）"


# ── with mock LLM ─────────────────────────────────────────────────────────────

def test_analyze_company_calls_generate(company, entries, mock_client):
    from src.analysis import llm as llm_mod
    llm_mod._client = None  # reset singleton
    mock_client.generate.return_value = "## 分析結果"

    from src.analysis.llm import analyze_company
    result = analyze_company(company, entries)

    mock_client.generate.assert_called_once()
    assert "分析結果" in result


def test_analyze_and_score_calls_generate_json(company, entries, mock_client):
    from src.analysis import llm as llm_mod
    llm_mod._client = None
    mock_client.generate_json.return_value = {
        "analysis": "## 分析",
        "scores": [{"id": "e1", "score": 4, "reason": "重要"}],
    }

    from src.analysis.llm import analyze_and_score
    text, scores = analyze_and_score(company, entries)

    mock_client.generate_json.assert_called_once()
    assert text == "## 分析"
    assert scores == {"e1": {"score": 4, "reason": "重要"}}


def test_score_entries_calls_generate_json(company, entries, mock_client):
    from src.analysis import llm as llm_mod
    llm_mod._client = None
    mock_client.generate_json.return_value = [
        {"id": "e1", "score": 5, "reason": "財報"},
        {"id": "e2", "score": 3, "reason": "擴廠"},
    ]

    from src.analysis.llm import score_entries
    result = score_entries(company, entries)

    assert result["e1"]["score"] == 5
    assert result["e2"]["score"] == 3


def test_analyze_and_score_non_dict_response(company, entries, mock_client):
    from src.analysis import llm as llm_mod
    llm_mod._client = None
    mock_client.generate_json.return_value = ["unexpected", "list"]

    from src.analysis.llm import analyze_and_score
    text, scores = analyze_and_score(company, entries)
    assert scores == {}


def test_score_entries_non_list_response(company, entries, mock_client):
    from src.analysis import llm as llm_mod
    llm_mod._client = None
    mock_client.generate_json.return_value = {"unexpected": "dict"}

    from src.analysis.llm import score_entries
    result = score_entries(company, entries)
    assert result == {}
