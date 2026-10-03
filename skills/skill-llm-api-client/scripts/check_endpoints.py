#!/usr/bin/env python3
"""Probe Codex-API-Server endpoints configured in .env.

Status checks are unauthenticated; inference checks use CODEX_API_KEY.
Secret values are never printed. The command succeeds when at least one endpoint
passes, which allows a healthy fallback endpoint while another route is offline.
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import httpx

from providers.codex import CODEX_ENDPOINTS


CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 180.0


def load_dotenv_literal(path: Path) -> dict[str, str]:
    """Load simple KEY=value lines without shell-evaluating secret values."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value
    return values


def probe_status(url: str, path: str) -> tuple[bool, float, str]:
    started = time.monotonic()
    try:
        response = httpx.get(url + path, timeout=httpx.Timeout(CONNECT_TIMEOUT))
        elapsed = (time.monotonic() - started) * 1000
        return response.is_success, elapsed, f"HTTP {response.status_code}"
    except Exception as exc:
        elapsed = (time.monotonic() - started) * 1000
        return False, elapsed, f"{type(exc).__name__}: {exc}"


def probe_inference(url: str, api_key: str) -> tuple[bool, float, str]:
    started = time.monotonic()
    try:
        response = httpx.post(
            url + "/exec",
            json={"prompt": "Reply with exactly pong.", "json_mode": False},
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            timeout=httpx.Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT,
                                  write=CONNECT_TIMEOUT, pool=CONNECT_TIMEOUT),
        )
        response.raise_for_status()
        output = " ".join(str(response.json().get("output", "")).split())
        elapsed = time.monotonic() - started
        return bool(output), elapsed, output[:120] if output else "<empty response>"
    except Exception as exc:
        elapsed = time.monotonic() - started
        return False, elapsed, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--skip-exec", action="store_true", help="Only run status probes")
    args = parser.parse_args()

    if not args.env_file.is_file():
        print(f"ERROR missing env file: {args.env_file}")
        return 2

    values = load_dotenv_literal(args.env_file)
    for key, value in values.items():
        os.environ.setdefault(key, value)
    urls = list(CODEX_ENDPOINTS)

    api_key = values.get("CODEX_API_KEY", os.getenv("CODEX_API_KEY", ""))
    print("=" * 80)
    print("LLM endpoint health check")
    print("=" * 80)
    print(f"Configured endpoints: {len(urls)}")
    print(f"API key status: {'configured' if api_key else 'missing'}")
    print(f"Inference: {'skipped' if args.skip_exec else 'enabled'}")

    healthy = 0
    for url in urls:
        print(f"\nTesting: {url}")
        statuses_ok = True
        for path in ("/codex/status", "/gemini/status"):
            ok, elapsed, detail = probe_status(url, path)
            statuses_ok &= ok
            print(f"  {path}: {'PASS' if ok else 'FAIL'} ({detail}, {elapsed:.1f} ms)")
        inference_ok = True
        if not args.skip_exec:
            if not api_key:
                inference_ok = False
                print("  inference: FAIL (CODEX_API_KEY is missing)")
            else:
                inference_ok, elapsed, detail = probe_inference(url, api_key)
                print(f"  inference: {'PASS' if inference_ok else 'FAIL'} ({elapsed:.2f} s, response={detail!r})")
        if statuses_ok and inference_ok:
            healthy += 1

    print(f"\nHealthy endpoints: {healthy}/{len(urls)}")
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
