#!/usr/bin/env python3
"""Fetch deep intraday history from Polygon for the instruments it covers.

Why
---
The optimiser needs a longer five-minute sample than Yahoo will serve.
Yahoo caps intraday history at 60 days; the live system has only 56 days of
real trades, and optimising profit factor on a sample that small produces
configurations that do not survive out of sample.

Polygon's coverage is partial and the difference matters:

  crypto  X:BTCUSD — five-minute bars go back at least a year, and the
          pagination chain confirms it. This is the only instrument in the
          book that can be extended, because the key in the Actions
          secrets returns zero results for every CME future (MNQ, MES,
          M2K, MGC, GC) with status DELAYED and resultsCount 0 — futures
          require a different plan.

How
---
Polygon's aggregate endpoint returns at most 50,000 bars per request, so
each month is requested as its own window and paged through. The result is
one CSV per month under automation/data/deep_history/<SYMBOL>/, which the
historical backtest reads back.

Everything here needs the Actions secret, so this runs from a workflow
rather than from a machine with a key.
"""
from __future__ import annotations
import os
import sys
import json
import time
import csv
import urllib.request
import urllib.error
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

OUT_ROOT = REPO / "automation/data/deep_history"
API = "https://api.polygon.io/v2/aggs/ticker"

# Polygon ticker -> output directory name. Only the instruments Polygon
# actually covers are listed; the CME futures return zero results on this
# plan and are omitted rather than fetched into empty files.
INSTRUMENTS = {
    "X:BTCUSD": "BTCUSD",
}

# Minutes -> Polygon multiplier and timespan
INTERVALS = {
    5: ("5", "minute"),
    15: ("15", "minute"),
    60: ("60", "minute"),
}

FIELDS = ["t", "o", "h", "l", "c", "v"]


def log(msg: str):
    print(f"[deep-hist] {datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


def _get(url: str):
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"message": f"{type(e).__name__}: {e}"}


def _rate_limited(j) -> bool:
    if not isinstance(j, dict):
        return False
    if j.get("status") == "ERROR" and "exceeded the maximum requests" in str(
            j.get("error", "")):
        return True
    return "exceeded the maximum requests" in str(j.get("message", ""))


def fetch_window(ticker: str, mult: str, span: str, frm: str, to: str,
                 key: str, retries: int = 5):
    """Fetch one window, following the pagination chain. Returns a list of bars.

    An empty result is not the same as no data. A rate-limited response
    carries an error body and no results array, and treating it as "no data
    for this month" silently truncates the history at whatever point the
    per-minute cap was hit. Rate-limited windows are retried with a longer
    wait instead.
    """
    url = (f"{API}/{ticker}/range/{mult}/{span}/{frm}/{to}"
           f"?apiKey={key}&limit=50000&sort=asc")
    bars = []
    pages = 0
    while url and pages < 60:
        code, j = _get(url)
        if not isinstance(j, dict):
            break
        if _rate_limited(j):
            wait = 20 * (retries + 1)
            log(f"    rate limited, waiting {wait}s")
            time.sleep(wait)
            retries -= 1
            if retries < 0:
                break
            continue
        res = j.get("results") or []
        bars.extend(res)
        pages += 1
        url = j.get("next_url")
        if url:
            if "apiKey=" not in url:
                url += f"&apiKey={key}"
            time.sleep(1.5)          # stay under the per-minute request cap
    return bars, pages


def month_windows(start: date, end: date):
    """Yield (from_date, to_date) month by month."""
    cur = start
    while cur < end:
        nxt = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        stop = min(nxt, end)
        yield cur, stop
        cur = stop


def write_month(path: Path, bars: list[dict]) -> int:
    if not bars:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts", "open", "high", "low", "close", "volume"])
        for b in bars:
            w.writerow([b.get("t"), b.get("o"), b.get("h"), b.get("l"),
                        b.get("c"), b.get("v")])
    return len(bars)


def main() -> int:
    key = os.environ.get("POLYGON_API_KEY", "")
    if not key:
        log("POLYGON_API_KEY not set — nothing to do")
        return 0

    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=400)
    ap.add_argument("--interval", type=int, default=5)
    ap.add_argument("--tickers", nargs="*", default=list(INSTRUMENTS))
    args = ap.parse_args()

    mult, span = INTERVALS[args.interval]
    end = date.today()
    start = end - timedelta(days=args.days)

    log(f"fetching {args.interval}m history for {args.tickers}, "
        f"{start} -> {end}")

    for ticker in args.tickers:
        out_dir = OUT_ROOT / INSTRUMENTS.get(ticker, ticker.replace(":", "_")) / f"{args.interval}m"
        total = 0
        months = 0
        for frm, to in month_windows(start, end):
            bars, pages = fetch_window(ticker, mult, span, frm.isoformat(),
                                       to.isoformat(), key)
            if not bars:
                log(f"  {ticker} {frm} -> {to}: no data")
                continue
            name = f"{frm.isoformat()}.csv"
            n = write_month(out_dir / name, bars)
            total += n
            months += 1
            log(f"  {ticker} {frm} -> {to}: {n} bars ({pages} pages)")
            time.sleep(3.0)
        log(f"  {ticker}: {total} bars over {months} months -> {out_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
