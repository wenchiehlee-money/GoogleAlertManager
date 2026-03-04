"""Load configuration from alerts.yaml and .env."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
ALERTS_DATA_DIR = DATA_DIR / "alerts"
REPORTS_DIR = DATA_DIR / "reports"
CONFIG_FILE = ROOT / "config" / "alerts.yaml"


def load_config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing environment variable: {key}")
    return value
