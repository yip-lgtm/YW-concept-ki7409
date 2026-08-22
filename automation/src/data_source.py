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
from typing import Optional

import requests
import pandas as pd

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


def fetch_yfinance(symbol: str, period: str = "5d", interval: str = "5m") -> pd.DataFrame:
    """Fetch OHLCV from yfinance (fallback).

    Note: yfinance 5m data is limited to last 60 days and is unreliable.
    """
    import yfinance as yf
    log.info(f"[yfinance] {symbol} {period} {interval}")
    df = yf.download(symbol, period=period, interval=interval,
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty:
        return df
    # Ensure UTC index
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC")
    return df


def fetch_bars(symbol: str = "BTC-USD", days: int = 5, interval_min: int = 5,
               use_polygon: bool = True) -> pd.DataFrame:
    """Main entry point: fetch OHLCV bars.

    Prefers Polygon (POLYGON_API_KEY required). Falls back to yfinance.
    """
    if use_polygon and os.environ.get("POLYGON_API_KEY"):
        try:
            return fetch_polygon(symbol, days=days, interval_min=interval_min)
        except Exception as e:
            log.warning(f"[data_source] Polygon failed: {e}, falling back to yfinance")
    return fetch_yfinance(symbol, period="5d", interval=f"{interval_min}m")


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
