#!/usr/bin/env python3
"""Historical backtest — synthesise a long trade history for the optimiser.

The problem this solves
-----------------------
The optimiser could only work with the 3254 trades the live system actually
opened, which span 56 days. On that sample, optimising for profit factor
produces configurations that do not survive out of sample: across nine
strategies, one generalised and four collapsed.

Two things were missing: more data, and a second sample that is independent
of the one being fitted.

How this adds them
------------------
Yahoo Finance caps five-minute history at 60 days, but one-hour history at
730 days. The detectors are written against a bar frame and read the last
bar, so running them over one-hour bars over a longer window produces a
second, independent trade history: same strategies, same entry logic,
different time horizon and a different period of market.

The live detectors are reused rather than reimplemented. `run_detector` is
called with a crafted data frame, so the entry logic, the gate arithmetic
and the level calculation are exactly the ones the live system uses.

The deep five-minute track
------------------------
`--mode deep5m` runs the same detectors over the real five-minute history in
`automation/data/deep_history`, fetched from Polygon (2025-09-15 onwards,
115200 bars of BTC-USD, 400 days). Resampled to one and four hours it gives
honest frames, so the detectors see the same shapes the live system builds:
five days of five-minute bars, thirty days of hourly bars, thirty days of
four-hour bars. Entry, stop and exit all resolve on five-minute bars, which
is the granularity the live system actually trades, so the mechanics are the
live ones instead of one-hour approximations. `--deep-step` sets the
evaluation cadence; the default of 48 bars is four hours, the same cadence as
the one-hour track, so the two samples stay comparable.

The grade is the one thing that cannot be reproduced. The live pipeline
grades a signal with the LLM, and calling the model across 180 days of
history is not practical. Instead the detector's own strength is mapped
onto the grade bands the LLM tends to produce. That is an approximation and
it is labelled as one: every record carries `grade_source: "detector_proxy"`.

What the result is used for
---------------------------
Not as a replacement for the live sample but as a second opinion. The
optimiser requires a configuration to improve the holdout profit factor on
BOTH the live five-minute history and this longer one-hour history before
it is published. A configuration that only fits one of them is discarded.
"""
from __future__ import annotations
import os
import sys
import json
import argparse
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

sys.path.insert(0, str(REPO / "automation" / "scripts"))
sys.path.insert(0, str(REPO / "automation" / "src"))
HKT = timezone(timedelta(hours=8))

OUT_DIR = REPO / "automation/reports/historical_backtest"
TRADES_OUT = OUT_DIR / "trades.jsonl"

# How much history the detector sees at each evaluation point. Large enough
# for the longest indicator lookback in the book, small enough that the
# sweep stays linear.
DETECTOR_WINDOW = 500

# Evaluate every N hours. One hour is too dense to be worth the runtime and
# makes neighbouring positions near-duplicates.
EVAL_STEP_HOURS = 4

# Entry happens at the close of the evaluation bar, which is what the live
# system does after the LLM confirms the signal.
ENTRY_DELAY_BARS = 1

# Grade bands, approximating what the LLM produces from the same signal.
GRADE_A_MIN = 78
GRADE_B_MIN = 58
MIN_CONF = 40          # LLM_MIN_CONF in live_scan.py


def log(msg: str):
    print(f"[hist-bt] {datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


DEEP_DIR = REPO / "automation" / "data" / "deep_history"

# Frame sizes for the deep five-minute track, mirroring what live_scan.py
# builds for the live system: five days of five-minute bars, thirty days of
# hourly bars, and the same hourly history resampled to four hours.
DEEP_5M_WINDOW = 1440
DEEP_1H_WINDOW = 720
DEEP_4H_WINDOW = 180

# How often to evaluate. Forty-eight five-minute bars is four hours, the
# same cadence the one-hour track uses, so the two tracks stay comparable.
DEEP_STEP_BARS = 48


def load_deep_history(symbol_dir: str, interval_min: int = 5):
    """Load the deep intraday history fetched from Polygon.

    Unlike the one-hour reconstruction, these are real five-minute bars at
    the granularity the live system trades, so a strategy's parameters
    measured here transfer directly. Only the instruments the Polygon plan
    covers have this depth.
    """
    import csv as _csv
    d = DEEP_DIR / symbol_dir / f"{interval_min}m"
    if not d.exists():
        return None
    frames = []
    for f in sorted(d.glob("*.csv")):
        try:
            with f.open() as fh:
                rd = _csv.DictReader(fh)
                rows = [(int(r["ts"]), float(r["open"]), float(r["high"]),
                         float(r["low"]), float(r["close"]), float(r["volume"]))
                        for r in rd if r.get("ts") and r.get("close")]
            if not rows:
                continue
            rows.sort()
            idx = pd.DatetimeIndex(
                [pd.Timestamp(t, unit="ms", tz="UTC") for t, *_ in rows])
            frames.append(pd.DataFrame(
                {"Open": [x[1] for x in rows], "High": [x[2] for x in rows],
                 "Low": [x[3] for x in rows], "Close": [x[4] for x in rows],
                 "Volume": [x[5] for x in rows]}, index=idx))
        except Exception as e:
            log(f"  deep history {f.name} failed: {e}")
    if not frames:
        return None
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def fetch_1h(ticker: str, days: int):
    from data_source import fetch_bars
    try:
        df = fetch_bars(ticker, days=days, interval_min=60)
    except Exception as e:
        log(f"  bars {ticker} failed: {e}")
        return None
    if df is None or df.empty:
        return None
    if df.index.tz is not None:
        df = df.tz_convert("UTC")
    return df


def grade_from_strength(det: dict) -> tuple[str, int]:
    """Map the detector's own strength onto a confidence and a grade band."""
    strength = det.get("strength")
    if strength is None:
        strength = det.get("confidence", 0)
    try:
        conf = int(float(strength))
    except (TypeError, ValueError):
        conf = 0
    conf = max(0, min(100, conf))
    if conf >= GRADE_A_MIN:
        return "A", conf
    if conf >= GRADE_B_MIN:
        return "B", conf
    return "C", conf


def build_trade(strategy: str, ticker: str, det: dict, df: pd.DataFrame,
                idx: int, atr: float, tf: str = "1h") -> dict | None:
    """Turn a detector hit at bar `idx` into a synthetic trade."""
    direction = det.get("direction")
    if direction not in ("long", "short"):
        return None
    grade, conf = grade_from_strength(det)
    if grade == "C" or conf < MIN_CONF:
        return None
    if idx + ENTRY_DELAY_BARS >= len(df):
        return None
    entry_bar = df.iloc[idx + ENTRY_DELAY_BARS]
    entry = float(entry_bar["Close"])
    if entry <= 0 or atr <= 0:
        return None

    sign = 1 if direction == "long" else -1
    sl_dist = atr * 1.6
    sl = entry - sign * sl_dist
    risk = sl_dist
    t1 = entry + sign * risk * 1.0
    t2 = entry + sign * risk * 1.618
    t3 = entry + sign * risk * 2.618

    # Walk forward to resolve the exit.
    fwd = df.iloc[idx + ENTRY_DELAY_BARS + 1: idx + ENTRY_DELAY_BARS + 1 + 96]
    exit_price = None
    exit_level = None
    bars_held = 0
    for j, (_, bar) in enumerate(fwd.iterrows(), start=1):
        hi, lo = float(bar["High"]), float(bar["Low"])
        bars_held = j
        if direction == "long":
            if lo <= sl:
                exit_price, exit_level = sl, "SL"
                break
            if hi >= t2:
                exit_price, exit_level = t2, "T2"
                break
        else:
            if hi >= sl:
                exit_price, exit_level = sl, "SL"
                break
            if lo <= t2:
                exit_price, exit_level = t2, "T2"
                break
    if exit_price is None:
        return None

    r = sign * (exit_price - entry) / risk
    return {
        "signal_id": f"{strategy}|{ticker}|{tf}|{df.index[idx].isoformat()}",
        "strategy": strategy,
        "ticker": ticker,
        "direction": direction,
        "grade": grade,
        "grade_source": "detector_proxy",
        "confidence": conf,
        "raw_confidence": conf,
        "entry": entry,
        "entry_time": str(df.index[idx + ENTRY_DELAY_BARS]),
        "sl": sl,
        "sl_dist": risk,
        "t1": t1, "t2": t2, "t3": t3,
        "atr": atr,
        "exit_price": exit_price,
        "exit_level": exit_level,
        "exit_time": str(fwd.index[bars_held - 1]) if bars_held <= len(fwd.index) else None,
        "R_multiple": round(r, 4),
        "pnl_usd": 0.0,
        "bars_held": bars_held,
        "status": "closed",
        "timeframe": tf,
        "source": ("historical_backtest_deep5m" if tf == "5m"
                   else "historical_backtest_1h"),
        "reason": det.get("reason", "")[:180],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--tickers", nargs="*",
                    default=["MNQ=F", "MES=F", "M2K=F", "MGC=F", "BTC-USD"])
    ap.add_argument("--out", default=str(TRADES_OUT))
    ap.add_argument("--mode", choices=["1h", "deep5m"], default="1h",
                    help="1h = one-hour reconstruction; deep5m = real "
                         "five-minute history from the deep-history fetch")
    ap.add_argument("--deep-symbol", default="BTCUSD",
                    help="symbol directory under automation/data/deep_history")
    ap.add_argument("--deep-step", type=int, default=DEEP_STEP_BARS,
                    help="evaluate every N five-minute bars in deep mode")
    args = ap.parse_args()

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "live_scan", str(REPO / "automation" / "scripts" / "live_scan.py"))
    ls = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ls)

    log("=" * 60)
    if args.mode == "deep5m":
        log(f"Historical backtest — deep 5m track "
            f"(eval every {args.deep_step} bars)")
    else:
        log(f"Historical backtest — {args.days}d on 1h bars "
            f"(eval every {EVAL_STEP_HOURS}h)")
    log("=" * 60)

    # Which detectors to run. The L-series and Argon need frame combinations
    # the one-hour history does not carry faithfully, so they are excluded.
    # OCS-BTC-5m is excluded because it fits a KNN at every evaluation point,
    # which is far too slow for a sweep, and it is a separate strategy with
    # its own pipeline.
    # B1-3in1 is excluded because it costs about 415 ms per evaluation
    # against one to fifteen for everything else, which alone would take
    # five minutes per ticker for one strategy. It is also a multi-asset
    # combination, so it has no clean single-cell story in this sweep.
    skip = {"Argon-Gold", "TTrades-Fractal", "TTrades-L12", "TTrades-L13",
            "TTrades-L14", "OCS-BTC-5m", "B1-3in1"}
    det_names = [n for n in ls.STRATEGIES if n not in skip]
    log(f"  detectors: {len(det_names)} ({', '.join(det_names)})")

    deep = args.mode == "deep5m"
    tf = "5m" if deep else "1h"
    tickers = [args.deep_symbol] if deep else args.tickers

    all_trades = []
    for ticker in tickers:
        if deep:
            df = load_deep_history(ticker, 5)
            if df is None:
                log(f"  {ticker}: no deep 5m history")
                continue
            log(f"  {ticker}: {len(df)} deep 5m bars "
                f"({df.index[0].date()} → {df.index[-1].date()})")
        else:
            df = fetch_1h(ticker, args.days)
            if df is None or len(df) < 100:
                log(f"  {ticker}: no usable 1h history")
                continue
            log(f"  {ticker}: {len(df)} 1h bars "
                f"({df.index[0].date()} → {df.index[-1].date()})")

        # Pre-compute ATR once per bar.
        prev_close = df["Close"].shift(1)
        tr = pd.concat([df["High"] - df["Low"],
                        (df["High"] - prev_close).abs(),
                        (df["Low"] - prev_close).abs()], axis=1).max(axis=1)
        atr_series = tr.rolling(14, min_periods=5).mean().fillna(0.0).to_numpy()

        if deep:
            df_1h = df.resample("1h").agg({
                "Open": "first", "High": "max", "Low": "min",
                "Close": "last", "Volume": "sum"}).dropna()
            df_4h = df_1h.resample("4h").agg({
                "Open": "first", "High": "max", "Low": "min",
                "Close": "last", "Volume": "sum"}).dropna()
        else:
            df_4h = df.resample("4h").agg({
                "Open": "first", "High": "max", "Low": "min",
                "Close": "last", "Volume": "sum"}).dropna()

        step = args.deep_step if deep else max(1, EVAL_STEP_HOURS)
        first_idx = DEEP_5M_WINDOW if deep else DETECTOR_WINDOW
        idxs = range(first_idx, len(df) - ENTRY_DELAY_BARS - 1, step)
        n_hits = 0
        for idx in idxs:
            if deep:
                win = df.iloc[idx - DEEP_5M_WINDOW + 1: idx + 1]
                w1 = df_1h[df_1h.index <= df.index[idx]]
                w1 = w1.iloc[-DEEP_1H_WINDOW:] if len(w1) > DEEP_1H_WINDOW else w1
                w4 = df_4h[df_4h.index <= df.index[idx]]
                w4 = w4.iloc[-DEEP_4H_WINDOW:] if len(w4) > DEEP_4H_WINDOW else w4
            else:
                win = df.iloc[max(0, idx - DETECTOR_WINDOW + 1): idx + 1]
                w4 = df_4h[df_4h.index <= df.index[idx]]
                w4 = w4.iloc[-60:] if len(w4) > 60 else w4
                w1 = win
            data = {"df_5m": win, "df_1h": w1, "df_4h": w4,
                    "n_5m": len(win), "n_1h": len(w1), "n_4h": len(w4)}
            atr = float(atr_series[idx])
            if atr <= 0:
                continue
            for name in det_names:
                cfg = ls.STRATEGIES[name]
                try:
                    det = ls.run_detector(name, cfg, ticker, data)
                except Exception:
                    continue
                if not det.get("present"):
                    continue
                t = build_trade(name, ticker, det, df, idx, atr, tf)
                if t:
                    all_trades.append(t)
                    n_hits += 1
        log(f"    {n_hits} synthetic trades")

    # Deduplicate by signal id.
    seen = set()
    uniq = []
    for t in all_trades:
        if t["signal_id"] in seen:
            continue
        seen.add(t["signal_id"])
        uniq.append(t)
    uniq.sort(key=lambda t: str(t.get("entry_time", "")))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for t in uniq:
            f.write(json.dumps(t, default=str) + "\n")

    log(f"wrote {len(uniq)} synthetic trades → {out}")
    by = defaultdict(int)
    for t in uniq:
        by[t["strategy"]] += 1
    for s, n in sorted(by.items(), key=lambda kv: -kv[1]):
        log(f"    {s:<18} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
