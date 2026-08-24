#!/usr/bin/env python3
"""OCS BTC 5m - Position tracker with R-multiple P&L.

Walks forward through open positions, checks if SL / T1-T5 has been hit.
On close: logs to trades.jsonl, updates stats.json, sends TG alert.
"""
from __future__ import annotations
import os
import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

# Polygon-preferred data source
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from data_source import fetch_bars_since as _fetch_bars_since_raw


# Auto-detect repo path: GHA uses $GITHUB_WORKSPACE, local uses /workspace
if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

OCS_DIR = REPO / "automation" / "reports" / "ocs_btc_5m"
POSITIONS_FILE = OCS_DIR / "positions.json"
TRADES_FILE = OCS_DIR / "trades.jsonl"
STATS_FILE = OCS_DIR / "stats.json"
SYMBOL = "BTC-USD"


def load_positions():
    if not POSITIONS_FILE.exists():
        return []
    return json.loads(POSITIONS_FILE.read_text())


def save_positions(positions):
    OCS_DIR.mkdir(parents=True, exist_ok=True)
    POSITIONS_FILE.write_text(json.dumps(positions, indent=2, default=str))


def load_trades():
    if not TRADES_FILE.exists():
        return []
    with TRADES_FILE.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def append_trade(trade):
    OCS_DIR.mkdir(parents=True, exist_ok=True)
    with TRADES_FILE.open("a") as f:
        f.write(json.dumps(trade, default=str) + "\n")


def compute_stats(trades):
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


def save_stats(stats):
    OCS_DIR.mkdir(parents=True, exist_ok=True)
    STATS_FILE.write_text(json.dumps(stats, indent=2))


def open_position_from_log():
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


def fetch_bars_since(start_iso, max_bars=5000):
    """Fetch 5m bars since start_iso (UTC) via polygon preferred, yfinance fallback."""
    return _fetch_bars_since_raw(SYMBOL, start_iso, interval_min=5, max_bars=max_bars)


def check_position_exit(pos, df):
    """Walk bars after entry, return first hit (SL or T1-T5) or None."""
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

        # SL priority: if both SL and any TP hit, assume SL
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
        print(f"\n[tracker] Checking {str(pos['signal_id'])[:20]}... ({pos['direction']} @ {pos['entry']:.2f})")
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
            # DEDUPE: only add to closed list + jsonl if not already in trades
            existing_trades_pre = load_trades()
            if trade["signal_id"] not in {t.get("signal_id") for t in existing_trades_pre}:
                closed.append(trade)
                append_trade(trade)
            else:
                print(f"  DEDUPE: signal_id {trade['signal_id'][:20]} already in trades.jsonl, skip")

    # Check for new signals to open (DEDUPED: skip if signal_id already closed)
    new_pos = open_position_from_log()
    if new_pos:
        existing_trades = load_trades()
        existing_open_ids = {p["signal_id"] for p in still_open}
        existing_closed_ids = {t.get("signal_id") for t in existing_trades}
        if new_pos["signal_id"] in existing_closed_ids:
            print(f"\n[tracker] Skip {str(new_pos['signal_id'])[:20]} — already closed in trades.jsonl")
        elif new_pos["signal_id"] in existing_open_ids:
            print(f"\n[tracker] Position already open: {str(new_pos['signal_id'])[:20]}")
        else:
            print(f"\n[tracker] New position: {str(new_pos['signal_id'])[:20]} "
                  f"({new_pos['direction']} @ {new_pos['entry']:.2f})")
            still_open.append(new_pos)

    save_positions(still_open)

    # Update stats
    all_trades = load_trades()
    stats = compute_stats(all_trades)
    save_stats(stats)
    print(f"\n[tracker] Stats: {stats['n_trades']} trades, WR {stats['win_rate']}%, "
          f"avg R {stats['avg_R']}, total R {stats['total_R']}")

    # TG notification on close (DEDUPED: skip signal_ids already in trades.jsonl)
    if closed:
        existing_trades = load_trades()
        existing_ids = {t.get("signal_id") for t in existing_trades}
        new_closes = [t for t in closed if t.get("signal_id") not in existing_ids]
        if not new_closes:
            print(f"[tracker] No new closes ({len(closed)} duplicate(s) skipped)")
        else:
            print(f"[tracker] {len(new_closes)} new close(s) ({len(closed) - len(new_closes)} duplicate(s) skipped)")
        try:
            import requests
            tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
            if tg_token and tg_chat and new_closes:
                lines = ["OCS BTC 5m - Position Closed\n"]
                for t in new_closes:
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
                r = requests.post(
                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                    json={"chat_id": tg_chat, "text": msg},
                    timeout=15,
                )
                print(f"[tracker] TG close alert sent: HTTP {r.status_code}")
        except Exception as e:
            print(f"[tracker] TG error: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
