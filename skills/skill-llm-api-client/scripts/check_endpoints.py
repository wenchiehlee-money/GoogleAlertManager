#!/usr/bin/env python3
"""SOP 工具：驗證 Codex 伺服器存活狀態與各端點回應時間 (Latency / Response Time)。

用法：
    python skills/skill-llm-api-client/scripts/check_endpoints.py
    python skills/skill-llm-api-client/scripts/check_endpoints.py --url https://api.wenchiehlee.synology.me:8443
"""
from __future__ import annotations

import argparse
import os
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import httpx

DEFAULT_CANDIDATES = [
    "https://api.wenchiehlee.synology.me:8443",
    "http://llm-cli-api.tail28f10.ts.net:5001",
]


def test_endpoint(url: str, api_key: str, check_exec: bool = True) -> dict:
    url = url.rstrip("/")
    headers = {"X-API-Key": api_key} if api_key else {}
    results = {
        "url": url,
        "alive": False,
        "codex_status": None,
        "codex_latency_ms": None,
        "gemini_status": None,
        "gemini_latency_ms": None,
        "exec_ok": False,
        "exec_latency_s": None,
        "error": None,
    }

    # 1. 探測 /codex/status
    t0 = time.perf_counter()
    try:
        r = httpx.get(f"{url}/codex/status", headers=headers, timeout=httpx.Timeout(connect=2.0, read=3.0, write=2.0, pool=2.0))
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        if r.status_code == 200:
            results["alive"] = True
            results["codex_status"] = r.json()
            results["codex_latency_ms"] = elapsed_ms
        else:
            results["codex_status"] = f"HTTP {r.status_code}"
    except Exception as e:
        results["error"] = type(e).__name__

    # 2. 探測 /gemini/status
    t0 = time.perf_counter()
    try:
        r = httpx.get(f"{url}/gemini/status", headers=headers, timeout=httpx.Timeout(connect=2.0, read=3.0, write=2.0, pool=2.0))
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        if r.status_code == 200:
            results["gemini_status"] = r.json()
            results["gemini_latency_ms"] = elapsed_ms
        else:
            results["gemini_status"] = f"HTTP {r.status_code}"
    except Exception:
        pass

    # 3. 測試 /exec 推論回應時間（若主機存活且要求測試）
    if results["alive"] and check_exec:
        t0 = time.perf_counter()
        try:
            r = httpx.post(
                f"{url}/exec",
                json={"prompt": "Reply with pong"},
                headers=headers,
                timeout=httpx.Timeout(connect=3.0, read=30.0, write=3.0, pool=3.0),
            )
            elapsed_s = round(time.perf_counter() - t0, 2)
            if r.status_code == 200:
                results["exec_ok"] = True
                results["exec_latency_s"] = elapsed_s
                results["exec_output"] = r.json().get("output", "").strip()
            else:
                results["exec_output"] = f"HTTP {r.status_code}"
        except Exception as e:
            results["exec_output"] = f"Error: {type(e).__name__}"

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="驗證 Codex 伺服器存活狀態與回應時間")
    parser.add_argument("--url", help="指定單一 URL 進行測試（預設自動檢查所有候選端點）")
    parser.add_argument("--skip-exec", action="store_true", help="跳過 /exec 推論測試，只測試 status 端點")
    args = parser.parse_args()

    api_key = os.getenv("CODEX_API_KEY", "")

    candidates = [args.url] if args.url else list(DEFAULT_CANDIDATES)

    print("📡 Codex 伺服器健康度與回應時間驗證 (SOP)")
    print("=" * 80)
    print(f"API 金鑰狀態     : {'已設定 (' + str(len(api_key)) + ' chars)' if api_key else '未設定'}")
    print(f"預計檢查端點數   : {len(candidates)}")
    print("-" * 80)

    best_url = None
    best_latency = float("inf")

    for url in candidates:
        print(f"\n🔍 正在測試: {url} ...")
        res = test_endpoint(url, api_key, check_exec=not args.skip_exec)

        if res["alive"]:
            status_desc = f"✅ 存活 (/codex/status: {res['codex_latency_ms']} ms"
            if res["gemini_latency_ms"]:
                status_desc += f", /gemini/status: {res['gemini_latency_ms']} ms"
            status_desc += ")"
            print(f"   狀態: {status_desc}")

            if not args.skip_exec:
                if res["exec_ok"]:
                    print(f"   推論: ✅ 成功 (耗時: {res['exec_latency_s']}s, 回應: {repr(res.get('exec_output'))})")
                    if res["exec_latency_s"] < best_latency:
                        best_latency = res["exec_latency_s"]
                        best_url = url
                else:
                    print(f"   推論: ⚠️ 失敗 ({res.get('exec_output')})")
            else:
                if res["codex_latency_ms"] < best_latency:
                    best_latency = res["codex_latency_ms"]
                    best_url = url
        else:
            print(f"   狀態: ❌ 無法連線 ({res['error'] or 'No response'})")

    print("\n" + "=" * 80)
    if best_url:
        print(f"🏆 最佳推薦端點: {best_url}")
        print("=" * 80)
        return 0
    else:
        print("❌ 警告：所有端點皆無法正常連線！請檢查 NAS、Tailscale 或網路連線。")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
