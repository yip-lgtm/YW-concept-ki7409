#!/usr/bin/env python3
"""LLM iteration for the TTrades family, on the deep five-minute history.

Same discipline as llm_iterate_50d.py: a tuning window, a held-back
validation window, and nothing selected on the validation window.

The family has its own levers rather than the main book's:

  t2_r              the R multiple the position closes at
  t1_reduce         the fraction taken at T1
  max_bars_held     how long the position is held before it is abandoned
  cooldown_hours    how long the same setup is blocked after it closes
  stop_mult         the stop distance as a multiple of ATR

The window is longer than the main book's 50 days on purpose. The
TTrades family trades far less often — over thirteen months of real
five-minute history the Fractal model produced 233 trades and L13
produced 66, while L12 and L14 produced none at all on BTC. A 50-day
window would hold a handful of trades and any profit factor computed
from it would be noise.

What this cannot do: the live family trades mostly MGC and MNQ, and the
deep history covers BTC only, so this measures the family on an
instrument it rarely trades. Argon-Gold is not here at all — GC=F has
no five-minute history from any source available here, and it has
never produced a live trade to fall back on.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "automation" / "scripts"))
sys.path.insert(0, str(REPO / "automation" / "src"))

import importlib.util
import types as _types

# ttrades_btc imports requests at module level and none of the detection
# logic uses it. A minimal stub lets this run where requests is not
# installed; in CI the real one is there and this is skipped.
if "requests" not in sys.modules:
    _stub = _types.ModuleType("requests")
    _stub.post = lambda *a, **k: None
    _stub.get = lambda *a, **k: None
    _stub.exceptions = _types.SimpleNamespace(
        HTTPError=Exception, Timeout=Exception, RequestException=Exception)
    sys.modules["requests"] = _stub
if "yfinance" not in sys.modules:
    # Same for yfinance: the deep history comes from the repository, so
    # nothing here ever calls it.
    _yf = _types.ModuleType("yfinance")

    def _no_download(*a, **k):
        raise RuntimeError("yfinance stub: this backtest reads the repository")

    _yf.download = _no_download
    sys.modules["yfinance"] = _yf

_spec = importlib.util.spec_from_file_location(
    "tts", str(REPO / "automation" / "scripts" / "ttrades_l_strategies.py"))
tts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tts)

_iter_spec = importlib.util.spec_from_file_location(
    "iter50", str(REPO / "automation" / "scripts" / "llm_iterate_50d.py"))
it50 = importlib.util.module_from_spec(_iter_spec)
_iter_spec.loader.exec_module(it50)

OUT_DIR = REPO / "automation" / "reports" / "llm_iteration_ttrades"

AGENTS = ["TTrades-Fractal", "TTrades-L12", "TTrades-L13", "TTrades-L14"]

LEVERS = {
    "t2_r":           {"min": 1.0, "max": 3.0, "step": 0.01,
                       "why": "R multiple the position closes at"},
    "t1_reduce":      {"min": 0.0, "max": 1.0, "step": 0.1,
                       "why": "fraction of the position taken at T1"},
    "max_bars_held": {"min": 8, "max": 96, "step": 8,
                       "why": "bars the position is held before it is abandoned"},
    "cooldown_hours": {"min": 0, "max": 24, "step": 1,
                       "why": "hours the same setup is blocked after it closes"},
    "stop_mult":      {"min": 0.8, "max": 3.0, "step": 0.05,
                       "why": "stop distance as a multiple of ATR"},
}

T1_R = 1.0
FORWARD = 96


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def metrics(rs):
    n = len(rs)
    if n == 0:
        return None
    w = [r for r in rs if r > 0]
    l = [r for r in rs if r < 0]
    nw, nl = len(w), len(l)
    gw, gl = sum(w), abs(sum(l))
    pf = gw / gl if gl > 0 else (10.0 if gw > 0 else 0.0)
    aw = (gw / nw) if nw else 0.0
    al = (gl / nl) if nl else 0.0
    rr = aw / al if al > 0 else (10.0 if aw > 0 else 0.0)
    decided = nw + nl
    lo, hi = wilson(nw, decided) if decided else (0.0, 1.0)
    return {"n": n, "wins": nw, "losses": nl, "wr": nw / decided if decided else 0.0,
            "pf": pf, "rr": rr, "avg_win_R": aw, "avg_loss_R": al,
            "total_R": sum(rs), "avg_R": sum(rs) / n,
            "pf_lo": (lo * 1.618 / (1 - lo)) if lo < 1 else 99.0,
            "pf_hi": (hi * 1.618 / (1 - hi)) if hi < 1 else 99.0}


def detect(agent, h4, m15):
    if agent == "TTrades-L12":
        return tts.detect_l12(h4, m15)
    if agent == "TTrades-L13":
        return tts.detect_l13(h4, m15)
    if agent == "TTrades-L14":
        return tts.detect_l14(h4, m15)
    return None


def run_agent(df, agent, cfg, start, end):
    import pandas as pd
    from ttrades_btc import detect_c2_closure, detect_c3_closure, check_cisd
    h4 = df.resample("4h").agg({"Open": "first", "High": "max", "Low": "min",
                                 "Close": "last"}).dropna()
    m15 = df.resample("15min").agg({"Open": "first", "High": "max", "Low": "min",
                                   "Close": "last"}).dropna()
    prev = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - prev).abs(),
                    (df["Low"] - prev).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=5).mean().fillna(0.0).to_numpy()

    t2_r = float(cfg.get("t2_r", 1.618))
    t1_reduce = float(cfg.get("t1_reduce", 0.5))
    max_bars = int(cfg.get("max_bars_held", FORWARD))
    cool = float(cfg.get("cooldown_hours", 4))
    stop_mult = float(cfg.get("stop_mult", 1.6))

    rs = []
    last_exit = {}
    for idx in range(200, len(df) - FORWARD - 2, 3):
        ts = df.index[idx]
        if ts < start or ts > end:
            continue
        # The frames must match what the live path gives the detector:
        # ttrades_l_strategies.main() builds H4 from 30 days of hourly
        # bars (180 H4 bars) and M15 from 7 days of fifteen-minute bars
        # (672 M15 bars). A shorter H4 frame makes find_htf_poi search a
        # different set of pivots, which changes the number of trades
        # outright — L12 produced 0 trades on a full frame and 81 on a
        # truncated one.
        w4 = h4[h4.index <= ts].iloc[-180:]
        w15 = m15[m15.index <= ts].iloc[-672:]
        if len(w4) < 4 or len(w15) < 30:
            continue
        try:
            if agent == "TTrades-Fractal":
                swing = detect_c2_closure(w4)
                if not swing:
                    swing = detect_c3_closure(w4)
                if not swing:
                    continue
                direction = swing["direction"]
                cisd = check_cisd(w15, direction)
                if not cisd.get("confirmed"):
                    continue
            else:
                det = detect(agent, w4, w15)
                if not det.get("fired"):
                    continue
                direction = det["direction"]
        except Exception:
            continue
        if direction not in ("long", "short"):
            continue
        key = (agent, ts.floor("4h"))
        if cool > 0:
            prev_exit = last_exit.get((agent, direction))
            if prev_exit is not None and (ts - prev_exit).total_seconds() / 3600.0 < cool:
                continue
        a = float(atr[idx])
        if a <= 0:
            continue
        entry = float(df.iloc[idx + 1]["Close"])
        sign = 1 if direction == "long" else -1
        risk = a * stop_mult
        sl = entry - sign * risk
        t1 = entry + sign * risk * T1_R
        t2 = entry + sign * risk * t2_r
        exit_price = None
        t1_hit = False
        for _, bar in df.iloc[idx + 2: idx + 2 + max_bars].iterrows():
            hi, lo = float(bar["High"]), float(bar["Low"])
            if direction == "long":
                if lo <= sl:
                    exit_price = sl
                    break
                if hi >= t1:
                    t1_hit = True
                if hi >= t2:
                    exit_price = t2
                    break
            else:
                if hi >= sl:
                    exit_price = sl
                    break
                if lo <= t1:
                    t1_hit = True
                if lo <= t2:
                    exit_price = t2
                    break
        if exit_price is None:
            continue
        rs.append(sign * (exit_price - entry) / risk)
        last_exit[(agent, direction)] = ts
    return metrics(rs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", nargs="*", default=AGENTS)
    ap.add_argument("--iterations", type=int, default=8)
    ap.add_argument("--target-pf", type=float, default=1.2)
    ap.add_argument("--target-rr", type=float, default=1.5)
    ap.add_argument("--tune-days", type=int, default=270)
    ap.add_argument("--validate-days", type=int, default=120)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = it50.load_deep()
    end = df.index[-1]
    val_start = end - timedelta(days=args.validate_days)
    tune_start = val_start - timedelta(days=args.tune_days)
    print(f"deep 5m {len(df)} bars, {df.index[0].date()} → {end.date()}")
    print(f"TUNE      {tune_start.date()} → {val_start.date()}  ({args.tune_days}d)")
    print(f"VALIDATE  {val_start.date()} → {end.date()}  ({args.validate_days}d)")
    print("note: the family trades mostly MGC and MNQ; this measures it on BTC\n")

    results = {}
    for agent in args.agents:
        print(f"=== {agent} ===", flush=True)
        base = {"t2_r": 1.618, "t1_reduce": 0.5, "max_bars_held": FORWARD,
                "cooldown_hours": 4, "stop_mult": 1.6}
        cfg = dict(base)
        m = run_agent(df, agent, cfg, tune_start, val_start)
        if not m:
            print("  no trades on the tuning window", flush=True)
            results[agent] = {"status": "no_trades"}
            continue
        best = (m["pf"], dict(cfg), m)
        history = []
        print(f"  baseline: n={m['n']} (W{m['wins']}/L{m['losses']}) "
              f"WR={100*m['wr']:.1f}% PF={m['pf']:.2f} RR={m['rr']:.2f}", flush=True)
        for i in range(args.iterations):
            prompt = it50.build_prompt(agent, m, cfg, history,
                                       args.target_pf, args.target_rr)
            text, err = it50.call_llm(prompt)
            if err:
                print(f"  iter {i+1}: LLM error: {err}", flush=True)
                break
            new_cfg = it50.parse_config(text)
            if not new_cfg:
                text2, err2 = it50.call_llm(
                    prompt + "\n\nReply with the JSON object only.",
                    max_tokens=600)
                new_cfg = it50.parse_config(text2) if not err2 else None
            if not new_cfg:
                print(f"  iter {i+1}: no JSON in the reply — skipping", flush=True)
                continue
            cand = dict(cfg)
            cand.update(new_cfg)
            cm = run_agent(df, agent, cand, tune_start, val_start)
            if cm is None:
                continue
            history.append({"cfg": new_cfg, "m": cm})
            hit = cm["pf"] >= args.target_pf and cm["rr"] >= args.target_rr
            print(f"  iter {i+1}: {new_cfg} -> n={cm['n']} "
                  f"PF={cm['pf']:.2f} RR={cm['rr']:.2f} WR={100*cm['wr']:.1f}%"
                  f"{'  ← TARGET MET' if hit else ''}", flush=True)
            if cm["pf"] > best[0]:
                best = (cm["pf"], dict(cand), cm)
                cfg = dict(cand)
                m = cm
                if hit:
                    break
        vm = run_agent(df, agent, best[1], val_start, end)
        bmv = run_agent(df, agent, base, val_start, end)
        print(f"  BEST: {best[1]}")
        print(f"    tune     PF={best[2]['pf']:.2f} RR={best[2]['rr']:.2f} n={best[2]['n']}")
        if vm:
            print(f"    validate PF={vm['pf']:.2f} n={vm['n']} "
                  f"(baseline PF={bmv['pf']:.2f} n={bmv['n']})", flush=True)
        results[agent] = {"baseline_tune": m, "best_cfg": best[1],
                           "best_tune": best[2], "best_validate": vm,
                           "baseline_validate": bmv, "history": history,
                           "tune_met": bool(best[2]["pf"] >= args.target_pf
                                            and best[2]["rr"] >= args.target_rr),
                           "target_met": bool(vm and vm["pf"] >= args.target_pf
                                              and vm["rr"] >= args.target_rr)}
        dest = OUT_DIR / "results.json"
        merged = {}
        if dest.exists():
            try:
                merged = json.loads(dest.read_text())
            except Exception:
                merged = {}
        merged.update(results)
        dest.write_text(json.dumps(merged, indent=2, default=str))
    print(f"\nwrote {OUT_DIR / 'results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
