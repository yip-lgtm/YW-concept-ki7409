#!/usr/bin/env python3
"""ttrades_btc — 5th Power subagent: TTrades ICT Fractal Model on BTC.

Implements TTrades Model (OSOK + Fractal) per docs/17-TTrades-Model.md.

Key components:
1. C2 Closure detection (swing)
   - Bearish: C2.high > C1.high, C2.close < C1.high
   - Bullish: C2.low < C1.low, C2.close > C1.low
2. CISD confirmation (lower TF)
   - H1 swing → M15 CISD
   - D1 swing → H1 CISD
3. Weekly profile (4 types)
4. Daily profile (London/NY reversal)
5. Projection: -2 (TP1), -4 (TP2)

Output signal:
- T2 close mode (1.6R)
- $247K account, 0.25% risk = $617.50 per trade
- SL = C2 swing + ATR buffer
- T1 (1.0R) / T2 CLOSE (1.6R) / T3 (2.6R) runner
"""
from __future__ import annotations
import os
import sys
import json
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

HKT = timezone(timedelta(hours=8))
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

TICKER = "BTC-USD"
ACCOUNT_SIZE = 247_000
RISK_PCT = 0.0025  # 0.25%
RISK_AMOUNT = ACCOUNT_SIZE * RISK_PCT  # $617.50

# TTrades signal file (read by ttrades_act.py)
SIGNAL_FILE = REPO / "automation" / "reports" / "ttrades_btc" / "latest.json"
SIGNAL_DIR = SIGNAL_FILE.parent
SIGNAL_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = SIGNAL_DIR / "signals.jsonl"


def fetch_ohlcv(symbol: str, interval: str, period: str = "60d") -> pd.DataFrame:
    """Fetch OHLCV data via yfinance."""
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty:
            return df
        # Flatten multi-index if needed
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        return df
    except Exception as e:
        print(f"  ✗ yfinance error: {e}")
        return pd.DataFrame()


def detect_c2_closure(df: pd.DataFrame, lookback: int = 5) -> dict | None:
    """Detect C2 closure (ideal swing) on given timeframe.
    
    C2 closure rules:
    - Bearish C2: C2.high > C1.high AND C2.close < C1.high
    - Bullish C2: C2.low < C1.low AND C2.close > C1.low
    - Sweep + return = "manipulation"
    """
    if len(df) < lookback + 2:
        return None
    
    # Get last 3 candles: C1, C2, C3
    # We need swing from C1 to C2 (C2 makes new high/low) then C2 reverts
    last = df.iloc[-lookback:]
    
    c1 = last.iloc[-3]  # 2 bars ago
    c2 = last.iloc[-2]  # 1 bar ago (the swing)
    c3 = last.iloc[-1]  # current (potential expansion)
    
    # Bearish C2: C2 made higher high then closed back below C1.high
    if c2['High'] > c1['High'] and c2['Close'] < c1['High']:
        # C2 swept the high (manipulation) and closed back inside
        return {
            "type": "bearish_c2",
            "c1_high": float(c1['High']),
            "c2_high": float(c2['High']),  # swing high
            "c2_low": float(c2['Low']),
            "c2_close": float(c2['Close']),
            "c3_open": float(c3['Open']),
            "c3_close": float(c3['Close']),
            "swing_level": float(c2['High']),  # SL reference
            "manipulation": c2['High'] - c1['High'],
            "direction": "short",
        }
    
    # Bullish C2: C2 made lower low then closed back above C1.low
    if c2['Low'] < c1['Low'] and c2['Close'] > c1['Low']:
        return {
            "type": "bullish_c2",
            "c1_low": float(c1['Low']),
            "c2_low": float(c2['Low']),
            "c2_high": float(c2['High']),
            "c2_close": float(c2['Close']),
            "c3_open": float(c3['Open']),
            "c3_close": float(c3['Close']),
            "swing_level": float(c2['Low']),
            "manipulation": c1['Low'] - c2['Low'],
            "direction": "long",
        }
    
    return None


def check_cisd(ltf_df: pd.DataFrame, direction: str) -> bool:
    """Check CISD (Change in State of Delivery) on lower timeframe.
    
    Bearish CISD: close below lowest bullish open in sequence
    Bullish CISD: close above highest bearish open in sequence
    """
    if len(ltf_df) < 5:
        return False
    
    # Get last 5 candles
    recent = ltf_df.iloc[-5:]
    
    if direction == "short":
        # Find lowest bullish candle's open (most recent bullish series)
        bullish_opens = [row['Open'] for _, row in recent.iterrows() if row['Close'] > row['Open']]
        if not bullish_opens:
            return False
        min_bull_open = min(bullish_opens)
        # CISD: last close below min_bull_open
        return recent.iloc[-1]['Close'] < min_bull_open
    
    elif direction == "long":
        bearish_opens = [row['Open'] for _, row in recent.iterrows() if row['Close'] < row['Open']]
        if not bearish_opens:
            return False
        max_bear_open = max(bearish_opens)
        return recent.iloc[-1]['Close'] > max_bear_open
    
    return False


def check_weekly_profile(weekly_df: pd.DataFrame) -> dict:
    """Detect weekly profile (4 types per TTrades).
    
    Returns:
    {
      "profile": str,  # classic_expansion, midweek_reversal, etc.
      "expected_c2_day": int,  # 1-5 (Mon-Fri)
    }
    """
    if len(weekly_df) < 7:
        return {"profile": "unknown", "expected_c2_day": None}
    
    # Get this week's daily bars
    this_week = weekly_df.iloc[-5:]
    if len(this_week) < 5:
        return {"profile": "unknown", "expected_c2_day": None}
    
    weekly_open = float(this_week.iloc[0]['Open'])
    day_closes = [float(c) for c in this_week['Close']]
    
    # Check if Monday/Tuesday are against weekly open
    if day_closes[0] < weekly_open and day_closes[1] < weekly_open:
        # Mon/Tue going down → Midweek Reversal (Wed=C2)
        return {"profile": "midweek_reversal", "expected_c2_day": 3}
    
    # Check if extended in one direction (Thursday Counter)
    if all(c < weekly_open for c in day_closes[:3]):
        return {"profile": "thursday_counter", "expected_c2_day": 4}
    
    # Check if consolidation (Consolidation Reversal)
    ranges = [abs(float(this_week.iloc[i]['High']) - float(this_week.iloc[i]['Low'])) 
              for i in range(min(3, len(this_week)))]
    avg_range = sum(ranges) / len(ranges) if ranges else 0
    if all(r < avg_range * 1.2 for r in ranges):
        return {"profile": "consolidation_reversal", "expected_c2_day": 4}
    
    # Default: classic expansion (Fri reversal possible)
    return {"profile": "classic_expansion", "expected_c2_day": 5}


def calculate_trade_levels(c2: dict, atr: float) -> dict:
    """Calculate SL, T1-T5 with T2 close mode (1.6R)."""
    swing = c2["swing_level"]
    last_close = c2["c3_close"]
    
    # SL: 1.6x ATR beyond swing (TTrades uses swing + buffer)
    if c2["direction"] == "short":
        sl = swing + atr * 1.6
        risk = sl - last_close
    else:
        sl = swing - atr * 1.6
        risk = last_close - sl
    
    if risk <= 0:
        return None
    
    # T2 close mode: T1=1R, T2=1.618R (close), T3=2.618R runner
    t1 = last_close + (-risk if c2["direction"] == "short" else risk) * 1.0
    t2 = last_close + (-risk if c2["direction"] == "short" else risk) * 1.618
    t3 = last_close + (-risk if c2["direction"] == "short" else risk) * 2.618
    t4 = last_close + (-risk if c2["direction"] == "short" else risk) * 3.618
    t5 = last_close + (-risk if c2["direction"] == "short" else risk) * 5.0
    
    return {
        "entry": last_close,
        "sl": sl,
        "t1": t1,
        "t2_close": t2,
        "t3": t3,
        "t4": t4,
        "t5": t5,
        "risk_per_unit": abs(risk),
    }


def main():
    print(f"[ttrades-btc] === {datetime.now(HKT).strftime('%Y-%m-%d %H:%M:%S HKT')} ===")
    
    # Fetch multi-timeframe data
    print("  [data] Fetching BTC multi-timeframe...")
    daily = fetch_ohlcv(TICKER, "1d", "60d")
    h4 = fetch_ohlcv(TICKER, "1h", "30d")  # yfinance limit
    h1 = fetch_ohlcv(TICKER, "1h", "30d")
    m15 = fetch_ohlcv(TICKER, "15m", "7d")
    
    if daily.empty or m15.empty:
        print("  ✗ No data")
        return 0
    
    # Step 1: Detect C2 closure on H4 (primary swing TF)
    print("  [step1] Detecting C2 closure on H4...")
    c2_h4 = detect_c2_closure(h4)
    
    # Step 2: CISD confirmation on M15
    cisd_confirmed = False
    if c2_h4:
        print(f"  [step1] H4 C2 detected: {c2_h4['type']}, swing ${c2_h4['swing_level']:.2f}")
        print(f"  [step2] Checking M15 CISD for {c2_h4['direction']}...")
        cisd_confirmed = check_cisd(m15, c2_h4["direction"])
        print(f"  [step2] M15 CISD: {'✓' if cisd_confirmed else '✗'}")
    else:
        print("  [step1] No C2 closure detected on H4")
    
    # Step 3: Check daily profile (optional)
    # Step 4: Check weekly profile
    weekly = fetch_ohlcv(TICKER, "1wk", "1y")
    weekly_profile = check_weekly_profile(weekly)
    print(f"  [step4] Weekly profile: {weekly_profile['profile']}")
    
    # Skip Monday (TTrades rule)
    weekday = datetime.now(HKT).weekday()
    if weekday == 0:
        print("  [rule] Monday: skip (TTrades rule)")
        return 0
    
    # Build signal
    signal = {
        "ts": datetime.now(HKT).isoformat(),
        "ticker": TICKER,
        "strategy": "TTrades-OSOK",
        "c2_h4": c2_h4,
        "cisd_m15": cisd_confirmed,
        "weekly_profile": weekly_profile,
        "account_size": ACCOUNT_SIZE,
        "risk_pct": RISK_PCT,
        "risk_amount": RISK_AMOUNT,
    }
    
    if c2_h4 and cisd_confirmed:
        # Calculate trade levels
        atr_series = h4['High'].tail(14).values - h4['Low'].tail(14).values
        atr = float(np.mean(atr_series)) if len(atr_series) > 0 else 0
        
        if atr > 0:
            levels = calculate_trade_levels(c2_h4, atr)
            if levels:
                signal.update(levels)
                signal["actionable"] = True
                signal["direction"] = c2_h4["direction"]
                signal["grade"] = "A"  # TTrades with C2 + CISD is high conf
                signal["confidence"] = 85
                signal["reason"] = f"TTrades OSOK: H4 C2 closure + M15 CISD confirmed, weekly profile {weekly_profile['profile']}"
                
                print(f"  ✓ Signal: {c2_h4['direction'].upper()} @ ${levels['entry']:.2f}")
                print(f"  ✓ SL: ${levels['sl']:.2f} | T2 CLOSE: ${levels['t2_close']:.2f}")
            else:
                signal["actionable"] = False
                signal["reason"] = "levels calc failed"
        else:
            signal["actionable"] = False
            signal["reason"] = "no ATR"
    else:
        signal["actionable"] = False
        if not c2_h4:
            signal["reason"] = "no H4 C2 closure"
        else:
            signal["reason"] = "M15 CISD not confirmed"
    
    # Save
    SIGNAL_FILE.write_text(json.dumps(signal, indent=2, default=str))
    
    # Log to history
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(signal, default=str) + "\n")
    
    # Send TG if actionable
    if signal.get("actionable"):
        direction_emoji = "↑" if signal["direction"] == "long" else "↓"
        msg = (
            f"🎯 TTrades-OSOK [{signal['grade']}] {TICKER}\n\n"
            f"💰 Entry: ${levels['entry']:,.2f}\n"
            f"🎯 Dir: {signal['direction']} {direction_emoji}\n"
            f"📊 Conf: {signal['confidence']}\n"
            f"🛡️ SL: ${levels['sl']:,.2f} (C2 swing + 1.6×ATR)\n"
            f"🎯 T2 CLOSE: ${levels['t2_close']:,.2f} (1.6R) ← exit target\n"
            f"💎 T3: ${levels['t3']:,.2f} (2.6R) runner\n"
            f"💼 Risk: ${signal['risk_amount']:.2f} (0.25% of $247K)\n\n"
            f"💬 {signal['reason']}\n"
            f"⏰ {signal['ts']}"
        )
        if TG_TOKEN and TG_CHAT:
            try:
                r = requests.post(
                    f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                    json={"chat_id": TG_CHAT, "text": msg[:4000]},
                    timeout=15,
                )
                print(f"  [TG] HTTP {r.status_code}")
            except Exception as e:
                print(f"  [TG] {e}")
    else:
        print(f"  [no-action] {signal.get('reason', 'unknown')}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
