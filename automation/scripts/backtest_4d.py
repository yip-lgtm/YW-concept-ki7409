#!/usr/bin/env python3
"""4-day rolling backtest for all 9 strategies.

Loads 4d of 5min data per ticker, runs each detector, simulates SL/TP hits.
Returns per-strategy ranking by PF / WR / R.
"""
from __future__ import annotations
import os, sys, json, argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings("ignore")

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

sys.path.insert(0, str(REPO / "automation/src"))

import pandas as pd
import numpy as np
import yfinance as yf
import requests

# 9 strategies with detector function + tickers
STRATEGIES = [
    {"id": "h-pattern",       "ticker": "MNQ=F", "fn": None, "module": "yw_indicators",       "fn_name": "detect_h_pattern"},
    {"id": "3-pushes",        "ticker": "MNQ=F", "fn": None, "module": "yw_indicators",       "fn_name": "detect_3_pushes"},
    {"id": "two-yang",        "ticker": "MNQ=F", "fn": None, "module": "yw_indicators",       "fn_name": "detect_two_yang_one_yin"},
    {"id": "rsi-div",         "ticker": "MNQ=F", "fn": None, "module": "yw_indicators",       "fn_name": "detect_rsi_divergence"},
    {"id": "50-20-pullback",  "ticker": "MNQ=F", "fn": None, "module": "yw_indicators",       "fn_name": "detect_5020_pullback"},
    {"id": "stair-pattern",   "ticker": "MNQ=F", "fn": None, "module": "yw_indicators_extra", "fn_name": "detect_stair_pattern"},
    {"id": "crt",             "ticker": "MNQ=F", "fn": None, "module": "yw_indicators_extra", "fn_name": "detect_crt", "needs_4h": True},
    {"id": "kell-cycle",      "ticker": "MNQ=F", "fn": None, "module": "yw_indicators_extra", "fn_name": "detect_kell_setups"},
    {"id": "ocs-btc",         "ticker": "BTC-USD", "fn": None, "module": "ocs_btc_5m",         "fn_name": "compute_signal", "skip": True},
]

def get_data(ticker: str, days: int = 4):
    """Fetch 5min data for last N days."""
    df = yf.download(ticker, period=f"{days}d", interval="5m", progress=False, auto_adjust=True)
    if hasattr(df.columns, 'levels'):
        df.columns = df.columns.get_level_values(0)
    return df

def normalize(detection: dict) -> dict:
    """Normalize detector output to {present, direction, strength}."""
    if not isinstance(detection, dict):
        return {"present": False, "direction": "none"}
    if "present" in detection and "direction" in detection:
        return {"present": bool(detection["present"]), "direction": detection.get("direction", "none"), "strength": detection.get("strength", 0)}
    # Custom formats
    if "type" in detection:  # RSI div
        present = detection.get("type") in ("bullish", "bearish")
        return {"present": present, "direction": detection.get("type", "none"), "strength": detection.get("strength", 0)}
    if "cross_type" in detection:  # 50/20 pullback
        return {"present": detection.get("pullback") == "at_ema20", "direction": "long" if detection.get("trend") == "up" else "short", "strength": 50}
    if "reversal_extension" in detection:  # Kell (5 sub)
        any_present = any(v.get("present", False) for v in detection.values() if isinstance(v, dict))
        first_dir = next((v.get("direction") for v in detection.values() if isinstance(v, dict) and v.get("present")), "none")
        return {"present": any_present, "direction": first_dir, "strength": 60}
    return {"present": False, "direction": "none", "raw": detection}

def backtest_strategy(strategy: dict, days: int = 4) -> dict:
    """Run rolling backtest on a single strategy."""
    # Import
    try:
        mod = __import__(strategy["module"])
        fn = getattr(mod, strategy["fn_name"])
    except Exception as e:
        return {"strategy": strategy["id"], "error": f"import: {e}", "n_trades": 0, "win_rate": 0, "total_R": 0, "profit_factor": 0}

    # Load data
    try:
        df = get_data(strategy["ticker"], days)
    except Exception as e:
        return {"strategy": strategy["id"], "error": f"data: {e}", "n_trades": 0, "win_rate": 0, "total_R": 0, "profit_factor": 0}
    
    if df.empty or len(df) < 50:
        return {"strategy": strategy["id"], "error": "insufficient data", "n_trades": 0, "win_rate": 0, "total_R": 0, "profit_factor": 0}

    # Walk forward: every 5min, run detector, simulate trade
    trades = []
    step = 6  # check every 30min
    cooldown = 12  # 1hr cooldown after each trade
    last_trade_bar = -cooldown
    atr_period = 14
    df["ATR"] = (df["High"] - df["Low"]).rolling(atr_period).mean()

    for i in range(50, len(df), step):
        if i - last_trade_bar < cooldown:
            continue
        window = df.iloc[max(0, i-100):i+1]
        if len(window) < 50:
            continue

        # Detect
        try:
            if strategy.get("needs_4h"):
                df_4h = window.resample("4H").agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum","ATR":"mean"}).dropna()
                if len(df_4h) < 2:
                    continue
                det = fn(df_4h, window)
            else:
                det = fn(window)
        except Exception as e:
            continue

        norm = normalize(det)
        if not norm["present"]:
            continue
        if norm["direction"] in ("none", None):
            continue

        # Simulate trade
        entry = float(df["Close"].iloc[i])
        atr = float(df["ATR"].iloc[i]) if not pd.isna(df["ATR"].iloc[i]) else entry * 0.002
        sl_dist = atr * 1.6
        if norm["direction"] in ("long", "up", "bullish"):
            sl = entry - sl_dist
            tps = [entry + sl_dist * m for m in (1.0, 1.618, 2.618, 3.618, 5.0)]
        else:
            sl = entry + sl_dist
            tps = [entry - sl_dist * m for m in (1.0, 1.618, 2.618, 3.618, 5.0)]

        # Walk forward 24 bars (2hr max)
        exit_price = None
        exit_level = None
        bars_held = 0
        for j in range(i+1, min(i+25, len(df))):
            high = float(df["High"].iloc[j])
            low = float(df["Low"].iloc[j])
            close = float(df["Close"].iloc[j])
            bars_held += 1
            if norm["direction"] in ("long", "up", "bullish"):
                if low <= sl:
                    exit_price = sl
                    exit_level = "SL"
                    break
                if high >= tps[0]:
                    exit_price = tps[0]
                    exit_level = "T1"
                    break
            else:
                if high >= sl:
                    exit_price = sl
                    exit_level = "SL"
                    break
                if low <= tps[0]:
                    exit_price = tps[0]
                    exit_level = "T1"
                    break
        if exit_price is None:
            exit_price = float(df["Close"].iloc[min(i+24, len(df)-1)])
            exit_level = "TIMEOUT"

        if norm["direction"] in ("long", "up", "bullish"):
            r = (exit_price - entry) / sl_dist
        else:
            r = (entry - exit_price) / sl_dist
        trades.append({"entry": entry, "exit": exit_price, "R": r, "level": exit_level, "bars": bars_held})
        last_trade_bar = i

    if not trades:
        return {"strategy": strategy["id"], "n_trades": 0, "win_rate": 0, "total_R": 0, "profit_factor": 0}

    n = len(trades)
    wins = sum(1 for t in trades if t["R"] > 0)
    wr = wins / n * 100
    total_r = sum(t["R"] for t in trades)
    gw = sum(t["R"] for t in trades if t["R"] > 0)
    gl = abs(sum(t["R"] for t in trades if t["R"] <= 0))
    pf = gw / (gl + 1e-9) if gl > 0 else (10.0 if gw > 0 else 1.0)
    pf = min(pf, 10.0)

    return {
        "strategy": strategy["id"],
        "ticker": strategy["ticker"],
        "n_trades": n,
        "win_rate": round(wr, 1),
        "total_R": round(total_r, 2),
        "profit_factor": round(pf, 2),
        "avg_R": round(total_r / n, 3),
        "wins": wins,
        "losses": n - wins,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=4, help="Backtest window in days")
    parser.add_argument("--tg", action="store_true", help="Send to TG")
    args = parser.parse_args()

    HKT = timezone(timedelta(hours=8))
    ts = datetime.now(HKT).strftime("%Y%m%d_%H%M%S")
    today = datetime.now(HKT).strftime("%Y-%m-%d")

    print(f"[backtest-{args.days}d] Running 9 strategies × {args.days}d window @ {ts} HKT\n")

    # Run in parallel
    results = []
    with ThreadPoolExecutor(max_workers=9) as executor:
        futures = {executor.submit(backtest_strategy, s, args.days): s for s in STRATEGIES}
        for future in as_completed(futures):
            s = futures[future]
            try:
                r = future.result()
                results.append(r)
                if "error" in r:
                    print(f"  ❌ {s['id']:20s} {r.get('error', '?')[:50]}")
                else:
                    print(f"  {s['id']:20s} {r['n_trades']:3d} trades WR {r['win_rate']:5.1f}% R {r['total_R']:+5.2f} PF {r['profit_factor']:.2f}")
            except Exception as e:
                print(f"  💥 {s['id']}: {e}")
                results.append({"strategy": s["id"], "error": str(e), "n_trades": 0})

    # Sort
    results.sort(key=lambda r: (-r.get("profit_factor", 0), -r.get("total_R", 0)))

    # Save
    out_dir = REPO / "automation/reports/strategy_ranking"
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "date": today,
        "window_days": args.days,
        "timestamp": ts,
        "strategies": results,
    }
    out = out_dir / f"backtest_{args.days}d_{today}.json"
    out.write_text(json.dumps(data, indent=2, default=str))
    print(f"\n[backtest] Saved: {out}")

    # MD
    md = [f"# {args.days}-Day Backtest — {today}\n",
          f"**9 strategies** backtested on {args.days}d of 5min data per ticker.\n",
          "| Rank | Strategy | Ticker | N | W-L | WR | Total R | PF |",
          "|------|----------|--------|---|-----|----|---------|-----|"]
    for i, r in enumerate(results, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}"
        if "error" in r:
            md.append(f"| {medal} | {r['strategy']} | - | - | - | - | - | ERROR: {r['error'][:40]} |")
        elif r.get("n_trades", 0) == 0:
            md.append(f"| {medal} | {r['strategy']} | {r.get('ticker','?')} | 0 | 0-0 | - | +0.00R | - |")
        else:
            md.append(f"| {medal} | {r['strategy']} | {r.get('ticker','?')} | {r['n_trades']} | {r['wins']}-{r['losses']} | {r['win_rate']:.1f}% | {r['total_R']:+.2f}R | {r['profit_factor']:.2f} |")
    md_path = out_dir / f"backtest_{args.days}d_{today}.md"
    md_path.write_text("\n".join(md) + "\n")
    print(f"          {md_path}")

    # TG
    if args.tg:
        n_with_data = sum(1 for r in results if r.get('n_trades', 0) > 0)
        lines = [f"📊 {args.days}-Day Backtest — {today}\n",
                 f"  {n_with_data}/9 strats 有 trades ({args.days}d × 5min)\n"]
        for i, r in enumerate(results, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f" {i}."
            if "error" in r:
                lines.append(f"{medal} {r['strategy']:18s} ❌ {r['error'][:50]}")
            elif r.get('n_trades', 0) == 0:
                lines.append(f"{medal} {r['strategy']:18s} ⚪ 0 trades")
            else:
                lines.append(f"{medal} {r['strategy']:18s} {r['n_trades']:2d} trades WR {r['win_rate']:5.1f}% R {r['total_R']:+.2f} PF {r['profit_factor']:.2f}")
        r = requests.post(
            f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
            json={"chat_id": os.environ['TELEGRAM_CHAT_ID'], "text": "\n".join(lines)},
            timeout=15,
        )
        print(f"\n[backtest] TG: msg_id {r.json().get('result', {}).get('message_id', 'N/A')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
