#!/usr/bin/env python3
"""ttrades_btc — 5th Power: TTrades ICT Fractal Model on BTC (per docs/17).

v2 corrections (after user review of v1):
- CISD scoped to consecutive bullish/bearish series only
- C3 Closure fallback when C2 didn't return to C1
- C2 wick EQ respect check (price on correct side of EQ)
- Weekly profile is LABEL only, never hard-gate
  - classic_expansion only valid on/after Thu
  - Tue/Wed: 'early_week' label, doesn't block
- SL = C2 swing + 0.15×ATR buffer (not 1.6×ATR)
- Daily profile check: London expanded → skip NY
- Manipulation -2 / -4 projection targets
- Position sizing: $617.50 / risk_per_unit = units
"""
from __future__ import annotations
import os, sys, json, requests
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
RISK_PCT = 0.0025
RISK_AMOUNT = ACCOUNT_SIZE * RISK_PCT  # $617.50

SIGNAL_DIR = REPO / "automation" / "reports" / "ttrades_btc"
SIGNAL_DIR.mkdir(parents=True, exist_ok=True)
SIGNAL_FILE = SIGNAL_DIR / "latest.json"
LOG_FILE = SIGNAL_DIR / "signals.jsonl"


def fetch_ohlcv(symbol, interval, period="60d"):
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty: return df
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        return df
    except Exception as e:
        print(f"  ✗ yfinance: {e}")
        return pd.DataFrame()


def detect_c2_closure(df):
    """H4 C2 Closure: sweep C1 extreme + close back inside."""
    if len(df) < 3: return None
    c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    
    if c2['High'] > c1['High'] and c2['Close'] < c1['High']:
        eq = (float(c2['High']) + float(c2['Low'])) / 2
        return {"type": "c2_closure", "side": "bearish",
                "c2_high": float(c2['High']), "c2_low": float(c2['Low']),
                "c2_close": float(c2['Close']), "c2_eq": eq,
                "c3_close": float(c3['Close']),
                "swing_level": float(c2['High']), "direction": "short"}
    if c2['Low'] < c1['Low'] and c2['Close'] > c1['Low']:
        eq = (float(c2['High']) + float(c2['Low'])) / 2
        return {"type": "c2_closure", "side": "bullish",
                "c2_high": float(c2['High']), "c2_low": float(c2['Low']),
                "c2_close": float(c2['Close']), "c2_eq": eq,
                "c3_close": float(c3['Close']),
                "swing_level": float(c2['Low']), "direction": "long"}
    return None


def detect_c3_closure(df):
    """H4 C3 Closure fallback: C2 didn't return, C3 strong body confirms."""
    if len(df) < 4: return None
    c1, c2, c3, c4 = df.iloc[-4], df.iloc[-3], df.iloc[-2], df.iloc[-1]
    
    c3_body = abs(float(c3['Close']) - float(c3['Open']))
    c3_range = float(c3['High']) - float(c3['Low'])
    if c3_range <= 0 or c3_body / c3_range < 0.55:
        return None
    
    if c2['High'] > c1['High'] and c2['Close'] >= c1['High'] and c3['Close'] < c3['Open']:
        eq = (float(c2['High']) + float(c2['Low'])) / 2
        return {"type": "c3_closure", "side": "bearish",
                "c2_high": float(c2['High']), "c2_eq": eq,
                "c4_close": float(c4['Close']),
                "swing_level": float(c2['High']), "direction": "short"}
    if c2['Low'] < c1['Low'] and c2['Close'] <= c1['Low'] and c3['Close'] > c3['Open']:
        eq = (float(c2['High']) + float(c2['Low'])) / 2
        return {"type": "c3_closure", "side": "bullish",
                "c2_low": float(c2['Low']), "c2_eq": eq,
                "c4_close": float(c4['Close']),
                "swing_level": float(c2['Low']), "direction": "long"}
    return None


def _consecutive_series(ltf_df, max_lookback=8):
    """Group consecutive bullish/bearish candles. Return list of (dir, start, end)."""
    series = []
    current_dir = None
    start = None
    for i, (_, row) in enumerate(ltf_df.tail(max_lookback).iterrows()):
        if row['Close'] > row['Open']: d = "bull"
        elif row['Close'] < row['Open']: d = "bear"
        else: continue
        if d != current_dir:
            if current_dir is not None:
                series.append((current_dir, start, i - 1))
            current_dir = d
            start = i
    if current_dir is not None:
        series.append((current_dir, start, max_lookback - 1))
    return series


def check_cisd(ltf_df, direction):
    """M15 CISD: close breaks opposing series' extreme open (scoped to last series)."""
    if len(ltf_df) < 5:
        return {"confirmed": False, "reason": "insufficient"}
    
    series = _consecutive_series(ltf_df)
    if not series:
        return {"confirmed": False, "reason": "no series"}
    
    last_close = float(ltf_df['Close'].iloc[-1])
    target_dir = "bull" if direction == "short" else "bear"
    opposing = [(d, s, e) for d, s, e in series if d == target_dir]
    
    if not opposing:
        return {"confirmed": False, "reason": f"no {target_dir} series to break"}
    
    d, s, e = opposing[-1]
    series_opens = [float(ltf_df['Open'].iloc[i]) for i in range(s, e + 1)]
    extreme = min(series_opens) if direction == "short" else max(series_opens)
    confirmed = (last_close < extreme) if direction == "short" else (last_close > extreme)
    
    return {
        "confirmed": confirmed,
        "opposing_open": extreme,
        "series_length": e - s + 1,
        "last_close": last_close,
        "reason": f"cisd_{direction}" if confirmed else "no break",
    }


def check_eq_respect(swing, ltf_df):
    """Price must respect C2 wick EQ (be on correct side)."""
    eq = swing.get("c2_eq")
    if eq is None or len(ltf_df) < 1: return False
    last = float(ltf_df['Close'].iloc[-1])
    if swing["direction"] == "short":
        return last <= eq
    return last >= eq


def label_weekly_profile(weekly_df):
    """Label-only weekly profile. Never hard-gate.
    
    Tightened rules per docs/17:
    - Tue/Wed: 'early_week' (too early to label, doesn't block)
    - midweek_reversal: Wed only (Mon-Tue against weekly open)
    - thursday_counter / consolidation_reversal: Thu+
    - classic_expansion: Fri only (Mon-Thu trend + Fri reversal)
    """
    weekday = datetime.now(HKT).weekday()
    label = {"profile": "unknown", "valid_for_signal": True, "notes": ""}
    
    if weekday < 2:
        label["profile"] = "early_week"
        label["notes"] = f"day {weekday+1} - too early, not blocking"
        return label
    
    if len(weekly_df) < 5:
        return label
    
    weekly_open = float(weekly_df['Open'].iloc[-1])
    if weekly_open == 0:
        return label
    
    # Get this week's daily closes up to today
    n_days = weekday + 1
    this_week_closes = [float(weekly_df['Close'].iloc[-n_days + i]) for i in range(n_days)]
    
    if weekday == 2 and n_days >= 3:
        if this_week_closes[0] < weekly_open and this_week_closes[1] < weekly_open:
            label["profile"] = "midweek_reversal"
            return label
    
    if weekday >= 3 and n_days >= 4:
        same_dir = sum(1 for c in this_week_closes[:3] if c < weekly_open)
        if same_dir >= 3:
            label["profile"] = "thursday_counter"
            return label
        if weekday == 4 and same_dir >= 3:
            label["profile"] = "classic_expansion"
            label["notes"] = "Fri potential reversal (20-50% range)"
            return label
        # consolidation
        ranges = [abs(float(weekly_df['High'].iloc[-n_days + i]) - float(weekly_df['Low'].iloc[-n_days + i]))
                  for i in range(min(3, n_days))]
        avg_range = sum(ranges) / len(ranges) if ranges else 0
        if avg_range > 0 and all(r < avg_range * 1.2 for r in ranges):
            label["profile"] = "consolidation_reversal"
            return label
    
    return label


def check_daily_profile(h1_df):
    """Lightweight: if London already expanded (range > 2× ATR), skip NY."""
    if len(h1_df) < 8:
        return {"london_expanded": False, "skip_ny": False}
    
    recent = h1_df.tail(16)
    try:
        london_bars = recent[recent.index.hour.isin(range(8, 16))]
    except Exception:
        return {"london_expanded": False, "skip_ny": False}
    
    if len(london_bars) < 3:
        return {"london_expanded": False, "skip_ny": False}
    
    london_range = float(london_bars['High'].max()) - float(london_bars['Low'].min())
    recent_atr = float((recent['High'] - recent['Low']).mean())
    expanded = london_range > recent_atr * 2
    
    return {
        "london_expanded": expanded,
        "london_range": london_range,
        "skip_ny": expanded,
    }


def calculate_trade_levels(swing, atr):
    """SL = C2 swing + 0.15×ATR. T1=1R, T2=1.6R, T3=2.6R. -2/-4 projection."""
    swing_level = swing["swing_level"]
    last_close = swing.get("c3_close") or swing.get("c4_close")
    if last_close is None: return None
    
    buffer = atr * 0.15
    if swing["direction"] == "short":
        sl = swing_level + buffer
        risk = sl - last_close
    else:
        sl = swing_level - buffer
        risk = last_close - sl
    
    if risk <= 0: return None
    
    sign = -1 if swing["direction"] == "short" else 1
    entry = last_close
    t1 = entry + sign * risk * 1.0
    t2_close = entry + sign * risk * 1.6
    t3 = entry + sign * risk * 2.6
    t4 = entry + sign * risk * 3.6
    t5 = entry + sign * risk * 5.0
    
    # Manipulation projection
    if swing["direction"] == "short":
        pivot = swing.get("c2_high", swing_level)
        proj_neg2 = entry - (pivot - entry) * 1.0
        proj_neg4 = entry - (pivot - entry) * 2.0
    else:
        pivot = swing.get("c2_low", swing_level)
        proj_neg2 = entry + (entry - pivot) * 1.0
        proj_neg4 = entry + (entry - pivot) * 2.0
    
    units = RISK_AMOUNT / risk
    
    return {
        "entry": entry, "sl": sl,
        "t1": t1, "t2_close": t2_close, "t3": t3, "t4": t4, "t5": t5,
        "risk_per_unit": risk, "units": units, "notional": units * entry,
        "manipulation_pivot": pivot,
        "projection_neg2": proj_neg2, "projection_neg4": proj_neg4,
        "sl_buffer_atr": buffer,
    }


def main():
    print(f"[ttrades-btc] === {datetime.now(HKT).strftime('%Y-%m-%d %H:%M:%S HKT')} ===")
    weekday = datetime.now(HKT).weekday()
    
    if weekday == 0:
        print("  [skip] Monday (OSOK rule)")
        SIGNAL_FILE.write_text(json.dumps({
            "ts": datetime.now(HKT).isoformat(), "ticker": TICKER,
            "actionable": False, "reason": "Monday skip (OSOK rule)",
            "account_size": ACCOUNT_SIZE, "risk_amount": RISK_AMOUNT,
        }, indent=2, default=str))
        return 0
    
    print("  [data] Fetching multi-TF...")
    h1 = fetch_ohlcv(TICKER, "1h", "30d")
    m15 = fetch_ohlcv(TICKER, "15m", "7d")
    weekly = fetch_ohlcv(TICKER, "1wk", "1y")
    
    if h1.empty or m15.empty:
        print("  ✗ No data"); return 0
    
    # Resample H1 to H4
    h4 = h1.resample("4h").agg({
        "Open": "first", "High": "max", "Low": "min", "Close": "last"
    }).dropna()
    
    # Step 1: C2 Closure or C3 Closure fallback
    print("  [step1] H4 swing detection...")
    swing = detect_c2_closure(h4)
    swing_type = "C2"
    if swing is None:
        swing = detect_c3_closure(h4)
        swing_type = "C3"
    if swing is None:
        print("  [step1] No H4 C2/C3 closure")
        SIGNAL_FILE.write_text(json.dumps({
            "ts": datetime.now(HKT).isoformat(), "ticker": TICKER,
            "actionable": False, "reason": f"no H4 {swing_type} closure (Fractal quiet)",
            "weekly_profile": label_weekly_profile(weekly),
            "account_size": ACCOUNT_SIZE, "risk_amount": RISK_AMOUNT,
        }, indent=2, default=str))
        return 0
    print(f"  [step1] H4 {swing_type}: {swing['side']} @ swing ${swing['swing_level']:.2f}")
    
    # Step 2: CISD (scoped to last series)
    print(f"  [step2] M15 CISD ({swing['direction']})...")
    cisd = check_cisd(m15, swing["direction"])
    print(f"  [step2] CISD: {'✓' if cisd['confirmed'] else '✗'} ({cisd.get('reason')})")
    
    # Step 3: EQ respect
    eq_ok = check_eq_respect(swing, m15)
    print(f"  [step3] EQ respect (EQ=${swing.get('c2_eq', 0):.2f}): {'✓' if eq_ok else '✗'}")
    
    # Step 4: Weekly label (not gate)
    weekly_label = label_weekly_profile(weekly)
    print(f"  [step4] Weekly: {weekly_label['profile']}")
    
    # Step 5: Daily profile (skip NY if London expanded)
    daily_profile = check_daily_profile(h1)
    print(f"  [step5] London expanded: {daily_profile.get('london_expanded')}, skip_ny: {daily_profile.get('skip_ny')}")
    
    # Build signal
    signal = {
        "ts": datetime.now(HKT).isoformat(),
        "ticker": TICKER,
        "strategy": "TTrades-Fractal",
        "swing_type": swing_type,
        "side": swing["side"],
        "swing": swing,
        "cisd": cisd,
        "eq_respected": eq_ok,
        "weekly_profile": weekly_label,
        "daily_profile": daily_profile,
        "account_size": ACCOUNT_SIZE,
        "risk_pct": RISK_PCT,
        "risk_amount": RISK_AMOUNT,
    }
    
    # Actionable: CISD + EQ + not London-expanded
    if cisd["confirmed"] and eq_ok and not daily_profile.get("skip_ny", False):
        atr_vals = (h1['High'].tail(14) - h1['Low'].tail(14))
        atr = float(atr_vals.mean()) if len(atr_vals) > 0 else 0
        
        if atr > 0:
            levels = calculate_trade_levels(swing, atr)
            if levels:
                signal.update(levels)
                signal["actionable"] = True
                signal["direction"] = swing["direction"]
                if swing_type == "C2" and weekly_label["profile"] in ("midweek_reversal", "consolidation_reversal"):
                    signal["grade"] = "A"; signal["confidence"] = 85
                else:
                    signal["grade"] = "B"; signal["confidence"] = 72
                signal["reason"] = (
                    f"TTrades Fractal: H4 {swing_type} closure ({swing['side']}) + "
                    f"M15 CISD ({cisd['series_length']}-bar series) + EQ respected"
                )
                print(f"  ✓ {signal['direction'].upper()} @ ${levels['entry']:.2f}")
                print(f"  ✓ SL ${levels['sl']:.2f} (C2 + 0.15×ATR)")
                print(f"  ✓ T2 CLOSE ${levels['t2_close']:.2f} (1.6R)")
            else:
                signal["actionable"] = False
                signal["reason"] = "levels calc failed"
        else:
            signal["actionable"] = False
            signal["reason"] = "no ATR"
    else:
        signal["actionable"] = False
        reasons = []
        if not cisd["confirmed"]: reasons.append("CISD not confirmed")
        if not eq_ok: reasons.append("EQ not respected")
        if daily_profile.get("skip_ny", False): reasons.append("London expanded (skip NY)")
        signal["reason"] = "; ".join(reasons) if reasons else "no trigger"
    
    SIGNAL_FILE.write_text(json.dumps(signal, indent=2, default=str))
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(signal, default=str) + "\n")
    
    if signal.get("actionable") and TG_TOKEN and TG_CHAT:
        try:
            d_emoji = "↑" if signal["direction"] == "long" else "↓"
            msg = (
                f"🎯 TTrades-Fractal [{signal['grade']}] {TICKER}\n\n"
                f"💰 Entry: ${levels['entry']:,.2f}\n"
                f"🎯 Dir: {signal['direction']} {d_emoji}\n"
                f"📊 Conf: {signal['confidence']}\n"
                f"🛡️ SL: ${levels['sl']:,.2f} (C2 swing + 0.15×ATR)\n"
                f"🎯 T1: ${levels['t1']:,.2f} (1.0R) reduce\n"
                f"🎯 T2 CLOSE: ${levels['t2_close']:,.2f} (1.6R) ← exit target\n"
                f"💎 T3: ${levels['t3']:,.2f} (2.6R) runner\n"
                f"📐 Manipulation -2: ${levels['projection_neg2']:,.2f}\n"
                f"📐 Projection -4: ${levels['projection_neg4']:,.2f}\n"
                f"💼 Units: {levels['units']:.4f} BTC (notional ${levels['notional']:,.0f})\n\n"
                f"💬 {signal['reason']}\n"
                f"📅 Weekly: {weekly_label['profile']}\n"
                f"⏰ {signal['ts']}"
            )
            r = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg[:4000]}, timeout=15)
            print(f"  [TG] HTTP {r.status_code}")
        except Exception as e:
            print(f"  [TG] {e}")
    else:
        print(f"  [no-action] {signal.get('reason', '?')}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
