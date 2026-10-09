#!/usr/bin/env python3
"""Data-driven weight optimizer — PF/WR/RR decide, LLM only sanity-checks.

User directive (2026-10-08, option B): stop relying on the LLM to *decide*
param changes. The LLM has been grading its own suggestions D/C almost
100% of the time (all-time: 396×D, 74×C, 3×B, 0×A) because 7d live samples
are thin. So the decision is made from the trades themselves, with a
Bayesian shrinkage factor, and the LLM is only asked to veto nonsense.

WHAT weight ACTUALLY DOES
  In live_scan.py, at signal build time:
      conf = round(llm_confidence * weight)
  A higher weight makes a strategy easier to fire; a lower weight demands
  more confluence. So weight is "how much do we trust this strategy right
  now", and it should be a direct function of realised edge — not a guess.

THE MODEL
  1. Edge index, normalised so 1.0 = "meets all three expectations":

      edge = (PF / 1.00) × (WR / 0.45) × (RR / 1.00)

      PF normalises against break-even. WR normalises against 0.45 because
      most of these strategies are low-win-rate / high-RR, and 0.45 is a
      realistic "healthy" WR for that profile (a 0.50 bar would put every
      good RR strategy below the line — see the settlement work). RR
      normalises against break-even.

  2. Raw target weight, linear around edge = 1.0:

      raw = 1.0 + (edge - 1.0) * EDGE_SCALE        EDGE_SCALE = 0.60

  3. Bayesian shrinkage toward 1.0 (no opinion) by sample size:

      shrink = n / (n + PRIOR_STRENGTH)           PRIOR_STRENGTH = 20
      weight = 1.0 + (raw - 1.0) * shrink

      n=0   -> shrink 0.00 -> weight exactly 1.00   (never guesses)
      n=5   -> shrink 0.20
      n=20  -> shrink 0.50
      n=50  -> shrink 0.71
      n=200 -> shrink 0.91

  This is why a thin-sample strategy cannot be punished or rewarded on
  noise: at n=5 the optimiser can move weight by at most ±0.06 no matter
  how good or bad the ratio looks.

GUARDRAILS (numeric; the LLM cannot widen any of these)
  - MIN_TRADES_TO_ACT = 5     below this, weight is pinned to 1.0
  - WEIGHT_BOUNDS = [0.40, 1.80]
  - MAX_DELTA_PER_CYCLE = 0.20
  - COOLDOWN_DAYS = 5         one change per strategy per 5 days
  - Hard floor so no strategy is ever silenced entirely (0.40 still fires)

LLM SANITY CHECK
  Only invoked when |Δweight| >= LLM_VETO_THRESHOLD (0.10). It is asked to
  answer ONE question: "does a weight of X make sense for a strategy with
  this character and these metrics?" It may return AGREE or VETO. A VETO
  blocks that cycle's change and is recorded. It cannot propose numbers.

OUTPUT
  automation/config/weight_overrides.json
  automation/reports/weight_optimization/weight_<date>.{json,md}
"""
from __future__ import annotations
import os
import sys
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

OUT_DIR = REPO / "automation/reports/weight_optimization"
OVERRIDES_FILE = REPO / "automation/config/weight_overrides.json"

# ---- Model constants --------------------------------------------------------
WINDOW_DAYS = 14
PRIOR_STRENGTH = 20.0
EDGE_SCALE = 0.60
WR_REFERENCE = 0.45
MIN_TRADES_TO_ACT = 10
WEIGHT_MIN, WEIGHT_MAX = 0.40, 1.80
MAX_DELTA_PER_CYCLE = 0.20
COOLDOWN_DAYS = 5
LLM_VETO_THRESHOLD = 0.10

TRADE_SOURCES = [
    ("automation/reports/live_scan/trades.jsonl", None),      # strategy field present
    ("automation/reports/ocs_btc_5m/trades.jsonl", "OCS-BTC-5m"),  # no strategy field
    # TTrades family (2026-10-09). ttrades_tracker.py is what makes this row
    # useful: before it existed the family wrote signals only, so there was
    # never a closed trade and therefore never a PF / WR / RR to score.
    ("automation/reports/ttrades_btc/trades.jsonl", None),    # strategy field present
]

STRATEGY_CHARACTER = {
    "H-Pattern":      "Structural reversal. Moderate WR, moderate RR.",
    "3-Pushes":       "Exhaustion reversal, counter-trend. Low WR is fine if RR is high.",
    "Two-Yang":       "Candle pattern, thin sample typical.",
    "RSI-Div":        "Mean reversion, higher WR expected, thin RR. Judge on PF.",
    "50-20-Pullback": "High-RR trend pullback. Low WR is BY DESIGN; RR is the edge.",
    "Stair":          "Trend continuation. Needs momentum.",
    "B1":             "Multi-indicator confluence, balanced profile.",
    "B1-3in1":        "Multi-asset combined, diversified.",
    "Kell-Cycle":     "Cycle-based, volatile. Low WR / high RR is normal.",
    "CRT":            "High-RR range reversal with T2 (1.618R) close. WR naturally moderate.",
    "OCS-BTC-5m":     "ML/kNN based, BTC 24/7. Different session profile.",
    "TTrades-Fractal": "ICT Fractal Model (C1-C4 candle structure). Original model is BTC-native; MNQ/MGC are an extrapolation. Runs on 3 tickers.",
    "TTrades-L12":     "Strictest entry: C2 sweep+reclaim AT an HTF POI, then paired-TF CISD. Never enters on the C2 close.",
    "TTrades-L13":     "Expansion candles only; entry at the C3 continuation order block; target >= 2R. Does not chase a swept target.",
    "TTrades-L14":     "Two closures: C2 sweep+reclaim, or no sweep with C3 closing beyond the C2 BODY (which then only trades C4). No subjective fill."
}


def log(msg: str):
    print(f"[weight-opt] {msg}", flush=True)


def parse_ts(ts: str):
    if not ts:
        return None
    try:
        ts = ts.replace("Z", "+00:00").replace(" ", "T")
        d = datetime.fromisoformat(ts)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return None


def load_trades(window_days: int) -> dict[str, list[dict]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    by: dict[str, list[dict]] = {}
    for rel, force_name in TRADE_SOURCES:
        p = REPO / rel
        if not p.exists():
            continue
        try:
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if not line or line[0] in "<=>":
                        continue
                    try:
                        t = json.loads(line)
                    except Exception:
                        continue
                    if t.get("status") != "closed":
                        continue
                    et = parse_ts(t.get("exit_time", ""))
                    if not et or et < cutoff:
                        continue
                    name = force_name or t.get("strategy")
                    if not name:
                        continue
                    by.setdefault(name, []).append(t)
        except Exception:
            continue
    return by


def metrics_of(trades: list[dict]) -> dict:
    n = len(trades)
    if n == 0:
        return {"n": 0, "pf": 0.0, "wr": 0.0, "rr": 0.0,
                "total_r": 0.0, "pnl": 0.0, "avg_win": 0.0, "avg_loss": 0.0}
    R = [float(t.get("R_multiple", 0) or 0) for t in trades]
    wins = [r for r in R if r > 0]
    losses = [r for r in R if r <= 0]
    gw = sum(wins)
    gl = abs(sum(losses))
    pf = gw / gl if gl > 0 else (10.0 if gw > 0 else 0.0)
    aw = gw / len(wins) if wins else 0.0
    al = gl / len(losses) if losses else 0.0
    rr = aw / al if al > 0 else (10.0 if aw > 0 else 0.0)
    return {
        "n": n,
        "pf": round(pf, 3),
        "wr": round(len(wins) / n, 4),
        "rr": round(rr, 3),
        "total_r": round(sum(R), 3),
        "pnl": round(sum(float(t.get("pnl_usd", 0) or 0) for t in trades), 2),
        "avg_win": round(aw, 3),
        "avg_loss": round(al, 3),
    }


def target_weight(m: dict) -> tuple[float, dict]:
    """Return (target_weight, explanation dict). Shrinks to exactly 1.0 at n=0."""
    n = m["n"]
    if n < MIN_TRADES_TO_ACT:
        return 1.0, {"skipped": f"n={n} < MIN_TRADES_TO_ACT={MIN_TRADES_TO_ACT}"}

    pf_c = min(max(m["pf"], 0.0), 3.0) / 1.00
    wr_c = min(max(m["wr"], 0.0), 0.95) / WR_REFERENCE
    rr_c = min(max(m["rr"], 0.0), 4.0) / 1.00
    edge = pf_c * wr_c * rr_c

    raw = 1.0 + (edge - 1.0) * EDGE_SCALE
    raw = min(max(raw, WEIGHT_MIN), WEIGHT_MAX)

    shrink = n / (n + PRIOR_STRENGTH)
    final = 1.0 + (raw - 1.0) * shrink

    # HARD RULE 1 — a strategy that is net losing (PF < 1.0) may never be
    # up-weighted above neutral, no matter how good its RR looks.
    #
    # HARD RULE 2 — being net losing is not merely "not above neutral", it is
    # an active downgrade proportional to the shortfall. Without this, a
    # high-RR profile can mask a losing PF inside the multiplicative index:
    # 50-20-Pullback at n=88, PF 0.80, RR 1.62 scores edge 0.95 and would sit
    # within 0.03 of neutral while bleeding money on the largest sample in the
    # book. Losing money has to cost trust.
    if m["pf"] < 1.0:
        final = min(final, 1.0)
        final *= max(0.5, m["pf"])   # PF 0.80 -> x0.80 ; PF 0.60 -> x0.60

    final = round(min(max(final, WEIGHT_MIN), WEIGHT_MAX), 3)

    return final, {
        "pf_component": round(pf_c, 3),
        "wr_component": round(wr_c, 3),
        "rr_component": round(rr_c, 3),
        "edge_index": round(edge, 3),
        "raw_weight": round(raw, 3),
        "shrink": round(shrink, 3),
        "losing_penalty_applied": m["pf"] < 1.0,
    }


def current_weights() -> dict[str, float]:
    """Read effective weight from live_scan.py, layered with any override."""
    src = (REPO / "automation/scripts/live_scan.py").read_text()
    out: dict[str, float] = {}
    m = re.search(r"^STRATEGIES\s*=\s*\{(.*?)^\}", src, re.DOTALL | re.MULTILINE)
    if m:
        for line in m.group(1).splitlines():
            nm = re.match(r'\s*"([^"]+)"\s*:\s*\{', line)
            if not nm:
                continue
            w = re.search(r'"weight"\s*:\s*([0-9.]+)', line)
            if w:
                out[nm.group(1)] = float(w.group(1))
    if OVERRIDES_FILE.exists():
        try:
            data = json.loads(OVERRIDES_FILE.read_text())
            for k, v in data.items():
                if k.startswith("_") or not isinstance(v, dict):
                    continue
                if isinstance(v.get("weight"), (int, float)):
                    out[k] = float(v["weight"])
        except Exception:
            pass
    return out


def load_overrides() -> dict:
    if not OVERRIDES_FILE.exists():
        return {}
    try:
        return json.loads(OVERRIDES_FILE.read_text())
    except Exception:
        return {}


def on_cooldown(entry: dict, days: int = COOLDOWN_DAYS) -> bool:
    ts = (entry or {}).get("last_changed")
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= datetime.now(timezone.utc) - timedelta(days=days)
    except Exception:
        return False


def llm_sanity_check(name: str, m: dict, proposed: float) -> dict:
    """Ask the LLM only one question: does this weight make sense? It may veto."""
    key = os.environ.get("MINIMAX_API_KEY", "")
    if not key:
        return {"llm": "skipped (no key)"}

    char = STRATEGY_CHARACTER.get(name, "Unknown strategy character.")
    prompt = f"""A trading system recalculated the confidence weight for one strategy from its realised performance. Your ONLY job is to sanity-check whether the number is plausible for this type of strategy. You may VETO if it is implausible. You cannot propose a different number.

STRATEGY: {name}
Character: {char}

Realised performance (14d):
  n      = {m['n']} trades
  PF     = {m['pf']}          (1.0 = break-even)
  WR     = {m['wr']*100:.1f}%       (0.45 is a healthy baseline for this profile)
  RR     = {m['rr']}          (1.0 = break-even)
  Total  = {m['total_r']:+.2f}R  /  ${m['pnl']:+,.0f}

PROPOSED NEW WEIGHT: {proposed}
  (weight multiplies signal confidence; 1.0 = neutral, >1 = fires more readily, <1 = needs more confluence)

Question: is {proposed} plausible for a strategy of this character with these numbers?

Answer in EXACTLY this format, nothing else:
VERDICT: AGREE
or
VERDICT: VETO
REASON: <max 15 words>"""

    try:
        r = requests.post(
            "https://api.minimax.io/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": "MiniMax-M3",
                "max_tokens": 300,
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content":
                     "You sanity-check trading strategy confidence weights. You may only "
                     "AGREE or VETO. You never propose numbers."},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=45,
        )
        text = r.json()["choices"][0]["message"]["content"]
        m2 = re.search(r"VERDICT:\s*(AGREE|VETO)", text, re.IGNORECASE)
        rm = re.search(r"REASON:\s*(.+)", text)
        verdict = (m2.group(1).upper() if m2 else "AGREE")
        return {
            "llm": verdict,
            "llm_reason": (rm.group(1).strip()[:150] if rm else ""),
        }
    except Exception as e:
        return {"llm": f"error: {type(e).__name__}"}


def main() -> int:
    now = datetime.now(timezone.utc)
    HKT = timezone(timedelta(hours=8))
    day = datetime.now(HKT).strftime("%Y-%m-%d")

    log(f"Data-driven weight optimization — {day}")
    log(f"Window {WINDOW_DAYS}d | shrink toward 1.0 by n/(n+{int(PRIOR_STRENGTH)}) | "
        f"bounds [{WEIGHT_MIN}, {WEIGHT_MAX}] | Δcap {MAX_DELTA_PER_CYCLE}")

    trades = load_trades(WINDOW_DAYS)
    total = sum(len(v) for v in trades.values())
    log(f"Loaded {total} closed trades across {len(trades)} strategies")
    if total == 0:
        log("No trades in window — nothing to optimise")
        return 0

    cur_w = current_weights()
    overrides = load_overrides()
    overrides.setdefault("_meta", {
        "_comment": "Data-driven weight overrides. Written by weight_optimizer.py "
                    "(PF/WR/RR + Bayesian shrinkage), read by live_scan.py at import. "
                    "LLM may only VETO, never propose.",
        "created": now.isoformat(),
        "changes": 0,
    })

    candidates = []
    for name, tl in sorted(trades.items()):
        m = metrics_of(tl)
        target, why = target_weight(m)
        cur = cur_w.get(name, 1.0)
        delta = target - cur

        if "skipped" in why:
            candidates.append({"strategy": name, "metrics": m, "current": cur,
                               "target": cur, "delta": 0.0,
                               "status": "no-sample", "detail": why})
            continue
        if abs(delta) < 0.02:
            candidates.append({"strategy": name, "metrics": m, "current": cur,
                               "target": target, "delta": round(delta, 3),
                               "status": "at-target", "detail": why})
            continue
        if on_cooldown(overrides.get(name, {})):
            candidates.append({"strategy": name, "metrics": m, "current": cur,
                               "target": target, "delta": round(delta, 3),
                               "status": "cooldown",
                               "detail": {"note": f"changed within {COOLDOWN_DAYS}d"}})
            continue
        # Cap the per-cycle move
        capped = round(cur + max(-MAX_DELTA_PER_CYCLE,
                                 min(MAX_DELTA_PER_CYCLE, delta)), 3)
        capped = round(min(max(capped, WEIGHT_MIN), WEIGHT_MAX), 3)
        candidates.append({"strategy": name, "metrics": m, "current": cur,
                           "target": capped, "delta": round(capped - cur, 3),
                           "status": "candidate", "detail": why,
                           "uncapped_target": target})

    # LLM sanity check only on material changes
    to_check = [c for c in candidates
                if c["status"] == "candidate" and abs(c["delta"]) >= LLM_VETO_THRESHOLD]
    if to_check:
        log(f"LLM sanity check on {len(to_check)} material change(s) "
            f"(Δ >= {LLM_VETO_THRESHOLD})")
        with ThreadPoolExecutor(max_workers=min(4, len(to_check))) as pool:
            futs = {pool.submit(llm_sanity_check, c["strategy"], c["metrics"], c["target"]): c
                    for c in to_check}
            for fut in as_completed(futs):
                c = futs[fut]
                try:
                    c["llm_check"] = fut.result()
                except Exception as e:
                    c["llm_check"] = {"llm": f"error: {e}"}
    else:
        log("No material changes — LLM check not needed")

    # Apply
    applied = vetoed = 0
    for c in candidates:
        if c["status"] != "candidate":
            continue
        chk = c.get("llm_check", {})
        if str(chk.get("llm", "")).upper() == "VETO":
            c["status"] = "vetoed"
            vetoed += 1
            continue

        name = c["strategy"]
        entry = dict(overrides.get(name, {}))
        entry["weight"] = c["target"]
        entry["last_changed"] = now.isoformat()
        entry["reason"] = (
            f"data-driven: n={c['metrics']['n']} PF={c['metrics']['pf']} "
            f"WR={c['metrics']['wr']*100:.1f}% RR={c['metrics']['rr']} "
            f"→ edge={c['detail'].get('edge_index')} shrink={c['detail'].get('shrink')}"
        )
        entry["metrics"] = c["metrics"]
        entry["model"] = {k: v for k, v in c["detail"].items() if k != "skipped"}
        entry["llm_check"] = chk
        entry["previous_weight"] = c["current"]
        entry["changes"] = entry.get("changes", 0) + 1
        entry["history"] = (entry.get("history", []) + [{
            "date": day,
            "from": c["current"],
            "to": c["target"],
            "n": c["metrics"]["n"],
            "pf": c["metrics"]["pf"],
            "wr": c["metrics"]["wr"],
            "rr": c["metrics"]["rr"],
            "llm": chk.get("llm", "skipped"),
        }])[-20:]
        overrides[name] = entry
        c["status"] = "applied"
        applied += 1

    overrides["_meta"]["changes"] = overrides["_meta"].get("changes", 0) + applied
    overrides["_meta"]["last_run"] = now.isoformat()
    overrides["_meta"]["last_applied"] = applied
    overrides["_meta"]["window_days"] = WINDOW_DAYS

    OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    OVERRIDES_FILE.write_text(json.dumps(overrides, indent=2, ensure_ascii=False))

    # Report
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"weight_{day}.json").write_text(
        json.dumps({"date": day, "window_days": WINDOW_DAYS,
                    "candidates": candidates}, indent=2, ensure_ascii=False, default=str))

    md = [f"# Weight Optimization — {day}", "",
          f"Window **{WINDOW_DAYS}d** · shrink = n/(n+{int(PRIOR_STRENGTH)}) · "
          f"bounds [{WEIGHT_MIN}, {WEIGHT_MAX}] · Δcap {MAX_DELTA_PER_CYCLE} · "
          f"min n to act = {MIN_TRADES_TO_ACT}", "",
          "Model: `edge = (PF/1.00) × (WR/0.45) × (RR/1.00)`, then "
          "`weight = 1.0 + (edge - 1.0) × 0.60 × n/(n+20)`, with a hard cap of "
          "1.0 whenever PF < 1.0.", "",
          "**Verdict is judged against 1.0, not against the previous value.** The "
          "hardcoded weights in live_scan.py are legacy August guesses that were "
          "dead config (never read at runtime), so a move toward 1.0 can mean "
          "*removing* an arbitrary penalty rather than rewarding a loser.", "",
          "| Strategy | n | PF | WR | RR | edge | shrink | current | target | verdict | Δ | status |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]

    def verdict(t: float) -> str:
        if t > 1.05:
            return "⬆ trust"
        if t < 0.95:
            return "⬇ distrust"
        return "= neutral"

    for c in sorted(candidates, key=lambda x: -abs(x["delta"])):
        m = c["metrics"]
        # detail is normally the model-explanation dict, but a few status
        # paths carry a plain note. Coerce so the report never dies on it.
        d = c.get("detail")
        if not isinstance(d, dict):
            d = {}
        md.append(
            f"| {c['strategy']} | {m['n']} | {m['pf']:.2f} | {m['wr']*100:.1f}% | "
            f"{m['rr']:.2f} | {d.get('edge_index','—')} | {d.get('shrink','—')} | "
            f"{c['current']:.2f} | {c['target']:.2f} | {verdict(c['target'])} | "
            f"{c['delta']:+.2f} | {c['status']} |"
        )
    md += ["", f"**Applied {applied}** · vetoed {vetoed} · "
              f"at-target {sum(1 for c in candidates if c['status']=='at-target')} · "
              f"cooldown {sum(1 for c in candidates if c['status']=='cooldown')} · "
              f"no-sample {sum(1 for c in candidates if c['status']=='no-sample')}"]
    (OUT_DIR / f"weight_{day}.md").write_text("\n".join(md))

    log("")
    for c in sorted(candidates, key=lambda x: -abs(x["delta"])):
        m = c["metrics"]
        log(f"  {c['strategy']:<18} n={m['n']:<4} PF={m['pf']:<6.2f} "
            f"WR={m['wr']*100:<5.1f}% RR={m['rr']:<5.2f} "
            f"{c['current']:.2f}→{c['target']:.2f} ({c['delta']:+.2f}) {c['status']}"
            + (f" llm={c['llm_check'].get('llm')}" if c.get("llm_check") else ""))
    log("")
    log(f"Applied {applied}, vetoed {vetoed}")
    log(f"Saved → {OVERRIDES_FILE}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        print(f"[weight-opt] UNCAUGHT: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(99)
