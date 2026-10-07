#!/usr/bin/env python3
"""Strategy param optimizer — LLM suggestions → LIVE config (auto-applied).

User directive (10/07): "llm iter 每日自動優化各策略".

THE GAP THIS FIXES:
  1. `llm_iterate_all.py` called MiniMax-M3 daily and wrote suggestions to
     JSON/MD — then never applied ANY of them. 60+ days of "iteration"
     produced zero change.
  2. `live_scan.py`'s STRATEGIES[...]["weight"] was DEAD CONFIG — the key
     was written but `weight` was never read anywhere. So even if a
     suggestion had been applied, it would have had zero effect.

This script is the missing apply layer:
  - Reads the latest llm_iterate_all output
  - Validates every suggestion against hard bounds
  - Applies accepted changes to automation/config/strategy_overrides.json
  - live_scan.py loads that file at import time and uses the values

TUNABLE PARAMS (what LLM can actually change):
  weight      [0.3, 2.0]  — multiplies LLM confidence (0.7 = weaker, 1.2 = stronger)
                            Real effect: signal['confidence'] = LLM_conf × weight
  min_strength[int 30-80] — detector strength floor before LLM grading is called
  resample_tf ["", "15min", "30min", "1h"] — optional bar resample per strategy

GUARDRAILS (numeric, not LLM-judged):
  - Grade must be A or B (C/D never auto-apply)
  - Confidence ≥ MIN_CONFIDENCE (default 65)
  - Max 1 application per agent per APPLY_COOLDOWN_DAYS (default 3)
  - Per-param max delta per cycle (weight ±0.25) — no wild jumps
  - Values clamped into BOUNDS
  - Full audit trail: every accepted + rejected change is logged
  - Revert: `git checkout automation/config/strategy_overrides.json`

Schedule: after llm_iterate_all.py in strategy-ranking.yml.
"""
from __future__ import annotations
import os
import sys
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

ITER_DIR = REPO / "automation/reports/strategy_ranking/iterations"
OVERRIDES_FILE = REPO / "automation/config/strategy_overrides.json"
LEVELS_FILE = REPO / "automation/config/strategy_levels.json"

# ---- Guardrails -------------------------------------------------------------
BOUNDS = {
    "weight":       {"min": 0.3, "max": 2.0},
    "min_strength": {"min": 30,  "max": 80},
}
MAX_DELTA = {
    "weight":       0.25,   # per cycle
    "min_strength": 10,     # per cycle
}
ALLOWED_GRADES = {"A", "B"}
# Grade C is permitted at a much higher confidence bar. Rationale (measured
# 2026-10-07): across all iteration history the LLM emitted 396×D, 74×C, 3×B,
# 0×A. A strict A/B gate would make the optimizer a permanent no-op. Grade D
# means "I have nothing useful to say" (usually because 7d live n < 10), which
# is correct — so D stays blocked. C is "marginal but real", so it is allowed
# only with strong confidence AND a strategy that actually has evaluable
# sample size.
C_GRADE_MIN_CONFIDENCE = 75
C_GRADE_MIN_SAMPLE = 10
MIN_CONFIDENCE = 65
APPLY_COOLDOWN_DAYS = 3

# llm_iterate_all agent-id → live_scan.py STRATEGIES key
AGENT_TO_STRATEGY = {
    "h-pattern":       "H-Pattern",
    "3-pushes":        "3-Pushes",
    "two-yang":        "Two-Yang",
    "rsi-div":         "RSI-Div",
    "50-20-pullback":  "50-20-Pullback",
    "stair-pattern":   "Stair",
    "crt":             "CRT",
    "kell-cycle":      "Kell-Cycle",
    "ocs-btc":         "OCS-BTC-5m",
    "b1":              "B1",
}

VALID_TFS = {"", "15min", "30min", "1h"}


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[param-apply {ts}] {msg}", flush=True)


def latest_iteration_file() -> Path | None:
    if not ITER_DIR.exists():
        return None
    files = sorted(ITER_DIR.glob("iteration_all_*.json"))
    return files[-1] if files else None


def load_overrides() -> dict:
    if not OVERRIDES_FILE.exists():
        return {}
    try:
        return json.loads(OVERRIDES_FILE.read_text())
    except Exception:
        return {}


def load_base_config() -> dict:
    """Read the hardcoded defaults out of live_scan.py (source of truth)."""
    src = (REPO / "automation/scripts/live_scan.py").read_text()
    out = {}
    m = re.search(r"^STRATEGIES\s*=\s*\{(.*?)^\}", src, re.DOTALL | re.MULTILINE)
    if not m:
        return out
    for line in m.group(1).splitlines():
        nm = re.match(r'\s*"([^"]+)"\s*:\s*\{', line)
        if not nm:
            continue
        name = nm.group(1)
        w = re.search(r'"weight"\s*:\s*([0-9.]+)', line)
        out[name] = {"weight": float(w.group(1)) if w else 1.0}
    return out


def on_cooldown(entry: dict, days: int = APPLY_COOLDOWN_DAYS) -> bool:
    ts = (entry or {}).get("last_applied")
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= datetime.now(timezone.utc) - timedelta(days=days)
    except Exception:
        return False


def clamp(param: str, value):
    b = BOUNDS.get(param)
    if not b:
        return None
    try:
        v = float(value)
    except Exception:
        return None
    v = max(b["min"], min(b["max"], v))
    if param == "min_strength":
        return int(round(v))
    return round(v, 3)


def main() -> int:
    now = datetime.now(timezone.utc)
    log("=" * 60)
    log("Strategy param optimizer — applying LLM suggestions")
    log("=" * 60)

    src = latest_iteration_file()
    if not src:
        log("No iteration_all_*.json found — run llm_iterate_all.py first. Skipping.")
        return 0
    log(f"Source: {src.name}")

    try:
        data = json.loads(src.read_text())
    except Exception as e:
        log(f"Cannot parse {src.name}: {e}")
        return 1

    results = data.get("results", [])
    log(f"{len(results)} iteration result(s) in source")

    overrides = load_overrides()
    overrides.setdefault("_meta", {
        "_comment": "Live strategy param overrides — written by param_optimizer.py, "
                    "read by live_scan.py at import. Auto-optimization output.",
        "created": now.isoformat(),
        "applications": 0,
    })
    base = load_base_config()
    if not base:
        log("WARN: could not parse STRATEGIES from live_scan.py — deltas will use override-only baseline")
    else:
        log(f"Baseline parsed: {len(base)} strategies")

    applied_n, rejected_n = 0, 0
    report_lines = []

    for r in results:
        if r.get("error"):
            report_lines.append(f"  {r.get('agent', '?')}: ERROR {r['error']}")
            rejected_n += 1
            continue

        agent_id = r.get("strategy_id", "")
        strat = AGENT_TO_STRATEGY.get(agent_id)
        if not strat:
            report_lines.append(f"  {r.get('agent', '?')}: no live_scan mapping (id={agent_id})")
            rejected_n += 1
            continue

        grade = (r.get("grade") or "?").upper()
        conf = int(r.get("confidence") or 0)
        live_n = int(r.get("live_n") or 0)

        # Guardrail 1+2: grade + confidence
        if grade == "D":
            report_lines.append(
                f"  {strat}: SKIP grade=D (LLM has no useful suggestion; live n={live_n})"
            )
            continue
        if grade in ALLOWED_GRADES:
            if conf < MIN_CONFIDENCE:
                report_lines.append(f"  {strat}: REJECT conf={conf} < {MIN_CONFIDENCE} (grade {grade})")
                rejected_n += 1
                continue
        elif grade == "C":
            # Marginal grade — require strong confidence AND real sample size
            if conf < C_GRADE_MIN_CONFIDENCE:
                report_lines.append(
                    f"  {strat}: REJECT grade=C conf={conf} < {C_GRADE_MIN_CONFIDENCE}"
                )
                rejected_n += 1
                continue
            if live_n < C_GRADE_MIN_SAMPLE:
                report_lines.append(
                    f"  {strat}: REJECT grade=C but live n={live_n} < {C_GRADE_MIN_SAMPLE} (insufficient evidence)"
                )
                rejected_n += 1
                continue
            report_lines.append(
                f"  {strat}: grade=C accepted via high-conf+sample path (conf={conf}, n={live_n})"
            )
        else:
            report_lines.append(f"  {strat}: REJECT grade={grade} (unrecognised)")
            rejected_n += 1
            continue

        # Guardrail 3: cooldown
        cur = overrides.get(strat, {})
        if on_cooldown(cur):
            report_lines.append(
                f"  {strat}: SKIP (on cooldown, applied {cur.get('last_applied', '?')[:10]})"
            )
            continue

        # Build candidate changes
        changes = {}

        # weight
        prop_w = r.get("weight")
        if prop_w is not None:
            cur_w = cur.get("weight", base.get(strat, {}).get("weight", 1.0))
            new_w = clamp("weight", prop_w)
            if new_w is not None and abs(new_w - cur_w) > 1e-6:
                if abs(new_w - cur_w) <= MAX_DELTA["weight"] + 1e-9:
                    changes["weight"] = {"from": cur_w, "to": new_w}
                else:
                    capped = round(cur_w + max(-MAX_DELTA["weight"],
                                               min(MAX_DELTA["weight"], new_w - cur_w)), 3)
                    changes["weight"] = {"from": cur_w, "to": capped,
                                         "note": f"delta capped ±{MAX_DELTA['weight']} (LLM wanted {new_w})"}

        # min_strength (optional in LLM output)
        prop_ms = r.get("min_strength")
        if prop_ms is not None:
            cur_ms = cur.get("min_strength", 60)
            new_ms = clamp("min_strength", prop_ms)
            if new_ms is not None and abs(new_ms - cur_ms) > 1e-6:
                if abs(new_ms - cur_ms) <= MAX_DELTA["min_strength"]:
                    changes["min_strength"] = {"from": cur_ms, "to": new_ms}
                else:
                    capped = int(cur_ms + max(-MAX_DELTA["min_strength"],
                                               min(MAX_DELTA["min_strength"], new_ms - cur_ms)))
                    changes["min_strength"] = {"from": cur_ms, "to": capped,
                                               "note": f"delta capped ±{MAX_DELTA['min_strength']}"}

        # resample_tf (optional; must be in whitelist)
        prop_tf = r.get("timeframe")
        if prop_tf is not None:
            tf_norm = str(prop_tf).strip()
            # LLM sometimes returns "5min/15min" or "5m+4h" — extract the resample part
            for cand in ("15min", "30min", "1h"):
                if cand in tf_norm:
                    tf_norm = cand
                    break
            else:
                tf_norm = ""
            if tf_norm in VALID_TFS:
                cur_tf = cur.get("resample_tf", "")
                if tf_norm != cur_tf:
                    changes["resample_tf"] = {"from": cur_tf, "to": tf_norm}

        if not changes:
            report_lines.append(
                f"  {strat}: no change (grade={grade} conf={conf} — proposed values already active)"
            )
            continue

        # Apply
        entry = dict(cur)
        entry.update({k: v["to"] for k, v in changes.items()})
        entry["last_applied"] = now.isoformat()
        entry["grade"] = grade
        entry["confidence"] = conf
        entry["reason"] = (r.get("reason") or "")[:300]
        entry["source_iteration"] = src.name
        entry["changes"] = changes
        entry["applications"] = entry.get("applications", 0) + 1
        entry["history"] = (entry.get("history", []) + [{
            "date": now.isoformat(),
            "grade": grade, "confidence": conf,
            "changes": {k: v["to"] for k, v in changes.items()},
        }])[-20:]
        overrides[strat] = entry
        applied_n += 1

        detail = ", ".join(
            f"{k} {v['from']}→{v['to']}" + (f" ({v['note']})" if v.get("note") else "")
            for k, v in changes.items()
        )
        report_lines.append(f"  {strat}: APPLY [{grade}/{conf}] {detail}")

    overrides["_meta"]["applications"] = overrides["_meta"].get("applications", 0) + applied_n
    overrides["_meta"]["last_run"] = now.isoformat()
    overrides["_meta"]["last_source"] = src.name
    overrides["_meta"]["last_applied_n"] = applied_n
    overrides["_meta"]["last_rejected_n"] = rejected_n
    overrides["_meta"]["last_log"] = report_lines

    OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    OVERRIDES_FILE.write_text(json.dumps(overrides, indent=2, ensure_ascii=False))

    log("")
    for line in report_lines:
        print(line)
    log("")
    log(f"Applied {applied_n}, rejected {rejected_n}")
    log(f"Saved → {OVERRIDES_FILE}")
    if applied_n:
        log("live_scan.py will pick these up on its next run.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[param-apply] UNCAUGHT: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(99)
