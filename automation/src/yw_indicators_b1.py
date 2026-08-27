"""B1 Strategy (右侧交易) — multi-MA BBI + KDJ.

Chinese right-side trading system popular in stocks & crypto:
- BBI = average of MA(3,6,12,24)
- KDJ with default 9,3,3
- Buy signal (B1) when:
  1. Close > BBI and BBI rising
  2. Yesterday J < -20 (oversold pit)
  3. Today J > yesterday J (turning up)
  4. Bullish candle (Close > Open) and Close > yesterday high (right-side breakout)
  5. Optional: Volume > 5d MA

Returns: {present, direction: 'long', strength, bbi, k, d, j, signal_low, reason}
"""
from __future__ import annotations
import pandas as pd
import numpy as np


def calculate_bbi(df: pd.DataFrame, periods=(3, 6, 12, 24)) -> pd.DataFrame:
    """計算 BBI 多空指數 = MA(3,6,12,24) 平均"""
    for p in periods:
        df[f'_bbi_ma{p}'] = df['Close'].rolling(window=p).mean()
    df['BBI'] = df[[f'_bbi_ma{p}' for p in periods]].mean(axis=1)
    return df


def calculate_kdj(df: pd.DataFrame, n: int = 9, k_smooth: int = 3, d_smooth: int = 3) -> pd.DataFrame:
    """計算 KDJ 指標"""
    low_min = df['Low'].rolling(window=n).min()
    high_max = df['High'].rolling(window=n).max()
    rsv = (df['Close'] - low_min) / (high_max - low_min) * 100
    rsv = rsv.fillna(50)
    k = rsv.ewm(alpha=1/k_smooth, adjust=False).mean()
    d = k.ewm(alpha=1/d_smooth, adjust=False).mean()
    j = 3 * k - 2 * d
    df['K'] = k
    df['D'] = d
    df['J'] = j
    return df


def detect_b1(
    df: pd.DataFrame,
    j_threshold: float = -20,
    use_volume_filter: bool = True,
    vol_ma_period: int = 5,
) -> dict:
    """B1 買點偵測 — 5 conditions all true.

    Returns dict with present, direction='long', strength, key levels.
    """
    if df.empty or len(df) < 30:
        return {"present": False, "direction": "long", "filtered": False}

    df = df.copy()
    df = calculate_bbi(df)
    df = calculate_kdj(df)
    if 'Volume' in df.columns and use_volume_filter:
        df['_vol_ma'] = df['Volume'].rolling(vol_ma_period).mean()
    else:
        df['_vol_ma'] = 0

    # Need at least 2 rows for shift(1)
    if len(df) < 2:
        return {"present": False, "direction": "long", "filtered": False}

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # 1. Close > BBI and BBI rising
    cond1_price = float(last['Close']) > float(last['BBI'])
    cond1_bbi_up = float(last['BBI']) > float(prev['BBI'])

    # 2. Yesterday J in pit (< j_threshold)
    cond2 = float(prev['J']) < j_threshold

    # 3. Today J turning up
    cond3 = float(last['J']) > float(prev['J'])

    # 4. Bullish candle + right-side breakout
    cond4_bullish = float(last['Close']) > float(last['Open'])
    cond4_breakout = float(last['Close']) > float(prev['High'])

    # 5. Volume filter
    cond5 = True
    if use_volume_filter and 'Volume' in df.columns:
        cond5 = float(last['Volume']) > float(last['_vol_ma'])

    present = cond1_price and cond1_bbi_up and cond2 and cond3 and cond4_bullish and cond4_breakout and cond5

    if not present:
        return {
            "present": False, "direction": "long", "strength": 0,
            "bbi": float(last['BBI']),
            "k": float(last['K']), "d": float(last['D']), "j": float(last['J']),
            "filtered": not cond5 if use_volume_filter else False,
        }

    # Strength: based on confluence
    strength = 50
    if float(last['J']) > 0:
        strength += 20
    if cond4_breakout:
        strength += 15
    if cond5:
        strength += 15

    return {
        "present": True,
        "direction": "long",  # B1 is always long
        "strength": min(strength, 100),
        "bbi": float(last['BBI']),
        "k": float(last['K']),
        "d": float(last['D']),
        "j": float(last['J']),
        "signal_low": float(last['Low']),  # for stop loss
        "signal_high": float(prev['High']),
        "details": (
            f"B1: Close {float(last['Close']):.2f} > BBI {float(last['BBI']):.2f} ↑, "
            f"prev J {float(prev['J']):.1f} < {j_threshold} (pit), "
            f"now J {float(last['J']):.1f} turning up, "
            f"right-side breakout above {float(prev['High']):.2f}"
        ),
    }
