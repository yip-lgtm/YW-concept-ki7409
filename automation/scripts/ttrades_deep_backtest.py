#!/usr/bin/env python3
"""Backtest the whole TTrades family over real five-minute history.

The family is four agents: the base Fractal model plus L12, L13 and L14.
All four publish levels and are tracked and settled, but only the base
ever had a backtest, and that one is frozen at 2026-09-01 with zero
trades. The L-series has no backtest at all, so nothing measured them
outside the live book.

This runs all four over the Polygon deep history — real five-minute bars
for BTCUSD, 13 months — resampled into the frames each agent actually
uses:

  H4     the C2/C3 closure timeframe
  M15    the paired lower timeframe for CISD and execution
  D1     the daily trend filter
  1wk    the weekly profile

Entries resolve on the M15 frame at 1.618R with the agent's own stop, so
the mechanics match what the tracker does live. The same three-sample
discipline the main book uses applies here: a strategy that only looks
good at one resolution is not good.

Usage:
    python3 automation/scripts/ttrades_deep_backtest.py
    python3 automation/scripts/ttrades_deep_backtest.py --step 4
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "automation" / "scripts"
sys.path.insert(0, str(SCRIPTS))

DEEP = REPO / "automation" / "data" / "deep_history" / "BTCUSD" / "5m"
OUT = REPO / "automation" / "reports" / "ttrades_btc" / "deep_backtest.json"

T2_R = 1.618
MAX_BARS_HELD = 96        # 96 x 5m = 8h, same as the tracker


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_deep():
    import pandas as pd
    rows = []
    for f in sorted(DEEP.glob("*.csv")):
        with f.open() as fh:
            for r in csv.DictReader(fh):
                if r.get("ts") and r.get("close"):
                    rows.append((int(r["ts"]), float(r["open"]), float(r["high"]),
                                 float(r["low"]), float(r["close"])))
    rows.sort()
    idx = pd.DatetimeIndex([pd.Timestamp(t, unit="ms", tz="UTC") for t, *_ in rows])
    return pd.DataFrame({"Open": [x[1] for x in rows], "High": [x[2] for x in rows],
                         "Low": [x[3] for x in rows], "Close": [x[4] for x in rows]},
                        index=idx)


def resample(df, rule):
    return df.resample(rule).agg({"Open": "first", "High": "max", "Low": "min",
                                  "Close": "last"}).dropna()


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def pf_from_wr(wr):
    if wr >= 1.0:
        return float("inf")
    return wr * T2_R / (1 - wr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=2,
                    help="evaluate every Nth H4 bar (default 2)")
    args = ap.parse_args()

    if not DEEP.exists():
        print(f"no deep history at {DEEP}", file=sys.stderr)
        return 1

    base = load("ttrades_btc", SCRIPTS / "ttrades_btc.py")
    lser = load("ttrades_l_strategies", SCRIPTS / "ttrades_l_strategies.py")

    df = load_deep()
    h1 = resample(df, "1h")
    h4 = resample(df, "4h")
    m15 = resample(df, "15min")
    d1 = resample(df, "1D")
    wk = resample(df, "1W")
    print(f"deep 5m bars {len(df)} ({df.index[0].date()} → {df.index[-1].date()})")
    print(f"frames: H1 {len(h1)}  H4 {len(h4)}  M15 {len(m15)}  D1 {len(d1)}  1wk {len(wk)}")

    trades = []
    rejected = defaultdict(int)

    for i in range(60, len(h4) - 2, args.step):
        w = h4.iloc[i - 3: i + 1]          # C1..C4
        if len(w) < 4:
            continue
        # M15 up to the H4 bar's close is what the detector may see. The
        # forward walk needs the bars AFTER it, so keep the full frame too.
        m_full = m15
        m = m_full[m_full.index <= w.index[-1]]
        if len(m) < 30:
            continue
        d = d1[d1.index <= w.index[-1]]
        # The base sizes its stop off a 1h ATR: mean of the last 14 hourly
        # ranges. Same formula as ttrades_btc.py, so the stop is the live one.
        atr = float((h1["High"].tail(14) - h1["Low"].tail(14)).mean())

        # --- base Fractal ---------------------------------------------------
        try:
            swing = base.detect_c2_closure(w)
            if not swing:
                swing = base.detect_c3_closure(w)
            if swing:
                bias = base.check_d1_trend(d, swing["direction"])
                if not bias.get("aligned"):
                    rejected["Fractal:D1 bias"] += 1
                else:
                    cisd = base.check_cisd(m, swing["direction"])
                    if not cisd.get("confirmed"):
                        rejected["Fractal:CISD"] += 1
                    else:
                        levels = base.calculate_trade_levels(swing, atr)
                        if levels is None:
                            rejected["Fractal:no levels"] += 1
                        else:
                            trades.append(("TTrades-Fractal", swing["direction"],
                                           w.index[-1], levels, m_full))
        except Exception as e:
            rejected[f"Fractal:EXC {type(e).__name__}"] += 1

        # --- L-series -------------------------------------------------------
        for name in ("TTrades-L12", "TTrades-L13", "TTrades-L14"):
            try:
                if name == "TTrades-L12":
                    r = lser.detect_l12(w, m)
                elif name == "TTrades-L13":
                    r = lser.detect_l13(w, m)
                else:
                    r = lser.detect_l14(w, m)
            except Exception as e:
                rejected[f"{name}:EXC {type(e).__name__}"] += 1
                continue
            if r.get("fired"):
                # The detectors do not carry levels; the live path attaches
                # them here too, using each agent's own documented stop.
                lser._attach_levels(r, w)
                if not r.get("has_levels"):
                    rejected[f"{name}:no levels"] += 1
                    continue
                trades.append((name, r.get("direction"), w.index[-1], r, m_full))
            else:
                rejected[f"{name}:{str(r.get('stage'))[:34]}"] += 1

    # --- resolve the outcomes on M15 ---------------------------------------
    out = defaultdict(list)
    for name, direction, ts, payload, m in trades:
        entry = payload.get("entry")
        sl = payload.get("sl")
        t2 = payload.get("t2_close") or payload.get("t2")
        if entry is None or sl is None or t2 is None:
            continue
        entry, sl, t2 = float(entry), float(sl), float(t2)
        risk = abs(entry - sl)
        if risk <= 0:
            continue
        fwd = m.loc[m.index > ts][:MAX_BARS_HELD]
        exit_price = None
        level = None
        for _, bar in fwd.iterrows():
            hi, lo = float(bar["High"]), float(bar["Low"])
            if direction == "short":
                if hi >= sl:
                    exit_price, level = sl, "SL"
                    break
                if lo <= t2:
                    exit_price, level = t2, "T2"
                    break
            else:
                if lo <= sl:
                    exit_price, level = sl, "SL"
                    break
                if hi >= t2:
                    exit_price, level = t2, "T2"
                    break
        if exit_price is None:
            continue
        sign = 1 if direction == "long" else -1
        R = sign * (exit_price - entry) / risk
        out[name].append({"ts": str(ts), "direction": direction,
                          "entry": entry, "sl": sl, "t2": t2,
                          "exit": exit_price, "level": level, "R": R})

    print(f"\n{len(trades)} signals, {sum(len(v) for v in out.values())} resolved trades")
    print(f"\n{'strategy':16} {'n':>5} {'wins':>5} {'WR%':>6} {'PF':>6} {'PF 95% CI':>15} {'totalR':>9}  verdict")
    summary = {}
    for name in sorted(out):
        rows = out[name]
        w = sum(1 for r in rows if r["R"] > 0)
        n = len(rows)
        tot = sum(r["R"] for r in rows)
        lo, hi = wilson(w, n)
        pf = pf_from_wr(w / n) if n else 0
        plo, phi = pf_from_wr(lo), pf_from_wr(hi)
        v = ("PF>1 significant" if plo > 1 else
             "PF<1 significant" if phi < 1 else "indistinguishable from 1")
        pfs = "inf" if pf == float("inf") else f"{pf:.2f}"
        print(f"{name:16} {n:>5} {w:>5} {100*w/n:>5.1f}% {pfs:>6} "
              f"[{plo:>5.2f},{phi:>5.2f}] {tot:>+9.2f}  {v}")
        summary[name] = {"n": n, "wins": w, "pf": pf, "total_r": tot,
                         "pf_lo": plo, "pf_hi": phi, "verdict": v}

    print("\ntop rejection reasons:")
    for k, v in sorted(rejected.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {v:6d}  {k}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"generated_at": str(h4.index[-1]), "step": args.step,
                                "summary": summary,
                                "rejected": dict(rejected)}, indent=2, default=str))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
