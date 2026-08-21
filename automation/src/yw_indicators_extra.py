"""Extended YW strategy detectors: CRT + Stair + Kell Cycle.

Each function takes OHLCV DataFrame + strategy-specific parameters
and returns a signal dict {present, direction, strength, details}.

These are simplified Python versions of the MT5 EAs (5min timeframe proxy).
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Literal

from yw_indicators import compute_rsi, compute_ma


def detect_crt(df_4h: pd.DataFrame, df_5m: pd.DataFrame) -> dict:
    """CRT Candle Range Theory (4H range → 5min execution).

    Bullish CRT:
      1. Mark last closed 4H K's High (CRT-H) and Low (CRT-L)
      2. In next 4H session, 5min price raids CRT-L and closes back above
      3. Confirm with MSS-like (close above raid candle's High)

    Bearish CRT: symmetric.
    """
    if df_4h.empty or len(df_4h) < 2 or df_5m.empty or len(df_5m) < 20:
        return {"present": False, "direction": "none"}

    last_4h = df_4h.iloc[-1]
    crt_high = float(last_4h["High"])
    crt_low = float(last_4h["Low"])

    # Look for 5min raid in current 4H window
    # 4H = 48 5min bars. Find candles that raided CRT-L or CRT-H.
    recent_5m = df_5m.tail(48)
    crt_range_pct = (crt_high - crt_low) / crt_low * 100

    # Bullish: 5min dipped below crt_low then closed back above
    raids_low = recent_5m[recent_5m["Low"] < crt_low]
    if not raids_low.empty:
        raid_idx = raids_low.index[0]
        raid_candle = recent_5m.loc[raid_idx]
        # Confirm: next candle closes above raid candle's High (MSS)
        if raid_idx != recent_5m.index[-1]:
            after = recent_5m[recent_5m.index > raid_idx]
            if not after.empty and after.iloc[0]["Close"] > raid_candle["High"]:
                return {
                    "present": True,
                    "direction": "bullish",
                    "strength": 80,
                    "crt_high": crt_high,
                    "crt_low": crt_low,
                    "raid_low": float(raid_candle["Low"]),
                    "mss_confirm": float(after.iloc[0]["Close"]),
                    "details": f"掃 CRT-L {float(raid_candle['Low']):.2f} + MSS 收 {float(after.iloc[0]['Close']):.2f}",
                }

    raids_high = recent_5m[recent_5m["High"] > crt_high]
    if not raids_high.empty:
        raid_idx = raids_high.index[0]
        raid_candle = recent_5m.loc[raid_idx]
        if raid_idx != recent_5m.index[-1]:
            after = recent_5m[recent_5m.index > raid_idx]
            if not after.empty and after.iloc[0]["Close"] < raid_candle["Low"]:
                return {
                    "present": True,
                    "direction": "bearish",
                    "strength": 80,
                    "crt_high": crt_high,
                    "crt_low": crt_low,
                    "raid_high": float(raid_candle["High"]),
                    "mss_confirm": float(after.iloc[0]["Close"]),
                    "details": f"掃 CRT-H {float(raid_candle['High']):.2f} + MSS 收 {float(after.iloc[0]['Close']):.2f}",
                }

    return {
        "present": False,
        "direction": "none",
        "crt_high": crt_high,
        "crt_low": crt_low,
        "crt_range_pct": round(crt_range_pct, 2),
        "details": f"4H range {crt_low:.2f}-{crt_high:.2f} ({crt_range_pct:.2f}%); 5min 暫未掃邊+收返",
    }


def detect_stair_pattern(df: pd.DataFrame) -> dict:
    """YW Stair Pattern (H-Pattern 變體).

    Features:
      1. First candle: large bearish (大陰燭), close in lower 50%, small/no upper wick
      2. Middle: ≥2 candles with upper wicks (selling pressure)
      3. Confirm: last candle closes below 20 EMA
    """
    if df.empty or len(df) < 10:
        return {"present": False}

    recent = df.tail(10)
    atr = (df["High"] - df["Low"]).tail(14).mean()
    if atr == 0 or pd.isna(atr):
        return {"present": False}

    # 1. Find first large bearish candle
    big_bear = None
    for i in range(len(recent) - 5):
        c = recent.iloc[i]
        body = abs(c["Close"] - c["Open"])
        rng = c["High"] - c["Low"]
        if rng == 0:
            continue
        upper_wick = c["High"] - max(c["Open"], c["Close"])
        if (c["Close"] < c["Open"]
            and body / rng >= 0.5  # 實體 ≥ 50% range
            and upper_wick / rng <= 0.2  # 上影 ≤ 20%
            and rng >= 1.2 * atr):  # range ≥ 1.2×ATR
            # Check close in lower 50%
            close_pct = (c["Close"] - c["Low"]) / rng
            if close_pct <= 0.5:
                big_bear = (i, c)
                break

    if big_bear is None:
        return {"present": False, "details": "No large bearish candle in last 10 bars"}

    bear_idx, bear_candle = big_bear

    # 2. Count subsequent candles with upper wicks
    after = recent.iloc[bear_idx+1:bear_idx+5]
    if len(after) < 2:
        return {"present": False, "details": "Not enough candles after bearish start"}

    wick_count = 0
    for _, c in after.iterrows():
        rng = c["High"] - c["Low"]
        if rng == 0:
            continue
        upper_wick = c["High"] - max(c["Open"], c["Close"])
        if upper_wick / rng >= 0.2:  # 上影 ≥ 20% range
            wick_count += 1

    if wick_count < 2:
        return {"present": False, "details": f"只有 {wick_count} 根上影 candle (need ≥2)"}

    # 3. Confirm: last candle close below 20 EMA
    ema20 = compute_ma(df["Close"], 20, "ema")
    last_close = df["Close"].iloc[-1]
    last_ema = ema20.iloc[-1]
    below_ema = bool(last_close < last_ema)

    return {
        "present": below_ema and wick_count >= 2,
        "direction": "short",
        "strength": min(100, 50 + wick_count * 15),
        "big_bear_idx": bear_idx,
        "wick_count": wick_count,
        "close_below_ema20": below_ema,
        "details": f"大陰啟動 + {wick_count} 根上影 + close {'<' if below_ema else '>'} EMA20",
    }


def detect_kell_setups(df: pd.DataFrame) -> dict:
    """Detect all 5 Kell Cycle setups + return dict of which are present.

    Returns:
      {
        "reversal_extension": {present, direction, ...},
        "wedge_pop_drop": {present, direction, ...},
        "ema_crossback": {present, direction, ...},
        "base_n_break": {present, direction, ...},
        "exhaustion": {present, direction, count},
      }
    """
    if df.empty or len(df) < 80:
        return {"all_present": False}

    ema10 = compute_ma(df["Close"], 10, "ema")
    ema20 = compute_ma(df["Close"], 20, "ema")
    ema50 = compute_ma(df["Close"], 50, "ema")
    atr = (df["High"] - df["Low"]).tail(14).mean()
    if atr == 0 or pd.isna(atr):
        return {"all_present": False}

    last_close = df["Close"].iloc[-1]
    last_ema10 = ema10.iloc[-1]
    last_ema20 = ema20.iloc[-1]
    last_ema50 = ema50.iloc[-1]

    # 1. Reversal Extension: LTF price far from EMA10 + near EMA50
    dist_ema10_atr = (last_close - last_ema10) / atr
    dist_ema50_atr = (last_close - last_ema50) / atr
    reversal_ext = {
        "present": abs(dist_ema10_atr) > 1.2 and abs(dist_ema50_atr) < 1.5,
        "direction": "long" if dist_ema10_atr < 0 and dist_ema50_atr < 0.5 else "short",
        "details": f"距 EMA10 {dist_ema10_atr:.1f}×ATR, 距 EMA50 {dist_ema50_atr:.1f}×ATR",
    }

    # 2. Wedge Pop/Drop: EMA10 + EMA20 converging (narrowing) + price reclaim
    recent_emas_diff = (ema10 - ema20).tail(12)
    earlier_emas_diff = (ema10 - ema20).iloc[-24:-12] if len(ema10) >= 24 else recent_emas_diff
    recent_avg = abs(recent_emas_diff.mean())
    earlier_avg = abs(earlier_emas_diff.mean()) if len(earlier_emas_diff) > 0 else recent_avg
    if earlier_avg > 0:
        tight_ratio = recent_avg / earlier_avg
    else:
        tight_ratio = 1.0
    # Reclaim = price crossed EMA20 from below in last 5 bars
    reclaim_long = df["Close"].iloc[-1] > ema20.iloc[-1] and df["Close"].iloc[-6] < ema20.iloc[-6]
    reclaim_short = df["Close"].iloc[-1] < ema20.iloc[-1] and df["Close"].iloc[-6] > ema20.iloc[-6]
    wedge_pop_drop = {
        "present": tight_ratio < 0.55 and (reclaim_long or reclaim_short),
        "direction": "long" if reclaim_long else "short" if reclaim_short else "none",
        "details": f"EMA 收窄 {tight_ratio:.2f}, 收復 {'EMA20' if reclaim_long or reclaim_short else '?'}",
    }

    # 3. EMA Crossback: Wedge just happened (last 16 bars) + now pulling back to EMA
    had_wedge = tight_ratio < 0.55  # Recent wedge
    pullback_to_ema = abs(last_close - last_ema10) / atr < 0.35
    crossback = {
        "present": had_wedge and pullback_to_ema,
        "direction": "long" if last_close > last_ema50 else "short",
        "details": f"wedge 後 {pullback_to_ema} 回踩 EMA10",
    }

    # 4. Base n' Break: consolidation along EMA (range < 1.8 ATR) for 6-30 bars
    if len(df) >= 30:
        last_30 = df.tail(30)
        range_30 = (last_30["High"].max() - last_30["Low"].min())
        base_atr = range_30 / atr
        # Count how many bars along EMA10 (within 0.5 ATR)
        along_ema = 0
        for i in range(len(last_30)):
            if abs(last_30["Close"].iloc[i] - ema10.iloc[-(30-i)]) / atr < 0.5:
                along_ema += 1
        # Break: last close > recent high
        recent_high = last_30["High"].iloc[-6:-1].max()
        broke_out = last_close > recent_high
        base_n_break = {
            "present": 6 <= along_ema <= 30 and base_atr < 1.8 and broke_out,
            "direction": "long" if last_close > last_ema50 else "short",
            "details": f"沿 EMA {along_ema} 根, 範圍 {base_atr:.1f}×ATR, 突破 {broke_out}",
        }
    else:
        base_n_break = {"present": False, "details": "資料不足"}

    # 5. Exhaustion: 2nd+ time far from EMA10 (count in last 80 bars)
    ext_count = 0
    last_state = "near"
    if len(df) >= 80:
        for i in range(-80, 0):
            dist = (df["Close"].iloc[i] - ema10.iloc[i]) / atr
            state = "far" if abs(dist) > 1.6 else "near"
            if state == "far" and last_state == "near":
                ext_count += 1
            last_state = state
    exhaustion = {
        "present": ext_count >= 2,
        "count": ext_count,
        "details": f"近期 {ext_count} 次遠離 EMA10 (>1.6×ATR)",
    }

    return {
        "reversal_extension": reversal_ext,
        "wedge_pop_drop": wedge_pop_drop,
        "ema_crossback": crossback,
        "base_n_break": base_n_break,
        "exhaustion": exhaustion,
        "all_present": False,
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    import yfinance as yf

    print("=== CRT (4H range → 5min) ===")
    df_4h = yf.download("MNQ=F", period="1mo", interval="1h", progress=False, auto_adjust=True)
    if isinstance(df_4h.columns, __import__("pandas").MultiIndex):
        df_4h.columns = df_4h.columns.get_level_values(0)
    # Resample 1h to 4h
    df_4h = df_4h.resample("4h").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
    df_5m = yf.download("MNQ=F", period="5d", interval="5m", progress=False, auto_adjust=True)
    if isinstance(df_5m.columns, __import__("pandas").MultiIndex):
        df_5m.columns = df_5m.columns.get_level_values(0)
    print(detect_crt(df_4h, df_5m))

    print("\n=== Stair Pattern (5min) ===")
    df_5m2 = yf.download("MNQ=F", period="5d", interval="5m", progress=False, auto_adjust=True)
    if isinstance(df_5m2.columns, __import__("pandas").MultiIndex):
        df_5m2.columns = df_5m2.columns.get_level_values(0)
    print(detect_stair_pattern(df_5m2))

    print("\n=== Kell Cycle 5 setups (5min) ===")
    print(detect_kell_setups(df_5m2))
