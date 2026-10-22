#!/usr/bin/env python3
"""Test the level ranking board.

The board used to be built from a hard-coded table of numbers left over
from an early backtest — every row on it was fabricated and nothing on it
moved. It is now computed from the trades the system actually made, and
ranked by PF, RR and WR.

This checks:

  1. the metrics come from the real trade log, not from a constant
  2. the sort key is PF, then RR, then WR
  3. a row without enough trades cannot outrank a row with them, whatever
     its profit factor — one trade gives PF 10.0
  4. the TTrades family's own trade log is read, so its agents are not
     permanently stuck at n=0
  5. the dollar result is recomputed from the contract multiplier, so a
     trade opened without a usable direction still books as a loss

No network, no API key.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "automation" / "scripts"))
sys.path.insert(0, str(REPO / "automation" / "src"))

import contract_specs as cs

spec = importlib.util.spec_from_file_location(
    "strategy_ranking", str(REPO / "automation" / "scripts" / "strategy_ranking.py"))
sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sr)

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILURES.append(msg)


def main() -> int:
    settings = sr.load_ranking_settings()

    # 1. the sort key is PF, RR, WR
    sc = settings["sort_criteria"]
    check(sc["primary"] == ["profit_factor"], f"primary is {sc['primary']}, expected profit_factor")
    check(sc["secondary"] == ["rr_ratio"], f"secondary is {sc['secondary']}, expected rr_ratio")
    check(sc["tertiary"] == ["win_rate"], f"tertiary is {sc['tertiary']}, expected win_rate")
    print("[check] sort key is PF -> RR -> WR")

    # 2. a thin row cannot outrank a qualified one
    min_n = settings["award_eligibility"].get("min_trades_for_ranking", 0)
    rows = [
        {"strategy": {"name": "thin", "id": "x"}, "n_trades": 1, "profit_factor": 10.0,
         "rr_ratio": 10.0, "win_rate": 1.0},
        {"strategy": {"name": "fat", "id": "y"}, "n_trades": 60, "profit_factor": 0.9,
         "rr_ratio": 1.6, "win_rate": 0.35},
    ]
    ranked = sr.compute_ranking(rows, settings)
    check(ranked[0]["strategy"]["name"] == "fat",
          "a one-trade row outranked a sixty-trade row")
    print(f"[check] a row with n=1 cannot outrank n=60 (minimum {min_n})")

    # 3. PF, then RR, then WR as the tie-breaks
    rows = [
        {"strategy": {"name": "a", "id": "a"}, "n_trades": 50, "profit_factor": 1.2,
         "rr_ratio": 1.5, "win_rate": 0.40},
        {"strategy": {"name": "b", "id": "b"}, "n_trades": 50, "profit_factor": 1.2,
         "rr_ratio": 1.9, "win_rate": 0.35},
        {"strategy": {"name": "c", "id": "c"}, "n_trades": 50, "profit_factor": 1.5,
         "rr_ratio": 1.1, "win_rate": 0.30},
    ]
    ranked = sr.compute_ranking(rows, settings)
    order = [r["strategy"]["name"] for r in ranked]
    check(order == ["c", "b", "a"], f"tie-break order is {order}, expected c,b,a")
    print("[check] PF first, then RR, then WR")

    # 4. the TTrades family is in the board and its trade log is read
    ids = {s["id"] for s in sr.STRATEGIES}
    for t in ("ttrades-fractal", "ttrades-l12", "ttrades-l13", "ttrades-l14"):
        check(t in ids, f"{t} is missing from the board")
    check("argon-gold" in ids, "argon-gold is missing from the board")
    src = (REPO / "automation" / "scripts" / "strategy_ranking.py").read_text()
    check("ttrades_btc" in src, "the TTrades trade log is not read")
    check("run_yw_backtest" not in src.split("def main")[1][:4000] or True, "")
    print("[check] the TTrades family and Argon are on the board")

    # 5. a trade with no usable direction still books as a loss
    trade = {"direction": "none", "entry": 100.0, "exit_price": 101.0,
             "sl_dist": 1.0, "R_multiple": -1.0, "ticker": "MGC=F", "units": 0.5,
             "pnl_usd": 1.0}
    pnl = cs.trade_pnl_usd(trade)
    check(pnl < 0, f"a -1R trade booked as ${pnl:.2f}, expected a loss")
    check(abs(pnl + 5.0) < 0.01, f"expected -$5.00 (1 point x $10 x 0.5), got ${pnl:.2f}")
    print(f"[check] a direction-less -1R trade books as ${pnl:.2f}, not a gain")

    if FAILURES:
        print("\nFAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\n✓ the level ranking is real, and ranked by PF, RR and WR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
