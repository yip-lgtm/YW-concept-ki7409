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


def fetch(symbol: str, interval: str, rng: str, retries: int = 4):
    url = (API.format(symbol=symbol) + f"?range={rng}&interval={interval}"
           "&includePrePost=false&events=div%2Csplit")
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                              "AppleWebKit/537.36 Chrome/120 Safari/537.36"})
            with urllib.request.urlopen(req, timeout=60) as r:
                payload = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            if e.code in (429, 503):
                wait = 20 * (attempt + 1)
                print(f"    {e.code}, waiting {wait}s", flush=True)
                time.sleep(wait)
                continue
            raise
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(5)
            continue
        res = (payload.get("chart", {}).get("result") or [None])[0]
        if not res:
            last_err = f"no result: {payload.get('chart', {}).get('error')}"
            time.sleep(5)
            continue
        ts = res.get("timestamp") or []
        q = res.get("indicators", {}).get("quote", [{}])[0]
        o, h, l, c, v = (q.get("open") or [], q.get("high") or [], q.get("low") or [],
                          q.get("close") or [], q.get("volume") or [])
        bars = []
        for i, t in enumerate(ts):
            vals = (o[i] if i < len(o) else None, h[i] if i < len(h) else None,
                    l[i] if i < len(l) else None, c[i] if i < len(c) else None,
                    v[i] if i < len(v) else None)
            if any(x is None for x in vals[:4]):
                continue
            bars.append({"t": t * 1000, "o": vals[0], "h": vals[1],
                         "l": vals[2], "c": vals[3], "v": vals[4] or 0})
        return bars
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
