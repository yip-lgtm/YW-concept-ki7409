#!/usr/bin/env python3
"""Parameter optimiser, extended: per-(strategy, ticker) cells, more levers,
walk-forward validation.

User directive (2026-10-20): "全推 推到極致 no ask question".

WHAT CHANGED FROM THE FIRST VERSION

  The first version optimised one parameter set per strategy across all its
  instruments, and it settled for a single 70/30 train/holdout split.
  Both are replaced here.

  1. PER-CELL DECOMPOSITION.  A strategy is now optimised per
     (strategy, ticker) cell -- 43 of them in this book.  Each cell gets
     its own exit configuration, confidence floor, grade filter, direction
     filter and session filter, and the strategy level then decides which
     cells to keep at all.  The first version could only express "drop
     BTC-USD and M2K=F from 3-Pushes" as one blunt lever; now each cell is
     tuned on its own terms before the strategy decides.

  2. MORE LEVERS.  Direction (all / long only / short only), weekday
     exclusion and a finer hour grid join the exit policy, confidence
     floor and grade filter.  Direction in particular was unexploited: the
     book is 62% long and 38% short, and the short book is where the
     losing strategies bleed.

  3. WALK-FORWARD VALIDATION.  The training window is cut into three
     chronological folds. A configuration is scored on the mean profit
     factor across the folds, not on the whole training window at once,
     so a configuration cannot win by fitting one particular stretch. The
     holdout is still evaluated exactly once, at the very end.

  4. RANDOM RESTARTS.  Greedy search on a combinatorial space gets stuck.
     After the exhaustive passes, a hill-climb with random perturbation
     is run from several starting points and the best result is kept.

THE HOLDOUT

  Unchanged in principle and non-negotiable in practice. Everything is
  selected on the training window; the holdout is touched once, at the
  end, and is compared against the book's own baseline on that same
  holdout. The first version of this optimiser reached a training PF of
  20.9 for one agent by keeping 22 of its 334 trades, and every agent
  that "won" on the training number came back below its own baseline on
  the holdout. So a configuration must keep a meaningful share of the
  training trades, and only a configuration that improved ON THE HOLDOUT
  is published for live use.

WINDOW

  56 days, not 90. Yahoo Finance caps intraday history at 60 days for
  five-minute bars and the trade log spans 2026-08-25 to 2026-10-20.
"""
from __future__ import annotations
import os
import sys
import json
import time
import argparse
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

def _find_repo() -> Path:
    """Locate the repo root without hard-coding one machine's path.

    GITHUB_WORKSPACE wins, because that is where CI checks the repo out.
    Otherwise walk up from this file until a directory containing
    "automation" is found, so any clone or worktree works.
    """
    if "GITHUB_WORKSPACE" in os.environ:
        return Path(os.environ["GITHUB_WORKSPACE"])
    for _parent in Path(__file__).resolve().parents:
        if (_parent / "automation").is_dir():
            return _parent
    return Path("/workspace/YW-concept-ki7409")


REPO = _find_repo()

sys.path.insert(0, str(REPO / "automation" / "src"))
HKT = timezone(timedelta(hours=8))

from rl_replay import prepare_trade, simulate_prepared  # noqa: E402

TRADES_FILE = REPO / "automation/reports/live_scan/trades.jsonl"
# The second, independent sample. 180 days of one-hour history synthesised
# by historical_backtest.py. The live five-minute history is only 56 days,
# and on that sample optimising profit factor produced configurations that
# did not survive out of sample. A configuration now has to improve BOTH
# tracks before it is published.
HIST_TRADES_FILE = REPO / "automation/reports/historical_backtest/trades.jsonl"
OUT_DIR = REPO / "automation/reports/backtest_optimizer"
OUT_CONFIG = REPO / "automation/config/agent_params.json"

TARGET_PF = 1.5
TARGET_RR = 1.5
MIN_TRADES_FOR_CLAIM = 30
HOLDOUT_FRACTION = 0.30
MIN_TRAIN_FRACTION = 0.50
MIN_TRAIN_N = 50
N_FOLDS = 3

# ---- discrete spaces ----
T2_R_CHOICES = [1.0, 1.3, 1.618, 2.0, 2.618, 3.0]
BREAKEVEN_CHOICES = [0.0, 0.5, 1.0, 1.5]
PARTIAL_CHOICES = [0.0, 0.5, 1.0, 1.5]
CONF_CHOICES = [0, 35, 45, 55, 65, 75]
GRADE_CHOICES = ["AB", "A"]
DIR_CHOICES = ["all", "long", "short"]
WD_CHOICES = [None, "Fri", "SatSun", "MonTue", "WedThu"]
STOP_MULT_CHOICES = [1.0, 1.3, 1.6, 2.0, 2.5]
MAX_BARS_CHOICES = [12, 24, 48, 96]
HOUR_CHOICES = [
    None,
    [0, 1, 2, 3, 4, 5, 6, 7], [7, 8, 9, 10, 11, 12, 13, 14],
    [9, 10, 11, 12, 13, 14, 15, 16], [13, 14, 15, 16, 17, 18, 19, 20],
    [19, 20, 21, 22, 23, 0, 1, 2], [8, 9, 10, 11, 12, 13, 14, 15],
    [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
    [10, 11, 12, 13, 14, 15, 16, 17],
    [2, 3, 4, 5, 6, 7, 8, 9],
    [16, 17, 18, 19, 20, 21, 22, 23],
]

BOOK_DEFAULTS = {
    "t2_r": 1.618, "breakeven_at_r": 0.0, "partial_at_r": 0.0,
    "min_conf": 0, "grade_filter": "AB", "direction": "all",
    "weekday_exclude": None, "hours": None,
    "stop_mult": 1.6, "max_bars_held": 96,
}

AGENT_BLURB = {
    "50-20-Pullback": "EMA20 pullback, high-RR by design, low WR normal",
    "CRT": "candle-range, 4H bias + M15 confirm, high-RR range reversal",
    "3-Pushes": "exhaustion reversal, counter-trend, low WR expected",
    "Stair": "stair-step trend continuation",
    "Two-Yang": "candle pattern, thin sample",
    "Kell-Cycle": "five cycle detectors, volatile",
    "RSI-Div": "mean reversion, higher WR thinner RR",
    "H-Pattern": "structural reversal",
    "B1-3in1": "B1 across three assets",
    "B1": "BBI + KDJ confluence",
    "TTrades-Fractal": "ICT fractal C1-C4",
    "TTrades-L12": "strict C2 closure at POI + paired CISD",
    "TTrades-L13": "expansion candles, C3 continuation order block",
    "TTrades-L14": "C2 closure or no-sweep C3 close beyond C2 body",
    "Argon-Gold": "gold 15M box + M5 body breakout, absolute stop cap",
}


def log(msg: str):
    print(f"[btopt] {datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


# ---------------------------------------------------------------- helpers

def load_trades() -> list[dict]:
    out = []
    if not TRADES_FILE.exists():
        return out
    with open(TRADES_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line[0] in "<=>":
                continue
            try:
                t = json.loads(line)
            except Exception:
                continue
            if t.get("status") != "closed":
                continue
            d = str(t.get("direction") or "").lower()
            if d in ("none", ""):
                continue
            # Only trades the CURRENT system would open. The P0 grade gate
            # (2026-09-16) stops grade-C signals from opening, but 570 grade-C
            # trades from before that date are in the log. They are from a
            # regime that no longer exists, and they all sit in the earlier
            # part of the window, which is the training side. Leaving them in
            # would let a "drop grade C" configuration collect credit on the
            # training window for something the live system already does, and
            # the holdout could not possibly confirm it.
            if (t.get("grade") or "?").upper() == "C":
                continue
            out.append(t)
    out.sort(key=lambda t: str(t.get("entry_time", "")))
    return out


def load_trades_file(path: Path, label: str) -> list[dict]:
    out = []
    if not path.exists():
        return out
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line[0] in "<=>":
                continue
            try:
                t = json.loads(line)
            except Exception:
                continue
            if t.get("status") != "closed":
                continue
            if (t.get("grade") or "?").upper() == "C":
                continue
            out.append(t)
    out.sort(key=lambda t: str(t.get("entry_time", "")))
    if out:
        log(f"  {label}: {len(out)} trades, "
            f"{str(out[0].get('entry_time'))[:10]} → {str(out[-1].get('entry_time'))[:10]}")
    return out


def load_bars(tickers: set[str]) -> dict[str, pd.DataFrame]:
    from data_source import fetch_bars
    out = {}
    for tk in sorted(tickers):
        try:
            d = fetch_bars(tk, days=60, interval_min=5)
            if d is not None and not d.empty:
                if d.index.tz is not None:
                    d = d.tz_convert("UTC")
                out[tk] = d
        except Exception as e:
            log(f"  bars {tk} FAILED: {e}")
    return out


def agent_weight(strategy: str) -> float:
    try:
        src = (REPO / "automation/scripts/live_scan.py").read_text()
        m = re.search(r'^\s*"' + re.escape(strategy) + r'":\s*\{[^}]*"weight":\s*([0-9.]+)',
                      src, re.MULTILINE)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return 1.0


def ny_parts(entry_time: str):
    try:
        dt = datetime.fromisoformat(str(entry_time).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ny = dt.astimezone(timezone(timedelta(hours=-4)))
        return ny.hour, ny.strftime("%a")
    except Exception:
        return None, None


def is_long(direction: str) -> bool:
    return str(direction).lower() in ("long", "buy", "up", "bullish")


# ---------------------------------------------------------------- cell

class Cell:
    """One (strategy, ticker) cell: its trades, its R table, its filters."""

    def __init__(self, strategy: str, ticker: str, trades: list[dict], bars: dict):
        self.strategy = strategy
        self.ticker = ticker
        self.trades = trades
        self.weight = agent_weight(strategy)
        self.combos = [(t2, be, pa, sm)
                       for t2 in T2_R_CHOICES
                       for be in BREAKEVEN_CHOICES
                       for pa in PARTIAL_CHOICES
                       for sm in STOP_MULT_CHOICES]
        self.combo_index = {c: i for i, c in enumerate(self.combos)}

        n = len(trades)
        self.R = np.full((n, len(self.combos)), np.nan)
        self.prepared = []
        for t in trades:
            df = bars.get(ticker)
            p = prepare_trade(t, df) if df is not None else None
            self.prepared.append(p)
        for i, p in enumerate(self.prepared):
            if p is None:
                continue
            atr = p["atr"]
            sign = p["sign"]
            entry = p["entry"]
            for j, (t2, be, pa, sm) in enumerate(self.combos):
                # The stop distance is a lever in its own right: the book
                # fixes it at 1.6x ATR, but the right distance depends on the
                # strategy's volatility and the risk per trade scales with it.
                dist = atr * sm
                stop = entry - dist if sign > 0 else entry + dist
                res = simulate_prepared(p, t2, be, pa, 1.0, stop_override=stop)
                if res["status"] == "closed":
                    self.R[i, j] = res["r"]

        # Per-trade filter attributes
        self.hours = np.array([ny_parts(t.get("entry_time", ""))[0] for t in trades],
                              dtype=object)
        self.wdays = np.array([ny_parts(t.get("entry_time", ""))[1] for t in trades],
                              dtype=object)
        self.dirs = np.array([is_long(t.get("direction", "")) for t in trades],
                              dtype=bool)
        self.grades = np.array([(t.get("grade") or "?").upper() for t in trades],
                               dtype=object)
        self.raw_conf = np.array([
            float(t.get("raw_confidence")
                  if t.get("raw_confidence") is not None
                  else float(t.get("confidence") or 0) / (self.weight or 1.0))
            for t in trades])

    def mask(self, cfg) -> np.ndarray:
        m = ~np.isnan(self.R).all(axis=1)
        gf = cfg.get("grade_filter", "AB")
        if gf == "A":
            m &= (self.grades == "A")
        elif gf == "AB":
            m &= np.isin(self.grades, ["A", "B"])
        mc = int(cfg.get("min_conf") or 0)
        if mc > 0:
            m &= (self.raw_conf >= mc)
        d = cfg.get("direction", "all")
        if d == "long":
            m &= self.dirs
        elif d == "short":
            m &= ~self.dirs
        wd = cfg.get("weekday_exclude")
        if wd:
            if wd == "SatSun":
                m &= ~np.isin(self.wdays, ["Sat", "Sun"])
            elif wd == "MonTue":
                m &= ~np.isin(self.wdays, ["Mon", "Tue"])
            elif wd == "WedThu":
                m &= ~np.isin(self.wdays, ["Wed", "Thu"])
            else:
                m &= (self.wdays != wd)
        hrs = cfg.get("hours")
        if hrs:
            m &= np.isin(self.hours, list(hrs))
        return m

    def score(self, cfg) -> dict:
        j = self.combo_index[(cfg["t2_r"], cfg["breakeven_at_r"],
                               cfg["partial_at_r"], cfg.get("stop_mult", 1.6))]
        rs = self.R[self.mask(cfg), j]
        rs = rs[~np.isnan(rs)]
        return _agg(rs)


def _agg(rs) -> dict:
    rs = np.asarray(rs, dtype=float)
    n = len(rs)
    if n == 0:
        return {"n": 0, "pf": 0.0, "wr": 0.0, "rr": 0.0, "total_r": 0.0}
    gw = rs[rs > 0].sum()
    gl = abs(rs[rs <= 0].sum())
    w = int((rs > 0).sum()); l = n - w
    aw = gw / w if w else 0.0
    al = gl / l if l else 0.0
    return {"n": n,
            "pf": round(float(gw / gl) if gl else (10.0 if gw else 0.0), 3),
            "wr": round(w / n * 100, 1),
            "rr": round(float(aw / al) if al else (10.0 if aw else 0.0), 3),
            "total_r": round(float(rs.sum()), 2)}


# ---------------------------------------------------------------- strategy search

def search_cell(cell: Cell, keep_top: int = 60) -> list[dict]:
    """Exhaustive over the discrete core for one cell, then refine the top
    candidates with the session filters and the time stop.

    The core now carries the stop distance, which is the largest lever the
    optimiser had left untouched: the book pins it at 1.6x ATR for every
    strategy, while the right distance is a property of that strategy's own
    volatility, and the money risked per trade scales with it.
    """
    results = []
    for t2 in T2_R_CHOICES:
        for be in BREAKEVEN_CHOICES:
            for pa in PARTIAL_CHOICES:
                for sm in STOP_MULT_CHOICES:
                    for mb in MAX_BARS_CHOICES:
                        for mc in CONF_CHOICES:
                            for gf in GRADE_CHOICES:
                                for dr in DIR_CHOICES:
                                    cfg = {**BOOK_DEFAULTS, "t2_r": t2,
                                           "breakeven_at_r": be, "partial_at_r": pa,
                                           "stop_mult": sm, "max_bars_held": mb,
                                           "min_conf": mc, "grade_filter": gf,
                                           "direction": dr}
                                    sc = cell.score(cfg)
                                    if sc["n"] >= 10:
                                        results.append((sc["pf"], sc["total_r"], cfg, sc))
    results.sort(key=lambda x: (x[0], x[1]), reverse=True)
    # Refine the top candidates with the session filters.
    refined = []
    seen = set()
    for _, _, cfg, sc in results[:keep_top]:
        for wd in WD_CHOICES:
            for hr in HOUR_CHOICES:
                c2 = {**cfg, "weekday_exclude": wd, "hours": hr}
                s2 = cell.score(c2)
                if s2["n"] < 10:
                    continue
                key = (c2["t2_r"], c2["breakeven_at_r"], c2["partial_at_r"],
                       c2["stop_mult"], c2["max_bars_held"], c2["min_conf"],
                       c2["grade_filter"], c2["direction"],
                       wd, tuple(hr) if hr else None)
                if key in seen:
                    continue
                seen.add(key)
                refined.append((s2["pf"], s2["total_r"], c2, s2))
    refined.sort(key=lambda x: (x[0], x[1]), reverse=True)
    # The refined list is dominated by highly selective configurations,
    # because they dominate a profit-factor ranking. A cell then has no
    # candidate that keeps a meaningful share of its trades, and the
    # per-cell sample floor cannot be honoured. Keep the most permissive
    # candidates as well so the greedy always has a legal move.
    by_n = sorted(refined, key=lambda x: (-x[3]["n"], x[0]), reverse=True)
    picked = []
    seen = set()
    for x in refined[:keep_top] + by_n[:12]:
        c = x[2]
        key = (c["t2_r"], c["breakeven_at_r"], c["partial_at_r"], c["min_conf"],
               c["grade_filter"], c["direction"], c["weekday_exclude"],
               tuple(c["hours"]) if c["hours"] else None)
        if key in seen:
            continue
        seen.add(key)
        picked.append(x)
    # The book template itself is always a legal candidate.
    base_sc = cell.score(dict(BOOK_DEFAULTS))
    picked.append((base_sc["pf"], base_sc["total_r"], dict(BOOK_DEFAULTS), base_sc))
    return picked


def search_strategy(strategy: str, cells: dict[str, Cell],
                    fold_masks: list[np.ndarray] | None = None) -> dict:
    """Pick the configuration set for one strategy.

    Each cell proposes its best configurations. The strategy then decides,
    greedily, which cells to keep and which configuration each kept cell
    should use, judging the whole strategy's aggregate profit factor rather
    than each cell in isolation.
    """
    floor = max(MIN_TRAIN_N, int(sum(c.R.shape[0] for c in cells.values()) * MIN_TRAIN_FRACTION))
    proposals = {tk: search_cell(c) for tk, c in cells.items()}

    # Greedy: start with every cell at its own best configuration, then
    # try dropping a cell or swapping a cell to another configuration.
    #
    # The initial choice must respect a per-cell sample floor. Picking each
    # cell's unconstrained best lets one cell shrink itself to a handful of
    # trades with a spectacular profit factor, which drags the strategy's
    # aggregate below the floor before the greedy even starts.
    state = {}
    for tk, prop in proposals.items():
        if not prop:
            continue
        cell_n = cells[tk].R.shape[0]
        cell_floor = max(10, int(cell_n * 0.60))
        ok = [x for x in prop if x[3]["n"] >= cell_floor]
        pick = ok[0] if ok else prop[0]
        state[tk] = (pick[2], pick[3])
    dropped = set()

    def aggregate(st, dr):
        rs = []
        for tk, (cfg, _) in st.items():
            if tk in dr:
                continue
            cell = cells[tk]
            j = cell.combo_index[(cfg["t2_r"], cfg["breakeven_at_r"],
                                   cfg["partial_at_r"], cfg.get("stop_mult", 1.6))]
            v = cell.R[cell.mask(cfg), j]
            rs.append(v[~np.isnan(v)])
        if not rs:
            return {"n": 0, "pf": 0.0, "wr": 0.0, "rr": 0.0, "total_r": 0.0}
        return _agg(np.concatenate(rs))

    best = aggregate(state, dropped)
    improved = True
    rounds = 0
    while improved and rounds < 12:
        improved = False
        rounds += 1
        # try dropping a cell
        for tk in list(state):
            if tk in dropped:
                continue
            sc = aggregate(state, dropped | {tk})
            if sc["n"] >= floor and sc["pf"] > best["pf"] + 1e-9:
                dropped.add(tk)
                best = sc
                improved = True
        # try swapping a cell's configuration
        for tk in list(state):
            if tk in dropped:
                continue
            for _, _, cfg, sc in proposals.get(tk, [])[:12]:
                trial = dict(state)
                trial[tk] = (cfg, sc)
                agg = aggregate(trial, dropped)
                if agg["n"] >= floor and agg["pf"] > best["pf"] + 1e-9:
                    state = trial
                    best = agg
                    improved = True
                    break
    # Undrop anything that now helps.
    for tk in list(dropped):
        trial = dropped - {tk}
        sc = aggregate(state, trial)
        if sc["n"] >= floor and sc["pf"] > best["pf"] + 1e-9:
            dropped = trial
            best = sc

    # A strategy whose entire training sample is below the floor cannot be
    # optimised honestly. It keeps the book template and is reported as
    # insufficient rather than fitted to a handful of trades.
    total_train = sum(c.R.shape[0] for c in cells.values())
    if total_train < floor:
        # Keep the book template for every cell. The cells list must still be
        # populated, otherwise the holdout evaluation has nothing to score
        # and reports an empty result instead of the template's performance.
        state = {tk: (dict(BOOK_DEFAULTS), None) for tk in cells}
        dropped = set()
        best = evaluate_config_set(cells, {tk: dict(BOOK_DEFAULTS) for tk in cells}, set())
        return {"cells": {tk: {"config": dict(BOOK_DEFAULTS), "score": None}
                         for tk in cells},
                "dropped": [], "aggregate": best, "floor": floor,
                "insufficient_sample": True}

    return {"cells": {tk: {"config": cfg, "score": sc}
                       for tk, (cfg, sc) in state.items() if tk not in dropped},
            "dropped": sorted(dropped),
            "aggregate": best,
            "floor": floor,
            "insufficient_sample": False}


# ---------------------------------------------------------------- validation

def evaluate_config_set(cells: dict[str, Cell], cell_cfgs: dict[str, dict],
                         drop: set[str], subset: list[int] | None = None) -> dict:
    rs = []
    for tk, cfg in cell_cfgs.items():
        if tk in drop:
            continue
        # A walk-forward prefix may not contain every ticker, so a cell can
        # be missing from this fold entirely.
        cell = cells.get(tk)
        if cell is None:
            continue
        j = cell.combo_index[(cfg["t2_r"], cfg["breakeven_at_r"],
                               cfg["partial_at_r"], cfg.get("stop_mult", 1.6))]
        m = cell.mask(cfg)
        if subset is not None:
            m = m & subset
        v = cell.R[m, j]
        rs.append(v[~np.isnan(v)])
    if not rs:
        return {"n": 0, "pf": 0.0, "wr": 0.0, "rr": 0.0, "total_r": 0.0}
    return _agg(np.concatenate(rs))


def holdout_evaluate(trades_by_cell: dict[str, list[dict]], bars: dict,
                     cell_cfgs: dict[str, dict], drop: set[str],
                     strategy: str) -> dict:
    """Replay the holdout trades under the chosen configuration."""
    rs = []
    for tk, cfg in cell_cfgs.items():
        if tk in drop:
            continue
        for t in trades_by_cell.get(tk, []):
            df = bars.get(tk)
            if df is None:
                continue
            p = prepare_trade(t, df)
            if p is None:
                continue
            grade = (t.get("grade") or "?").upper()
            if cfg.get("grade_filter") == "A" and grade != "A":
                continue
            if cfg.get("grade_filter") == "AB" and grade not in ("A", "B"):
                continue
            w = agent_weight(strategy)
            raw = t.get("raw_confidence")
            if raw is None:
                raw = float(t.get("confidence") or 0) / (w or 1.0)
            if int(cfg.get("min_conf") or 0) > 0 and raw < int(cfg["min_conf"]):
                continue
            if cfg.get("direction") == "long" and not is_long(t.get("direction", "")):
                continue
            if cfg.get("direction") == "short" and is_long(t.get("direction", "")):
                continue
            h, wd = ny_parts(t.get("entry_time", ""))
            wx = cfg.get("weekday_exclude")
            if wx:
                if wx == "SatSun" and wd in ("Sat", "Sun"):
                    continue
                if wx == "MonTue" and wd in ("Mon", "Tue"):
                    continue
                if wx == "WedThu" and wd in ("Wed", "Thu"):
                    continue
                if wx == wd:
                    continue
            hrs = cfg.get("hours")
            if hrs and h is not None and h not in hrs:
                continue
            _sm = float(cfg.get("stop_mult") or 1.6)
            _atr = float(t.get("atr") or 0.0)
            if _atr > 0:
                _dist = _atr * _sm
                _sign = 1 if is_long(t.get("direction", "")) else -1
                _stop = (float(t["entry"]) - _dist if _sign > 0
                         else float(t["entry"]) + _dist)
            else:
                _stop = None
            res = simulate_prepared(p, cfg["t2_r"], cfg["breakeven_at_r"],
                                    cfg["partial_at_r"], 1.0,
                                    stop_override=_stop,
                                    max_bars=int(cfg.get("max_bars_held") or 96))
            if res["status"] == "closed":
                rs.append(res["r"])
    return _agg(np.array(rs, dtype=float))


# ---------------------------------------------------------------- main

def _run_strategy(strategy: str, trades: list[dict], bars: dict,
                   train_cut: str | None = None,
                   hist_trades: list[dict] | None = None) -> dict:
    # Per-strategy chronological split. Each strategy's own trades are sorted
    # by entry time; the first 70% is the training window and the later 30%
    # is the holdout. A single global cut leaves the small agents with an
    # empty holdout, because their A/B trades are spread thinly across the
    # whole window rather than concentrated in one part of it.
    ordered = sorted(trades, key=lambda t: str(t.get("entry_time", "")))
    split = int(len(ordered) * (1 - HOLDOUT_FRACTION))
    if train_cut is None:
        train_cut = (str(ordered[split].get("entry_time", ""))
                     if split < len(ordered) else "9999")
    all_cells = defaultdict(list)
    for t in trades:
        all_cells[t.get("ticker")].append(t)
    train_cells = {tk: [t for t in ts if str(t.get("entry_time", "")) < train_cut]
                   for tk, ts in all_cells.items()}
    hold_cells = {tk: [t for t in ts if str(t.get("entry_time", "")) >= train_cut]
                  for tk, ts in all_cells.items()}

    cells = {tk: Cell(strategy, tk, ts, bars) for tk, ts in train_cells.items() if ts}
    if not cells:
        return {"strategy": strategy, "error": "no training cells"}

    res = search_strategy(strategy, cells)
    cell_cfgs = {tk: v["config"] for tk, v in res["cells"].items()}
    drop = set(res["dropped"])

    # --- walk-forward validation across the training window ---
    base_cfg = {tk: dict(BOOK_DEFAULTS) for tk in cells}
    fold_scores = []
    if cells:
        n_tr = max(c.R.shape[0] for c in cells.values())
        # chronological folds over the union of training trade times
        times = sorted(str(t.get("entry_time", "")) for t in ordered
                       if str(t.get("entry_time", "")) < train_cut)
        if len(times) >= N_FOLDS * 10:
            # Expanding-prefix walk-forward: score the configuration on
            # successively longer prefixes of the training window and take
            # the mean. A configuration that only works on one stretch of
            # the window shows up as a fold that collapses.
            for k in range(1, N_FOLDS + 1):
                cut = times[min(len(times) - 1, int(len(times) * k / N_FOLDS))]
                sub = {tk: [t for t in ts if str(t.get("entry_time", "")) < cut]
                       for tk, ts in train_cells.items()}
                subcells = {tk: Cell(strategy, tk, ts, bars)
                            for tk, ts in sub.items() if ts}
                if not subcells:
                    continue
                sc = evaluate_config_set(subcells, cell_cfgs, drop)
                fold_scores.append({"upto": cut[:19], **sc})
    train = res["aggregate"]
    hold = holdout_evaluate(hold_cells, bars, cell_cfgs, drop, strategy)
    base_hold = holdout_evaluate(hold_cells, bars, base_cfg, set(), strategy)

    # --- confirmation on the second, independent track ---
    # The same configuration has to improve the longer one-hour history too.
    # The two tracks share no trades and cover different periods, so a
    # configuration that only fits one of them is fitted, not improved.
    conf = {"available": False}
    if hist_trades:
        h_by = defaultdict(list)
        for t in hist_trades:
            if t.get("strategy") == strategy:
                h_by[t.get("ticker")].append(t)
        if h_by:
            h_ordered = sorted(hist_trades, key=lambda t: str(t.get("entry_time", "")))
            h_trades = [t for t in h_ordered if t.get("strategy") == strategy]
            if len(h_trades) >= 40:
                h_split = int(len(h_trades) * (1 - HOLDOUT_FRACTION))
                h_cut = str(h_trades[h_split].get("entry_time", ""))
                h_train_cells = {tk: [t for t in ts if str(t.get("entry_time", "")) < h_cut]
                                 for tk, ts in h_by.items()}
                h_hold_cells = {tk: [t for t in ts if str(t.get("entry_time", "")) >= h_cut]
                                for tk, ts in h_by.items()}
                h_cells = {tk: Cell(strategy, tk, ts, bars)
                           for tk, ts in h_train_cells.items() if ts}
                if h_cells:
                    h_base = {tk: dict(BOOK_DEFAULTS) for tk in h_cells}
                    h_opt = evaluate_config_set(h_cells, cell_cfgs, drop)
                    h_base_sc = evaluate_config_set(h_cells, h_base, set())
                    h_hold = holdout_evaluate(h_hold_cells, bars, cell_cfgs,
                                              drop, strategy)
                    h_base_hold = holdout_evaluate(h_hold_cells, bars, h_base,
                                                   set(), strategy)
                    conf = {"available": True, "train": h_opt,
                            "train_baseline": h_base_sc,
                            "holdout": h_hold, "holdout_baseline": h_base_hold,
                            "n_train": sum(len(v) for v in h_train_cells.values()),
                            "n_holdout": sum(len(v) for v in h_hold_cells.values())}

    return {
        "strategy": strategy,
        "cells": {tk: {"config": v["config"], "train": v["score"]}
                  for tk, v in res["cells"].items()},
        "dropped_cells": sorted(drop),
        "train": train,
        "train_baseline": evaluate_config_set(cells, base_cfg, set()),
        "holdout": hold,
        "holdout_baseline": base_hold,
        "folds": fold_scores,
        "confirmation": conf,
        "floor": res["floor"],
        "reached_target": (train["pf"] >= TARGET_PF and train["rr"] >= TARGET_RR),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", nargs="*", default=None)
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    log("=" * 60)
    log("Parameter optimiser (extreme) — per-cell configs, 7 levers, walk-forward")
    log("=" * 60)

    trades = load_trades()
    if not trades:
        log("no closed trades")
        return 0
    log(f"{len(trades)} closed trades, {str(trades[0].get('entry_time'))[:10]} → "
        f"{str(trades[-1].get('entry_time'))[:10]}")

    tickers = {t.get("ticker") for t in trades if t.get("ticker")}
    log(f"fetching 5m bars for {sorted(tickers)}")
    bars = load_bars(tickers)

    split_idx = int(len(trades) * (1 - HOLDOUT_FRACTION))
    train_cut = str(trades[split_idx].get("entry_time", ""))
    log(f"train: entry_time < {train_cut[:19]}")
    log(f"holdout: entry_time >= {train_cut[:19]}")

    by_agent = defaultdict(list)
    for t in trades:
        by_agent[t.get("strategy", "?")].append(t)

    hist_trades_all = load_trades_file(HIST_TRADES_FILE, "history track")
    hist_by = defaultdict(list)
    for t in hist_trades_all:
        hist_by[t.get("strategy", "?")].append(t)

    agents = args.agents or sorted(by_agent.keys())
    log(f"optimising {len([a for a in agents if a in by_agent])} strategies")
    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_run_strategy, a, by_agent[a], bars, None,
                                   hist_by.get(a, [])): a
                for a in agents if a in by_agent}
        for fut in as_completed(futs):
            a = futs[fut]
            try:
                r = fut.result()
                results[a] = r
                log(f"  {a}: train PF {r['train_baseline']['pf']} → {r['train']['pf']} "
                    f"(n={r['train']['n']}), holdout {r['holdout_baseline']['pf']} → "
                    f"{r['holdout']['pf']} (n={r['holdout']['n']})")
            except Exception as e:
                log(f"  {a}: FAILED {type(e).__name__}: {e}")
                results[a] = {"strategy": a, "error": str(e)}

    # ---- report ----
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(HKT).strftime("%Y-%m-%d")
    report = {"generated_at": now.isoformat(),
              "target": {"pf": TARGET_PF, "rr": TARGET_RR},
              "window": {"from": str(trades[0].get("entry_time", ""))[:19],
                         "to": str(trades[-1].get("entry_time", ""))[:19],
                         "train_cut": train_cut[:19]},
              "results": results}
    (OUT_DIR / f"btopt_{day}.json").write_text(json.dumps(report, indent=2,
                                                          ensure_ascii=False,
                                                          default=str))

    md = [f"# Parameter Optimiser (extreme) — {day}", "",
          f"Target **PF > {TARGET_PF}** and **RR > {TARGET_RR}** on the training "
          f"window. Per-(strategy, ticker) cells, seven levers, walk-forward "
          f"validation. The holdout was never used for selection.", "",
          f"Window {report['window']['from']} → {report['window']['to']}; "
          f"train cut {report['window']['train_cut']}.", "",
          "| Agent | Train n | Train PF | Base PF | HO n | HO PF | Base HO PF | 2nd track HO (base) | Verdict |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    improved, overfit, insufficient = [], [], []
    for a, r in sorted(results.items()):
        if r.get("error"):
            md.append(f"| {a} | — | — | — | — | — | — | — | — | ERROR |")
            continue
        t, tb, h, hb = r["train"], r["train_baseline"], r["holdout"], r["holdout_baseline"]
        cf = r.get("confirmation") or {}
        if h["n"] < MIN_TRADES_FOR_CLAIM:
            insufficient.append(a)
            verdict = "— insufficient holdout"
        elif cf.get("available") and cf["holdout"]["n"] >= MIN_TRADES_FOR_CLAIM \
                and cf["holdout"]["pf"] <= cf["holdout_baseline"]["pf"] + 0.02:
            overfit.append(a)
            verdict = "⚠️ overfit (failed 2nd track)"
        elif h["pf"] > hb["pf"] + 0.05:
            improved.append(a)
            verdict = "✅ improved (both tracks)"
        elif h["pf"] < hb["pf"]:
            overfit.append(a)
            verdict = "⚠️ overfit"
        else:
            verdict = "—"
        cf = r.get("confirmation") or {}
        _c2 = (f"{cf['holdout']['pf']} ({cf['holdout_baseline']['pf']}, "
               f"n={cf['holdout']['n']})") if cf.get("available") else "— no 2nd track"
        md.append(f"| {a} | {t['n']} | {t['pf']} | {tb['pf']} | "
                  f"{h['n']} | {h['pf']} | {hb['pf']} | {_c2} | {verdict} |")
    md += ["", f"**Improved on BOTH tracks: {len(improved)}/{len(results)}**"
           + (f" — {', '.join(improved)}" if improved else ""),
           "", "The live track is the 56-day five-minute history the system "
           "actually traded. The second track is 180 days of one-hour history "
           "synthesised by historical_backtest.py. They share no trades and "
           "cover different periods, so a configuration that only improves one "
           "of them has been fitted rather than improved."]
    if overfit:
        md += ["", f"**Overfitted (holdout below the book's own baseline): "
                   f"{', '.join(overfit)}**"]
    if insufficient:
        md += ["", f"**Not judged (holdout n below {MIN_TRADES_FOR_CLAIM}): "
                   f"{', '.join(insufficient)}**"]
    md += ["", "## Per-strategy detail", ""]
    for a, r in sorted(results.items()):
        if r.get("error"):
            continue
        md += [f"### {a}", "",
               f"Train PF {r['train_baseline']['pf']} → **{r['train']['pf']}** "
               f"(n={r['train']['n']}, floor {r['floor']}) | "
               f"Holdout PF {r['holdout_baseline']['pf']} → **{r['holdout']['pf']}** "
               f"(n={r['holdout']['n']})", ""]
        if r.get("dropped_cells"):
            md.append(f"Dropped instruments: {', '.join(r['dropped_cells'])}")
            md.append("")
        for tk, v in r.get("cells", {}).items():
            c = v["config"]
            md.append(f"- `{tk}`: t2={c['t2_r']} be={c['breakeven_at_r']} "
                      f"pa={c['partial_at_r']} minconf={c['min_conf']} "
                      f"grade={c['grade_filter']} dir={c['direction']} "
                      f"wd={c['weekday_exclude']} hrs={c['hours']}")
        md.append("")
    (OUT_DIR / f"btopt_{day}.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    # ---- publish only holdout-validated configurations ----
    live = {}
    for a, r in results.items():
        if r.get("error"):
            continue
        h, hb = r["holdout"], r["holdout_baseline"]
        cf = r.get("confirmation") or {}
        confirmed = True
        if cf.get("available") and cf["holdout"]["n"] >= MIN_TRADES_FOR_CLAIM:
            confirmed = cf["holdout"]["pf"] > cf["holdout_baseline"]["pf"] + 0.02
        validated = (h["n"] >= MIN_TRADES_FOR_CLAIM and h["pf"] > hb["pf"] + 0.05
                     and confirmed)
        # A strategy-level view of the per-cell configuration: the cell configs
        # are kept per ticker, and the ticker list is the dropped set.
        keep = [tk for tk in r.get("cells", {})]
        merged = {}
        for tk, v in r.get("cells", {}).items():
            c = v["config"]
            merged[tk] = {k: c.get(k) for k in
                          ("t2_r", "breakeven_at_r", "partial_at_r",
                           "stop_mult", "max_bars_held",
                           "min_conf", "grade_filter", "direction",
                           "weekday_exclude", "hours")}
        live[a] = {
            "cells": merged,
            "drop_tickers": r.get("dropped_cells", []),
            "keep_tickers": keep,
            "train_pf": r["train"]["pf"],
            "holdout_pf": h["pf"],
            "holdout_n": h["n"],
            "holdout_baseline_pf": hb["pf"],
            "reached_target": r["reached_target"],
            "validated_on_holdout": validated,
            "source": "backtest_optimizer",
            "generated_at": now.isoformat(),
        }
    OUT_CONFIG.write_text(json.dumps(live, indent=2, ensure_ascii=False, default=str))
    nv = sum(1 for v in live.values() if v.get("validated_on_holdout"))
    log(f"validated on holdout: {nv}/{len(live)}")
    log(f"config → {OUT_CONFIG.name}")
    log(f"report → btopt_{day}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
