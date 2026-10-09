#!/usr/bin/env python3
"""TTrades position tracker — turns signals into closed trades.

Why this exists (2026-10-09): the TTrades family has 12 agents (Fractal
base + L12/L13/L14, each on MNQ/MGC/BTC) and they were all writing
signals and nothing else. weight_optimizer.py and daily_settlement.py
both need CLOSED trades — profit factor, win rate, reward:risk and an exit
timestamp — and a signal with no tracker never produces any of those. A
strategy that can never be scored can never be promoted or demoted, so
the whole settlement and weighting loop was blind to the TTrades family.

What it does, mirroring live_scan_tracker.py:
  1. reads every per-ticker signal log
  2. opens a paper position the first time it sees a signal_id
  3. walks 5m bars forward from entry, checking SL then T1
  4. T1 is a partial: 50% reduces, and per the 2026-10-08 user directive the
     remainder closes at T2 (1.618R). This is the same T2-close rule the
     rest of the book runs on, so R-multiples are comparable across agents.
  5. writes the closed trade to trades.jsonl and appends to open positions

Every position is paper. TTrades is not wired to a broker, and the
existing check_paper_mode() gate in ttrades_btc.py is untouched.
"""
from __future__ import annotations
import os
import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

sys.path.insert(0, str(REPO / "automation" / "scripts"))
HKT = timezone(timedelta(hours=8))

SIGNAL_DIR = REPO / "automation" / "reports" / "ttrades_btc"
TRADES_FILE = SIGNAL_DIR / "trades.jsonl"
POSITIONS_FILE = SIGNAL_DIR / "positions.json"

TICKERS = ["MNQ=F", "MGC=F", "BTC-USD"]
# Every agent in the family publishes levels as of 2026-10-09. The base
# Fractal reports them in the flat signal; the L-series report them nested
# under `result`. Both are handled below.
LEVEL_BEARING_AGENTS = {
    "TTrades-Fractal", "TTrades-L12", "TTrades-L13", "TTrades-L14",
}

# Bars to walk forward before giving up on a position.
MAX_BARS_HELD = 96          # 96 x 5m = 8h
# T1 partial close, remainder rides to T2.
T1_REDUCE_FRACTION = 0.5
T2_R_MULTIPLE = 1.618


def log(msg: str):
    print(f"[tt-tracker] {msg}", flush=True)


def slug(ticker: str) -> str:
    return ticker.replace("=", "").replace("-", "").replace("^", "")


def load_positions() -> dict:
    if not POSITIONS_FILE.exists():
        return {}
    try:
        return json.loads(POSITIONS_FILE.read_text())
    except Exception:
        return {}


def save_positions(pos: dict):
    POSITIONS_FILE.write_text(json.dumps(pos, indent=2, default=str))


def parse_ts(ts):
    if not ts:
        return None
    try:
        ts = ts.replace("Z", "+00:00").replace(" ", "T")
        d = datetime.fromisoformat(ts)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return None


def read_signals() -> list[dict]:
    """Read every signal log and normalise both record shapes.

    The base Fractal writes a flat record with entry/sl/t1 at the top level.
    The L-series writes {strategy, ticker, actionable, result:{...}} with the
    levels nested inside `result`. Both are flattened to the same shape so the
    rest of the tracker does not care which agent produced a signal.
    """
    out = []
    paths = sorted(SIGNAL_DIR.glob("signals_*.jsonl"))
    legacy = SIGNAL_DIR / "signals.jsonl"
    if legacy.exists():
        paths.append(legacy)
    # L-series: one log per ticker, records shaped {strategy, result:{...}}
    paths.extend(sorted(SIGNAL_DIR.glob("l_strategies_*.jsonl")))

    for p in paths:
        for line in p.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line or line[0] in "<=>":
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if not d.get("actionable"):
                continue
            d["_src"] = p.name

            res = d.get("result") or {}
            if res:
                if not res.get("has_levels"):
                    d["_no_levels"] = res.get("levels_note", "levels unavailable")
                    continue
                d = {
                    "strategy": d.get("strategy"),
                    "ticker": d.get("ticker"),
                    "ts": d.get("ts"),
                    "direction": res.get("direction"),
                    "grade": None,
                    "confidence": None,
                    "entry": res.get("entry"),
                    "sl": res.get("sl"),
                    "t1": res.get("t1"),
                    "t2_close": res.get("t2_close"),
                    "t3": res.get("t3"),
                    "units": None,
                    "risk_per_unit": res.get("risk"),
                    "reason": f"{d.get('strategy')}: {res.get('stage', '')}",
                    "swing_type": res.get("closure") or res.get("stage"),
                    "sl_basis": res.get("sl_basis"),
                }
            out.append(d)
    return out


def signal_id(sig: dict) -> str:
    return f"{sig.get('strategy','?')}|{sig.get('ticker','?')}|{sig.get('ts','?')}"


# 21d covers the longest realistic gap between a signal and the next run.
def fetch_bars(ticker: str, days: int = 21):
    try:
        import ttrades_btc as base
        return base.fetch_ohlcv(ticker, "5m", f"{days}d")
    except Exception as e:
        log(f"  fetch_bars({ticker}) failed: {e}")
        return None


def check_exit(direction: str, sl: float, t1: float, t2: float,
               df: pd.DataFrame, t1_hit: bool):
    """Walk bars forward. SL first (conservative), then T1, then T2.

    Returns (closed, exit_price, exit_level, R_multiple, bars_held, t1_hit,
    exit_time). exit_time is the bar timestamp itself, never a reconstructed
    index — see the coverage guard in main() for why that matters.
    """
    for i, (ts, bar) in enumerate(df.iterrows(), start=1):
        hi, lo = float(bar["High"]), float(bar["Low"])
        if direction in ("long", "buy", "up"):
            if lo <= sl:
                return True, sl, "SL", -1.0, i, t1_hit, ts
            if not t1_hit and hi >= t1:
                t1_hit = True
            if hi >= t2 or t1_hit:
                return True, t2, "T2", (T2_R_MULTIPLE if t1_hit else 1.0), i, t1_hit, ts
        else:
            if hi >= sl:
                return True, sl, "SL", -1.0, i, t1_hit, ts
            if not t1_hit and lo <= t1:
                t1_hit = True
            if lo <= t2 or t1_hit:
                return True, t2, "T2", (T2_R_MULTIPLE if t1_hit else 1.0), i, t1_hit, ts
    return False, None, None, 0.0, len(df), t1_hit, None


def main() -> int:
    log(f"=== {datetime.now(HKT).strftime('%Y-%m-%d %H:%M:%S HKT')} ===")

    positions = load_positions()
    signals = read_signals()
    log(f"{len(signals)} actionable signal(s) in per-ticker logs; "
        f"{len(positions)} open position(s)")

    # --- open new positions -------------------------------------------------
    opened = 0
    for sig in signals:
        sid = signal_id(sig)
        if sid in positions:
            continue
        if sig.get("strategy") not in LEVEL_BEARING_AGENTS:
            continue
        try:
            entry = float(sig["entry"]); sl = float(sig["sl"])
            t1 = float(sig["t1"]); t2 = float(sig.get("t2_close") or sig["t1"])
        except (KeyError, TypeError, ValueError):
            continue
        et = parse_ts(sig.get("ts"))
        if not et:
            continue
        # L-series detectors do not size a position; the base sizes off
        # RISK_AMOUNT / distance-to-stop. Reuse that so $ risk per trade is
        # identical across the family instead of scoring L-series as if it
        # were riskless.
        units = sig.get("units")
        if units is None:
            try:
                import ttrades_btc as base
                risk_dist = abs(float(sig["entry"]) - float(sig["sl"]))
                units = base.RISK_AMOUNT / risk_dist if risk_dist > 0 else 0.0
                units = min(units, base.TTRADES_MAX_UNITS_BTC)
                if units * float(sig["entry"]) > base.TTRADES_MAX_NOTIONAL_USD:
                    units = base.TTRADES_MAX_NOTIONAL_USD / float(sig["entry"])
            except Exception:
                units = 0.0
        positions[sid] = {
            "signal_id": sid,
            "strategy": sig.get("strategy"),
            "ticker": sig.get("ticker"),
            "direction": sig.get("direction"),
            "grade": sig.get("grade"),
            "confidence": sig.get("confidence"),
            "entry": entry, "sl": sl, "t1": t1, "t2": t2,
            "units": units,
            "risk_per_unit": sig.get("risk_per_unit"),
            "entry_time": sig.get("ts"),
            "entry_ts": et.isoformat(),
            "t1_hit": False,
            "status": "open",
            "reason": sig.get("reason", ""),
            "swing_type": sig.get("swing_type"),
        }
        opened += 1
        log(f"  OPEN {sig.get('strategy')} {sig.get('ticker')} {sig.get('direction')} "
            f"@{entry:,.2f} SL {sl:,.2f} T2 {t2:,.2f}")

    # --- check exits --------------------------------------------------------
    bars_cache: dict[str, pd.DataFrame | None] = {}
    closed = 0
    for sid, pos in list(positions.items()):
        if pos.get("status") != "open":
            continue
        tk = pos["ticker"]
        if tk not in bars_cache:
            bars_cache[tk] = fetch_bars(tk)
        df = bars_cache[tk]
        if df is None or df.empty:
            continue

        et = parse_ts(pos.get("entry_ts"))
        if et is None:
            continue

        # COVERAGE GUARD (2026-10-09). `df.index > et` is only a valid slice
        # if the fetched window actually starts at or before the entry. The
        # 5m feed is fetched with a 7d lookback, so any position older than
        # that has NO bars near its entry: every bar in the slice is weeks
        # later, the SL/T2 test runs against the wrong prices, and the trade
        # is recorded as a nonsense 1-bar close. Such positions are marked
        # untrackable instead of being scored.
        first_bar = df.index[0]
        if first_bar.tz is None and et.tzinfo is not None:
            et_cmp = et.tz_localize(None)
            first_cmp = first_bar
        elif first_bar.tz is not None and et.tzinfo is None:
            et_cmp = et.tz_localize("UTC")
            first_cmp = first_bar
        else:
            et_cmp, first_cmp = et, first_bar
        if first_cmp > et_cmp:
            gap_days = (first_cmp - et_cmp).total_seconds() / 86400
            pos["status"] = "untrackable"
            pos["note"] = (f"5m data starts {gap_days:.0f}d after entry "
                           f"(window too short to replay this trade)")
            log(f"  UNTRACKABLE {pos['strategy']} {tk}: {pos['note']}")
            continue

        after = df[df.index > (et if df.index.tz is not None else et_cmp)]
        if after.empty:
            continue

        hit, px, level, R, bars, t1_hit, exit_dt = check_exit(
            pos["direction"], pos["sl"], pos["t1"], pos["t2"],
            after, bool(pos.get("t1_hit")))
        if not hit:
            # mark stale so a position nobody watches does not live forever
            if len(after) > MAX_BARS_HELD:
                pos["status"] = "expired"
                pos["note"] = f"no SL/T2 within {MAX_BARS_HELD} bars"
            continue

        units = float(pos.get("units") or 0)
        risk = float(pos.get("risk_per_unit") or abs(pos["entry"] - pos["sl"]) or 0)
        pnl = R * risk * units if risk and units else 0.0
        # exit_dt is the bar's own timestamp, taken from the bar that actually
        # triggered, so it cannot drift when the slice is short.
        exit_time = exit_dt if exit_dt is not None else after.index[-1]

        trade = {
            "signal_id": sid,
            "strategy": pos["strategy"],
            "ticker": tk,
            "direction": pos["direction"],
            "grade": pos.get("grade"),
            "confidence": pos.get("confidence"),
            "entry": pos["entry"],
            "sl": pos["sl"], "t1": pos["t1"], "t2": pos["t2"],
            "units": units,
            "risk_per_unit": risk,
            "entry_time": pos.get("entry_time"),
            "exit_time": exit_time.isoformat(),
            "exit_price": px,
            "exit_level": level,
            "R_multiple": R,
            "pnl_usd": round(pnl, 2),
            "bars_held": bars,
            "status": "closed",
            "swing_type": pos.get("swing_type"),
            "reason": pos.get("reason", ""),
        }
        with TRADES_FILE.open("a") as f:
            f.write(json.dumps(trade, default=str) + "\n")
        pos["status"] = "closed"
        pos["exit_time"] = trade["exit_time"]
        pos["exit_level"] = level
        pos["R_multiple"] = R
        closed += 1
        log(f"  CLOSE {pos['strategy']} {tk} {level} R={R:+.3f} ${pnl:+.2f} "
            f"after {bars} bars")

    save_positions(positions)

    # --- report coverage gap ----------------------------------------------
    l_agents = set()
    for p in SIGNAL_DIR.glob("l_strategies_*.jsonl"):
        for line in p.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line or line[0] in "<=>":
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("actionable"):
                l_agents.add(d.get("strategy"))
    if l_agents:
        log(f"  NOTE: {sorted(l_agents)} fired but publish no SL/T1/T2 yet, "
            f"so they cannot be tracked or scored. Gap: "
            f"{len(l_agents)} agents visible in signals, absent from trades.jsonl")

    log(f"  opened={opened} closed={closed} open={sum(1 for p in positions.values() if p.get('status')=='open')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
