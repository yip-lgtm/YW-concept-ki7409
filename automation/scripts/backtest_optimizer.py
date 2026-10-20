#!/usr/bin/env python3
"""Autonomous parameter optimiser — exhaustive search with an optional LLM proposer.

User directive (2026-10-20): "無限token Backtest 90日 no ask question 自動llm
iteration 所有agent 無限次改參數 直至所有agent PF高過1.5 RR高過1.5".

WHY THIS IS NOT AN LLM LOOP

  The parameter space is small and completely enumerable:

    t2_r             6 options      breakeven_at_r   4 options
    partial_at_r     4 options      min_conf         6 options
    grade_filter     2 options      drop_tickers     2^k subsets
    keep_hours       coarse grid

  Exhaustive search over the discrete core (6x4x4x6x2 = 1152 combinations)
  plus a greedy pass over the ticker and hour subsets finds the global
  optimum of the discrete space, deterministically, in seconds. An LLM
  proposing one configuration at a time cannot beat that, and it burns
  tokens doing it. The LLM is kept as an optional extra proposer for the
  cases where the lever set is open-ended, and it is used when the token
  plan has quota; the search runs either way.

  This is also why the LLM quota running out was not a blocker: the search
  is the optimiser, not the model.

THE HOLDOUT

  Iterating parameters against a profit-factor target, on the same data,
  until the target is hit, is curve fitting by construction. With six
  independent levers and a thousand trades per agent, PF 1.5 is reachable
  on data that was optimised into it.

  So the trades are split:

    TRAIN     the first 70% of the window -- the search only ever sees this
    HOLDOUT   the last 30% -- never used for selection, and evaluated
              exactly once, at the end, with the chosen configuration

  Both numbers are reported. An agent whose training PF is 1.9 and whose
  holdout PF is 0.9 has not been improved, it has been fitted, and the
  report says so in those words.

WHAT IS COUNTERFACTUALLY EXACT AND WHAT IS NOT

  Exact, from the trade log alone:
    exit policy     t2_r, breakeven_at_r, partial_at_r
    ticker filter   which instruments the agent trades
    session filter  which hours it trades
    grade filter    A only, or A and B
    confidence floor a threshold on the LLM's raw confidence

  The confidence floor needs the LLM's raw confidence, before the weight
  multiplier. The tracker only started recording that recently, so for the
  historical trades it is recovered as recorded_confidence divided by the
  agent's configured weight, which is exact wherever the weight was at its
  default of 1.0 -- the large majority of the log.

  NOT modelled: the entry itself. A parameter change that would have
  suppressed a signal cannot bring in a signal that never fired. The
  optimiser therefore works over the realised trade set, and the holdout
  evaluation inherits the same limitation.

WINDOW

  The directive asked for 90 days. Yahoo Finance caps intraday history at
  60 days for 5-minute bars, and the trade log spans 56 days
  (2026-08-25 to 2026-10-20). 90 days of 5-minute data is not
  obtainable from this feed, so the optimiser uses the 56 days that
  exist and splits those into train and holdout.
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

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

sys.path.insert(0, str(REREPO := REPO / "automation" / "src"))
HKT = timezone(timedelta(hours=8))

from rl_replay import prepare_trade, simulate_prepared  # noqa: E402

TRADES_FILE = REPO / "automation/reports/live_scan/trades.jsonl"
OUT_DIR = REPO / "automation/reports/backtest_optimizer"
OUT_CONFIG = REPO / "automation/config/agent_params.json"

# ---------------- targets ----------------
TARGET_PF = 1.5
TARGET_RR = 1.5
MIN_TRADES_FOR_CLAIM = 30
HOLDOUT_FRACTION = 0.30
TRAIN_EVAL_LIMIT = 500
# A configuration must keep a meaningful share of the training trades. Without
# this the search wins by keeping the ten luckiest trades, which is
# overfitting by construction: the first run of this optimiser reached a
# training PF of 20.9 for 3-Pushes by discarding 93% of its trades, and
# every one of those agents came back below its own baseline on the
# holdout.
MIN_TRAIN_FRACTION = 0.50
MIN_TRAIN_N = 50

# ---------------- discrete parameter space ----------------
T2_R_CHOICES = [1.0, 1.3, 1.618, 2.0, 2.618, 3.0]
BREAKEVEN_CHOICES = [0.0, 0.5, 1.0, 1.5]
PARTIAL_CHOICES = [0.0, 0.5, 1.0, 1.5]
CONF_CHOICES = [0, 35, 45, 55, 65, 75]
GRADE_CHOICES = ["AB", "A"]
# Coarse hour grid: contiguous blocks rather than arbitrary 24-bit subsets.
HOUR_BLOCKS = [
    [], [0, 1, 2, 3, 4, 5, 6, 7], [7, 8, 9, 10, 11, 12, 13, 14],
    [9, 10, 11, 12, 13, 14, 15, 16], [13, 14, 15, 16, 17, 18, 19, 20],
    [19, 20, 21, 22, 23, 0, 1, 2], [8, 9, 10, 11, 12, 13, 14, 15],
    [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
]

BOOK_DEFAULTS = {
    "t2_r": 1.618, "breakeven_at_r": 0.0, "partial_at_r": 0.0,
    "min_conf": 0, "grade_filter": "AB",
    "keep_tickers": [], "drop_tickers": [], "keep_hours": [],
}

AGENT_BLURB = {
    "50-20-Pullback": "EMA20 pullback in an uptrend; high-RR by design, low win rate is normal",
    "CRT": "candle-range theory, 4H bias + M15 confirmation, high-RR range reversal",
    "3-Pushes": "three-pushes exhaustion reversal; counter-trend, low WR expected",
    "Stair": "stair-step trend continuation, needs momentum",
    "Two-Yang": "two-bullish-one-bearish candle pattern, thin sample",
    "Kell-Cycle": "five cycle detectors, volatile",
    "RSI-Div": "RSI divergence mean reversion, higher WR, thinner RR",
    "H-Pattern": "structural reversal pattern",
    "B1-3in1": "B1 across three assets combined",
    "B1": "BBI + KDJ multi-indicator confluence",
    "TTrades-Fractal": "ICT fractal C1-C4 candle structure",
    "TTrades-L12": "strict C2 closure at a POI with paired CISD",
    "TTrades-L13": "expansion candles only, C3 continuation order block",
    "TTrades-L14": "C2 closure or no-sweep C3 close beyond the C2 body",
    "Argon-Gold": "gold 15M box + M5 body breakout, absolute stop cap",
}


def log(msg: str):
    print(f"[btopt] {datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


# ---------------------------------------------------------------- data

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
            out.append(t)
    out.sort(key=lambda t: str(t.get("entry_time", "")))
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


def ny_hour(entry_time: str):
    try:
        dt = datetime.fromisoformat(str(entry_time).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone(timedelta(hours=-4))).hour
    except Exception:
        return None


# ---------------------------------------------------------------- core

class AgentSearch:
    """Precomputes the exit-policy R for every trade under every discrete
    combination, then searches the space. The expensive part (replaying the
    bar path) happens once per trade; the search itself is then just
    aggregation over a table."""

    def __init__(self, strategy: str, trades: list[dict], bars: dict, train_cut: str):
        self.strategy = strategy
        self.weight = agent_weight(strategy)
        self.trades = trades
        self.train = [t for t in trades if str(t.get("entry_time", "")) < train_cut]
        self.holdout = [t for t in trades if str(t.get("entry_time", "")) >= train_cut]
        self.all_tickers = sorted({t.get("ticker") for t in trades if t.get("ticker")})
        self.train = self.train[-TRAIN_EVAL_LIMIT:]

        # Precompute the R table.
        self.combos = [(t2, be, pa)
                       for t2 in T2_R_CHOICES
                       for be in BREAKEVEN_CHOICES
                       for pa in PARTIAL_CHOICES]
        self.combo_index = {c: i for i, c in enumerate(self.combos)}
        n_tr = len(self.train)
        self.R = np.full((n_tr, len(self.combos)), np.nan)
        self.prepared = []
        for t in self.train:
            df = bars.get(t.get("ticker"))
            if df is None:
                self.prepared.append(None)
                continue
            p = prepare_trade(t, df)
            self.prepared.append(p)
        for i, p in enumerate(self.prepared):
            if p is None:
                continue
            for j, (t2, be, pa) in enumerate(self.combos):
                res = simulate_prepared(p, t2, be, pa, 1.0)
                if res["status"] == "closed":
                    self.R[i, j] = res["r"]
        self.ok = ~np.isnan(self.R).all(axis=1)
        log(f"  {strategy}: train={len(self.train)} holdout={len(self.holdout)} "
            f"prepared={int(self.ok.sum())} combos={len(self.combos)}")

    # ---- filters that do not need a re-replay ----
    def _mask(self, cfg) -> np.ndarray:
        m = np.zeros(len(self.train), dtype=bool)
        for i, t in enumerate(self.train):
            if not self.ok[i]:
                continue
            tk = t.get("ticker")
            if cfg["keep_tickers"] and tk not in cfg["keep_tickers"]:
                continue
            if tk in cfg["drop_tickers"]:
                continue
            grade = (t.get("grade") or "?").upper()
            want = cfg["grade_filter"]
            if want == "A" and grade != "A":
                continue
            if want == "AB" and grade not in ("A", "B"):
                continue
            if cfg["min_conf"] > 0:
                raw = t.get("raw_confidence")
                if raw is None:
                    raw = float(t.get("confidence") or 0) / (self.weight or 1.0)
                if raw < cfg["min_conf"]:
                    continue
            if cfg["keep_hours"]:
                h = ny_hour(t.get("entry_time", ""))
                if h is not None and h not in cfg["keep_hours"]:
                    continue
            m[i] = True
        return m

    def _score(self, cfg, mask) -> dict:
        j = self.combo_index[(cfg["t2_r"], cfg["breakeven_at_r"], cfg["partial_at_r"])]
        rs = self.R[mask, j]
        rs = rs[~np.isnan(rs)]
        n = len(rs)
        if n == 0:
            return {"n": 0, "pf": 0.0, "wr": 0.0, "rr": 0.0, "total_r": 0.0}
        gw = rs[rs > 0].sum()
        gl = abs(rs[rs <= 0].sum())
        pf = gw / gl if gl > 0 else (10.0 if gw > 0 else 0.0)
        w = int((rs > 0).sum()); l = n - w
        aw = gw / w if w else 0.0
        al = gl / l if l else 0.0
        rr = aw / al if al else (10.0 if aw > 0 else 0.0)
        return {"n": n, "pf": round(float(pf), 3),
                "wr": round(w / n * 100, 1), "rr": round(float(rr), 3),
                "total_r": round(float(rs.sum()), 2)}

    def _min_n(self) -> int:
        return max(MIN_TRAIN_N, int(len(self.train) * MIN_TRAIN_FRACTION))

    def search(self) -> dict:
        """Exhaustive over the discrete core, then greedy over the subsets.

        Every candidate must keep at least `_min_n` training trades. The
        objective is profit factor, but only among configurations that
        actually still trade.
        """
        floor = self._min_n()
        best = None
        # ---- stage 1: exhaustive discrete core ----
        for t2 in T2_R_CHOICES:
            for be in BREAKEVEN_CHOICES:
                for pa in PARTIAL_CHOICES:
                    for mc in CONF_CHOICES:
                        for gf in GRADE_CHOICES:
                            cfg = dict(BOOK_DEFAULTS)
                            cfg.update(t2_r=t2, breakeven_at_r=be, partial_at_r=pa,
                                       min_conf=mc, grade_filter=gf)
                            m = self._mask(cfg)
                            sc = self._score(cfg, m)
                            if sc["n"] < floor:
                                continue
                            if best is None or (sc["pf"], sc["total_r"]) > (best[1]["pf"], best[1]["total_r"]):
                                best = (dict(cfg), sc)
        if best is None:
            # No configuration clears the sample floor. Keep the book template
            # rather than a degenerate one, and say so in the report.
            base = dict(BOOK_DEFAULTS)
            sc = self._score(base, self._mask(base))
            return {"config": base, "train": sc, "searched": 0,
                    "no_feasible_config": True}

        # ---- stage 2: greedy ticker exclusion ----
        cur_cfg, cur_sc = dict(best[0]), best[1]
        improved = True
        rounds = 0
        while improved and rounds < 8:
            improved = False
            rounds += 1
            for tk in self.all_tickers:
                if tk in cur_cfg["drop_tickers"]:
                    continue
                trial = dict(cur_cfg)
                trial["drop_tickers"] = cur_cfg["drop_tickers"] + [tk]
                sc = self._score(trial, self._mask(trial))
                if sc["n"] >= floor and sc["pf"] > cur_sc["pf"] + 1e-9:
                    cur_cfg, cur_sc = trial, sc
                    improved = True
        # ---- stage 3: greedy hour block ----
        improved = True
        rounds = 0
        while improved and rounds < 8:
            improved = False
            for block in HOUR_BLOCKS:
                trial = dict(cur_cfg)
                trial["keep_hours"] = block
                sc = self._score(trial, self._mask(trial))
                if sc["n"] >= floor and sc["pf"] > cur_sc["pf"] + 1e-9:
                    cur_cfg, cur_sc = trial, sc
                    improved = True
        # ---- stage 4: re-tune the core after the filters ----
        for t2 in T2_R_CHOICES:
            for be in BREAKEVEN_CHOICES:
                for pa in PARTIAL_CHOICES:
                    for mc in CONF_CHOICES:
                        for gf in GRADE_CHOICES:
                            trial = dict(cur_cfg)
                            trial.update(t2_r=t2, breakeven_at_r=be, partial_at_r=pa,
                                         min_conf=mc, grade_filter=gf)
                            sc = self._score(trial, self._mask(trial))
                            if sc["n"] < floor:
                                continue
                            if sc["pf"] > cur_sc["pf"] + 1e-9:
                                cur_cfg, cur_sc = trial, sc
        return {"config": cur_cfg, "train": cur_sc,
                "searched": len(T2_R_CHOICES) * len(BREAKEVEN_CHOICES) *
                            len(PARTIAL_CHOICES) * len(CONF_CHOICES) * len(GRADE_CHOICES)}

    # ---- holdout evaluation: needs a real replay, done once ----
    def holdout_score(self, cfg) -> dict:
        rows = []
        for t in self.holdout:
            df = self._hbars.get(t.get("ticker"))
            if df is None:
                continue
            p = prepare_trade(t, df)
            if p is None:
                continue
            grade = (t.get("grade") or "?").upper()
            if cfg["grade_filter"] == "A" and grade != "A":
                continue
            if cfg["grade_filter"] == "AB" and grade not in ("A", "B"):
                continue
            if cfg["keep_tickers"] and t.get("ticker") not in cfg["keep_tickers"]:
                continue
            if t.get("ticker") in cfg["drop_tickers"]:
                continue
            if cfg["min_conf"] > 0:
                raw = t.get("raw_confidence")
                if raw is None:
                    raw = float(t.get("confidence") or 0) / (self.weight or 1.0)
                if raw < cfg["min_conf"]:
                    continue
            if cfg["keep_hours"]:
                h = ny_hour(t.get("entry_time", ""))
                if h is not None and h not in cfg["keep_hours"]:
                    continue
            res = simulate_prepared(p, cfg["t2_r"], cfg["breakeven_at_r"],
                                    cfg["partial_at_r"], 1.0)
            if res["status"] == "closed":
                rows.append(res["r"])
        if not rows:
            return {"n": 0, "pf": 0.0, "wr": 0.0, "rr": 0.0, "total_r": 0.0}
        rs = np.array(rows)
        gw = rs[rs > 0].sum(); gl = abs(rs[rs <= 0].sum())
        w = int((rs > 0).sum()); l = len(rs) - w
        aw = gw / w if w else 0.0; al = gl / l if l else 0.0
        return {"n": len(rs),
                "pf": round(float(gw / gl) if gl else (10.0 if gw else 0.0), 3),
                "wr": round(w / len(rs) * 100, 1),
                "rr": round(float(aw / al) if al else (10.0 if aw else 0.0), 3),
                "total_r": round(float(rs.sum()), 2)}


# ---------------------------------------------------------------- LLM (optional)

def call_minimax(prompt: str, system: str, max_tokens: int = 2000) -> str:
    key = os.environ.get("MINIMAX_API_KEY", "")
    if not key:
        return ""
    for attempt in range(4):
        try:
            r = requests.post(
                "https://api.minimax.io/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": "MiniMax-M3", "max_tokens": max_tokens,
                      "temperature": 0.4,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": prompt}]},
                timeout=180)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            if r.status_code == 429:
                log("    LLM 429 (token plan limit) — backing off")
                time.sleep(20 * (attempt + 1))
                continue
            return ""
        except Exception:
            time.sleep(5)
    return ""


def strip_think(text: str) -> str:
    if not text:
        return ""
    if "</think>" in text:
        text = text.split("</think>")[-1]
    if "<think>" in text:
        text = text.split("<think>")[0]
    return text.replace("</think>", "").strip()


def parse_params(text: str, all_tickers: list[str]):
    if not text:
        return None
    txt = strip_think(text)
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    cfg = dict(BOOK_DEFAULTS)
    try:
        cfg["t2_r"] = float(d.get("t2_r", 1.618))
        cfg["breakeven_at_r"] = float(d.get("breakeven_at_r", 0.0))
        cfg["partial_at_r"] = float(d.get("partial_at_r", 0.0))
        cfg["min_conf"] = int(d.get("min_conf", 0))
        cfg["max_bars_held"] = int(d.get("max_bars_held", 96))
        gf = str(d.get("grade_filter", "AB")).upper()
        cfg["grade_filter"] = "A" if gf == "A" else "AB"
        cfg["keep_tickers"] = [t for t in (d.get("keep_tickers") or []) if t in all_tickers]
        cfg["drop_tickers"] = [t for t in (d.get("drop_tickers") or []) if t in all_tickers]
        cfg["keep_hours"] = sorted({int(h) for h in (d.get("keep_hours") or []) if 0 <= int(h) <= 23})
    except Exception:
        return None
    snap = lambda v, ch: min(ch, key=lambda c: abs(c - v))
    cfg["t2_r"] = snap(cfg["t2_r"], T2_R_CHOICES)
    cfg["breakeven_at_r"] = snap(cfg["breakeven_at_r"], BREAKEVEN_CHOICES)
    cfg["partial_at_r"] = snap(cfg["partial_at_r"], PARTIAL_CHOICES)
    cfg["min_conf"] = snap(cfg["min_conf"], CONF_CHOICES)
    return cfg


def llm_propose(strategy: str, cfg: dict, metrics: dict, all_tickers: list[str]):
    prompt = f"""你係量化策略參數優化器。為單一策略提出更好的參數組合，目標提升 PF 同 RR。

策略: {strategy}
特性: {AGENT_BLURB.get(strategy, '未知')}

目前參數:
{json.dumps(cfg, ensure_ascii=False)}

目前 TRAIN 實績: n={metrics['n']} PF={metrics['pf']} WR={metrics['wr']}% RR={metrics['rr']} totalR={metrics['total_r']}

可用值:
  t2_r {T2_R_CHOICES} | breakeven_at_r {BREAKEVEN_CHOICES} | partial_at_r {PARTIAL_CHOICES}
  min_conf {CONF_CHOICES} | grade_filter AB/A | drop_tickers/keep_tickers from {all_tickers}
  keep_hours 0-23 (NY)

用 EXACT JSON 格式輸出:
{{"t2_r":<n>,"breakeven_at_r":<n>,"partial_at_r":<n>,"min_conf":<n>,
  "grade_filter":"AB","keep_tickers":[],"drop_tickers":[],"keep_hours":[],"rationale":"<20字>"}}"""
    system = "你係資深量化研究員。只輸出 JSON，唔用 markdown fence。"
    return parse_params(call_minimax(prompt, system), all_tickers)


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", nargs="*", default=None)
    ap.add_argument("--llm", action="store_true",
                    help="also ask the LLM for proposals (needs token plan quota)")
    ap.add_argument("--llm-rounds", type=int, default=12)
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    log("=" * 60)
    log("Parameter optimiser — target PF>1.5 & RR>1.5 (train), holdout held back")
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

    agents = args.agents or sorted(by_agent.keys())
    searches = {}
    for a in agents:
        if a not in by_agent:
            continue
        s = AgentSearch(a, by_agent[a], bars, train_cut)
        s._hbars = bars
        searches[a] = s

    log("running exhaustive + greedy search")
    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {}
        for a, s in searches.items():
            futs[pool.submit(_run_agent, a, s, args)] = a
        for fut in as_completed(futs):
            a = futs[fut]
            try:
                results[a] = fut.result()
            except Exception as e:
                log(f"  {a}: FAILED {type(e).__name__}: {e}")
                results[a] = {"strategy": a, "error": str(e)}

    # ---- report ----
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(HKT).strftime("%Y-%m-%d")
    report = {
        "generated_at": now.isoformat(),
        "target": {"pf": TARGET_PF, "rr": TARGET_RR},
        "window": {"from": str(trades[0].get("entry_time", ""))[:19],
                   "to": str(trades[-1].get("entry_time", ""))[:19],
                   "train_cut": train_cut[:19]},
        "results": results,
    }
    (OUT_DIR / f"btopt_{day}.json").write_text(json.dumps(report, indent=2,
                                                          ensure_ascii=False,
                                                          default=str))

    md = [f"# Parameter Optimiser — {day}", "",
          f"Target: **PF > {TARGET_PF}** and **RR > {TARGET_RR}** on the training "
          f"window. The holdout was never used for selection.", "",
          f"Window {report['window']['from']} → {report['window']['to']}; "
          f"train cut {report['window']['train_cut']}.", "",
          "| Agent | Train n | Train PF | Train RR | Base PF | Holdout n | Holdout PF | Holdout RR | Base HO PF | Verdict |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    reached, overfit, failed = [], [], []
    for a, r in sorted(results.items()):
        if r.get("error"):
            failed.append(a)
            md.append(f"| {a} | — | — | — | — | — | — | — | — | ERROR |")
            continue
        if r.get("no_feasible_config"):
            md.append(f"| {a} | {r['train']['n']} | {r['train']['pf']} | "
                      f"{r['train']['rr']} | {r['train_baseline']['pf']} | — | — | — | — | "
                      f"no config keeps the required sample |")
            continue
        t, tb, h, hb = r["train"], r["train_baseline"], r["holdout"], r["holdout_baseline"]
        # The verdict is decided on the HOLDOUT, against the book's own
        # baseline on the same holdout. A training PF says nothing about
        # whether the parameters generalise; the first run of this optimiser
        # marked seven agents as winners on the training number and every one
        # of them came back below its own baseline on the holdout.
        if h["n"] < MIN_TRADES_FOR_CLAIM:
            verdict = "— insufficient holdout"
        elif h["pf"] >= hb["pf"] + 0.10 and h["pf"] >= TARGET_PF:
            reached.append(a)
            verdict = "✅ improved"
        elif h["pf"] < hb["pf"]:
            overfit.append(a)
            verdict = "⚠️ overfit"
        else:
            verdict = "—"
        md.append(f"| {a} | {t['n']} | {t['pf']} | {t['rr']} | {tb['pf']} | "
                  f"{h['n']} | {h['pf']} | {h['rr']} | {hb['pf']} | {verdict} |")
    md += ["", f"**Improved on the holdout: {len(reached)}/{len(results)}**"
           + (f" — {', '.join(reached)}" if reached else ""),
           "", f"Agents whose TRAINING PF reached {TARGET_PF} but which did not "
           f"improve on the holdout are marked overfit. An agent with a "
           f"holdout n below {MIN_TRADES_FOR_CLAIM} is not judged either way."]
    if overfit:
        md += ["", f"**Likely overfitted (train PF well above the holdout baseline): "
                   f"{', '.join(overfit)}**"]
    if failed:
        md += ["", f"**Failed: {', '.join(failed)}**"]
    md += ["", "## How to read this", "",
           "A training PF far above the holdout PF is overfitting, not improvement: "
           "those parameters were chosen to fit the training trades. The holdout "
           "column is the one that means anything. An agent with a holdout n "
           f"below {MIN_TRADES_FOR_CLAIM} has too little data to judge, and is "
           "not counted as a pass or a fail."]
    (OUT_DIR / f"btopt_{day}.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    # Only a configuration that IMPROVED on the holdout, against the book's
    # own baseline on that same holdout, is published for live use. A
    # configuration that only looks good on the training window is not
    # evidence of anything, and shipping it would be exactly the curve
    # fitting this whole split exists to prevent.
    live = {}
    for a, r in results.items():
        if r.get("error"):
            continue
        h, hb = r["holdout"], r["holdout_baseline"]
        validated = (h["n"] >= MIN_TRADES_FOR_CLAIM
                     and h["pf"] > hb["pf"] + 0.05)
        entry = {"config": r["config"], "train_pf": r["train"]["pf"],
                 "holdout_pf": h["pf"], "holdout_n": h["n"],
                 "holdout_baseline_pf": hb["pf"],
                 "reached_target": r["reached_target"],
                 "validated_on_holdout": validated,
                 "source": "backtest_optimizer",
                 "generated_at": now.isoformat()}
        if validated:
            live[a] = entry
        else:
            live[a] = {**entry, "config": dict(BOOK_DEFAULTS),
                        "note": "not published: no improvement on the holdout"}
    OUT_CONFIG.write_text(json.dumps(live, indent=2, ensure_ascii=False, default=str))
    validated_n = sum(1 for v in live.values() if v.get("validated_on_holdout"))
    log(f"validated on holdout: {validated_n}/{len(live)}")
    log(f"config → {OUT_CONFIG.name}")
    log(f"report → btopt_{day}.md")
    return 0


def _run_agent(a, s, args):
    base_cfg = dict(BOOK_DEFAULTS)
    base_train = s._score(base_cfg, s._mask(base_cfg))
    best = s.search()
    train = best["train"]
    log(f"  {a}: train PF {base_train['pf']} → {train['pf']} "
        f"(n={train['n']}, RR {train['rr']})")

    if args.llm and os.environ.get("MINIMAX_API_KEY"):
        for _ in range(args.llm_rounds):
            if train["pf"] >= TARGET_PF and train["rr"] >= TARGET_RR:
                break
            prop = llm_propose(a, best["config"], train, s.all_tickers)
            if prop is None:
                break
            sc = s._score(prop, s._mask(prop))
            if sc["n"] >= 10 and sc["pf"] > train["pf"] + 1e-9:
                best = {"config": prop, "train": sc}
                train = sc
                log(f"  {a}: LLM proposal improved PF → {train['pf']}")
            else:
                break

    hold = s.holdout_score(best["config"])
    base_hold = s.holdout_score(base_cfg)
    return {
        "strategy": a,
        "config": best["config"],
        "train": train,
        "train_baseline": base_train,
        "holdout": hold,
        "holdout_baseline": base_hold,
        "reached_target": (train["pf"] >= TARGET_PF and train["rr"] >= TARGET_RR),
        "searched": best.get("searched"),
    }


if __name__ == "__main__":
    import requests
    sys.exit(main())
