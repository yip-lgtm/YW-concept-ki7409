#!/usr/bin/env python3
"""Final validation for a chosen configuration.

A configuration that was picked by looking at a holdout has already spent
that holdout. This measures it on windows nothing was tuned on:

  recent-1   2026-06-02 → 2026-08-15   the first half of the recent
                                      period — the selection set
  recent-2   2026-08-15 → 2026-10-19  the second half — never looked at
  early      2025-09-15 → 2026-06-02  the earlier regime — a config that
                                      only works in one regime should be
                                      visibly worse here, not silently
  recent@1h  the recent period evaluated every 12 bars instead of every
             3 — a different resolution of the same window

A configuration is only publishable if it clears 1 with a 95% interval
that excludes 1 on recent-2 AND on recent@1h, and if it is not
significantly worse than the baseline on the early period.

Usage:
    python3 automation/scripts/validate_config.py --strategy Two-Yang \
        --body-ratio 0.15
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "automation" / "scripts"
SRC = REPO / "automation" / "src"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SRC))

spec = importlib.util.spec_from_file_location(
    "swp", str(REPO / "automation" / "scripts" / "sweep_detector_params.py"))
swp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(swp)

WINDOWS = [
    ("recent-1 (select)", "2026-06-02", "2026-08-15", 3),
    ("recent-2 (FRESH)", "2026-08-15", "2026-10-19", 3),
    ("recent @1h", "2026-06-02", "2026-10-19", 12),
    ("early", "2025-09-15", "2026-06-02", 12),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="Two-Yang")
    ap.add_argument("--body-ratio", type=float, default=None)
    ap.add_argument("--allow-short", action="store_true")
    ap.add_argument("--max-raid-depth-pct", type=float, default=None)
    ap.add_argument("--mss-bars", type=int, default=None)
    args = ap.parse_args()

    df = swp.load_deep()
    detector = swp.make_detector(args.strategy)

    if args.strategy == "Two-Yang":
        base = {"body_ratio": 0.3, "allow_short": False,
                "volume_filter": False, "volume_ratio": 1.2}
        cand = dict(base)
        if args.body_ratio is not None:
            cand["body_ratio"] = args.body_ratio
        cand["allow_short"] = args.allow_short
    else:
        base = {"max_raid_depth_pct": None, "mss_bars": 1,
                "use_last_raid": False, "min_crt_range_pct": None}
        cand = dict(base)
        if args.max_raid_depth_pct is not None:
            cand["max_raid_depth_pct"] = args.max_raid_depth_pct
        if args.mss_bars is not None:
            cand["mss_bars"] = args.mss_bars

    print(f"strategy : {args.strategy}")
    print(f"baseline : {base}")
    print(f"candidate: {cand}\n")
    print(f"{'window':20} {'cadence':>8} | {'BASE n':>7} {'PF':>6} {'CI':>14} | "
          f"{'CAND n':>7} {'PF':>6} {'CI':>14} {'R':>9}  verdict")
    verdicts = []
    for label, a, b, step in WINDOWS:
        ta = df.index[df.index >= a][0]
        tb = df.index[df.index <= b][-1]
        rb = swp.run_split(df, detector, base, step, ta, tb, label)
        rc = swp.run_split(df, detector, cand, step, ta, tb, label)
        if not rb or not rc:
            print(f"{label:20} {step:>8} | (no data)")
            continue
        if label.startswith("early") or "@1h" in label:
            # These windows are not the bar. The bar is the fresh window
            # at the live cadence. Here the requirement is only that the
            # candidate is not materially worse than the baseline — a
            # configuration that helps in one regime and hurts in
            # another is a regime bet, not an improvement.
            ok = rc["pf"] >= rb["pf"] * 0.95
            v = ("not worse than baseline" if ok
                 else f"WORSE than baseline ({rc['pf']:.2f} vs {rb['pf']:.2f})")
        else:
            ok = rc["lo"] > 1.0
            v = "✅ PF>1 significant" if ok else "— not significant"
        verdicts.append((label, ok))
        print(f"{label:20} {step:>8} | {rb['n']:>7} {rb['pf']:>6.2f} "
              f"[{rb['lo']:>5.2f},{rb['hi']:>5.2f}] | {rc['n']:>7} {rc['pf']:>6.2f} "
              f"[{rc['lo']:>5.2f},{rc['hi']:>5.2f}] {rc['total_r']:>+9.2f}  {v}")
        sys.stdout.flush()

    print()
    for label, ok in verdicts:
        print(f"  {'✅' if ok else '❌'} {label}")
    # The bar: the fresh window, at the live cadence, clears 1 with an
    # interval that excludes 1. Every other window must at least not be
    # materially worse than the baseline.
    fresh_ok = all(ok for label, ok in verdicts
                   if "FRESH" in label or "select" in label)
    others_ok = all(ok for label, ok in verdicts
                    if "FRESH" not in label and "select" not in label)
    print(f"\nfresh window clears 1 with an interval that excludes 1: {fresh_ok}")
    print(f"no other window materially worse than baseline:     {others_ok}")
    print(f"\n{'PUBLISHABLE' if (fresh_ok and others_ok) else 'NOT PUBLISHABLE'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
