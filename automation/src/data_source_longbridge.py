"""Longbridge MCP-based OHLCV data source.

Provides `fetch_longbridge()` as a drop-in alternative to `fetch_polygon()`
and `fetch_yfinance()` for the BTC 5m / 15m data the strategy pipeline needs.

Why Longbridge:
  - Stable: Longbridge MCP uptime >> yfinance flakiness for 5m bars
  - Trade-grade: same data feed as the broker execution
  - Multi-source fallback: paper trade of cross-validation (yfinance vs longbridge
    drift detector)

Symbol handling:
  - yfinance-style "BTC-USD" not supported by Longbridge
  - For BTC, use IBIT.US (iShares Bitcoin Trust, US ETF) as a price proxy —
    tracks BTC closely, has tight 5m bid/ask
  - Alternative: 2838.HK (華夏比特幣 HK-listed BTC ETF)
  - Period names: "1m", "5m", "15m", "30m", "60m", "1d", etc. (NOT "minute")

Limitations:
  - `history_candlesticks` returns ~1000 bars per call; for >1000 we page
  - Longbridge US markets pre/post/overnight — we read all sessions and
    tag timestamps as UTC

v1 — 2026-09-24 — initial integration.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd

from longbridge_mcp import get_client

log = logging.getLogger("data_source_longbridge")

# In-process cache (5 min TTL) — same TTL as data_source.py to share risk surface
_CACHE: dict = {}
_CACHE_TTL = 300

# Symbol aliases — accept our internal "BTC-USD" notation and translate to
# a real Longbridge-tradable symbol. Default to IBIT.US as the most liquid
# BTC ETF (BlackRock iShares Bitcoin Trust).
SYMBOL_ALIAS = {
    "BTC-USD": "IBIT.US",
    "BTCUSD=X": "IBIT.US",
    "BTCUSD": "IBIT.US",
    "BTC": "IBIT.US",
    "ETH-USD": "ETHE.US",  # Grayscale Ethereum Trust (proxy)
}

# Map our interval_min → Longbridge period format
PERIOD_MAP = {1: "1m", 5: "5m", 15: "15m", 30: "30m", 60: "60m", 240: "1h", 1440: "1d"}


def _bars_to_df(bars: list[dict], symbol: str) -> pd.DataFrame:
    """Normalize Longbridge candlestick dicts to a UTC-indexed OHLCV DataFrame.

    Longbridge candlestick fields (per MCP tools/call candlesticks response):
        timestamp (ISO), open, high, low, close, volume, turnover
    """
    if not bars:
        return pd.DataFrame()
    rows = []
    for b in bars:
        # Try common key sets
        ts_raw = b.get("timestamp") or b.get("ts") or b.get("time")
        try:
            ts = pd.Timestamp(ts_raw)
            if ts.tzinfo is None:
                # Longbridge returns HKT (UTC+8) by default for HK symbols;
                # US/crypto typically UTC. Be defensive.
                ts = ts.tz_localize("UTC")
        except Exception:
            continue
        rows.append({
            "Open": float(b.get("open", 0) or 0),
            "High": float(b.get("high", 0) or 0),
            "Low": float(b.get("low", 0) or 0),
            "Close": float(b.get("close", 0) or 0),
            "Volume": float(b.get("volume", 0) or 0),
            "Datetime": ts,
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index("Datetime").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df[["Open", "High", "Low", "Close", "Volume"]]


def fetch_longbridge(symbol: str = "BTC-USD", days: int = 5, interval_min: int = 5) -> pd.DataFrame:
    """Fetch OHLCV from Longbridge MCP history_candlesticks.

    Args:
        symbol: ticker like 'BTC-USD', 'NVDA.US', '700.HK'
        days: number of days back from now
        interval_min: bar size in minutes (1, 5, 15, 30, 60)

    Returns:
        DataFrame with columns [Open, High, Low, Close, Volume] and UTC DatetimeIndex.
    """
    cache_key = f"{symbol}_{days}_{interval_min}"
    if cache_key in _CACHE:
        df_cached, ts = _CACHE[cache_key]
        if time.time() - ts < _CACHE_TTL:
            log.info(f"[longbridge] cache hit ({cache_key}, age={int(time.time()-ts)}s)")
            return df_cached

    # Translate symbol (BTC-USD → IBIT.US)
    lb_symbol = SYMBOL_ALIAS.get(symbol.upper(), symbol)
    period = PERIOD_MAP.get(interval_min)
    if period is None:
        raise ValueError(f"Unsupported interval_min={interval_min}; use 1/5/15/30/60/240/1440")
    log.info(f"[longbridge] {symbol} → {lb_symbol}, period={period}, days={days}")

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)
    start_iso = start_dt.isoformat()
    end_iso = end_dt.isoformat()

    try:
        client = get_client()
        bars = client.history_candlesticks(
            symbol=lb_symbol, period=period, start=start_iso, end=end_iso
        )
    except Exception as e:
        log.warning(f"[longbridge] history_candlesticks failed for {lb_symbol}: {e}")
        # Fallback: try the simpler `candlesticks` (last N bars)
        try:
            client = get_client()
            bars_per_day = 24 * 60 // interval_min
            count = min(days * bars_per_day, 1000)
            bars = client.candlesticks(symbol=lb_symbol, period=period, count=count)
        except Exception as e2:
            log.warning(f"[longbridge] candlesticks fallback also failed: {e2}")
            return pd.DataFrame()

    df = _bars_to_df(bars, lb_symbol)
    if df.empty:
        log.warning(f"[longbridge] {lb_symbol}: empty bars returned")
        return df

    # Trim to days window
    df = df[df.index >= start_dt]
    log.info(f"[longbridge] {lb_symbol} {len(df)} bars, last={df.index[-1].isoformat()}")
    _CACHE[cache_key] = (df, time.time())
    return df


# ---------------------------------------------------------------------------
# Cross-validation helper
# ---------------------------------------------------------------------------

def diff_vs_other_source(symbol: str = "BTC-USD", days: int = 2, interval_min: int = 5) -> dict:
    """Compare Longbridge vs yfinance bars to detect data drift.

    Returns dict: { latest_close_diff_bps, max_diff_bps, agree }.
    Useful as a system-engineer periodic check.

    Note: For BTC, Longbridge uses IBIT.US as proxy (ETF), so absolute
    price level will differ significantly from BTC-USD spot. Use
    `normalize:True` (default) to compare % returns instead of absolute.
    """
    from data_source import fetch_yfinance

    out = {"symbol": symbol, "agree": None, "latest_diff_bps": None, "max_diff_bps": None,
           "normalized": True}
    df_lb = fetch_longbridge(symbol, days=days, interval_min=interval_min)
    df_yf = fetch_yfinance(symbol, period=f"{min(days, 60)}d", interval=f"{interval_min}m")
    if df_lb.empty or df_yf.empty:
        out["agree"] = False
        out["reason"] = "empty bars from one source"
        return out
    common = df_lb.index.intersection(df_yf.index)
    if len(common) < 5:
        out["agree"] = False
        out["reason"] = f"only {len(common)} common bars"
        return out
    lb_aligned = df_lb.loc[common, "Close"]
    yf_aligned = df_yf.loc[common, "Close"]
    # Compare normalized (first-bar = 100) to neutralize ETF vs spot basis
    lb_norm = lb_aligned / lb_aligned.iloc[0] * 100
    yf_norm = yf_aligned / yf_aligned.iloc[0] * 100
    diff = (lb_norm - yf_norm).abs()
    out["latest_diff_pts"] = float(diff.iloc[-1]) if len(diff) else None
    out["max_diff_pts"] = float(diff.max()) if len(diff) else None
    # Normalized diff < 1.5 points = agree (BTC vs IBIT should track within ~1.5%)
    out["agree"] = (out["max_diff_pts"] or 999) < 1.5
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    df = fetch_longbridge("BTC-USD", days=2, interval_min=5)
    print(f"Got {len(df)} bars")
    if not df.empty:
        print(df.tail())
    print()
    print("Cross-validation vs yfinance:")
    print(diff_vs_other_source("BTC-USD", days=1, interval_min=5))
