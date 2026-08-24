"""Technical indicators for YW strategy detection.

Computes concrete signals from OHLCV data:
  - RSI (Relative Strength Index)
  - EMA / SMA crossovers
  - Price-vs-MA distance
  - Divergence detection (price vs RSI)
  - Pullback proximity (price near MA20)

Used to pre-detect patterns before LLM confirmation.
"""
from __future__ import annotations
import pandas as pd
import numpy as np


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Standard Wilder RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder's smoothing (EMA with alpha=1/period)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_ma(close: pd.Series, period: int, kind: str = "ema") -> pd.Series:
    """EMA or SMA."""
    if kind == "ema":
        return close.ewm(span=period, adjust=False).mean()
    return close.rolling(period).mean()


def detect_rsi_divergence(df: pd.DataFrame, lookback: int = 20,
                            ema_filter: bool = True, volume_filter: bool = True) -> dict:
    """Detect bullish/bearish RSI divergence on the last N bars.

    LLM-OPTIMIZED v1.5 (2026-08-25): Added EMA50 trend filter + volume confirmation
    to reduce false divergence signals (PF 0.92 → target 1.2+).

    Filters:
      - ema_filter: trade only in direction of EMA50 trend
        * bullish divergence: price must be ABOVE EMA50 (downtrend exhaustion, then up)
        * bearish divergence: price must be BELOW EMA50
      - volume_filter: divergence candle must have volume >= 1.2x avg
        * filters out low-conviction divergences (need volume to confirm reversal)

    Bullish: price makes lower low, RSI makes higher low (trend filter: above EMA50)
    Bearish: price makes higher high, RSI makes lower high (trend filter: below EMA50)
    """
    if df.empty or len(df) < lookback:
        return {"type": "none", "strength": 0, "filtered": False}

    window = df.tail(lookback)
    close = window["Close"]
    rsi = compute_rsi(close).dropna()

    if len(rsi) < 5:
        return {"type": "none", "strength": 0, "filtered": False}

    # Find last 2 swing highs/lows
    mid = len(window) // 2
    first_half = window.iloc[:mid]
    second_half = window.iloc[mid:]

    p1_low = first_half["Low"].min()
    p2_low = second_half["Low"].min()
    r1 = compute_rsi(first_half["Close"]).dropna()
    r2 = compute_rsi(second_half["Close"]).dropna()
    r1_low = r1.min() if len(r1) else 0
    r2_low = r2.min() if len(r2) else 0

    p1_high = first_half["High"].max()
    p2_high = second_half["High"].max()
    r1_high = r1.max() if len(r1) else 0
    r2_high = r2.max() if len(r2) else 0

    result = {"type": "none", "strength": 0, "price_diff_pct": 0, "rsi_diff": 0, "filtered": False}

    # Bullish: price lower, RSI higher
    if p2_low < p1_low and r2_low > r1_low:
        price_diff = (p2_low - p1_low) / p1_low * 100
        rsi_diff = r2_low - r1_low
        strength = min(100, abs(rsi_diff) * 5)
        result = {
            "type": "bullish",
            "strength": strength,
            "price_diff_pct": round(price_diff, 2),
            "rsi_diff": round(rsi_diff, 1),
            "filtered": False,
        }
    # Bearish: price higher, RSI lower
    elif p2_high > p1_high and r2_high < r1_high:
        price_diff = (p2_high - p1_high) / p1_high * 100
        rsi_diff = r1_high - r2_high
        strength = min(100, abs(rsi_diff) * 5)
        result = {
            "type": "bearish",
            "strength": strength,
            "price_diff_pct": round(price_diff, 2),
            "rsi_diff": round(rsi_diff, 1),
            "filtered": False,
        }
    # Looser match
    elif p2_low < p1_low * 0.9995 and r2_low > r1_low + 0.3:
        result = {"type": "bullish", "strength": 25, "price_diff_pct": -0.05, "rsi_diff": 0.3, "filtered": False}
    elif p2_high > p1_high * 1.0005 and r2_high < r1_high - 0.3:
        result = {"type": "bearish", "strength": 25, "price_diff_pct": 0.05, "rsi_diff": -0.3, "filtered": False}
    else:
        return result

    # Apply LLM-optimized filters
    if result["type"] != "none":
        # Filter 1: EMA50 trend direction
        if ema_filter and len(df) >= 50:
            ema50 = compute_ma(close, 50, "ema").iloc[-1]
            last_close = close.iloc[-1]
            if result["type"] == "bullish" and last_close < ema50:
                result["filtered"] = True
                result["filter_reason"] = "price below EMA50 (no trend support)"
                result["strength"] = max(0, result["strength"] // 3)  # heavily penalize
                return result
            if result["type"] == "bearish" and last_close > ema50:
                result["filtered"] = True
                result["filter_reason"] = "price above EMA50 (no trend support)"
                result["strength"] = max(0, result["strength"] // 3)
                return result

        # Filter 2: Volume confirmation (divergence candle must have volume >= 1.2x avg)
        if volume_filter and "Volume" in window.columns and len(window) >= 5:
            last_vol = window["Volume"].iloc[-1]
            avg_vol = window["Volume"].tail(10).mean()
            if last_vol < avg_vol * 1.2:
                result["filtered"] = True
                result["filter_reason"] = f"volume {last_vol:.0f} < 1.2x avg {avg_vol:.0f}"
                result["strength"] = max(0, result["strength"] // 2)
                return result

    return result


def detect_5020_pullback(df: pd.DataFrame, lookback: int = 30) -> dict:
    """Detect 20 EMA / 50 SMA cross + current price pullback to EMA20.

    Returns:
      {
        "cross_type": "golden" / "death" / "none",
        "cross_bars_ago": int,
        "pullback": "at_ema20" / "below_ema20" / "above_ema20" / "none",
        "distance_to_ema20_pct": float,
        "above_50sma": bool,
        "trend": "up" / "down" / "sideways"
      }
    """
    if df.empty or len(df) < 50:
        return {"cross_type": "none", "trend": "sideways"}

    close = df["Close"]
    ema20 = compute_ma(close, 20, "ema")
    sma50 = compute_ma(close, 50, "sma")

    # Detect cross in last `lookback` bars
    cross_type = "none"
    cross_bars_ago = -1
    for i in range(len(df) - 1, max(len(df) - lookback, 1), -1):
        if pd.isna(ema20.iloc[i]) or pd.isna(sma50.iloc[i]):
            continue
        if pd.isna(ema20.iloc[i-1]) or pd.isna(sma50.iloc[i-1]):
            continue
        # Golden: EMA20 crosses ABOVE SMA50
        if ema20.iloc[i-1] <= sma50.iloc[i-1] and ema20.iloc[i] > sma50.iloc[i]:
            cross_type = "golden"
            cross_bars_ago = len(df) - i
            break
        # Death: EMA20 crosses BELOW SMA50
        if ema20.iloc[i-1] >= sma50.iloc[i-1] and ema20.iloc[i] < sma50.iloc[i]:
            cross_type = "death"
            cross_bars_ago = len(df) - i
            break

    last = close.iloc[-1]
    last_ema = ema20.iloc[-1]
    last_sma = sma50.iloc[-1]

    # Pullback state
    dist_ema_pct = (last - last_ema) / last_ema * 100
    if abs(dist_ema_pct) < 0.1:
        pullback = "at_ema20"
    elif dist_ema_pct < -0.1:
        pullback = "below_ema20"  # 急跌穿 EMA20
    elif dist_ema_pct > 0.5:
        pullback = "above_ema20"  # 強勢單邊
    else:
        pullback = "near_ema20"  # 0.1-0.5% above = 標準回踩

    above_50sma = bool(last > last_sma)
    if above_50sma and cross_type == "golden":
        trend = "up"
    elif not above_50sma and cross_type == "death":
        trend = "down"
    else:
        trend = "sideways"

    return {
        "cross_type": cross_type,
        "cross_bars_ago": cross_bars_ago,
        "pullback": pullback,
        "distance_to_ema20_pct": round(dist_ema_pct, 3),
        "above_50sma": above_50sma,
        "trend": trend,
        "ema20": round(last_ema, 2),
        "sma50": round(last_sma, 2),
        "last": round(last, 2),
    }


def detect_h_pattern(df: pd.DataFrame) -> dict:
    """Detect YW H-Pattern signature.

    H-Pattern features:
      1. Long straight candle (first vertical of 'h')
      2. Top wick at turn (selling pressure)
      3. <50% pullback
      4. Break below to complete
    """
    if df.empty or len(df) < 5:
        return {"present": False}

    recent = df.tail(8)

    # Find the long candle (range > 1.5x average)
    avg_range = (recent["High"] - recent["Low"]).mean()
    long_candle_idx = None
    for i in range(len(recent) - 1, -1, -1):
        rng = recent["High"].iloc[i] - recent["Low"].iloc[i]
        if rng > avg_range * 1.5:
            long_candle_idx = i
            break

    if long_candle_idx is None:
        return {"present": False}

    long_candle = recent.iloc[long_candle_idx]
    body = abs(long_candle["Close"] - long_candle["Open"])
    upper_wick = long_candle["High"] - max(long_candle["Open"], long_candle["Close"])
    lower_wick = min(long_candle["Open"], long_candle["Close"]) - long_candle["Low"]

    # Top wick at turn
    has_top_wick = upper_wick > body * 0.2

    # Pullback < 50% (only if bearish long candle)
    if long_candle["Close"] < long_candle["Open"]:
        pullback_depth = (long_candle["Open"] - recent["Low"].iloc[long_candle_idx+1:].min()) / body
    else:
        pullback_depth = (long_candle["Open"] - recent["Low"].iloc[long_candle_idx+1:].min()) / body

    # Break below (price went below long candle's low)
    broke_low = recent["Low"].iloc[long_candle_idx+1:].min() < long_candle["Low"]

    present = has_top_wick and pullback_depth < 0.5 and broke_low

    return {
        "present": present,
        "long_candle": "bullish" if long_candle["Close"] > long_candle["Open"] else "bearish",
        "body_size": round(body, 2),
        "upper_wick_pct": round(upper_wick / (long_candle["High"] - long_candle["Low"]) * 100, 1),
        "pullback_pct": round(pullback_depth * 100, 1),
        "broke_low": broke_low,
    }


def detect_3_pushes(df: pd.DataFrame) -> dict:
    """Detect YW 3-Pushes pattern.

    Features:
      1. Three pushes (3 swing highs or lows in same direction)
      2. Last push narrowing (range < previous)
      3. Equal high/low exists to break
    """
    if df.empty or len(df) < 15:
        return {"present": False, "direction": "none"}

    recent = df.tail(15)

    # Find swing highs
    highs = []
    for i in range(1, len(recent) - 1):
        if recent["High"].iloc[i] > recent["High"].iloc[i-1] and recent["High"].iloc[i] > recent["High"].iloc[i+1]:
            highs.append((i, recent["High"].iloc[i]))
    lows = []
    for i in range(1, len(recent) - 1):
        if recent["Low"].iloc[i] < recent["Low"].iloc[i-1] and recent["Low"].iloc[i] < recent["Low"].iloc[i+1]:
            lows.append((i, recent["Low"].iloc[i]))

    # Look for 3 swing highs (downtrend exhaustion) or 3 swing lows (uptrend exhaustion)
    if len(highs) >= 3:
        last3 = [h[1] for h in highs[-3:]]
        if last3[2] < last3[1] < last3[0]:  # Lower highs
            narrowing = abs(last3[2] - last3[1]) < abs(last3[1] - last3[0])
            return {"present": narrowing, "direction": "up", "count": 3, "narrowing": narrowing}
        # Looser: just lower highs without strict narrowing
        if last3[2] < last3[1] < last3[0]:
            return {"present": True, "direction": "up", "count": 3, "narrowing": False, "loose": True}
    if len(lows) >= 3:
        last3 = [l[1] for l in lows[-3:]]
        if last3[2] > last3[1] > last3[0]:  # Higher lows (uptrend)
            narrowing = abs(last3[2] - last3[1]) < abs(last3[1] - last3[0])
            return {"present": narrowing, "direction": "down", "count": 3, "narrowing": narrowing}
        if last3[2] > last3[1] > last3[0]:
            return {"present": True, "direction": "down", "count": 3, "narrowing": False, "loose": True}

    return {"present": False, "direction": "none"}


def detect_two_yang_one_yin(df: pd.DataFrame) -> dict:
    """Detect YW 兩陽夾一陰 (15min).

    Pattern: middle bearish candle body wrapped by 2 bullish candles' bodies.
    """
    if df.empty or len(df) < 5:
        return {"present": False, "direction": "none"}

    # Look at last 5 candles
    for i in range(len(df) - 3, max(len(df) - 8, 2), -1):
        c1 = df.iloc[i]      # first candle
        c2 = df.iloc[i + 1]  # middle (should be bearish)
        c3 = df.iloc[i + 2]  # last candle

        # Get body of each candle
        def body(c):
            return abs(c["Close"] - c["Open"])

        def is_bullish(c):
            return c["Close"] > c["Open"]

        def body_range(c):
            return c["High"] - c["Low"]

        # Middle must be bearish with significant body
        if is_bullish(c2):
            continue
        b2 = body(c2)
        if b2 < (df["Close"].iloc[i:i+3].max() - df["Close"].iloc[i:i+3].min()) * 0.3:
            continue  # body too small

        # c1 and c3 must be bullish with bodies that wrap c2's body
        if not is_bullish(c1) or not is_bullish(c3):
            continue
        b1 = body(c1)
        b3 = body(c3)
        if b1 < b2 * 0.3 or b3 < b2 * 0.3:
            continue

        # Check wrap: c2 body range must be within c1+c3 body range
        c2_top = max(c2["Open"], c2["Close"])
        c2_bot = min(c2["Open"], c2["Close"])
        c1_top = max(c1["Open"], c1["Close"])
        c1_bot = min(c1["Open"], c1["Close"])
        c3_top = max(c3["Open"], c3["Close"])
        c3_bot = min(c3["Open"], c3["Close"])
        # c2 must be wrapped by c1 above and c3 below (or vice versa)
        if c2_top <= c1_top and c2_bot >= c3_bot:
            return {
                "present": True, "direction": "long",
                "strength": 70,
                "details": f"兩陽夾一陰: c1 body {b1:.0f}, c2 body {b2:.0f}, c3 body {b3:.0f}",
            }

    return {"present": False, "direction": "none"}


if __name__ == "__main__":
    # Quick test
    import yfinance as yf
    df = yf.download("MNQ=F", period="5d", interval="5m", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    print("RSI Div:", detect_rsi_divergence(df))
    print("50/20:", detect_5020_pullback(df))
    print("H-Pat:", detect_h_pattern(df))
    print("3-Pushes:", detect_3_pushes(df))
    print("兩陽夾一陰:", detect_two_yang_one_yin(df))
