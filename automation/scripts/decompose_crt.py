#!/usr/bin/env python3
"""Separate the period effect from the cadence effect.

CRT looked like the only strategy with an edge above 1 on all three
real five-minute tracks: PF 1.32 at a 4-hour cadence, 1.15 at an hourly
one, 1.11 at the 15-minute one the live system actually uses. But split
the history and the picture changes — the first 65% looks good and the
last 35% does not.

Those two are different variables. The split changed the period AND the
cadence at the same time, so it cannot say which one did it. This runs
the same configuration over both halves at all three cadences, and over
the whole history at all three, so the two effects are separable.

Usage:
    python3 automation/scripts/decompose_crt.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "automation" / "scripts"))
sys.path.insert(0, str(REPO / "automation" / "src"))

import importlib.util

spec = importlib.util.spec_from_file_location(
    "swp", str(REPO / "automation" / "scripts" / "sweep_detector_params.py"))
swp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(swp)

from yw_indicators_extra import detect_crt

CFG = {"max_raid_depth_pct": None, "mss_bars": 1, "use_last_raid": False,
       "min_crt_range_pct": None}


def main() -> int:
    df = swp.load_deep()
    split_at = df.index[int(len(df) * swp.TRAIN_FRACTION)]
    halves = [
        ("first 65%", df.index[0], split_at),
        ("last 35%", split_at, df.index[-1]),
        ("whole", df.index[0], df.index[-1]),
    ]
    print(f"deep 5m bars {len(df)}  {df.index[0].date()} → {df.index[-1].date()}")
    print(f"split at {split_at.date()}\n")
    print(f"{'period':12} {'step':>5} {'cadence':>10} {'n':>7} {'WR%':>6} {'PF':>6} "
          f"{'PF 95% CI':>15} {'totalR':>9}")
    for label, a, b in halves:
        for step, cad in ((48, "4h"), (12, "1h"), (3, "15m/live")):
            r = swp.run_split(df, detect_crt, CFG, step, a, b, label)
            if not r:
                print(f"{label:12} {step:>5} {cad:>10}  (no data)")
                continue
            print(f"{label:12} {step:>5} {cad:>10} {r['n']:>7} {100*r['wr']:>5.1f}% "
                  f"{r['pf']:>6.2f} [{r['lo']:>5.2f},{r['hi']:>5.2f}] {r['total_r']:>+9.2f}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
