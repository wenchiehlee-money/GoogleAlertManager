"""Load configuration from alerts.yaml and .env."""

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

TZ_TAIPEI = timezone(timedelta(hours=8))


def today_taipei() -> date:
    """回傳台灣時間（UTC+8）的今日日期。"""
    return datetime.now(TZ_TAIPEI).date()

load_dotenv()

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
ALERTS_DATA_DIR = DATA_DIR / "alerts"
REPORTS_DIR = DATA_DIR / "reports"
COMPETITORS_DIR = DATA_DIR / "competitors"
INSTITUTIONAL_REPORTS_DIR = DATA_DIR / "institutional_reports"
INSTITUTIONAL_THESIS_DIR = DATA_DIR / "institutional_thesis"
CONFIG_FILE = ROOT / "config" / "alerts.yaml"


def load_config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing environment variable: {key}")
    return value



def llm_environment_status(env: dict[str, str] | None = None) -> dict[str, dict[str, object]]:
    """Return safe LLM configuration status without exposing secret values."""
    values = os.environ if env is None else env
    gemini_keys = [values.get("GEMINI_API_KEY", "")] + [
        values.get(f"GEMINI_API_KEY_{i}", "") for i in range(1, 20)
    ]
    return {
        "codex": {
            "ready": bool(values.get("CODEX_API_URL") and values.get("CODEX_API_KEY")),
            "missing": [name for name in ("CODEX_API_URL", "CODEX_API_KEY") if not values.get(name)],
        },
        "gemini": {
            "ready": any(gemini_keys),
            "missing": [] if any(gemini_keys) else ["GEMINI_API_KEY"],
        },
        "mlx": {
            "ready": bool(values.get("MLX_API_URL") and values.get("MLX_SERVER_API_KEY")),
            "missing": [name for name in ("MLX_API_URL", "MLX_SERVER_API_KEY") if not values.get(name)],
        },
    }


def require_llm_environment(env: dict[str, str] | None = None) -> dict[str, dict[str, object]]:
    """Validate that at least one provider has both config and secret values."""
    status = llm_environment_status(env)
    if not any(provider["ready"] for provider in status.values()):
        missing = "; ".join(
            f"{name}: {', '.join(provider['missing'])}"
            for name, provider in status.items()
        )
        raise RuntimeError(f"No LLM provider configured ({missing})")
    return status
