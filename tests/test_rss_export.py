import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "skills/skill-google-alert-fetch/scripts/google_alert_fetch.py"
spec = importlib.util.spec_from_file_location("google_alert_fetch", SCRIPT)
skill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(skill)


@pytest.mark.parametrize("rss_map", [{}, {"2330": ""}])
def test_empty_export_preserves_fallback(tmp_path, monkeypatch, rss_map):
    from src.alerts import manager

    monkeypatch.setattr(manager, "get_rss_map", lambda: rss_map)
    output = tmp_path / "config/rss_urls.json"
    output.parent.mkdir()
    original = '{"2330": "https://google.com/alerts/feeds/existing"}\n'
    output.write_text(original)

    assert skill.cmd_export_rss(tmp_path) == 1
    assert output.read_text() == original


def test_valid_export_updates_map(tmp_path, monkeypatch):
    from src.alerts import manager

    monkeypatch.setattr(manager, "get_rss_map", lambda: {"2330": "https://google.com/alerts/feeds/new", "2317": ""})
    output = tmp_path / "config/rss_urls.json"
    output.parent.mkdir()

    assert skill.cmd_export_rss(tmp_path) == 0
    assert json.loads(output.read_text()) == {"2330": "https://google.com/alerts/feeds/new"}
