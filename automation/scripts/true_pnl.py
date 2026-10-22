#!/usr/bin/env python3
"""What the live book actually made, in dollars.

The tracker recorded `pnl_usd = (exit_price - entry) * sign` — the price
difference with no contract multiplier and no position size. Every
instrument was therefore treated as $1 per point, which is right for
BTC-USD and wrong by 2x on MNQ, 5x on MES and M2K, 10x on MGC and 100x
on GC.

This recomputes the same trades with the real multipliers from
automation/config/contract_specs.json, and reports the risk each trade
carried against the account's $100 loss envelope.

Usage:
    python3 automation/scripts/true_pnl.py
    python3 automation/scripts/true_pnl.py --recent-days 7
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPECS = REPO / "automation" / "config" / "contract_specs.json"
TRADES = REPO / "automation" / "reports" / "live_scan" / "trades.jsonl"


def load_specs():
    d = json.loads(SPECS.read_text())
    return d.get("specs", {}), d.get("_risk_budget_usd", 100)


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recent-days", type=int, default=0,
                    help="only the last N days (0 = all)")
    args = ap.parse_args()

    specs, budget = load_specs()
    if not TRADES.exists():
        print(f"no trades at {TRADES}", file=sys.stderr)
        return 1

    cut = None
    if args.recent_days:
        cut = datetime.now(timezone.utc) - timedelta(days=args.recent_days)

    per = defaultdict(lambda: {"n": 0, "w": 0, "r": 0.0,
                               "pnl_booked": 0.0, "pnl_true": 0.0,
                               "risk": 0.0, "max_risk": 0.0,
                               "over_budget": 0})
    unknown = defaultdict(int)
    for line in TRADES.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line or line[0] in "<=>":
            continue
        try:
            t = json.loads(line)
        except Exception:
            continue
        if t.get("status") != "closed":
            continue
        ts = parse_ts(t.get("exit_time")) or parse_ts(t.get("entry_time"))
        if cut and (ts is None or ts < cut):
            continue
        tk = t.get("ticker")
        spec = specs.get(tk)
        if spec is None:
            unknown[tk] += 1
            continue
        mult = float(spec["usd_per_point"])
        sl = t.get("sl_dist")
        entry, exit_ = t.get("entry"), t.get("exit_price")
        booked = t.get("pnl_usd")
        a = per[tk]
        a["n"] += 1
        r = t.get("R_multiple")
        if r is not None:
            r = float(r)
            a["r"] += r
            if r > 0:
                a["w"] += 1
        if booked is not None:
            a["pnl_booked"] += float(booked)
        # the real dollar result: the same price move times the multiplier
        if entry is not None and exit_ is not None:
            sign = 1 if t.get("direction") in ("long", "buy", "up", "bullish") else -1
            a["pnl_true"] += sign * (float(exit_) - float(entry)) * mult
        if sl:
            risk = float(sl) * mult
            a["risk"] += risk
            a["max_risk"] = max(a["max_risk"], risk)
            if risk > budget:
                a["over_budget"] += 1

    print(f"{'ticker':9} {'n':>5} {'mult':>7} {'WR%':>6} {'totalR':>8} "
          f"{'帳面 pnl$':>12} {'真實 pnl$':>12} {'平均風險$':>11} {'最大風險$':>11} {'超額':>5}")
    tb = tt = tr = 0.0
    for tk in sorted(per, key=lambda k: -per[k]["n"]):
        a = per[tk]
        mult = specs[tk]["usd_per_point"]
        print(f"{tk:9} {a['n']:>5} {mult:>7.2f} {100*a['w']/a['n']:>5.1f}% {a['r']:>+8.2f} "
              f"{a['pnl_booked']:>+12,.2f} {a['pnl_true']:>+12,.2f} "
              f"{a['risk']/a['n']:>11,.2f} {a['max_risk']:>11,.2f} {a['over_budget']:>5}")
        tb += a["pnl_booked"]
        tt += a["pnl_true"]
        tr += a["r"]
    print(f"{'TOTAL':9} {sum(a['n'] for a in per.values()):>5} {'':>7} {'':>6} {tr:>+8.2f} "
          f"{tb:>+12,.2f} {tt:>+12,.2f}")
    print(f"\n帳面 pnl$ 同真實 pnl$ 差 {tt - tb:>+,.2f}")
    if unknown:
        print(f"冇乘數嘅標的（唔計入）: {dict(unknown)}")
    print(f"風險預算 ${budget}/單 —— 上表「最大風險$」係單筆最大，超過 ${budget} 即係一單食晒日蝕上限")
    return 0


if __name__ == "__main__":
    sys.exit(main())
