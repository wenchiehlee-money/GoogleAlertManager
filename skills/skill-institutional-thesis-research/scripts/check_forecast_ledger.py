#!/usr/bin/env python3
"""Lightweight checks for repository forecast ledgers."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ALLOWED_CONFIDENCE = {"low", "medium", "high"}
ALLOWED_LAYERS = {"fact", "institution_interpretation", "repository_inference"}
FIELD_RE = re.compile(r"^\s*([A-Za-z0-9_]+):\s*(.*)\s*$")


def clean_scalar(value: str) -> str:
    value = value.strip()
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        return value[1:-1]
    return value


def scan_file(path: Path) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    ids: dict[str, int] = {}
    current: dict[str, tuple[str, int]] = {}
    in_forecasts = False

    def finish_record() -> None:
        if not current:
            return
        forecast = current.get("forecast_id")
        if forecast:
            forecast_id, line = forecast
            ids[forecast_id] = ids.get(forecast_id, 0) + 1
            if ids[forecast_id] > 1:
                errors.append(f"{path}:{line}: duplicate forecast_id {forecast_id!r}")
        else:
            line = next(iter(current.values()))[1]
            warnings.append(f"{path}:{line}: forecast record missing forecast_id")

        if "source_path" not in current and "source_url" not in current:
            line = next(iter(current.values()))[1]
            warnings.append(f"{path}:{line}: forecast record missing source_path/source_url")

        confidence = current.get("confidence")
        if confidence and confidence[0] not in ALLOWED_CONFIDENCE:
            errors.append(
                f"{path}:{confidence[1]}: confidence must be one of {sorted(ALLOWED_CONFIDENCE)}"
            )

        layer = current.get("epistemic_layer")
        if layer and layer[0] not in ALLOWED_LAYERS:
            errors.append(
                f"{path}:{layer[1]}: epistemic_layer must be one of {sorted(ALLOWED_LAYERS)}"
            )

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        return [], [f"{path}: cannot read as UTF-8: {exc}"]

    for line_number, line in enumerate(lines, start=1):
        if line.startswith("forecasts:"):
            in_forecasts = True
            continue
        if not in_forecasts:
            continue
        if line and not line.startswith(" ") and not line.startswith("#"):
            finish_record()
            current = {}
            in_forecasts = False
            continue

        if line.startswith("  - "):
            finish_record()
            current = {}
            stripped = line[4:].strip()
        elif line.startswith("    "):
            stripped = line.strip()
        else:
            continue

        match = FIELD_RE.match(stripped)
        if match:
            key, value = match.groups()
            current[key] = (clean_scalar(value), line_number)

    finish_record()
    return warnings, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Check institutional forecast ledger files.")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()

    all_warnings: list[str] = []
    all_errors: list[str] = []
    for path in args.paths:
        if not path.exists():
            all_errors.append(f"{path}: file does not exist")
            continue
        warnings, errors = scan_file(path)
        all_warnings.extend(warnings)
        all_errors.extend(errors)

    for warning in all_warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in all_errors:
        print(f"error: {error}", file=sys.stderr)

    if all_errors:
        return 1
    print(f"checked {len(args.paths)} forecast ledger file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
