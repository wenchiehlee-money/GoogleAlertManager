"""Compatibility wrapper for refreshing GoogleAlertManager watchlist CSVs."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SCRIPT = (
    ROOT
    / "skills"
    / "skill-google-alert-fetch"
    / "scripts"
    / "google_alert_fetch.py"
)


def download():
    subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(ROOT), "update-list"],
        check=True,
    )


if __name__ == "__main__":
    download()
