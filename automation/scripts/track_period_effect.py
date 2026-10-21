#!/usr/bin/env python3
"""Does each strategy still have an edge in the recent period?

CRT measured PF 1.25 [1.17, 1.34] on the first 65% of the deep history
and 0.97 [0.88, 1.08] on the last 35% — the whole-sample number of 1.15
was carried by the earlier period. That is the trap the previous
optimiser fell into: a configuration that improved the sample it was
fitted to.

This runs every strategy over both halves at all three cadences, so the
period effect can be separated from the cadence effect, and so a
strategy can be judged on the period that matters rather than the one
that flatters it.

The detector dispatch mirrors live_scan.run_detector, so each strategy
sees the same frames it sees live: the 5-minute window, a 15-minute
resample for the two that use it, an hour and a four-hour frame.

Usage:
    python3 automation/scripts/track_period_effect.py
    python3 automation/scripts/track_period_effect.py --step 3
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "automation" / "scripts"
SRC = REPO / "automation" / "src"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SRC))

import importlib.util

spec = importlib.util.spec_from_file_location(
    "swp", str(REPO / "automation" / "scripts" / "sweep_detector_params.py"))
swp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(swp)

from yw_indicators import (detect_3_pushes, detect_5020_pullback,
                           detect_h_pattern, detect_rsi_divergence,
                           detect_two_yang_one_yin)
from yw_indicators_extra import detect_crt, detect_kell_setups, detect_stair_pattern

# The live system runs every detector through live_scan._normalize_detector
# before it uses the result. Three of the detectors do not return a
# top-level "present" at all — 50-20 returns {cross_type, trend, ...},
# RSI-Div returns {type, strength, ...} and Kell-Cycle returns a dict of
# sub-setups — so a raw call sees no signal and the strategy looks dead.
# Using the live normaliser keeps the backtest and the live system in
# agreement, which is the whole point of the exercise.
_ls_spec = importlib.util.spec_from_file_location(
    "live_scan", str(SCRIPTS / "live_scan.py"))
_ls = importlib.util.module_from_spec(_ls_spec)
_ls_spec.loader.exec_module(_ls)
_normalize = _ls._normalize_detector

T2_R = 1.618
STOP_MULT = 1.6
FORWARD_BARS = 96
TRAIN_FRACTION = 0.65

STRATEGIES = ["CRT", "Two-Yang", "Stair", "50-20-Pullback", "3-Pushes",
              "Kell-Cycle", "H-Pattern", "RSI-Div"]

# The detector function name live_scan dispatches on.
_FN_OF = {"CRT": "crt", "Two-Yang": "two_yang", "Stair": "stair",
          "50-20-Pullback": "pb_5020", "3-Pushes": "3_pushes",
          "Kell-Cycle": "kell", "H-Pattern": "h_pattern", "RSI-Div": "rsi_div"}


def detect_for(name, df5, df15, df1h, df4h):
    """One detector call, with the same frames live_scan gives it."""
    if name == "CRT":
        return detect_crt(df4h, df5)
    if name == "Two-Yang":
        # Live passes the 5-minute frame; the "tf": "15m" in the config is
        # not wired to anything for this strategy.
        return detect_two_yang_one_yin(df5)
    if name == "Stair":
        return detect_stair_pattern(df5)
    if name == "50-20-Pullback":
        return detect_5020_pullback(df5)
    if name == "3-Pushes":
        return detect_3_pushes(df5)
    if name == "Kell-Cycle":
        return detect_kell_setups(df5)
    if name == "H-Pattern":
        return detect_h_pattern(df5)
    if name == "RSI-Div":
        return detect_rsi_divergence(df15)
    raise KeyError(name)


def run(df, name, step, start, end):
    import pandas as pd
    df_15m = df.resample("15min").agg({"Open": "first", "High": "max", "Low": "min",
                                        "Close": "last"}).dropna()
    df_1h = df.resample("1h").agg({"Open": "first", "High": "max", "Low": "min",
                                   "Close": "last"}).dropna()
    df_4h = df.resample("4h").agg({"Open": "first", "High": "max", "Low": "min",
                                   "Close": "last"}).dropna()

    prev_close = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - prev_close).abs(),
                    (df["Low"] - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=5).mean().fillna(0.0).to_numpy()

    wins = losses = 0
    total_r = 0.0
    n = 0
    for idx in range(200, len(df) - FORWARD_BARS - 2, step):
        ts = df.index[idx]
        if ts < start or ts > end:
            continue
        w5 = df.iloc[idx - 1440 + 1: idx + 1]
        w15 = df_15m[df_15m.index <= ts].iloc[-200:]
        w1 = df_1h[df_1h.index <= ts].iloc[-720:]
        w4 = df_4h[df_4h.index <= ts].iloc[-180:]
        if len(w1) < 12 or len(w4) < 2:
            continue
        try:
            det = detect_for(name, w5, w15, w1, w4)
        except Exception:
            continue
        present, direction, _strength = _normalize(_FN_OF[name], det)
        if not present:
            continue
        # _normalize_detector leaves 3-Pushes' "up"/"down" alone; the live
        # system maps them with _normalize_direction a second time. Both
        # steps are needed to see every strategy.
        direction = _ls._normalize_direction(direction)
        if direction not in ("long", "short"):
            continue
        a = float(atr[idx])
        if a <= 0:
            continue
        entry = float(df.iloc[idx + 1]["Close"])
        sign = 1 if direction == "long" else -1
        risk = a * STOP_MULT
        sl = entry - sign * risk
        t2 = entry + sign * risk * T2_R
        exit_price = None
        for _, bar in df.iloc[idx + 2: idx + 2 + FORWARD_BARS].iterrows():
            hi, lo = float(bar["High"]), float(bar["Low"])
            if direction == "long":
                if lo <= sl:
                    exit_price = sl
                    break
                if hi >= t2:
                    exit_price = t2
                    break
            else:
                if hi >= sl:
                    exit_price = sl
                    break
                if lo <= t2:
                    exit_price = t2
                    break
        if exit_price is None:
            continue
        R = sign * (exit_price - entry) / risk
        n += 1
        total_r += R
        if R > 0:
            wins += 1
        else:
            losses += 1
    if n == 0:
        return None
    wr = wins / n
    lo, hi = swp.wilson(wins, n)
    return {"n": n, "wins": wins, "wr": wr, "pf": swp.pf_of(wr),
            "lo": swp.pf_of(lo), "hi": swp.pf_of(hi), "total_r": total_r}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=3, help="cadence to evaluate (3 = live)")
    ap.add_argument("--only", default=None, help="only this strategy")
    args = ap.parse_args()

    df = swp.load_deep()
    split_at = df.index[int(len(df) * TRAIN_FRACTION)]
    halves = [("early", df.index[0], split_at), ("recent", split_at, df.index[-1])]
    print(f"deep 5m bars {len(df)}  {df.index[0].date()} → {df.index[-1].date()}")
    print(f"early  {df.index[0].date()} → {split_at.date()}")
    print(f"recent {split_at.date()} → {df.index[-1].date()}")
    print(f"cadence: every {args.step} bars\n")
    print(f"{'strategy':16} | {'early n':>8} {'PF':>6} {'CI':>15} {'R':>8} | "
          f"{'recent n':>9} {'PF':>6} {'CI':>15} {'R':>8}  verdict")
    for name in STRATEGIES:
        if args.only and name != args.only:
            continue
        e = run(df, name, args.step, *halves[0][1:])
        r = run(df, name, args.step, *halves[1][1:])
        if not e or not r:
            print(f"{name:16} | (no data)")
            continue
        if e["lo"] > 1 and r["lo"] > 1:
            v = "✅ 兩個期間都顯著 >1"
        elif e["lo"] > 1 and r["hi"] < 1:
            v = "❌ 早期有 edge，近期顯著 <1（衰減）"
        elif r["lo"] > 1:
            v = "✅ 近期顯著 >1"
        elif r["hi"] < 1:
            v = "❌ 近期顯著 <1"
        else:
            v = "— 近期同 1 無分別"
        print(f"{name:16} | {e['n']:>8} {e['pf']:>6.2f} [{e['lo']:>5.2f},{e['hi']:>5.2f}] "
              f"{e['total_r']:>+8.2f} | {r['n']:>9} {r['pf']:>6.2f} [{r['lo']:>5.2f},{r['hi']:>5.2f}] "
              f"{r['total_r']:>+8.2f}  {v}")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
