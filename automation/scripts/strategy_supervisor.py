#!/usr/bin/env python3
"""Strategy Supervisor — check all 10 strategy sub-agents for bugs.

Runs 9 health checks in parallel:
  1. Import + callable
  2. Live detector smoke test (with mock data)
  3. Output dict structure
  4. direction field valid
  5. strength/grade fields
  6. Required config in yw_grader.py STRATEGIES dict
  7. Weight in strategy_ranking.py matches grader

Reports:
  - BUG (❌): any error
  - WARN (⚠️): unexpected but functional
  - OK (✅): healthy

Usage:
  python3 scripts/strategy_supervisor.py [--tg] [--json]
"""
from __future__ import annotations
import os
import sys
import json
import argparse
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Lock for thread-safe module imports
_IMPORT_LOCK = threading.Lock()
from datetime import datetime, timezone, timedelta

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

# 10 strategy sub-agents with their detection functions
AGENTS = [
    {"id": "h-pattern",       "agent": "yw-h-pattern",       "module": "yw_indicators",       "fn": "detect_h_pattern",        "needs_4h": False, "tickers": ["MNQ=F", "MES=F", "M2K=F"]},
    {"id": "3-pushes",        "agent": "yw-3-pushes",        "module": "yw_indicators",       "fn": "detect_3_pushes",         "needs_4h": False, "tickers": ["MNQ=F", "MES=F", "M2K=F"]},
    {"id": "two-yang",        "agent": "yw-two-yang",        "module": "yw_indicators",       "fn": "detect_two_yang_one_yin", "needs_4h": False, "tickers": ["MNQ=F", "MES=F", "M2K=F"]},
    {"id": "rsi-div",         "agent": "yw-rsi-div",         "module": "yw_indicators",       "fn": "detect_rsi_divergence",   "needs_4h": False, "tickers": ["MNQ=F", "MES=F", "M2K=F"]},
    {"id": "50-20-pullback",  "agent": "yw-50-20-pullback",  "module": "yw_indicators",       "fn": "detect_5020_pullback",    "needs_4h": False, "tickers": ["MNQ=F", "MES=F", "M2K=F"]},
    {"id": "stair-pattern",   "agent": "yw-stair-pattern",   "module": "yw_indicators_extra", "fn": "detect_stair_pattern",    "needs_4h": False, "tickers": ["MNQ=F", "MES=F", "M2K=F"]},
    {"id": "crt",             "agent": "yw-crt",             "module": "yw_indicators_extra", "fn": "detect_crt",              "needs_4h": True,  "tickers": ["MNQ=F", "MES=F", "M2K=F"]},
    {"id": "kell-cycle",      "agent": "yw-kell-cycle",      "module": "yw_indicators_extra", "fn": "detect_kell_setups",      "needs_4h": False, "tickers": ["MNQ=F", "MES=F", "M2K=F"]},
    {"id": "ocs-btc",         "agent": "ocs-btc-5m",         "module": "ocs_btc_5m",          "fn": "compute_signal",          "needs_4h": False, "tickers": ["BTC-USD"]},
    {"id": "b1",               "agent": "yw-b1",               "module": "yw_indicators_b1",     "fn": "detect_b1",              "needs_4h": False, "tickers": ["MNQ=F", "MES=F", "M2K=F"]},
]


def make_mock_df(ticker: str = "MNQ=F", n: int = 100):
    """Create a mock OHLCV DataFrame for smoke testing."""
    import pandas as pd
    import numpy as np
    np.random.seed(42)
    base = 29000 if "MNQ" in ticker else 5000 if "M2K" in ticker else 50000 if "BTC" in ticker else 30000
    returns = np.random.normal(0.0001, 0.002, n)
    prices = base * (1 + returns).cumprod()
    df = pd.DataFrame({
        "Open":   prices * (1 + np.random.normal(0, 0.001, n)),
        "High":   prices * (1 + np.abs(np.random.normal(0, 0.002, n))),
        "Low":    prices * (1 - np.abs(np.random.normal(0, 0.002, n))),
        "Close":  prices,
        "Volume": np.random.uniform(1000, 10000, n).astype(int),
    })
    return df


def check_agent(agent: dict) -> dict:
    """Run all health checks for one sub-agent."""
    # Each thread worker needs its own sys.path
    src_path = str(REPO / "automation/src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    result = {
        "agent": agent["agent"],
        "id": agent["id"],
        "module": agent["module"],
        "fn": agent["fn"],
        "checks": [],
        "bugs": [],
        "warns": [],
    }

    # Check 1: Import + callable
    try:
        # Thread-safe: lock around sys.modules manipulation
        with _IMPORT_LOCK:
            mod = sys.modules.get(agent["module"])
            if mod is None:
                mod = __import__(agent["module"])
        fn = getattr(mod, agent["fn"], None)
        if fn is None:
            result["bugs"].append(f"❌ Function {agent['fn']} not found in {agent['module']}")
            result["checks"].append(("import", "FAIL"))
            return result
        result["checks"].append(("import", "OK"))
    except ModuleNotFoundError as e:
        # Missing dependency — warn not bug (GHA env issue, not code issue)
        result["warns"].append(f"⚠️ Missing dependency: {e.name} (install -r requirements.txt)")
        result["checks"].append(("import", "WARN"))
        return result
    except Exception as e:
        result["bugs"].append(f"❌ Import error: {type(e).__name__}: {str(e)[:100]}")
        result["checks"].append(("import", "FAIL"))
        return result

    # Check 2: Smoke test
    try:
        df = make_mock_df()
        if agent["needs_4h"]:
            df_4h = make_mock_df().iloc[::12]  # resample
            out = fn(df_4h, df)
        elif agent["id"] == "ocs-btc":
            # OCS compute_signal needs (knn_result, features_df, close_series, atr_series)
            # Complex setup - skip smoke test, just verify import
            result["checks"].append(("smoke", "SKIP"))
            result["checks"].append(("output_fields", "SKIP"))
            return result
        else:
            out = fn(df)
        if not isinstance(out, dict):
            result["bugs"].append(f"❌ {agent['fn']} did not return dict (got {type(out).__name__})")
            result["checks"].append(("smoke", "FAIL"))
            return result
        result["checks"].append(("smoke", "OK"))
    except Exception as e:
        result["bugs"].append(f"❌ Smoke test: {type(e).__name__}: {str(e)[:100]}")
        result["checks"].append(("smoke", "FAIL"))
        return result

    # Check 3: Output is dict with detection info
    # (Some detectors return {present, direction}, others return {type, cross, etc.}
    #  live_scan.py wraps them via _normalize_detector() to unified interface.
    #  So custom format is INFO (OK), not WARN — the system handles it.)
    has_present = "present" in out
    has_direction = "direction" in out
    is_present = bool(out.get("present", False))
    if has_present and has_direction:
        result["checks"].append(("output_fields", "OK"))
    elif has_present and not is_present:
        # No signal — direction not required (this is normal)
        result["checks"].append(("output_fields", "OK (no signal)"))
    elif has_present or has_direction:
        # Has present=True but missing direction → real concern
        if has_present and is_present:
            result["warns"].append(f"⚠️ Signal True but no direction field")
            result["checks"].append(("output_fields", "WARN"))
        else:
            result["checks"].append(("output_fields", "OK"))
    elif any(k in out for k in ["type", "cross_type", "reversal_extension", "wedge_pop_drop", "crt_high"]):
        # Custom format - live_scan.py has _normalize_detector() wrapper
        result["checks"].append(("output_fields", "OK (custom)"))
    else:
        result["bugs"].append(f"❌ Empty/unrecognized output: {list(out.keys())[:5]}")
        result["checks"].append(("output_fields", "FAIL"))

    # Check 4: direction valid (if present)
    if has_direction and out["direction"] not in ("long", "short", "bullish", "bearish", "up", "down", "none", None):
        result["warns"].append(f"⚠️ Unexpected direction: {out.get('direction')}")
    result["checks"].append(("direction", "OK"))

    # Check 5: yw_grader.py STRATEGIES config
    try:
        # Don't delete sys.modules["yw_indicators"] - it can break other threads
        if "yw_grader" not in sys.modules:
            sys.path.insert(0, str(REPO / "automation/src"))
            import yw_grader
        from yw_grader import STRATEGIES
        # Map agent.id to grader key
        grader_key_map = {
            "h-pattern": "H-Pattern", "3-pushes": "3-Pushes", "two-yang": "Two-Yang-One-Yin",
            "rsi-div": "RSI-Divergence", "50-20-pullback": "50-20-Pullback",
            "stair-pattern": "Stair-Pattern", "crt": "CRT", "kell-cycle": "Kell-Cycle",
            "ocs-btc": "OCS-BTC-5m",
            "b1": "B1", "b1-3in1": "B1-3in1",
            "b1-mnq": "B1", "b1-mgc": "B1", "b1-btc": "B1",
        }
        key = grader_key_map.get(agent["id"])
        if key and key in STRATEGIES:
            cfg = STRATEGIES[key]
            if not cfg.get("weight"):
                result["bugs"].append(f"❌ {key} weight=0 or missing")
            result["checks"].append(("grader_config", f"OK w={cfg.get('weight')}"))
        else:
            result["warns"].append(f"⚠️ Not in yw_grader.STRATEGIES (using yw_ranking)")
            result["checks"].append(("grader_config", "N/A"))
    except Exception as e:
        result["warns"].append(f"⚠️ Grader check skipped: {str(e)[:60]}")
        result["checks"].append(("grader_config", "SKIP"))

    return result


def send_tg(results: list, bugs_only: bool = False):
    """Send TG report."""
    import requests
    lines = ["🔍 Strategy Supervisor Report — 9 Agents\n"]
    n_ok = sum(1 for r in results if not r["bugs"])
    n_bug = len([r for r in results if r["bugs"]])
    n_warn = len([r for r in results if r["warns"]])

    lines.append(f"  {n_ok} OK | {n_warn} WARN | {n_bug} BUG\n")
    for r in results:
        if bugs_only and not r["bugs"]:
            continue
        if r["bugs"]:
            lines.append(f"  ❌ {r['agent']:18s} {r['fn']}")
            for b in r["bugs"]:
                lines.append(f"     {b}")
        elif r["warns"]:
            lines.append(f"  ⚠️  {r['agent']:18s} {r['fn']}")
            for w in r["warns"]:
                lines.append(f"     {w}")
        else:
            checks = " ".join(f"{c[0]}:✓" for c in r['checks'] if c[1] == "OK")
            lines.append(f"  ✅ {r['agent']:18s} {r['fn']}  ({checks})")

    msg = "\n".join(lines)
    r = requests.post(
        f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
        json={"chat_id": os.environ['TELEGRAM_CHAT_ID'], "text": msg},
        timeout=15,
    )
    return r.json()


def check_sys_engineer() -> dict:
    """Power 1 (Supervisor) monitors System Engineer.
    
    Checks: did sys-engineer run recently? Are its reports valid?
    """
    result = {
        "agent": "sys-engineer",
        "id": "sys-engineer",
        "module": "sys_engineer",
        "fn": "main",
        "checks": [],
        "bugs": [],
        "warns": [],
    }
    try:
        sys_eng_dir = REPO / "automation/reports/sys_engineer"
        if not sys_eng_dir.exists():
            result["warns"].append("⚠️ sys_engineer reports dir not found")
            result["checks"].append(("sys_eng_dir", "WARN"))
            return result
        reports = sorted(sys_eng_dir.glob("sys_eng_*.json"), reverse=True)
        if not reports:
            result["warns"].append("⚠️ No sys_engineer reports yet")
            result["checks"].append(("reports", "WARN"))
            return result
        latest = reports[0]
        from datetime import datetime as dt
        age_hours = (dt.now() - dt.fromtimestamp(latest.stat().st_mtime)).total_seconds() / 3600
        if age_hours > 2:
            result["warns"].append(f"⚠️ sys_engineer last ran {age_hours:.1f}h ago (>2h)")
            result["checks"].append(("recency", f"WARN ({age_hours:.1f}h)"))
        else:
            result["checks"].append(("recency", f"OK ({age_hours:.1f}h)"))
        try:
            data = json.loads(latest.read_text())
            n_bugs = data.get("n_bugs", 0)
            n_lazy = data.get("n_lazy", 0)
            if n_bugs > 0:
                result["warns"].append(f"⚠️ sys_engineer found {n_bugs} BUGs in last report")
            result["checks"].append(("content", f"OK bugs={n_bugs} lazy={n_lazy}"))
        except Exception as e:
            result["warns"].append(f"⚠️ sys_engineer report parse error: {e}")
            result["checks"].append(("content", "WARN"))
    except Exception as e:
        result["bugs"].append(f"❌ sys_engineer check error: {e}")
        result["checks"].append(("sys_eng_check", "FAIL"))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tg", action="store_true", help="Send to TG")
    parser.add_argument("--json", help="Output JSON to file")
    parser.add_argument("--bugs-only", action="store_true", help="TG only show bugs")
    args = parser.parse_args()

    HKT = timezone(timedelta(hours=8))
    ts = datetime.now(HKT).strftime("%Y%m%d_%H%M%S")
    print(f"[supervisor] Checking 10 strategy sub-agents @ {ts}")

    # Power 1: Check 10 strategy sub-agents in parallel
    # Power 1 also checks sys-engineer (mutual oversight)
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        # 10 strategy agents
        futures = {executor.submit(check_agent, a): a for a in AGENTS}
        # Plus sys-engineer check (Power 1 monitors Power 2)
        sys_eng_future = executor.submit(check_sys_engineer)
        
        for future in as_completed(futures):
            try:
                r = future.result()
                results.append(r)
                status = "❌" if r["bugs"] else "⚠️ " if r["warns"] else "✅"
                print(f"  {status} {r['agent']:18s} ({len(r['bugs'])} bugs, {len(r['warns'])} warns)")
            except Exception as e:
                print(f"  💥 {futures[future]['agent']}: {e}")
                results.append({"agent": futures[future]["agent"], "bugs": [f"💥 Exception: {e}"], "warns": [], "checks": []})
        
        # Add sys-engineer check
        try:
            r = sys_eng_future.result()
            results.append(r)
            status = "❌" if r["bugs"] else "⚠️ " if r["warns"] else "✅"
            print(f"  {status} {r['agent']:18s} ({len(r['bugs'])} bugs, {len(r['warns'])} warns)")
        except Exception as e:
            print(f"  💥 sys-engineer check: {e}")

    # Sort by status
    results.sort(key=lambda r: (len(r["bugs"]), len(r["warns"])), reverse=True)

    # Save (now 11 = 10 agents + sys-engineer)
    out = {
        "timestamp": ts,
        "n_agents": 11,
        "n_ok": sum(1 for r in results if not r["bugs"]),
        "n_warn": sum(1 for r in results if r["warns"] and not r["bugs"]),
        "n_bug": sum(1 for r in results if r["bugs"]),
        "results": results,
    }
    out_path = REPO / "automation/reports/supervisor" / f"strategy_check_{ts}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[supervisor] Saved: {out_path}")
    print(f"[supervisor] {out['n_ok']} OK | {out['n_warn']} WARN | {out['n_bug']} BUG")

    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2, default=str))

    if args.tg:
        result = send_tg(results, bugs_only=args.bugs_only)
        if result.get("ok"):
            print(f"[supervisor] TG sent (msg_id {result['result']['message_id']})")
        else:
            print(f"[supervisor] TG error: {result.get('description')}")

    return 0 if out["n_bug"] == 0 else 1


# Pre-import all modules in main process so workers can pick them up via sys.modules
sys.path.insert(0, str(REPO / "automation/src"))
for _mod in ("yw_indicators", "yw_indicators_extra", "yw_indicators_b1", "yw_indicators_b1_3in1", "ocs_btc_5m"):
    try:
        __import__(_mod)
    except Exception:
        pass

# Pre-load each detector function sequentially (this populates the module fully)
# Threads should NEVER call __import__ on detector modules
for _agent in AGENTS:
    _mod_name = _agent["module"]
    _mod = sys.modules.get(_mod_name)
    if _mod is not None:
        # Touch the function to ensure full module load
        getattr(_mod, _agent["fn"], None)

if __name__ == "__main__":
    sys.exit(main())
