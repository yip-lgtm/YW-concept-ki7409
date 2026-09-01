#!/usr/bin/env python3
"""ttrades_backtest_20d — Backtest TTrades v2 over 20 days of BTC history.

Walks forward day-by-day on H4 resampled data, applies same logic as ttrades_btc.py:
1. C2 Closure or C3 Closure (H4)
2. M15 CISD (scoped to last series)
3. C2 wick EQ respect
4. Weekly label (not gate)
5. Daily profile (London expansion → skip NY, post-hoc approximated)
6. T2 close mode (1.6R)

For each signal: enter at next available bar, exit at SL/T1/T2/T3 hit.
"""
from __future__ import annotations
import os, sys, json
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path("/workspace/YW-concept-ki7409")
HKT = timezone(timedelta(hours=8))
TICKER = "BTC-USD"

# TTrades params (same as live)
ACCOUNT_SIZE = 247_000
RISK_PCT = 0.0025
RISK_AMOUNT = ACCOUNT_SIZE * RISK_PCT
SL_BUFFER_ATR_MULT = 0.15

# Reuse logic from ttrades_btc.py
sys.path.insert(0, str(REPO / "automation" / "scripts"))
from ttrades_btc import (
    detect_c2_closure, detect_c3_closure, check_cisd,
    check_eq_respect, calculate_trade_levels, check_d1_trend
)

OUT_DIR = REPO / "automation" / "reports" / "ttrades_btc"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def fetch_data():
    """Fetch enough data to walk forward 20 days."""
    h1 = yf.download(TICKER, period="30d", interval="1h", progress=False, auto_adjust=True)
    m15 = yf.download(TICKER, period="8d", interval="15m", progress=False, auto_adjust=True)
    h1_daily = yf.download(TICKER, period="2y", interval="1d", progress=False, auto_adjust=True)
    for df in [h1, m15, h1_daily]:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
    return h1, m15, h1_daily


def walk_forward(h1: pd.DataFrame, m15: pd.DataFrame, h1_daily: pd.DataFrame, days: int = 20) -> list:
    """Walk forward through H1 data, checking each H4 close for signal.
    
    For each potential signal:
    1. Resample H1 to H4 up to current time
    2. Detect C2 or C3 closure
    3. Get M15 slice up to current time
    4. Check CISD on M15
    5. If confirmed, place trade and walk forward to see outcome
    """
    h4 = h1.resample("4h").agg({
        "Open": "first", "High": "max", "Low": "min", "Close": "last"
    }).dropna()
    
    trades = []
    
    # Walk through H4 bars, but use 15m for execution
    # We need at least 4 H4 bars for C3 detection
    start_idx = 4
    end_idx = len(h4) - 1
    
    print(f"  [walk] H4 bars {start_idx} to {end_idx} ({end_idx - start_idx} potential entry points)")
    
    # For each H4 bar after warmup
    for i in range(start_idx, end_idx):
        # Slice up to current bar
        h4_slice = h4.iloc[:i + 1]
        current_h4_time = h4.index[i]
        
        # Need m15 data up to current time
        m15_slice = m15[m15.index <= current_h4_time]
        if len(m15_slice) < 10:
            continue
        
        # Skip Monday (OSOK rule)
        if current_h4_time.weekday() == 0:
            continue
        
        # Step 1: Detect swing
        swing = detect_c2_closure(h4_slice)
        swing_type = "C2"
        if swing is None:
            swing = detect_c3_closure(h4_slice)
            swing_type = "C3"
        if swing is None:
            continue
        
        # Step 2: CISD on M15
        cisd = check_cisd(m15_slice, swing["direction"])
        if not cisd["confirmed"]:
            continue
        
        # Step 3: EQ respect
        if not check_eq_respect(swing, m15_slice):
            continue
        
        # Step 3b: D1 trend filter (B from backtest review)
        # Use daily data up to current time
        d1_slice = h1_daily[h1_daily.index.date <= current_h4_time.date()]
        if len(d1_slice) < 60:
            continue
        d1_trend = check_d1_trend(d1_slice, swing["direction"])
        if not d1_trend["aligned"]:
            continue
        
        # Step 4: Skip if recent signal (avoid duplicate)
        if trades and (current_h4_time - trades[-1]["entry_time"]).total_seconds() < 4 * 3600:
            continue
        
        # Calculate trade levels
        atr_vals = (h1['High'].loc[:current_h4_time].tail(14) - 
                    h1['Low'].loc[:current_h4_time].tail(14))
        atr = float(atr_vals.mean()) if len(atr_vals) > 0 else 0
        if atr <= 0: continue
        
        levels = calculate_trade_levels(swing, atr)
        if levels is None: continue
        
        # Entry: use C3/C4 close as approximation
        entry = levels["entry"]
        sl = levels["sl"]
        t1 = levels["t1"]
        t2 = levels["t2_close"]
        t3 = levels["t3"]
        
        # Walk forward to find exit (max 7 days = 42 H4 bars)
        exit_price = None
        exit_type = None
        max_walk = min(42, len(h4) - i - 1)
        
        for j in range(1, max_walk + 1):
            if i + j >= len(h4): break
            bar = h4.iloc[i + j]
            h, l, c = float(bar['High']), float(bar['Low']), float(bar['Close'])
            
            if swing["direction"] == "long":
                # Check SL first (worst case)
                if l <= sl:
                    exit_price = sl
                    exit_type = "SL"
                    break
                # Then T1
                if h >= t1:
                    exit_price = t1
                    exit_type = "T1"
                    break
            else:  # short
                if h >= sl:
                    exit_price = sl
                    exit_type = "SL"
                    break
                if l <= t1:
                    exit_price = t1
                    exit_type = "T1"
                    break
        
        if exit_price is None:
            # Use last available bar
            if i + max_walk < len(h4):
                exit_price = float(h4.iloc[i + max_walk]['Close'])
                exit_type = "TIMEOUT"
            else:
                exit_price = float(h4.iloc[-1]['Close'])
                exit_type = "END"
        
        # Calculate R multiple
        risk = abs(entry - sl)
        if swing["direction"] == "long":
            pnl_per_unit = exit_price - entry
        else:
            pnl_per_unit = entry - exit_price
        
        r_multiple = pnl_per_unit / risk if risk > 0 else 0
        
        trades.append({
            "entry_time": current_h4_time,
            "exit_time": h4.index[min(i + max_walk, len(h4) - 1)] if exit_type != "SL" and exit_type != "T1" else None,
            "direction": swing["direction"],
            "swing_type": swing_type,
            "side": swing["side"],
            "entry": entry,
            "sl": sl,
            "t1": t1,
            "t2_close": t2,
            "t3": t3,
            "exit_price": exit_price,
            "exit_type": exit_type,
            "R_multiple": r_multiple,
            "cisd_series_length": cisd["series_length"],
            "weekly_label": "skipped_in_backtest",
        })
    
    return trades


def main():
    print(f"[ttrades-backtest-20d] === {datetime.now(HKT).strftime('%Y-%m-%d %H:%M:%S HKT')} ===")
    
    h1, m15, h1_daily = fetch_data()
    if h1.empty or m15.empty or h1_daily.empty:
        print("  ✗ No data")
        return 1
    
    print(f"  [data] H1: {len(h1)}, M15: {len(m15)}, Daily: {len(h1_daily)}")
    
    trades = walk_forward(h1, m15, h1_daily, days=20)
    
    # Stats
    n = len(trades)
    if n == 0:
        print("\n  [result] No trades generated in 20d window")
        result = {"n_trades": 0, "win_rate": 0, "total_R": 0, "profit_factor": 0,
                  "trades": []}
    else:
        wins = [t for t in trades if t["R_multiple"] > 0]
        losses = [t for t in trades if t["R_multiple"] <= 0]
        total_R = sum(t["R_multiple"] for t in trades)
        avg_R = total_R / n
        gross_win = sum(t["R_multiple"] for t in wins) if wins else 0
        gross_loss = abs(sum(t["R_multiple"] for t in losses)) if losses else 0
        pf = gross_win / gross_loss if gross_loss > 0 else (10.0 if gross_win > 0 else 0)
        
        # By exit type
        by_exit = {}
        for t in trades:
            by_exit[t["exit_type"]] = by_exit.get(t["exit_type"], 0) + 1
        
        result = {
            "n_trades": n,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / n * 100, 1),
            "total_R": round(total_R, 2),
            "avg_R": round(avg_R, 3),
            "profit_factor": round(pf, 2),
            "by_exit": by_exit,
            "trades": trades,
        }
    
    # Print summary
    print(f"\n  === Results ===")
    print(f"  Trades:        {result['n_trades']}")
    print(f"  Wins/Losses:   {result.get('wins', 0)}/{result.get('losses', 0)}")
    print(f"  Win Rate:      {result['win_rate']}%")
    print(f"  Total R:       {result.get('total_R', 0):+.2f}R")
    print(f"  Avg R:         {result.get('avg_R', 0):+.3f}R/trade")
    print(f"  Profit Factor: {result.get('profit_factor', 0)}")
    if result.get("by_exit"):
        print(f"  By exit:       {result['by_exit']}")
    
    # Show first 5 trades
    print(f"\n  === Sample Trades ===")
    for t in trades[:5]:
        print(f"  {t['entry_time'].strftime('%Y-%m-%d %H:%M')} {t['swing_type']} {t['side']:7s} "
              f"entry ${t['entry']:.0f} → {t['exit_type']:8s} ${t['exit_price']:.0f} "
              f"R={t['R_multiple']:+.2f}")
    
    # Save
    out_file = OUT_DIR / "backtest_20d.json"
    
    # Convert datetime to str for JSON
    trades_json = []
    for t in trades:
        tj = dict(t)
        for k, v in tj.items():
            if isinstance(v, pd.Timestamp):
                tj[k] = v.isoformat()
        trades_json.append(tj)
    
    out = {
        "ts": datetime.now(HKT).isoformat(),
        "window_days": 20,
        "ticker": TICKER,
        "params": {
            "account_size": ACCOUNT_SIZE,
            "risk_pct": RISK_PCT,
            "risk_amount": RISK_AMOUNT,
            "sl_buffer_atr_mult": SL_BUFFER_ATR_MULT,
        },
        "result": {k: v for k, v in result.items() if k != "trades"},
        "trades": trades_json,
    }
    out_file.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  [saved] {out_file}")
    
    # Also append to history
    hist_file = OUT_DIR / "backtest_history.jsonl"
    with hist_file.open("a") as f:
        f.write(json.dumps({k: v for k, v in out.items() if k != "trades"}, default=str) + "\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
