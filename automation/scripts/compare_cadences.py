"""Compare profit factors across the backtest cadences.

The forward window is 96 bars, so at a dense cadence adjacent evaluation
points resolve the same exit and the same trade is counted many times
over. The profit factor is therefore only meaningful at a cadence where
one evaluation point is one trade — which is why the live cadence
(every 15 minutes) and the two sparser ones are the ones that get
compared here, and why this script also reports how many trades each
cadence produced so the overlap is visible.

Usage:
    python3 automation/scripts/compare_cadences.py
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
    ("deep 4h", HBT / "trades_5m_deep.jsonl"),
    ("deep 1h", HBT / "trades_5m_deep_s12.jsonl"),
    ("deep 15m (live)", HBT / "trades_5m_deep_s3.jsonl"),
]
EXTRA = [("deep 5m (every bar)", Path("/workspace/deep_s1.jsonl"))]


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
    return wr * 1.618 / (1 - wr)


def main() -> int:
    ref = [json.loads(l) for l in
           open(HBT / "trades_5m_deep.jsonl") if l.strip()]
    tickers = {str(d.get("ticker", "")).replace("-", "").upper() for d in ref}
    stamps = [d.get("entry_time") for d in ref if d.get("entry_time")]
    lo, hi = (min(stamps), max(stamps)) if stamps else ("", "")

    table = defaultdict(dict)
    for name, path in TRACKS + EXTRA:
        if not path.exists():
            continue
        per = defaultdict(lambda: {"n": 0, "w": 0, "r": 0.0})
        for line in path.open():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if str(d.get("ticker", "")).replace("-", "").upper() not in tickers:
                continue
            et = d.get("entry_time")
            if et and not (lo <= et <= hi):
                continue
            r = d.get("R_multiple")
            if r is None:
                continue
            a = per[d.get("strategy", "?")]
            a["n"] += 1
            a["r"] += float(r)
            if float(r) > 0:
                a["w"] += 1
        for s, a in per.items():
            n = a["n"]
            if n == 0:
                continue
            wlo, whi = wilson(a["w"], n)
            table[s][name] = {"n": n, "w": a["w"], "wr": 100 * a["w"] / n,
                              "pf": pf_of(a["w"] / n),
                              "lo": pf_of(wlo), "hi": pf_of(whi), "r": a["r"]}

    names = [n for n, _ in TRACKS + EXTRA]
    for s in sorted(table, key=lambda k: -max(v["n"] for v in table[k].values())):
        print(f"\n### {s}")
        print(f"{'cadence':22} {'n':>7} {'WR%':>6} {'PF':>6} {'PF 95% CI':>15} {'totalR':>10}  verdict")
        for name in names:
            v = table[s].get(name)
            if not v:
                print(f"{name:22} {'—':>7}")
                continue
            if v["lo"] > 1:
                verdict = "PF>1 SIGNIFICANT"
            elif v["hi"] < 1:
                verdict = "PF<1 SIGNIFICANT"
            else:
                verdict = "indistinguishable from 1"
            print(f"{name:22} {v['n']:>7} {v['wr']:>5.1f}% {v['pf']:>6.2f} "
                  f"[{v['lo']:>5.2f},{v['hi']:>5.2f}] {v['r']:>+10.2f}  {verdict}")
    print("\nNote: the every-bar cadence resolves the same exit from many "
          "evaluation points,\nso its trade count and profit factor are "
          "overlapping samples, not\nindependent trades. It is shown for "
          "completeness, not for ranking.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
