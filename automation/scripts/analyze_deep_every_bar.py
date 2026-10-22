#!/usr/bin/env python3
"""The every-five-minute track: the densest sample, and the one that settles
whether an edge is real or an artefact of how often the detectors fire.

At a four-hour cadence the detectors are evaluated 2,400 times over
thirteen months, and 3-Pushes and CRT produce no trades at all — the
sampling is too sparse to catch them. At every five minutes they are
evaluated about 115,000 times and both produce tens of thousands of
trades. That makes this track the closest the backtest gets to the live
system, which evaluates every fifteen minutes.

Two caveats, stated because they change how the numbers should be read:

  - The profit factors at different cadences are not directly
    comparable, because each cadence produces a different sample. What
    can be compared is whether a verdict holds at every cadence.
  - Trades at this cadence overlap in time — a pattern that persists for
    a dozen bars produces a dozen entries that resolve into the same
    move. The win rate is not inflated by it, but the confidence
    intervals are narrower than a genuinely independent sample would
    give. Read this track as a sensitivity check on density, not as
    more evidence than it is.

Usage:
    python3 automation/scripts/analyze_deep_every_bar.py
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEEP = Path("/workspace/deep_s1.jsonl")
REF = REPO / "automation" / "reports" / "historical_backtest" / "trades_5m_deep.jsonl"
OUT = REPO / "automation" / "reports" / "historical_backtest" / "deep_every_bar.json"

TRAIN_FRACTION = 0.65


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def pf_of(wr):
    return float("inf") if wr >= 1.0 else wr * 1.618 / (1 - wr)


def stats(rows):
    per = defaultdict(lambda: {"n": 0, "w": 0, "r": 0.0})
    for d in rows:
        r = d.get("R_multiple")
        if r is None:
            continue
        a = per[d["strategy"]]
        a["n"] += 1
        a["r"] += float(r)
        if float(r) > 0:
            a["w"] += 1
    out = {}
    for s, a in per.items():
        n = a["n"]
        lo, hi = wilson(a["w"], n)
        out[s] = {"n": n, "wins": a["w"], "wr": 100 * a["w"] / n,
                  "avg_r": a["r"] / n, "total_r": a["r"],
                  "pf": pf_of(a["w"] / n), "lo": pf_of(lo), "hi": pf_of(hi)}
    return out


def main() -> int:
    if not DEEP.exists():
        print(f"no data at {DEEP}", file=sys.stderr)
        return 1

    ref = [json.loads(l) for l in REF.read_text().splitlines() if l.strip()]
    tickers = {str(d.get("ticker", "")).replace("-", "").upper() for d in ref}
    stamps = [d.get("entry_time") for d in ref if d.get("entry_time")]
    lo_t, hi_t = min(stamps), max(stamps)
    split_at = sorted(stamps)[int(len(stamps) * TRAIN_FRACTION)]

    all_rows, early, late = [], [], []
    for line in DEEP.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if str(d.get("ticker", "")).replace("-", "").upper() not in tickers:
            continue
        et = d.get("entry_time")
        if et and not (lo_t <= et <= hi_t):
            continue
        all_rows.append(d)
        (early if et <= split_at else late).append(d)

    print(f"deep 5m, every bar — {len(all_rows)} trades, "
          f"{lo_t[:10]} → {hi_t[:10]}")
    print(f"split at {split_at[:10]}\n")

    for label, rows in (("WHOLE", all_rows), ("EARLY", early), ("LATE", late)):
        st = stats(rows)
        print(f"### {label}  (n={sum(a['n'] for a in st.values())})")
        print(f"{'strategy':16} {'n':>7} {'wins':>6} {'WR%':>6} {'PF':>6} "
              f"{'PF 95% CI':>15} {'avgR':>7} {'totalR':>10}  verdict")
        for s in sorted(st, key=lambda k: -st[k]["n"]):
            a = st[s]
            v = ("✅ PF>1 SIGNIFICANT" if a["lo"] > 1 else
                 "❌ PF<1 SIGNIFICANT" if a["hi"] < 1 else
                 "— indistinguishable from 1")
            print(f"{s:16} {a['n']:>7} {a['wins']:>6} {a['wr']:>5.1f}% {a['pf']:>6.2f} "
                  f"[{a['lo']:>5.2f},{a['hi']:>5.2f}] {a['avg_r']:>+7.3f} "
                  f"{a['total_r']:>+10.2f}  {v}")
        print()

    whole = stats(all_rows)
    OUT.write_text(json.dumps({
        "split_at": split_at,
        "whole": whole,
        "early": stats(early),
        "late": stats(late),
    }, indent=2, default=str))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
