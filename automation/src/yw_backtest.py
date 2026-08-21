#!/usr/bin/env python3
"""YW Concept backtester — validate strategy win rates on historical data.

Walks through 60 days of 5min OHLCV data, runs each strategy detector
on every bar, simulates a trade with fixed SL/TP, computes per-strategy
win rate + total PNL.

Usage:
  python3 yw_backtest.py [--ticker MNQ=F] [--days 60] [--sl 100] [--tp 150] [--strategy H-Pattern]

Output: JSON stats per strategy + console summary.
"""
from __future__ import annotations
import sys
import os
import json
import time
import argparse
from pathlib import Path

import pandas as pd
import numpy as np
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent))

from yw_indicators import compute_ma
from yw_indicators_extra import (
    detect_crt, detect_stair_pattern, detect_kell_setups,
)


STRATEGIES = ["H-Pattern", "3-Pushes", "Two-Yang-One-Yin", "RSI-Divergence",
              "50-20-Pullback", "Stair-Pattern", "Kell-Cycle"]


def detect_on_bar(strategy: str, df: pd.DataFrame, idx: int, df_4h: pd.DataFrame | None) -> dict:
    """Run a strategy detector on data up to and including bar idx.

    Returns {signal: bool, direction: "long"/"short", entry: float, ...}
    """
    if idx < 50:
        return {"signal": False}
    window = df.iloc[:idx+1]
    last = window.iloc[-1]

    if strategy == "H-Pattern":
        from yw_indicators import detect_h_pattern
        r = detect_h_pattern(window)
        if r.get("present") and r.get("broke_low"):
            return {
                "signal": True, "direction": "short",
                "entry": float(last["Close"]),
                "strength": 70,
                "details": str(r)[:100],
            }
    elif strategy == "3-Pushes":
        from yw_indicators import detect_3_pushes
        r = detect_3_pushes(window)
        if r.get("present") and r.get("narrowing"):
            return {
                "signal": True, "direction": r.get("direction", "long"),
                "entry": float(last["Close"]),
                "strength": 70,
                "details": str(r)[:100],
            }
    elif strategy == "RSI-Divergence":
        from yw_indicators import detect_rsi_divergence
        r = detect_rsi_divergence(window)
        if r.get("type") in ("bullish", "bearish") and r.get("strength", 0) > 30:
            return {
                "signal": True,
                "direction": "long" if r["type"] == "bullish" else "short",
                "entry": float(last["Close"]),
                "strength": r["strength"],
                "details": f"RSI div {r['type']} str {r['strength']:.0f}",
            }
    elif strategy == "50-20-Pullback":
        from yw_indicators import detect_5020_pullback
        r = detect_5020_pullback(window)
        if r.get("cross_type") == "golden" and r.get("pullback") in ("near_ema20", "at_ema20"):
            return {
                "signal": True, "direction": "long",
                "entry": float(last["Close"]),
                "strength": 70,
                "details": f"golden cross, pullback {r.get('pullback')}",
            }
        elif r.get("cross_type") == "death" and r.get("pullback") in ("near_ema20", "at_ema20"):
            return {
                "signal": True, "direction": "short",
                "entry": float(last["Close"]),
                "strength": 70,
                "details": f"death cross, pullback {r.get('pullback')}",
            }
    elif strategy == "Stair-Pattern":
        r = detect_stair_pattern(window)
        if r.get("present"):
            return {
                "signal": True, "direction": r.get("direction", "short"),
                "entry": float(last["Close"]),
                "strength": r.get("strength", 60),
                "details": f"stair wicks={r.get('wick_count', '?')}",
            }
    elif strategy == "Kell-Cycle":
        r = detect_kell_setups(window)
        active = []
        for k in ["reversal_extension", "wedge_pop_drop", "ema_crossback", "base_n_break"]:
            if r.get(k, {}).get("present"):
                active.append(k)
        if active:
            return {
                "signal": True, "direction": r[active[0]].get("direction", "long"),
                "entry": float(last["Close"]),
                "strength": 70,
                "details": f"kell: {','.join(active)}",
            }
    elif strategy == "3-Pushes":
        from yw_indicators import detect_3_pushes
        r = detect_3_pushes(window)
        if r.get("present"):
            return {
                "signal": True, "direction": r.get("direction", "long"),
                "entry": float(last["Close"]),
                "strength": 70,
                "details": f"3-pushes {r.get('direction')}",
            }
    elif strategy == "Two-Yang-One-Yin":
        from yw_indicators import detect_two_yang_one_yin
        r = detect_two_yang_one_yin(window)
        if r.get("present"):
            return {
                "signal": True, "direction": r.get("direction", "long"),
                "entry": float(last["Close"]),
                "strength": r.get("strength", 70),
                "details": r.get("details", ""),
            }
    elif strategy == "CRT":
        if df_4h is None or len(df_4h) < 2:
            return {"signal": False}
        r = detect_crt(df_4h, window)
        if r.get("present"):
            return {
                "signal": True, "direction": r.get("direction", "long"),
                "entry": float(last["Close"]),
                "strength": r.get("strength", 80),
                "details": str(r)[:100],
            }

    return {"signal": False}


def simulate_trade(direction: str, entry: float, sl_dollars: float, tp_dollars: float,
                   future_bars: pd.DataFrame) -> dict:
    """Walk forward and find SL/TP hit. Returns {pnl, exit, bars_held}."""
    if direction == "long":
        sl_price = entry - sl_dollars
        tp_price = entry + tp_dollars
    else:
        sl_price = entry + sl_dollars
        tp_price = entry - tp_dollars

    for i, (_, bar) in enumerate(future_bars.iterrows()):
        if direction == "long":
            hit_sl = bar["Low"] <= sl_price
            hit_tp = bar["High"] >= tp_price
        else:
            hit_sl = bar["High"] >= sl_price
            hit_tp = bar["Low"] <= tp_price
        if hit_sl and hit_tp:
            # Both hit same bar — assume SL (worst case)
            return {"pnl": -sl_dollars, "exit": "sl_same_bar", "bars_held": i + 1}
        if hit_sl:
            return {"pnl": -sl_dollars, "exit": "sl", "bars_held": i + 1}
        if hit_tp:
            return {"pnl": tp_dollars, "exit": "tp", "bars_held": i + 1}

    # No hit within window — close at last bar
    if direction == "long":
        pnl = float(future_bars["Close"].iloc[-1] - entry)
    else:
        pnl = float(entry - future_bars["Close"].iloc[-1])
    # Cap at SL/TP for EOD
    pnl = max(-sl_dollars, min(tp_dollars, pnl))
    return {"pnl": pnl, "exit": "eod", "bars_held": len(future_bars)}


def backtest_strategy(strategy: str, ticker: str, days: int, sl_dollars: float,
                     tp_dollars: float, cooldown_bars: int = 12,
                     max_bars_lookahead: int = 48) -> dict:
    """Run a backtest for one strategy on one ticker.

    cooldown_bars: minimum bars between trades (avoid over-trading)
    max_bars_lookahead: max bars to look forward for SL/TP
    """
    print(f"  [{strategy}] downloading {ticker} {days}d 5m...")
    df = yf.download(ticker, period=f"{days}d", interval="5m",
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty or len(df) < 100:
        return {"strategy": strategy, "ticker": ticker, "error": "insufficient data"}

    # For CRT, also get 4H data
    df_4h = None
    if strategy == "CRT":
        df_4h_raw = yf.download(ticker, period=f"{days + 7}d", interval="1h",
                                progress=False, auto_adjust=True)
        if isinstance(df_4h_raw.columns, pd.MultiIndex):
            df_4h_raw.columns = df_4h_raw.columns.get_level_values(0)
        if not df_4h_raw.empty:
            df_4h = df_4h_raw.resample("4h").agg({
                "Open": "first", "High": "max", "Low": "min",
                "Close": "last", "Volume": "sum"
            }).dropna()

    trades = []
    last_trade_bar = -cooldown_bars
    print(f"  [{strategy}] walking {len(df)} bars...")

    for idx in range(60, len(df) - max_bars_lookahead):
        if idx - last_trade_bar < cooldown_bars:
            continue
        # 4H context for CRT
        if strategy == "CRT" and df_4h is not None:
            current_time = df.index[idx]
            df_4h_window = df_4h[df_4h.index <= current_time]
        else:
            df_4h_window = None
        sig = detect_on_bar(strategy, df, idx, df_4h_window)
        if not sig.get("signal"):
            continue
        # Skip if direction unclear
        if sig.get("direction") not in ("long", "short"):
            continue
        # Simulate trade
        future = df.iloc[idx+1:idx+1+max_bars_lookahead]
        if len(future) < 1:
            continue
        result = simulate_trade(sig["direction"], sig["entry"], sl_dollars, tp_dollars, future)
        result["entry_time"] = str(df.index[idx])
        result["direction"] = sig["direction"]
        result["entry_price"] = sig["entry"]
        result["strategy_detail"] = sig.get("details", "")
        trades.append(result)
        last_trade_bar = idx

    if not trades:
        return {
            "strategy": strategy, "ticker": ticker, "n_trades": 0,
            "win_rate": 0, "total_pnl": 0, "avg_pnl": 0,
        }

    n = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in trades)
    return {
        "strategy": strategy,
        "ticker": ticker,
        "n_trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / n * 100, 1) if n else 0,
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(total_pnl / n, 2) if n else 0,
        "avg_bars_held": round(sum(t["bars_held"] for t in trades) / n, 1),
        "max_win": round(max(t["pnl"] for t in trades), 2),
        "max_loss": round(min(t["pnl"] for t in trades), 2),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="MNQ=F", help="Ticker to backtest")
    parser.add_argument("--days", type=int, default=60, help="Days of history")
    parser.add_argument("--sl", type=float, default=100, help="SL in $")
    parser.add_argument("--tp", type=float, default=150, help="TP in $")
    parser.add_argument("--strategies", nargs="+", default=STRATEGIES,
                        help="Strategies to backtest")
    parser.add_argument("--out", help="Output JSON file")
    args = parser.parse_args()

    print(f"YW Backtest: {args.ticker} {args.days}d, SL ${args.sl} TP ${args.tp}")
    results = []
    for sk in args.strategies:
        print(f"\n=== {sk} ===")
        r = backtest_strategy(sk, args.ticker, args.days, args.sl, args.tp)
        results.append(r)
        if r.get("n_trades", 0) > 0:
            print(f"  N={r['n_trades']:>3} WR={r['win_rate']:>5.1f}% "
                  f"PNL=${r['total_pnl']:>+8.0f} avg=${r['avg_pnl']:>+6.1f} "
                  f"avg_bars={r['avg_bars_held']:.0f}")
        else:
            print(f"  No trades")

    # Summary table
    print("\n" + "=" * 80)
    print(f"{'Strategy':<22} {'N':>4} {'WR%':>6} {'PNL$':>10} {'Avg$':>8} {'MaxWin':>8} {'MaxLoss':>8}")
    print("-" * 80)
    for r in results:
        if r.get("n_trades", 0) > 0:
            print(f"{r['strategy']:<22} {r['n_trades']:>4} {r['win_rate']:>6.1f} "
                  f"{r['total_pnl']:>+10.0f} {r['avg_pnl']:>+8.1f} "
                  f"{r.get('max_win',0):>+8.0f} {r.get('max_loss',0):>+8.0f}")

    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2))
        print(f"\nSaved: {args.out}")


if __name__ == "__main__":
    main()
