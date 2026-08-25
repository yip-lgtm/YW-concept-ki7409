#!/usr/bin/env python3
"""Live scan position tracker — walks forward 9-strategy positions.

Reads automation/reports/live_scan/positions.json, checks if any hit SL/T1-T5
since entry, and updates trades.jsonl + stats.json.

Mirrors OCS tracker logic but operates on the live_scan position file.
"""
from __future__ import annotations
import os
import sys
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

sys.path.insert(0, str(REPO / "automation" / "src"))
from data_source import fetch_bars as _fetch_bars

LS_DIR = REPO / "automation" / "reports" / "live_scan"
POSITIONS_FILE = LS_DIR / "positions.json"
TRADES_FILE = LS_DIR / "trades.jsonl"
STATS_FILE = LS_DIR / "stats.json"

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID")


def load_positions():
    if not POSITIONS_FILE.exists():
        return []
    return json.loads(POSITIONS_FILE.read_text())


def save_positions(positions):
    LS_DIR.mkdir(parents=True, exist_ok=True)
    POSITIONS_FILE.write_text(json.dumps(positions, indent=2, default=str))


def load_trades():
    if not TRADES_FILE.exists():
        return []
    with TRADES_FILE.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def append_trade(trade):
    LS_DIR.mkdir(parents=True, exist_ok=True)
    with TRADES_FILE.open("a") as f:
        f.write(json.dumps(trade, default=str) + "\n")


def compute_stats(trades):
    if not trades:
        return {"n_trades": 0, "win_rate": 0, "avg_R": 0, "profit_factor": 0,
                "total_R": 0, "best_R": 0, "worst_R": 0}
    rs = [t["R_multiple"] for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    import numpy as np
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
    }


def save_stats(stats):
    LS_DIR.mkdir(parents=True, exist_ok=True)
    STATS_FILE.write_text(json.dumps(stats, indent=2))


def fetch_bars_since(symbol: str, start_iso: str, max_bars=5000):
    """Fetch 5m bars since start_iso. Use longer window to be safe."""
    try:
        # Use 7d window to ensure we have data after entry
        df = _fetch_bars(symbol, days=7, interval_min=5)
        if df is None or df.empty:
            return None
        # Filter to start_iso - handle tz properly
        if start_iso:
            start = pd.Timestamp(start_iso)
            # If start has no tz, assume UTC
            if start.tzinfo is None:
                start = start.tz_localize("UTC")
            # df.index may be tz-aware (UTC) or naive
            if df.index.tz is None:
                start_naive = start.tz_convert(None) if start.tzinfo else start
                df = df[df.index >= start_naive]
            else:
                df = df[df.index >= start]
        if df is None or df.empty:
            return None
        return df.tail(max_bars)
    except Exception as e:
        print(f"  WARN: fetch_bars_since error: {e}", file=sys.stderr)
        return None


def check_position_exit(pos, df):
    """Walk bars after entry, return first hit (SL or T1-T5) or None."""
    direction = pos["direction"]
    sl = pos["sl"]
    t1, t2, t3, t4, t5 = pos["t1"], pos["t2"], pos["t3"], pos["t4"], pos["t5"]
    entry = pos["entry"]

    for i, (ts, bar) in enumerate(df.iterrows()):
        high = float(bar["High"])
        low = float(bar["Low"])
        if direction in ("long", "buy", "up"):
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
        pnl_usd = (exit_price - entry) * (1 if direction in ("long", "buy", "up") else -1)
        return {
            "exit_time": str(ts),
            "exit_price": exit_price,
            "exit_level": exit_level,
            "R_multiple": R_multiple,
            "pnl_usd": round(pnl_usd, 2),
            "bars_held": i + 1,
        }
    return None


def send_tg(text: str) -> int:
    if not TG_TOKEN or not TG_CHAT:
        return 0
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": text[:4000], "disable_web_page_preview": True},
            timeout=15,
        )
        return r.status_code
    except Exception as e:
        print(f"  [tg] error: {e}", file=sys.stderr)
        return 0


def main() -> int:
    print(f"[live-tracker] {datetime.now(timezone.utc).isoformat()}")
    positions = load_positions()
    open_positions = [p for p in positions if p.get("status") == "open"]
    print(f"[live-tracker] {len(open_positions)} open position(s)")

    closed = []
    still_open = []
    for pos in open_positions:
        ticker = pos["ticker"]
        entry_time = pos["entry_time"]
        print(f"\n[live-tracker] Checking {pos['strategy']} {ticker} ({pos['direction']} @ {pos['entry']:.2f})")
        df = fetch_bars_since(ticker, entry_time)
        if df is None or df.empty:
            print(f"  WARN: No bars since entry")
            still_open.append(pos)
            continue
        result = check_position_exit(pos, df)
        if result is None:
            current = float(df["Close"].iloc[-1])
            print(f"  Still open, current {current:.2f}")
            still_open.append(pos)
        else:
            print(f"  Exit: {result['exit_level']} @ {result['exit_price']:.2f} R={result['R_multiple']:+.2f}")
            trade = {**pos, **result, "status": "closed"}
            # DEDUPE by signal_id
            existing = load_trades()
            existing_ids = {t.get("signal_id") for t in existing}
            if trade["signal_id"] not in existing_ids:
                closed.append(trade)
                append_trade(trade)
            else:
                print(f"  DEDUPE: signal_id already in trades.jsonl, skip")

    save_positions(still_open)
    all_trades = load_trades()
    stats = compute_stats(all_trades)
    save_stats(stats)
    print(f"\n[live-tracker] Stats: {stats['n_trades']} trades, WR {stats['win_rate']}%, "
          f"avg R {stats['avg_R']}, total R {stats['total_R']}")

    # TG on close - closed[] is already deduped by loop above
    if closed:
            lines = ["<b>🎯 9-Strategy Live — Trade Journey Closed</b>\n"]
            for t in closed:
                label = "WIN ✅" if t["R_multiple"] > 0 else "LOSS ❌"
                emoji = "🟢" if t["R_multiple"] > 0 else "🔴"
                entry_time = t.get('entry_time', '?')[:19]
                exit_time = t.get('exit_time', '?')[:19]
                # Calculate duration
                try:
                    et = datetime.fromisoformat(t['entry_time'].replace('Z', '+00:00') if t['entry_time'].endswith('Z') else t['entry_time'])
                    xt = datetime.fromisoformat(t['exit_time'].replace('Z', '+00:00') if t['exit_time'].endswith('Z') else t['exit_time'])
                    duration = xt - et
                    mins = int(duration.total_seconds() // 60)
                    duration_str = f"{mins}min" if mins < 60 else f"{mins//60}h{mins%60}m"
                except Exception:
                    duration_str = "?"

                # Build full journey
                lines.append(
                    f"{emoji} <b>{label}: {t['strategy']}</b> [{t.get('grade','?')}] {t['ticker']}\n"
                    f"\n"
                    f"📊 <b>Signal</b>\n"
                    f"  Grade: {t.get('grade','?')} | Conf: {t.get('confidence', 0)} | ATR: ${t.get('atr', 0):.2f}\n"
                    f"  {t.get('reason', '')[:150]}\n"
                    f"\n"
                    f"📈 <b>Position Opened</b>\n"
                    f"  {t['direction'].upper()} {t['ticker']} @ ${t['entry']:,.2f}\n"
                    f"  Time: {entry_time} UTC\n"
                    f"  SL: ${t['sl']:,.2f} | T1: ${t['t1']:,.2f} | T5: ${t.get('t5', 0):,.2f}\n"
                    f"\n"
                    f"🎯 <b>Position Closed</b>\n"
                    f"  Exit: {t['exit_level']} @ ${t['exit_price']:,.2f}\n"
                    f"  Time: {exit_time} UTC\n"
                    f"  Held: {t['bars_held']} bars ({duration_str})\n"
                    f"\n"
                    f"💰 <b>P&L</b>\n"
                    f"  R-multiple: {t['R_multiple']:+.2f}R\n"
                    f"  Cash: ${t['pnl_usd']:+,.2f}\n"
                    f"  Equity impact: {t['R_multiple']:+.2f}R of 1.6×ATR risk"
                )
            lines.append(
                f"\n📈 <b>Running Stats</b>\n"
                f"  Trades: {stats['n_trades']} | WR: {stats['win_rate']}%\n"
                f"  Total R: {stats['total_R']:+.1f} | Avg R: {stats['avg_R']:+.2f}\n"
                f"  Profit Factor: {stats['profit_factor']:.2f}"
            )
            send_tg("\n".join(lines))
            print(f"[live-tracker] TG: {len(closed)} new close(s) with full journey")

    return 0


if __name__ == "__main__":
    sys.exit(main())
