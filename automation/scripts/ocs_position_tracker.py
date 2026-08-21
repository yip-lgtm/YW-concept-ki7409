#!/usr/bin/env python3
"""OCS BTC 5m - Position tracker with R-multiple P&L.

Reads open positions from automation/reports/ocs_btc_5m/positions.json.
On every run (5 min), checks if SL / T1 / T2 / T3 / T4 / T5 has been hit
for each open position. If hit, closes position + records result to trades.jsonl
with P&L (USD) + R-multiple achieved.

Position lifecycle:
  1. OCS scan -> signal published -> entry at close price
  2. Each subsequent 5m bar: check if SL or any T-level hit
  3. First hit closes the position
  4. SL = -1R loss, T1 = +1R, T2 = +1.618R, T3 = +2.618R, T4 = +3.618R, T5 = +5.0R

State files:
  - positions.json: list of open positions
  - trades.jsonl: closed trades (append-only log)
  - stats.json: running statistics (win rate, avg R, profit factor)
"""
from __future__ import annotations
import os
import sys
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import numpy as np
import yfinance as yf


REPO = Path("/workspace/YW-concept-ki7409")
OCS_DIR = REPO / "automation" / "reports" / "ocs_btc_5m"
POSITIONS_FILE = OCS_DIR / "positions.json"
TRADES_FILE = OCS_DIR / "trades.jsonl"
STATS_FILE = OCS_DIR / "stats.json"
SYMBOL = "BTC-USD"


def load_positions() -> list:
    if not POSITIONS_FILE.exists():
        return []
    return json.loads(POSITIONS_FILE.read_text())


def save_positions(positions: list) -> None:
    OCS_DIR.mkdir(parents=True, exist_ok=True)
    POSITIONS_FILE.write_text(json.dumps(positions, indent=2, default=str))


def load_trades() -> list:
    if not TRADES_FILE.exists():
        return []
    with TRADES_FILE.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def append_trade(trade: dict) -> None:
    OCS_DIR.mkdir(parents=True, exist_ok=True)
    with TRADES_FILE.open("a") as f:
        f.write(json.dumps(trade, default=str) + "\n")


def compute_stats(trades: list) -> dict:
    if not trades:
        return {"n_trades": 0, "win_rate": 0, "avg_R": 0, "profit_factor": 0,
                "total_R": 0, "best_R": 0, "worst_R": 0}

    rs = [t["R_multiple"] for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]

    return {
        "n_trades": len(trades),
        "n_wins": len(wins),
        "n_losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "avg_R": round(float(np.mean(rs)), 3),
        "total_R": round(sum(rs), 2),
        "best_R": round(max(rs), 2),
        "worst_R": round(min(rs), 2),
        "profit_factor": round(sum(wins) / (abs(sum(losses)) + 1e-9), 2),
        "t1_hits": sum(1 for t in trades if t["exit_level"] == "T1"),
        "t2_hits": sum(1 for t in trades if t["exit_level"] == "T2"),
        "t3_hits": sum(1 for t in trades if t["exit_level"] == "T3"),
        "t4_hits": sum(1 for t in trades if t["exit_level"] == "T4"),
        "t5_hits": sum(1 for t in trades if t["exit_level"] == "T5"),
        "sl_hits": sum(1 for t in trades if t["exit_level"] == "SL"),
    }


def save_stats(stats: dict) -> None:
    OCS_DIR.mkdir(parents=True, exist_ok=True)
    STATS_FILE.write_text(json.dumps(stats, indent=2))


def open_position_from_log() -> dict:
    """Read latest OCS signal from latest.json and convert to open position."""
    latest_file = Path("/tmp/ocs_btc/latest.json")
    if not latest_file.exists():
        return None
    sig = json.loads(latest_file.read_text())
    if sig.get("signal") not in ("buy", "sell"):
        return None
    signal_id = sig.get("ts", datetime.now().isoformat())
    direction = sig.get("direction")
    entry = sig.get("last_close", 0)
    atr = sig.get("atr", 0)
    if entry == 0 or atr == 0:
        return None
    sl_dist = atr * 1.6
    sl = entry - sl_dist if direction == "long" else entry + sl_dist
    return {
        "signal_id": signal_id,
        "direction": direction,
        "entry": entry,
        "entry_time": sig.get("ts"),
        "atr": atr,
        "sl": sl,
        "t1": entry + sl_dist * 1.0 if direction == "long" else entry - sl_dist * 1.0,
        "t2": entry + sl_dist * 1.618 if direction == "long" else entry - sl_dist * 1.618,
        "t3": entry + sl_dist * 2.618 if direction == "long" else entry - sl_dist * 2.618,
        "t4": entry + sl_dist * 3.618 if direction == "long" else entry - sl_dist * 3.618,
        "t5": entry + sl_dist * 5.0 if direction == "long" else entry - sl_dist * 5.0,
        "sl_dist": sl_dist,
        "status": "open",
    }


def fetch_bars_since(start_iso: str, max_bars: int = 200) -> pd.DataFrame:
    """Fetch 5m bars since start_iso (UTC)."""
    df = yf.download(SYMBOL, period="5d", interval="5m",
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty:
        return df
    start = pd.Timestamp(start_iso)
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC")
    return df[df.index >= start].head(max_bars)


def check_position_exit(pos: dict, df: pd.DataFrame) -> dict:
    """Walk bars after entry, return first hit (SL or T1-T5) or None if still open."""
    direction = pos["direction"]
    sl = pos["sl"]
    t1, t2, t3, t4, t5 = pos["t1"], pos["t2"], pos["t3"], pos["t4"], pos["t5"]
    entry = pos["entry"]

    for i, (ts, bar) in enumerate(df.iterrows()):
        high = float(bar["High"])
        low = float(bar["Low"])
        if direction == "long":
            hit_sl = low <= sl
            hit_t1 = high >= t1
            hit_t2 = high >= t2
            hit_t3 = high >= t3
            hit_t4 = high >= t4
            hit_t5 = high >= t5
        else:
            hit_sl = high >= sl
            hit_t1 = low <= t1
            hit_t2 = low <= t2
            hit_t3 = low <= t3
            hit_t4 = low <= t4
            hit_t5 = low <= t5

        # SL priority: if both SL and any TP hit, assume SL (worst case)
        if hit_sl:
            exit_price = sl
            exit_level = "SL"
            R_multiple = -1.0
        elif hit_t1:
            exit_price = t1
            exit_level = "T1"
            R_multiple = 1.0
        elif hit_t2:
            exit_price = t2
            exit_level = "T2"
            R_multiple = 1.618
        elif hit_t3:
            exit_price = t3
            exit_level = "T3"
            R_multiple = 2.618
        elif hit_t4:
            exit_price = t4
            exit_level = "T4"
            R_multiple = 3.618
        elif hit_t5:
            exit_price = t5
            exit_level = "T5"
            R_multiple = 5.0
        else:
            continue

        pnl_usd = (exit_price - entry) * (1 if direction == "long" else -1)
        return {
            "exit_time": str(ts),
            "exit_price": exit_price,
            "exit_level": exit_level,
            "R_multiple": R_multiple,
            "pnl_usd": round(pnl_usd, 2),
            "bars_held": i + 1,
        }

    return None


def main():
    print(f"[tracker] Loading positions from {POSITIONS_FILE}")
    positions = load_positions()
    open_positions = [p for p in positions if p.get("status") == "open"]
    print(f"[tracker] {len(open_positions)} open position(s)")

    closed = []
    still_open = []

    for pos in open_positions:
        print(f"\n[tracker] Checking {pos['signal_id'][:20]}... ({pos['direction']} @ {pos['entry']:.2f})")
        df = fetch_bars_since(pos["entry_time"])
        if df.empty:
            print(f"  WARN: No bars since entry {pos['entry_time']}")
            still_open.append(pos)
            continue
        result = check_position_exit(pos, df)
        if result is None:
            current = float(df["Close"].iloc[-1])
            print(f"  Still open, current price {current:.2f}")
            still_open.append(pos)
        else:
            print(f"  Exit: {result['exit_level']} @ {result['exit_price']:.2f} "
                  f"R={result['R_multiple']:+.3f} bars={result['bars_held']}")
            trade = {**pos, **result, "status": "closed"}
            closed.append(trade)
            append_trade(trade)

    # Check for new signals to open
    new_pos = open_position_from_log()
    if new_pos:
        already = any(p["signal_id"] == new_pos["signal_id"] for p in still_open)
        if not already:
            print(f"\n[tracker] New position: {new_pos['signal_id'][:20]} "
                  f"({new_pos['direction']} @ {new_pos['entry']:.2f})")
            still_open.append(new_pos)
        else:
            print(f"\n[tracker] Position already open: {new_pos['signal_id'][:20]}")

    save_positions(still_open)

    # Update stats
    all_trades = load_trades()
    stats = compute_stats(all_trades)
    save_stats(stats)
    print(f"\n[tracker] Stats: {stats['n_trades']} trades, WR {stats['win_rate']}%, "
          f"avg R {stats['avg_R']}, total R {stats['total_R']}")

    # TG notification on close
    if closed:
        try:
            import requests
            tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
            if tg_token and tg_chat:
                lines = ["OCS BTC 5m - Position Closed\n"]
                for t in closed:
                    label = "WIN" if t["R_multiple"] > 0 else "LOSS"
                    lines.append(
                        f"{label}: {t['direction'].upper()} "
                        f"entry {t['entry']:,.0f} -> {t['exit_level']} {t['exit_price']:,.0f} | "
                        f"R={t['R_multiple']:+.2f} | ${t['pnl_usd']:+,.0f} | {t['bars_held']} bars"
                    )
                lines.append(
                    f"\nStats: {stats['n_trades']} trades | WR {stats['win_rate']}% | "
                    f"avg R {stats['avg_R']} | total R {stats['total_R']:+.1f} | "
                    f"PF {stats['profit_factor']}"
                )
                msg = "\n".join(lines)
                requests.post(
                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                    json={"chat_id": tg_chat, "text": msg},
                    timeout=15,
                )
                print("[tracker] TG close alert sent")
        except Exception as e:
            print(f"[tracker] TG error: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
