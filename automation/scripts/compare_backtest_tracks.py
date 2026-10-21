#!/usr/bin/env python3
"""Compare the backtest tracks side by side.

The three tracks measure different things, so a raw comparison lies:

  live      real 5-minute bars, 56 days, the history the system traded
  1h        Yahoo 1-hour bars, 180 days, the optimiser's "second track"
  deep5m    Polygon real 5-minute bars, 13 months, BTC only

The 1h track covers five instruments over six months and the deep track
covers one instrument over thirteen months. Comparing them as-is compares
a basket with a single stock. This script therefore restricts both to
the same instrument and the same period before it prints anything.

R-multiples in the backtests are binary (-1.0 at the stop, +1.618 at T2),
so PF is a fixed multiple of the win rate and the only lever is the win
rate itself.

Usage:
    python3 automation/scripts/compare_backtest_tracks.py
    python3 automation/scripts/compare_backtest_tracks.py --no-restrict
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HBT = REPO / "automation" / "reports" / "historical_backtest"

TRACKS = {
    "1h": HBT / "trades.jsonl",
    "deep5m_4h": HBT / "trades_5m_deep.jsonl",
    "deep5m_1h": HBT / "trades_5m_deep_s12.jsonl",
}


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def norm_ticker(t: str) -> str:
    return str(t or "").replace("-", "").upper()


def aggregate(rows: list[dict]) -> dict:
    per = defaultdict(lambda: {"n": 0, "w": 0, "r": 0.0, "gp": 0.0, "gl": 0.0})
    for d in rows:
        r = d.get("R_multiple")
        if r is None:
            continue
        r = float(r)
        a = per[d.get("strategy", "?")]
        a["n"] += 1
        a["r"] += r
        if r > 0:
            a["w"] += 1
            a["gp"] += r
        else:
            a["gl"] += abs(r)
    out = {}
    for s, a in per.items():
        pf = (a["gp"] / a["gl"]) if a["gl"] > 0 else (float("inf") if a["gp"] > 0 else 0.0)
        out[s] = {"n": a["n"], "w": a["w"],
                  "wr": 100.0 * a["w"] / a["n"] if a["n"] else 0.0,
                  "pf": pf, "r": a["r"]}
    return out


def show(title: str, res: dict) -> None:
    print(f"\n### {title}")
    print(f"{'strategy':16} {'n':>5} {'w':>4} {'WR%':>6} {'PF':>6} {'totalR':>9}")
    tn = tw = 0
    tr = 0.0
    for s in sorted(res, key=lambda k: -res[k]["n"]):
        a = res[s]
        tn += a["n"]
        tw += a["w"]
        tr += a["r"]
        pf = "inf" if a["pf"] == float("inf") else f"{a['pf']:.2f}"
        print(f"{s:16} {a['n']:>5} {a['w']:>4} {a['wr']:>5.1f}% {pf:>6} {a['r']:>+9.2f}")
    wr = 100.0 * tw / tn if tn else 0.0
    print(f"{'TOTAL':16} {tn:>5} {tw:>4} {wr:>5.1f}% {'':>6} {tr:>+9.2f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-restrict", action="store_true",
                    help="compare the tracks as they are, without matching "
                         "instrument and period (misleading; for debugging)")
    args = ap.parse_args()

    tracks = {name: load(path) for name, path in TRACKS.items()}
    missing = [n for n, rows in tracks.items() if not rows]
    if missing:
        print(f"no data for: {', '.join(missing)} — run the backtests first", file=sys.stderr)

    if not args.no_restrict and tracks.get("deep5m_4h"):
        deep = tracks["deep5m_4h"]
        tickers = {norm_ticker(d.get("ticker")) for d in deep}
        stamps = [d.get("entry_time") for d in deep if d.get("entry_time")]
        lo, hi = (min(stamps), max(stamps)) if stamps else ("", "")
        print(f"restricting every track to tickers {sorted(tickers)} and "
              f"{lo[:10]} → {hi[:10]}")
        for name, rows in tracks.items():
            kept = [d for d in rows if norm_ticker(d.get("ticker")) in tickers]
            if stamps:
                kept = [d for d in kept
                        if not d.get("entry_time") or lo <= d["entry_time"] <= hi]
            tracks[name] = kept

    res = {name: aggregate(rows) for name, rows in tracks.items()}
    for name in tracks:
        show(name, res[name])

    if len(tracks) >= 2:
        names = list(tracks)
        a, b = names[0], names[1]
        print(f"\n### {a} vs {b}")
        print(f"{'strategy':16} {a+'_n':>8} {a+'_PF':>7} {a+'_R':>9} | "
              f"{b+'_n':>8} {b+'_PF':>7} {b+'_R':>9}")
        for s in sorted(set(res[a]) | set(res[b])):
            x = res[a].get(s, {"n": 0, "pf": 0.0, "r": 0.0})
            y = res[b].get(s, {"n": 0, "pf": 0.0, "r": 0.0})
            print(f"{s:16} {x['n']:>8} {x['pf']:>7.2f} {x['r']:>+9.2f} | "
                  f"{y['n']:>8} {y['pf']:>7.2f} {y['r']:>+9.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
