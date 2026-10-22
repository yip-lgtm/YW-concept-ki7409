#!/usr/bin/env python3
"""Fetch history from Yahoo Finance into the deep-history layout.

The Polygon deep history covers crypto only — it returns zero rows for
every CME future, which is why the TTrades family and Argon-Gold could
not be backtested on the instruments they actually trade. Yahoo has the
futures, and CI has network access to it, so the fetch runs there and
commits the result.

The output is the same shape as the Polygon files, so every tool that
reads the deep history reads this too:

    automation/data/deep_history/<SLUG>/<interval>/<YYYY-MM>.csv
    ts,open,high,low,close,volume

with ts in milliseconds. Intervals are written as 5m, 15m and 60m.

Usage:
    python3 automation/scripts/fetch_yahoo_history.py --ticker MGC=F
    python3 automation/scripts/fetch_yahoo_history.py --ticker MGC=F \
        --ticker MNQ=F --intervals 60m 15m 5m
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse

import pandas as pd
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_ROOT = REPO / "automation" / "data" / "deep_history"

# Yahoo caps how far back an interval reaches.
INTERVAL_RANGE = {"5m": "60d", "15m": "60d", "60m": "730d"}
INTERVAL_SEC = {"5m": 300, "15m": 900, "60m": 3600}
SLUGS = {"MGC=F": "MGCF", "GC=F": "GCF", "MNQ=F": "MNQF", "MES=F": "MESF",
         "M2K=F": "M2KF", "BTC-USD": "BTCUSD"}
API = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


def slug_for(ticker: str) -> str:
    if ticker in SLUGS:
        return SLUGS[ticker]
    return ticker.replace("=", "").replace("-", "").replace("^", "").upper()


def fetch(symbol: str, interval: str, rng: str, retries: int = 3):
    """Fetch bars through the repository's own data source.

    Writing a raw Yahoo client here was a mistake: Yahoo answers a
    datacentre address with 429 unless the request carries a cookie and
    a crumb, and the crumb request is refused the same way. The
    repository already has a client that works — data_source.fetch_bars,
    which goes through yfinance — and the 1h track was built with it, so
    the same path is used here rather than a second implementation.

    data_source also already handles the interval caps correctly:
    60 days for 5m/15m, 730 days for hourly and daily.
    """
    sys.path.insert(0, str(REPO / "automation" / "src"))
    from data_source import fetch_bars

    interval_min = {"5m": 5, "15m": 15, "60m": 60}[interval]
    days = 60 if interval_min < 60 else 730
    last_err = None
    for attempt in range(retries):
        try:
            df = fetch_bars(symbol, days=days, interval_min=interval_min,
                            use_cache=False)
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(10 * (attempt + 1))
            continue
        if df is None or df.empty:
            last_err = "no bars"
            time.sleep(10 * (attempt + 1))
            continue
        idx = df.index
        if idx.tzinfo is None:
            idx = idx.tz_localize("UTC")
        else:
            idx = idx.tz_convert("UTC")
        bars = []
        for ts, row in df.iterrows():
            o, h, l, c = (row.get("Open"), row.get("High"),
                           row.get("Low"), row.get("Close"))
            if any(x is None or (isinstance(x, float) and x != x) for x in (o, h, l, c)):
                continue
            v = row.get("Volume")
            bars.append({"t": int(pd.Timestamp(ts).timestamp() * 1000),
                         "o": float(o), "h": float(h), "l": float(l),
                         "c": float(c), "v": float(v) if v == v else 0.0})
        if bars:
            return bars
        last_err = "all rows incomplete"
    raise RuntimeError(f"{symbol} {interval}: {last_err}")


def write_month(path: Path, bars: list[dict]) -> int:
    if not bars:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts", "open", "high", "low", "close", "volume"])
        for b in bars:
            w.writerow([b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]])
    return len(bars)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", action="append", default=None,
                    help="Yahoo symbol, repeatable")
    ap.add_argument("--intervals", nargs="*", default=["60m", "15m", "5m"])
    args = ap.parse_args()
    tickers = args.ticker or ["MGC=F"]

    total = 0
    for ticker in tickers:
        slug = slug_for(ticker)
        for interval in args.intervals:
            rng = INTERVAL_RANGE.get(interval, "60d")
            print(f"[yahoo] {ticker} {interval} range={rng}", flush=True)
            try:
                bars = fetch(ticker, interval, rng)
            except Exception as e:
                print(f"  ✗ {ticker} {interval}: {e}", file=sys.stderr)
                continue
            if not bars:
                print(f"  ✗ {ticker} {interval}: no bars")
                continue
            by_month: dict[str, list] = {}
            for b in bars:
                month = datetime.fromtimestamp(b["t"] / 1000, tz=timezone.utc).strftime("%Y-%m")
                by_month.setdefault(month, []).append(b)
            out_dir = OUT_ROOT / slug / interval
            n = 0
            for month, mb in sorted(by_month.items()):
                n += write_month(out_dir / f"{month}.csv", mb)
            span = (datetime.fromtimestamp(bars[0]["t"] / 1000, tz=timezone.utc).date(),
                    datetime.fromtimestamp(bars[-1]["t"] / 1000, tz=timezone.utc).date())
            print(f"  ✓ {n} bars over {len(by_month)} months  {span[0]} → {span[1]}")
            total += n
            time.sleep(2)
    print(f"total {total} bars written under {OUT_ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
