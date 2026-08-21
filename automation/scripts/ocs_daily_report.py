#!/usr/bin/env python3
"""OCS BTC 5m - Daily report generator.

Reads trades.jsonl + stats.json, generates daily summary:
  - Total trades, win rate, avg R, profit factor
  - Per-level exit breakdown
  - Cumulative P&L curve
  - Best/worst trade
"""
from __future__ import annotations
import os
import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# Auto-detect repo path
if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

OCS_DIR = REPO / "automation" / "reports" / "ocs_btc_5m"
TRADES_FILE = OCS_DIR / "trades.jsonl"
STATS_FILE = OCS_DIR / "stats.json"
DAILY_DIR = OCS_DIR / "daily"


def load_trades():
    if not TRADES_FILE.exists():
        return []
    with TRADES_FILE.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def make_pnl_chart(trades, date_str, out_path):
    if not trades:
        return False
    rs = [t["R_multiple"] for t in trades]
    pnls = [t["pnl_usd"] for t in trades]
    cum_r = list(np.cumsum(rs))
    cum_pnl = list(np.cumsum(pnls))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    fig.suptitle(f"OCS BTC 5m - {date_str}", fontsize=14, fontweight="bold")

    ax1.plot(range(1, len(cum_r) + 1), cum_r, marker="o", color="steelblue", linewidth=2)
    ax1.axhline(0, color="gray", linestyle="--", alpha=0.5)
    ax1.set_ylabel("Cumulative R")
    ax1.set_title(f"Total R: {cum_r[-1]:+.2f}")
    ax1.grid(True, alpha=0.3)

    ax2.plot(range(1, len(cum_pnl) + 1), cum_pnl, marker="o", color="green", linewidth=2)
    ax2.axhline(0, color="gray", linestyle="--", alpha=0.5)
    ax2.set_xlabel("Trade #")
    ax2.set_ylabel("Cumulative P&L (USD)")
    ax2.set_title(f"Total P&L: ${cum_pnl[-1]:+,.0f}")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    fig.savefig(out_path, dpi=80, bbox_inches="tight")
    plt.close(fig)
    return True


def make_daily_markdown(trades, stats, date_str):
    if not trades:
        return f"""# OCS BTC 5m - {date_str}

**No trades today.**

Cumulative stats: {stats['n_trades']} trades | WR {stats['win_rate']}% | avg R {stats['avg_R']}
"""
    wins = [t for t in trades if t["R_multiple"] > 0]
    losses = [t for t in trades if t["R_multiple"] <= 0]
    best = max(trades, key=lambda t: t["R_multiple"])
    worst = min(trades, key=lambda t: t["R_multiple"])
    total_pnl = sum(t["pnl_usd"] for t in trades)
    total_r = sum(t["R_multiple"] for t in trades)
    avg_r = np.mean([t["R_multiple"] for t in trades])

    md = f"""# OCS BTC 5m - {date_str}

## Summary
- **Trades**: {len(trades)} ({len(wins)}W / {len(losses)}L)
- **Win Rate**: {len(wins) / len(trades) * 100:.1f}%
- **Total R**: {total_r:+.2f}R
- **Total P&L**: ${total_pnl:+,.0f}
- **Avg R**: {avg_r:+.2f}R
- **Profit Factor**: {stats['profit_factor']}

## Exit Breakdown
- T1 (+1.0R): {stats['t1_hits']}
- T2 (+1.618R): {stats['t2_hits']}
- T3 (+2.618R): {stats['t3_hits']}
- T4 (+3.618R): {stats['t4_hits']}
- T5 (+5.0R): {stats['t5_hits']}
- SL (-1.0R): {stats['sl_hits']}

## Best Trade
- **{best['direction'].upper()}** at {best['entry']:,.0f} -> {best['exit_level']} {best['exit_price']:,.0f}
- R = {best['R_multiple']:+.2f}, P&L = ${best['pnl_usd']:+,.0f}
- Held for {best['bars_held']} bars

## Worst Trade
- **{worst['direction'].upper()}** at {worst['entry']:,.0f} -> {worst['exit_level']} {worst['exit_price']:,.0f}
- R = {worst['R_multiple']:+.2f}, P&L = ${worst['pnl_usd']:+,.0f}
- Held for {worst['bars_held']} bars

## Cumulative Stats (Lifetime)
- Total trades: {stats['n_trades']}
- WR: {stats['win_rate']}%
- Avg R: {stats['avg_R']}
- Total R: {stats['total_R']:+.2f}R
- Profit Factor: {stats['profit_factor']}

## Chart
See `daily/{date_str}.png` for cumulative P&L curve.
"""
    return md


def main():
    trades = load_trades()
    if not STATS_FILE.exists():
        print("No stats.json found")
        return 0

    stats = json.loads(STATS_FILE.read_text())

    HKT = timezone(timedelta(hours=8))
    today_hkt = datetime.now(HKT).strftime("%Y-%m-%d")

    today_trades = [t for t in trades
                    if t.get("exit_time", "").startswith(today_hkt)]

    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    md_path = DAILY_DIR / f"{today_hkt}.md"
    png_path = DAILY_DIR / f"{today_hkt}.png"

    md_content = make_daily_markdown(today_trades, stats, today_hkt)
    md_path.write_text(md_content)
    print(f"Daily report: {md_path}")

    if make_pnl_chart(trades, today_hkt, png_path):
        print(f"Chart: {png_path}")
    else:
        print("No chart (no trades)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
