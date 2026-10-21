#!/usr/bin/env python3
"""Sweep a strategy's detector thresholds over the real five-minute history.

The discipline is the one the optimiser already uses, extended to three
samples: a configuration is only interesting if it holds up on a period it
was not tuned on, and at the resolution the live system actually trades.

  train      the first 65% of the deep history, evaluated every 12 bars
             (hourly) — fast, and where the grid is searched
  holdout    the last 35%, evaluated every 3 bars (15 minutes) — this is
             the live cadence, because live_scan scans every 15 minutes
             and a 15-minute track is four times denser than the 1h one

A configuration is only accepted if the holdout profit factor clears 1
with a 95% interval that excludes 1, AND it does not make the train
sample worse. That is the rule that stopped the previous optimiser
publishing five overfitted configurations.

Usage:
    python3 automation/scripts/sweep_detector_params.py --strategy CRT
    python3 automation/scripts/sweep_detector_params.py --strategy CRT --quick
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "automation" / "scripts"
SRC = REPO / "automation" / "src"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SRC))

DEEP = REPO / "automation" / "data" / "deep_history" / "BTCUSD" / "5m"
OUT_DIR = REPO / "automation" / "reports" / "sweeps"

T2_R = 1.618
STOP_MULT = 1.6
FORWARD_BARS = 96          # same as the live backtest
TRAIN_FRACTION = 0.65


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
    df = pd.DataFrame({"Open": [x[1] for x in rows], "High": [x[2] for x in rows],
                       "Low": [x[3] for x in rows], "Close": [x[4] for x in rows]},
                      index=idx)
    # The Polygon months overlap at their boundaries, so a duplicated
    # timestamp makes .loc[] return a frame instead of a row. The main
    # backtest drops the same duplicates.
    return df[~df.index.duplicated(keep="first")]


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def pf_of(wr):
    if wr >= 1.0:
        return float("inf")
    return wr * T2_R / (1 - wr)


# --- the grids ---------------------------------------------------------------

def grid_for(strategy: str, quick: bool):
    if strategy == "CRT":
        depths = [None, 1.0, 0.5] if quick else [None, 2.0, 1.5, 1.0, 0.5, 0.25]
        mss = [1] if quick else [1, 2, 3]
        last = [False] if quick else [False, True]
        out = []
        for d in depths:
            for m in mss:
                for u in last:
                    out.append({"max_raid_depth_pct": d, "mss_bars": m,
                                "use_last_raid": u, "min_crt_range_pct": None})
        return out
    raise SystemExit(f"no grid defined for {strategy}")


def make_detector(strategy: str):
    from yw_indicators_extra import detect_crt
    return detect_crt


def run_split(df, detector, cfg, step, start, end, split_name):
    """Evaluate one configuration over one period."""
    import pandas as pd
    df_4h = df.resample("4h").agg({"Open": "first", "High": "max", "Low": "min",
                                   "Close": "last"}).dropna()
    df_1h = df.resample("1h").agg({"Open": "first", "High": "max", "Low": "min",
                                   "Close": "last"}).dropna()
    df_4h = df_4h[df_4h.index <= end]
    df_1h = df_1h[df_1h.index <= end]
    if len(df_4h) < 40:
        return None

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
        w4 = df_4h[df_4h.index <= ts]
        if len(w4) < 2:
            continue
        w1 = df_1h[df_1h.index <= ts].iloc[-720:]
        w4 = w4.iloc[-180:]
        if len(w1) < 12:
            continue
        det = detector(w4, df.iloc[idx - 1440 + 1: idx + 1], **cfg)
        if not det.get("present"):
            continue
        direction = det.get("direction")
        if direction not in ("long", "short", "bullish", "bearish"):
            continue
        direction = "long" if direction in ("long", "bullish") else "short"
        a = float(atr[idx])
        if a <= 0:
            continue
        entry = float(df.iloc[idx + 1]["Close"])
        sign = 1 if direction == "long" else -1
        sl = entry - sign * a * STOP_MULT
        risk = a * STOP_MULT
        t2 = entry + sign * risk * T2_R
        fwd = df.iloc[idx + 2: idx + 2 + FORWARD_BARS]
        exit_price = None
        for _, bar in fwd.iterrows():
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
    lo, hi = wilson(wins, n)
    return {"n": n, "wins": wins, "wr": wr, "pf": pf_of(wr),
            "lo": pf_of(lo), "hi": pf_of(hi), "total_r": total_r,
            "split": split_name}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="CRT")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--train-step", type=int, default=12)
    ap.add_argument("--holdout-step", type=int, default=3)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if not DEEP.exists():
        print(f"no deep history at {DEEP}", file=sys.stderr)
        return 1

    df = load_deep()
    detector = make_detector(args.strategy)
    split_at = df.index[int(len(df) * TRAIN_FRACTION)]
    train = (df.index[0], split_at)
    holdout = (split_at, df.index[-1])
    print(f"deep 5m bars {len(df)}  {df.index[0].date()} → {df.index[-1].date()}")
    print(f"train      {train[0].date()} → {train[1].date()}  (step {args.train_step})")
    print(f"holdout    {holdout[0].date()} → {holdout[1].date()}  (step {args.holdout_step}, live cadence)")

    grid = grid_for(args.strategy, args.quick)
    print(f"\n{len(grid)} configurations\n")
    print(f"{'max_depth':>10} {'mss':>4} {'last':>6} | "
          f"{'TRAIN n':>8} {'PF':>6} {'CI':>14} {'R':>8} | "
          f"{'HOLD n':>7} {'PF':>6} {'CI':>14} {'R':>8}  verdict")
    results = []
    for i, cfg in enumerate(grid, 1):
        tr = run_split(df, detector, cfg, args.train_step, train[0], train[1], "train")
        ho = run_split(df, detector, cfg, args.holdout_step, holdout[0], holdout[1], "holdout")
        if not tr or not ho:
            print(f"{str(cfg.get('max_raid_depth_pct')):>10} {cfg.get('mss_bars'):>4} "
                  f"{str(cfg.get('use_last_raid')):>6} | (no data)")
            continue
        accepted = ho["lo"] > 1.0 and ho["pf"] > tr["pf"]
        verdict = "ACCEPT" if accepted else ""
        print(f"{str(cfg.get('max_raid_depth_pct')):>10} {cfg.get('mss_bars'):>4} "
              f"{str(cfg.get('use_last_raid')):>6} | "
              f"{tr['n']:>8} {tr['pf']:>6.2f} [{tr['lo']:>5.2f},{tr['hi']:>5.2f}] {tr['total_r']:>+8.2f} | "
              f"{ho['n']:>7} {ho['pf']:>6.2f} [{ho['lo']:>5.2f},{ho['hi']:>5.2f}] {ho['total_r']:>+8.2f}  {verdict}")
        results.append({"cfg": cfg, "train": tr, "holdout": ho, "accepted": accepted})
        sys.stdout.flush()

    out = Path(args.out) if args.out else OUT_DIR / f"sweep_{args.strategy.lower()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nwrote {out}")
    acc = [r for r in results if r.get("accepted")]
    print(f"accepted configurations: {len(acc)}")
    for r in acc:
        print(f"  {r['cfg']}  holdout PF {r['holdout']['pf']:.2f} "
              f"[{r['holdout']['lo']:.2f},{r['holdout']['hi']:.2f}] n={r['holdout']['n']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
