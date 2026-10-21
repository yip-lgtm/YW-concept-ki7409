#!/usr/bin/env python3
"""Audit the output format of every detector.

The detectors do not agree on how to spell a direction:

  3-Pushes   "up" / "down"
  RSI-Div    "bullish" / "bearish"
  CRT        "bullish" / "bearish"
  Two-Yang   "long" / "short"

The live system copes because live_scan._normalize_direction maps all of
them before a signal is built. Anything else that consumes a detector
directly has to do the same, and when it does not, the mismatch is
silent: the backtest dropped 100% of the 3-Pushes, RSI-Div and CRT
trades for a week before anyone noticed, and the "0 of 9 configurations
survive" verdict was computed on a track that held no data for those
three strategies.

This script runs every detector over the real five-minute history and
reports what each one actually emits, so a change in a detector's output
format is visible instead of silent.

Usage:
    python3 automation/scripts/audit_detector_formats.py
    python3 automation/scripts/audit_detector_formats.py --sample 300
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
for _parent in Path(__file__).resolve().parents:
    if (_parent / "automation" / "src").is_dir():
        REPO = _parent
        break
DEEP = REPO / "automation" / "data" / "deep_history" / "BTCUSD" / "5m"

CANONICAL = ("long", "short")


def load_live_scan():
    sys.path.insert(0, str(REPO / "automation" / "scripts"))
    sys.path.insert(0, str(REPO / "automation" / "src"))
    spec = importlib.util.spec_from_file_location(
        "live_scan", str(REPO / "automation" / "scripts" / "live_scan.py"))
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ModuleNotFoundError as e:
        print(f"live_scan needs {e.name} — install the automation requirements:\n"
              f"  pip install -r {REPO / 'automation' / 'requirements.txt'}",
              file=sys.stderr)
        raise SystemExit(2)
    return mod


def load_deep() -> pd.DataFrame:
    rows = []
    for f in sorted(DEEP.glob("*.csv")):
        with f.open() as fh:
            for r in csv.DictReader(fh):
                if r.get("ts") and r.get("close"):
                    rows.append((int(r["ts"]), float(r["open"]), float(r["high"]),
                                 float(r["low"]), float(r["close"]), float(r["volume"])))
    rows.sort()
    idx = pd.DatetimeIndex([pd.Timestamp(t, unit="ms", tz="UTC") for t, *_ in rows])
    return pd.DataFrame({"Open": [x[1] for x in rows], "High": [x[2] for x in rows],
                         "Low": [x[3] for x in rows], "Close": [x[4] for x in rows],
                         "Volume": [x[5] for x in rows]}, index=idx)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=600,
                    help="how many evaluation points to sample (default 600)")
    ap.add_argument("--step", type=int, default=240,
                    help="bars between evaluation points (default 240)")
    args = ap.parse_args()

    if not DEEP.exists():
        print(f"no deep history at {DEEP}", file=sys.stderr)
        return 1

    ls = load_live_scan()
    df = load_deep()
    df_1h = df.resample("1h").agg({"Open": "first", "High": "max", "Low": "min",
                                    "Close": "last", "Volume": "sum"}).dropna()
    df_4h = df_1h.resample("4h").agg({"Open": "first", "High": "max", "Low": "min",
                                      "Close": "last", "Volume": "sum"}).dropna()
    print(f"deep 5m bars: {len(df)}  ({df.index[0].date()} → {df.index[-1].date()})")
    print(f"sampling every {args.step} bars, {args.sample} points\n")

    print(f"{'strategy':16} {'hits':>6}  {'raw direction values':38} {'strength':>10}  note")
    print("-" * 100)

    problems = []
    for name, cfg in ls.STRATEGIES.items():
        dirs: Counter = Counter()
        strengths: Counter = Counter()
        hits = 0
        for i in range(5000, len(df) - 20, args.step):
            win = df.iloc[i - 1440 + 1: i + 1]
            w1 = df_1h[df_1h.index <= df.index[i]].iloc[-720:]
            w4 = df_4h[df_4h.index <= df.index[i]].iloc[-180:]
            data = {"df_5m": win, "df_1h": w1, "df_4h": w4,
                    "n_5m": len(win), "n_1h": len(w1), "n_4h": len(w4)}
            try:
                det = ls.run_detector(name, cfg, "BTC-USD", data)
            except Exception:
                continue
            if not det.get("present"):
                continue
            hits += 1
            dirs[str(det.get("direction"))] += 1
            if det.get("strength") is not None:
                strengths[str(det.get("strength"))] += 1

        raw = ", ".join(f"{k}×{v}" for k, v in dirs.most_common(4)) or "-"
        st = ", ".join(f"{k}×{v}" for k, v in strengths.most_common(3)) or "-"
        non_canonical = [d for d in dirs if d not in CANONICAL]
        note = ""
        if hits == 0:
            note = "never fires on real 5m"
        elif non_canonical:
            note = f"raw direction not canonical: {non_canonical}"
            problems.append((name, non_canonical))
        print(f"{name:16} {hits:>6}  {raw:38} {st:>10}  {note}")

    if problems:
        print("\nConsumers of a detector must normalise the direction themselves:")
        for name, vals in problems:
            print(f"  - {name}: emits {vals}; use live_scan._normalize_direction")
        print("\nAnything that skips that step will silently discard every "
              "trade from these strategies.")
    else:
        print("\n✓ every detector emits a canonical direction")
    return 0


if __name__ == "__main__":
    sys.exit(main())
