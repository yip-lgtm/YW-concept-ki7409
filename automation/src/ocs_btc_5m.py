"""OCS-Style AI Trader — Python port for BTC 5m.

Adapted from the OCS Pine Script (k2PaKAN) approximation:
  - 8 normalized features (RSI, Stoch, Supertrend offset, TRIX, Fisher, LMS slope, vol Z, close vs MA)
  - Rolling KNN with Lorentzian distance (log(1+|d|) summed)
  - Label: close[t] > close[t + horizon] (future return, non-lookahead)
  - Vote threshold: ±4 (out of 7)
  - Confidence: |vote| / used_neighbours
  - Layer score: combination of all features
  - Regime filter: chop detection
  - Supertrend / KAMA confirmation

Signal generation:
  - BUY: knnReady + vote >= 4 + conf >= 0.55 + layerScore > 0 + not inChop + close > KAMA
  - SELL: knnReady + vote <= -4 + conf >= 0.55 + layerScore < 0 + not inChop + close < KAMA

Run mode:
  - Once (signal check on latest bar)
  - Backtest (walk forward, compute hit rate)

Auto-publishes actionable signals to AI-Trader.
"""
from __future__ import annotations
import os
import sys
import json
import time
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Load env
from env_loader import load_env
load_env()

# Polygon-preferred data source
from data_source import fetch_bars as _fetch_bars_raw

def fetch_bars(symbol="BTC-USD", days=5, interval_min=5):
    return _fetch_bars_raw(symbol, days=days, interval_min=interval_min)

# Config
SYMBOL = "BTC-USD"  # Yahoo uses BTC-USD; user said BTC 5m
PERIOD = "5d"
INTERVAL = "5m"
K = 7
TRAIN_WINDOW = 160
HORIZON = 6
CONF_MIN = 0.55
VOTES_NEED = 4
USE_LORENTZ = True


def normalize_0_1(series: pd.Series, ref: float = 50.0) -> pd.Series:
    """Normalize to 0-1 range using running min/max or z-score."""
    return (series - series.rolling(50, min_periods=10).min()) / \
           (series.rolling(50, min_periods=10).max() - series.rolling(50, min_periods=10).min() + 1e-9)


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    return 100 - (100 / (1 + rs))


def compute_stoch(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    lowest = low.rolling(period).min()
    highest = high.rolling(period).max()
    return 100 * (close - lowest) / (highest - lowest + 1e-9)


def compute_supertrend_offset(close: pd.Series, atr: pd.Series, mult: float = 3.0) -> pd.Series:
    """Distance from supertrend line, normalized by ATR."""
    hl2 = (close.rolling(2).max() + close.rolling(2).min()) / 2
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    return (close - lower) / (upper - lower + 1e-9) - 0.5  # -0.5 to +0.5


def compute_trix(close: pd.Series, period: int = 15) -> pd.Series:
    ema1 = close.ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    ema3 = ema2.ewm(span=period, adjust=False).mean()
    return 100 * (ema3 - ema3.shift(1)) / (ema3.shift(1) + 1e-9)


def compute_fisher(close: pd.Series, period: int = 10) -> pd.Series:
    """Fisher transform of normalized price."""
    def _fisher(x):
        if len(x) < 2:
            return 0.0
        xmin, xmax = x.min(), x.max()
        if xmax - xmin < 1e-9:
            return 0.0
        n = (x - xmin) / (xmax - xmin) * 2 - 1
        n = np.clip(n, -0.999, 0.999)
        return 0.5 * np.log((1 + n[-1]) / (1 - n[-1]))
    return close.rolling(period).apply(_fisher, raw=True)


def compute_lms_slope(close: pd.Series, lookback: int = 20, mu: float = 0.02) -> pd.Series:
    """Adaptive LMS filter slope (simplified)."""
    slopes = pd.Series(index=close.index, dtype=float)
    weights = np.ones(lookback) / lookback
    for i in range(lookback, len(close)):
        x = np.arange(lookback)
        y = close.iloc[i-lookback:i].values
        # LMS update
        y_pred = np.dot(weights, x)
        err = y[-1] - y_pred
        grad = x * err
        weights = weights + mu * grad
        # Slope = last weight * scale
        slopes.iloc[i] = (weights[-1] - weights[0]) * 100  # scale to 0-100ish
    return slopes


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute 8 OCS features."""
    out = pd.DataFrame(index=df.index)
    close, high, low, vol = df["Close"], df["High"], df["Low"], df["Volume"]

    # ATR (for normalization)
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    # Feature 1: RSI (0-100)
    rsi = compute_rsi(close, 14)
    out["nRsi"] = normalize_0_1(rsi, 50)

    # Feature 2: Stochastic K (0-100)
    stoch = compute_stoch(high, low, close, 14)
    out["nSto"] = stoch / 100.0

    # Feature 3: Supertrend offset (-0.5 to +0.5)
    out["nSt"] = compute_supertrend_offset(close, atr, 3.0)

    # Feature 4: TRIX
    trix = compute_trix(close, 15)
    out["nTrix"] = normalize_0_1(trix, 50)

    # Feature 5: Fisher
    fisher = compute_fisher(close, 10)
    out["nFish"] = normalize_0_1(fisher, 50)

    # Feature 6: LMS slope (slow, computed once)
    # Use a faster proxy: slope of EMA20 over last 20 bars
    ema = close.ewm(span=20, adjust=False).mean()
    out["nLms"] = normalize_0_1((ema - ema.shift(5)) / (atr + 1e-9) * 100, 0)

    # Feature 7: Volume Z-score
    vol_sma = vol.rolling(20).mean()
    vol_std = vol.rolling(20).std()
    out["nVol"] = ((vol - vol_sma) / (vol_std + 1e-9)).clip(-3, 3) / 6 + 0.5

    # Feature 8: close vs 50 EMA (similar to KAMA/MA)
    ema50 = close.ewm(span=50, adjust=False).mean()
    out["nCvd"] = ((close - ema50) / (atr * 2 + 1e-9)).clip(-1, 1) * 0.5 + 0.5

    return out


def lorentzian_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Log(1+|diff|) summed across 8 features (Lorentzian / L1-like)."""
    return float(np.sum(np.log1p(np.abs(a - b))))


def label_future(close: pd.Series, horizon: int = 6) -> pd.Series:
    """Label: 1 if close > close[horizon] bars later, else -1."""
    future = close.shift(-horizon)
    return (close > future).astype(int) * 2 - 1


def rolling_knn(features: pd.DataFrame, labels: pd.Series, k: int = 7,
                min_train: int = 30) -> pd.DataFrame:
    """Rolling KNN classification.

    Returns DataFrame with columns: vote, used, conf.
    """
    out = pd.DataFrame(index=features.index, columns=["vote", "used", "conf"])
    out = out.astype(float)

    # Get feature array
    feat_arr = features.values
    label_arr = labels.values

    n = len(feat_arr)
    for i in range(min_train, n):
        if pd.isna(feat_arr[i]).any() or pd.isna(label_arr[i - HORIZON]):
            continue
        # Find K nearest neighbors in training window
        train_end = i - HORIZON
        if train_end < min_train:
            continue
        train_X = feat_arr[train_end - TRAIN_WINDOW:train_end]
        train_y = label_arr[train_end - TRAIN_WINDOW:train_end]
        # Filter valid samples
        valid = ~pd.isna(train_X).any(axis=1) & ~pd.isna(train_y)
        train_X = train_X[valid]
        train_y = train_y[valid]
        if len(train_X) < k:
            continue
        # Compute distances
        dists = np.array([lorentzian_distance(feat_arr[i], x) for x in train_X])
        # K nearest
        idx = np.argpartition(dists, k)[:k]
        votes = train_y[idx]
        vote = int(np.sum(votes))
        used = int(k)
        conf = abs(vote) / used
        out.iloc[i] = [vote, used, conf]
    return out


def compute_signal(knn_result: pd.Series, features: pd.DataFrame,
                   close: pd.Series, atr: pd.Series) -> dict:
    """Compute final signal from KNN + filters."""
    if pd.isna(knn_result["vote"]) or knn_result["used"] < K:
        return {"signal": "none", "vote": 0, "conf": 0}

    vote = int(knn_result["vote"])
    conf = float(knn_result["conf"])
    last_close = float(close.iloc[-1])
    last_atr = float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0

    # Layer score: weighted combo of features
    f = features.iloc[-1]
    layer_score = (
        f["nRsi"] * 0.15 +
        f["nSto"] * 0.1 +
        f["nSt"] * 0.2 +
        f["nTrix"] * 0.15 +
        f["nFish"] * 0.1 +
        f["nLms"] * 0.1 +
        f["nVol"] * 0.1 +
        f["nCvd"] * 0.1
    ) - 0.5  # center around 0

    # Chop filter: skip if ATR is too low (choppy market)
    in_chop = last_atr < close.rolling(50).std().mean() * 0.5

    # KAMA proxy: 50 EMA
    ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]

    sig = "none"
    direction = None
    if vote >= VOTES_NEED and conf >= CONF_MIN and layer_score > 0 and not in_chop and last_close > ema50:
        sig = "buy"
        direction = "long"
    elif vote <= -VOTES_NEED and conf >= CONF_MIN and layer_score < 0 and not in_chop and last_close < ema50:
        sig = "sell"
        direction = "short"

    return {
        "signal": sig,
        "direction": direction,
        "vote": vote,
        "conf": conf,
        "layer_score": layer_score,
        "in_chop": in_chop,
        "last_close": last_close,
        "atr": last_atr,
    }


def main():
    print(f"[OCS] Loading {SYMBOL} 5d 5m via data_source (polygon preferred)...")
    df = fetch_bars(SYMBOL, days=5, interval_min=5)
    if df.empty:
        print(f"[OCS] FATAL: No data from any source")
        return 2
    if len(df) < 100:
        print(f"[OCS] Insufficient data: {len(df)} bars (need 100+)")
        return 3

    print(f"[OCS] Computing features...")
    feats = compute_features(df)
    print(f"[OCS] Computing labels...")
    labels = label_future(df["Close"], HORIZON)
    print(f"[OCS] Running KNN (K={K}, train={TRAIN_WINDOW})...")
    knn = rolling_knn(feats, labels, K, min_train=30)

    # ATR
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift(1)).abs(),
        (df["Low"] - df["Close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    sig = compute_signal(knn.iloc[-1], feats, df["Close"], atr)
    print(f"\n[OCS] Last signal: {sig}")

    # Save to JSON for GHA
    out_dir = Path("/tmp/ocs_btc")
    out_dir.mkdir(exist_ok=True)
    out = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "ts": str(df.index[-1]),
        "last_close": sig.get("last_close"),
        "atr": sig.get("atr"),
        "vote": sig.get("vote"),
        "conf": sig.get("conf"),
        "layer_score": sig.get("layer_score"),
        "in_chop": sig.get("in_chop"),
        "signal": sig.get("signal"),
        "direction": sig.get("direction"),
    }
    (out_dir / "latest.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"[OCS] ✓ Saved: {out_dir / 'latest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
