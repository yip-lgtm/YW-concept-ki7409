"""Statistical comparison of every backtest track.

PF here is (wins x 1.618) / losses, because every backtest resolves at
-1R against the stop and +1.618R at T2. So a Wilson interval on the win
rate maps directly to an interval on PF, and "is this PF above 1" is a
binomial question.

Usage:
    python3 automation/scripts/compare_tracks_stats.py
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HBT = REPO / "automation" / "reports" / "historical_backtest"

TRACKS = [
    ("1h (Yahoo 180d)", HBT / "trades.jsonl"),
    ("deep5m 4h", HBT / "trades_5m_deep.jsonl"),
    ("deep5m 1h", HBT / "trades_5m_deep_s12.jsonl"),
    ("deep5m 15m (live)", HBT / "trades_5m_deep_s3.jsonl"),
]


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def pf(wr):
    if wr >= 1.0:
        return float("inf")
    return wr * 1.618 / (1 - wr)


def load(path):
    rows = []
    if not path.exists():
        return rows
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


def main() -> int:
    # Restrict every track to the deep track's instrument and period, so the
    # comparison is like for like.
    deep = load(HBT / "trades_5m_deep.jsonl")
    tickers = {str(d.get("ticker", "")).replace("-", "").upper() for d in deep}
    stamps = [d.get("entry_time") for d in deep if d.get("entry_time")]
    lo, hi = (min(stamps), max(stamps)) if stamps else ("", "")

    table = defaultdict(dict)
    for name, path in TRACKS:
        rows = load(path)
        if not rows:
            print(f"[skip] {name}: no file")
            continue
        rows = [d for d in rows
                if str(d.get("ticker", "")).replace("-", "").upper() in tickers
                and (not d.get("entry_time") or (lo <= d["entry_time"] <= hi))]
        per = defaultdict(lambda: [0, 0])
        for d in rows:
            r = d.get("R_multiple")
            if r is None:
                continue
            per[d.get("strategy", "?")][0 if float(r) > 0 else 1] += 1
        for s, (w, l) in per.items():
            n = w + l
            if n == 0:
                continue
            a, b = wilson(w, n)
            table[s][name] = {
                "n": n, "w": w, "wr": 100 * w / n, "pf": pf(w / n),
                "lo": pf(a), "hi": pf(b),
            }

    names = [n for n, _ in TRACKS]
    for s in sorted(table, key=lambda k: -max(v["n"] for v in table[k].values())):
        print(f"\n### {s}")
        print(f"{'track':22} {'n':>6} {'WR%':>6} {'PF':>7} {'PF 95% CI':>16}  verdict")
        for name in names:
            v = table[s].get(name)
            if not v:
                print(f"{name:22} {'—':>6}")
                continue
            if v["lo"] > 1:
                verdict = "PF>1 SIGNIFICANT"
            elif v["hi"] < 1:
                verdict = "PF<1 SIGNIFICANT"
            else:
                verdict = "indistinguishable from 1"
            pfs = "inf" if v["pf"] == float("inf") else f"{v['pf']:.2f}"
            print(f"{name:22} {v['n']:>6} {v['wr']:>5.1f}% {pfs:>7} "
                  f"[{v['lo']:>5.2f},{v['hi']:>5.2f}]  {verdict}")
        # how many tracks call it significant
        sig_up = sum(1 for n in names if table[s].get(n) and table[s][n]["lo"] > 1)
        sig_dn = sum(1 for n in names if table[s].get(n) and table[s][n]["hi"] < 1)
        print(f"{'':22} → {sig_up} track(s) significantly above 1, {sig_dn} significantly below")
    return 0


if __name__ == "__main__":
    sys.exit(main())
