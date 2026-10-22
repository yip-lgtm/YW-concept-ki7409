#!/usr/bin/env python3
"""Test position sizing and the real dollar P&L.

The book had no position sizing and recorded the price difference as
dollars, so every instrument was treated as $1 per point. That made the
live P&L wrong by 2x on MNQ and up to 100x on GC, and it made a single
BTC trade risk $154 against a $100 daily loss envelope.

This checks:

  1. the multipliers come from the config and match the contract specs
  2. a sized position risks the budget on every instrument, whatever
     the stop distance
  3. the tracker books a -1R stop as exactly the risk budget
  4. the old point-based figure is still reported, for comparison

No network, no API key.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "automation" / "scripts"))
sys.path.insert(0, str(REPO / "automation" / "src"))

import pandas as pd

# The tracker imports requests at module level; it never calls it here.
if "requests" not in sys.modules:
    import types as _types
    _stub = _types.ModuleType("requests")
    _stub.post = lambda *a, **k: None
    _stub.get = lambda *a, **k: None
    _stub.exceptions = _types.SimpleNamespace(HTTPError=Exception, Timeout=Exception)
    sys.modules["requests"] = _stub

import contract_specs as cs

spec = importlib.util.spec_from_file_location(
    "live_scan_tracker", str(REPO / "automation" / "scripts" / "live_scan_tracker.py"))
lst = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lst)

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILURES.append(msg)


EXPECTED = {"MES=F": 5.0, "MNQ=F": 2.0, "M2K=F": 5.0, "MYM=F": 0.5,
            "MGC=F": 10.0, "MCL=F": 100.0, "M6E=F": 12500.0, "GC=F": 100.0,
            "BTC-USD": 1.0}


def main() -> int:
    # 1. multipliers
    for tk, mult in EXPECTED.items():
        got = cs.usd_per_point(tk)
        check(abs(got - mult) < 1e-9, f"{tk} multiplier {got} != {mult}")
    print(f"[check] {len(EXPECTED)} contract multipliers match the specs")

    # 2. sizing puts exactly the budget at risk
    budget = cs.risk_budget_usd()
    for tk, dist in (("MNQ=F", 30.76), ("MES=F", 5.14), ("M2K=F", 2.39),
                     ("MGC=F", 6.72), ("GC=F", 5.85), ("BTC-USD", 140.27)):
        units, risk, _why = cs.size_position(tk, dist)
        check(units is not None, f"{tk}: could not size")
        check(abs(risk - budget) < 0.01, f"{tk}: risk {risk} != budget {budget}")
        check(abs(units * dist * cs.usd_per_point(tk) - budget) < 0.01,
              f"{tk}: sized position does not risk the budget")
    print(f"[check] every instrument sizes to a ${budget:.0f} risk")

    # the widest stop one contract can carry
    for tk, want in (("MES=F", 20.0), ("MNQ=F", 50.0), ("MGC=F", 10.0),
                     ("GC=F", 1.0), ("M6E=F", 0.008)):
        got = cs.max_stop_points(tk)
        check(abs(got - want) < 1e-6, f"{tk} max stop {got} != {want}")
    print("[check] max affordable stop distance matches the table")

    # 3. the tracker books a -1R stop as the budget
    tk = "MNQ=F"
    sl_dist = 34.97
    units, risk, _ = cs.size_position(tk, sl_dist)
    pos = {"direction": "short", "sl": 29943.97, "t1": 29874.03,
           "t2": 29852.42, "t3": 29800.0, "t4": 29700.0, "t5": 29600.0,
           "entry": 29909.0, "ticker": tk, "units": units,
           "usd_per_point": cs.usd_per_point(tk),
           "t2_r": 1.618, "breakeven_at_r": 0.0}
    df = pd.DataFrame([{"High": 29945.0, "Low": 29850.0}])
    res = lst.check_position_exit(pos, df)
    check(res is not None, "the tracker did not resolve an exit")
    if res:
        check(abs(res["pnl_usd"] + budget) < 0.01,
              f"a -1R stop was booked as ${res['pnl_usd']}, not -${budget}")
        check(abs(res["pnl_points"] + sl_dist) < 0.01,
              f"the point figure should still be {res['pnl_points']}")
        check(res["usd_per_point"] == 2.0, "the multiplier was not carried through")
        print(f"[check] a -1R stop books as ${res['pnl_usd']:.2f} "
              f"({res['pnl_points']:+.2f} points at {res['usd_per_point']:g}$/point)")

    if FAILURES:
        print("\nFAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\n✓ sizing and the real dollar P&L are correct")
    return 0


if __name__ == "__main__":
    sys.exit(main())
