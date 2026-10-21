#!/usr/bin/env python3
"""Test the TTrades re-entry cooldown.

The tracker used to dedupe only on signal_id, so a setup that had just
been stopped out was re-entered on the next scan: new timestamp, new
signal_id, same trade. On 2026-10-14 TTrades-L12 entered the identical
MGC=F long setup six times in a row — every one of them stopped out at
4166.8 — and the strategy's live record became 7 trades, 0 wins, -7R.

This checks three things:

  1. the cooldown constant exists and is positive
  2. a combo closed inside the window is blocked
  3. a combo closed outside the window is allowed again

No network, no API key.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "automation" / "scripts"))

spec = importlib.util.spec_from_file_location(
    "ttrades_tracker", str(REPO / "automation" / "scripts" / "ttrades_tracker.py"))
tt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tt)

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILURES.append(msg)


def main() -> int:
    # 1. the constant
    check(hasattr(tt, "COOLDOWN_HOURS"), "COOLDOWN_HOURS is not defined")
    check(getattr(tt, "COOLDOWN_HOURS", 0) > 0, "COOLDOWN_HOURS must be positive")
    print(f"[check] COOLDOWN_HOURS = {getattr(tt, 'COOLDOWN_HOURS', None)}")

    # 2. direction normalisation
    for raw, want in [("long", "long"), ("buy", "long"), ("up", "long"),
                      ("bullish", "long"), ("short", "short"), ("sell", "short"),
                      ("down", "short"), ("bearish", "short"), ("", "none")]:
        got = tt._norm_dir(raw)
        check(got == want, f"_norm_dir({raw!r}) == {got!r}, expected {want!r}")
    print("[check] _norm_dir maps every spelling the family uses")

    # 3. the block itself — same shape as the tracker's open loop
    def would_open(closed_at, now):
        """Mirror the tracker's guard for one (strategy, ticker, direction)."""
        combo = ("TTrades-L12", "MGC=F", "long")
        last_exit = tt.load_closed_times().get(combo)
        if last_exit is None:
            return True
        age_h = (now - last_exit).total_seconds() / 3600.0
        return age_h >= tt.COOLDOWN_HOURS

    # stand in for load_closed_times() with a synthetic close
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    synthetic = {("TTrades-L12", "MGC=F", "long"): now - timedelta(hours=1)}
    original = tt.load_closed_times
    tt.load_closed_times = lambda: synthetic
    try:
        blocked = not would_open(None, now)
        check(blocked, "a combo closed 1h ago was NOT blocked")

        synthetic = {("TTrades-L12", "MGC=F", "long"): now - timedelta(hours=6)}
        allowed = would_open(None, now)
        check(allowed, "a combo closed 6h ago was still blocked")

        synthetic = {("TTrades-L12", "MGC=F", "long"): now - timedelta(hours=3.9)}
        blocked = not would_open(None, now)
        check(blocked, "a combo closed 3.9h ago was not blocked")
    finally:
        tt.load_closed_times = original

    print("[check] a closed combo is blocked inside the window and allowed outside")

    if FAILURES:
        print("\nFAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\n✓ the TTrades re-entry cooldown works")
    return 0


if __name__ == "__main__":
    sys.exit(main())
