"""Unified OHLCV data source for OCS BTC 5m.

Supports two backends:
  - polygon: Polygon.io crypto aggregates (preferred, $9/mo Basic, stable)
  - yfinance: Yahoo Finance (free, flaky for 5m)

Polygon endpoint:
  GET https://api.polygon.io/v2/aggs/ticker/X:BTCUSD/range/5/minute/{from}/{to}
      ?adjusted=true&sort=asc&apiKey=KEY

Response:
  {"results": [{"o":..,"h":..,"l":..,"c":..,"v":..,"t":<ms>}, ...]}

If POLYGON_API_KEY env is set -> use polygon.
Else fallback to yfinance (for local dev).
"""
from __future__ import annotations
import os
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
import time as _time
from typing import Optional

import requests
import pandas as pd

# Simple in-memory cache (5 min TTL) to avoid Polygon 5 calls/min rate limit
_CACHE = {}
_CACHE_TTL = 300  # seconds

# Data providers (Polygon rebranded to Massive; both APIs work in parallel)
MASSIVE_BASE = "https://api.massive.com"
POLYGON_BASE = "https://api.polygon.io"
YFINANCE_TIMEOUT = 30
POLYGON_TIMEOUT = 30

log = logging.getLogger("data_source")


def _polygon_to_df(results: list[dict]) -> pd.DataFrame:
    """Convert Polygon results to DataFrame with OHLCV + datetime index."""
    if not results:
        return pd.DataFrame()
    rows = []
    for r in results:
        rows.append({
            "Open": r.get("o", 0.0),
            "High": r.get("h", 0.0),
            "Low": r.get("l", 0.0),
            "Close": r.get("c", 0.0),
            "Volume": r.get("v", 0.0),
            "timestamp_ms": r.get("t", 0),
        })
    df = pd.DataFrame(rows)
    # Polygon returns ms timestamps in UTC
    df["Datetime"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
    df = df.set_index("Datetime").drop(columns=["timestamp_ms"])
    df = df[~df.index.duplicated(keep="first")]
    df = df.sort_index()
    return df


def fetch_polygon(symbol: str, days: int = 5, interval_min: int = 5,
                  api_key: str = None) -> pd.DataFrame:
    """Fetch OHLCV from Polygon.io crypto aggregates.

    Args:
        symbol: e.g. "BTC-USD" or "BTCUSD" (we normalize to X:BTCUSD)
        days: number of days back
        interval_min: bar size in minutes
        api_key: Polygon API key (default: env POLYGON_API_KEY)
    """
    api_key = api_key or os.environ.get("POLYGON_API_KEY", "")
    if not api_key:
        raise ValueError("POLYGON_API_KEY not set")

    # Normalize: BTC-USD -> X:BTCUSD
    clean = symbol.upper().replace("-", "").replace("/", "")
    ticker = f"X:{clean}"

    # Date range (UTC)
    to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    from_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    timespan = "minute" if interval_min < 60 else "hour"
    url = (
        f"{POLYGON_BASE}/v2/aggs/ticker/{ticker}/range/"
        f"{interval_min}/{timespan}/{from_date}/{to_date}"
    )
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 5000,
        "apiKey": api_key,
    }

    log.info(f"[massive/polygon] GET {ticker} range={interval_min}{timespan} {from_date}..{to_date}")
    # Try massive.com first, fall back to polygon.io
    for base in (MASSIVE_BASE, POLYGON_BASE):
        try:
            r = requests.get(f"{base}/v2/aggs/ticker/{ticker}/range/"
                             f"{interval_min}/{timespan}/{from_date}/{to_date}",
                             params=params, timeout=POLYGON_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            log.info(f"[data_source] {base} ok")
            break
        except requests.exceptions.HTTPError as e:
            if r.status_code in (401, 403):
                log.warning(f"[data_source] {base} {r.status_code} - try next")
                continue
            raise
    else:
        raise RuntimeError("Both massive.com and polygon.io failed")

    status = data.get("status", "")
    if status == "NOT_AUTHORIZED":
        # Plan doesn't include this timeframe (e.g., 5m crypto requires Currencies Basic)
        raise RuntimeError(f"Plan upgrade required: {data.get('message', 'NOT_AUTHORIZED')}")
    if status not in ("OK", "DELAYED"):
        raise RuntimeError(f"Polygon error: {status} {data.get('error')}")
    if status == "DELAYED":
        log.info("[polygon] Status DELAYED (free tier) - using 15-min delayed data")

    results = data.get("results", [])
    if not results:
        return pd.DataFrame()

    df = _polygon_to_df(results)
    log.info(f"[polygon] {len(df)} bars, last: {df.index[-1] if not df.empty else 'N/A'}")
    return df


def fetch_yfinance(symbol: str, period: str = "5d", interval: str = "5m",
                  max_retries: int = 3) -> pd.DataFrame:
    """Fetch OHLCV from yfinance (fallback).

    Note: yfinance 5m data is limited to last 60 days and is unreliable.
    Retries with exponential backoff + tries alternate tickers if first fails.
    """
    import yfinance as yf
    # yfinance sometimes returns "possibly delisted" — try alternate symbols
    alt_symbols = {
        "BTC-USD": ["BTC-USD", "BTC=F", "BTCUSD=X"],
        "ETH-USD": ["ETH-USD", "ETH=F"],
    }.get(symbol, [symbol])

    for sym in alt_symbols:
        for attempt in range(max_retries):
            try:
                log.info(f"[yfinance] attempt {attempt+1}: {sym} {period} {interval}")
                df = yf.download(sym, period=period, interval=interval,
                                 progress=False, auto_adjust=True, timeout=15)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                if df.empty:
                    log.warning(f"[yfinance] {sym} returned empty")
                    break  # try next symbol
                if df.index.tzinfo is None:
                    df.index = df.index.tz_localize("UTC")
                log.info(f"[yfinance] {sym} OK: {len(df)} bars")
                return df
            except Exception as e:
                log.warning(f"[yfinance] {sym} attempt {attempt+1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # 1s, 2s, 4s
    return pd.DataFrame()




def fetch_coingecko(symbol: str = "BTC-USD", days: int = 5) -> pd.DataFrame:
    """Fallback: fetch OHLCV from CoinGecko free API.

    CoinGecko has 5m granularity (for paid plans), but free tier gives
    hourly granularity. Useful as a last-resort fallback.
    """
    import requests
    coingecko_ids = {
        "BTC-USD": "bitcoin",
        "BTCUSD=X": "bitcoin",
        "ETH-USD": "ethereum",
    }
    cg_id = coingecko_ids.get(symbol, symbol.lower().replace("-usd", ""))
    
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart"
        params = {"vs_currency": "usd", "days": min(days, 90)}
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        
        prices = data.get("prices", [])
        volumes = data.get("total_volumes", [])
        if not prices:
            return pd.DataFrame()
        
        df = pd.DataFrame(prices, columns=["ts", "Close"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df = df.set_index("ts")
        
        if volumes:
            df["Volume"] = [v[1] for v in volumes]
        else:
            df["Volume"] = 0
        
        # CoinGecko only gives close prices, fill OHLC as close
        df["Open"] = df["Close"]
        df["High"] = df["Close"]
        df["Low"] = df["Close"]
        
        return df[["Open", "High", "Low", "Close", "Volume"]]
    except Exception as e:
        print(f"[coingecko] {symbol} error: {e}")
        return pd.DataFrame()


def fetch_bars(symbol: str = "BTC-USD", days: int = 5, interval_min: int = 5,
               use_polygon: bool = False, use_cache: bool = True) -> pd.DataFrame:
    """Main entry point: fetch OHLCV bars.

    Prefers yfinance (60d 5m, free, reliable).
    Polygon is unreliable on free tier (5 calls/min, often returns 0 for 5m today).
    Caches results in memory for 5 min to avoid rate limits.
    """
    cache_key = f"{symbol}_{days}_{interval_min}_{use_polygon}"
    if use_cache and cache_key in _CACHE:
        df_cached, ts = _CACHE[cache_key]
        if _time.time() - ts < _CACHE_TTL:
            log.info(f"[data_source] Cache hit ({cache_key}, age={int(_time.time()-ts)}s)")
            return df_cached

    # Try yfinance first (reliable, 60d 5m, free)
    df = fetch_yfinance(symbol, period=f"{min(days, 60)}d", interval=f"{interval_min}m")
    if not df.empty:
        log.info(f"[data_source] yfinance primary: {len(df)} bars")
        _CACHE[cache_key] = (df, _time.time())
        return df

    # Fall back to Polygon if explicitly requested and yfinance fails
    if use_polygon and os.environ.get("POLYGON_API_KEY"):
        log.warning("[data_source] yfinance empty, trying Polygon...")
        try:
            df = fetch_polygon(symbol, days=days, interval_min=interval_min)
            _CACHE[cache_key] = (df, _time.time())
            return df
        except Exception as e:
            log.warning(f"[data_source] Polygon also failed: {e}")

    # Last resort: CoinGecko (only BTC/ETH, 1h granularity)
    if symbol.upper().startswith(("BTC", "ETH")):
        log.warning(f"[data_source] All sources failed, trying CoinGecko fallback...")
        try:
            df = fetch_coingecko(symbol, days=days)
            if not df.empty:
                _CACHE[cache_key] = (df, _time.time())
                return df
        except Exception as e:
            log.warning(f"[data_source] CoinGecko also failed: {e}")
    return df


def fetch_bars_since(symbol: str, start_iso: str, interval_min: int = 5,
                     use_polygon: bool = True, max_bars: int = 5000) -> pd.DataFrame:
    """Fetch bars from start_iso to now."""
    df = fetch_bars(symbol, days=5, interval_min=interval_min, use_polygon=use_polygon)
    if df.empty:
        return df
    start = pd.Timestamp(start_iso)
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    return df[df.index >= start].head(max_bars)


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    df = fetch_bars("BTC-USD", days=2, interval_min=5)
    print(f"Got {len(df)} bars")
    if not df.empty:
        print(df.tail())
