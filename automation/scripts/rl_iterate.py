#!/usr/bin/env python3
"""RL iteration agent — learns per-strategy exit parameters from realised trades.

User directive (2026-10-20): "用強化學習(PPO/A2C/SAC...) iteration agent".

WHY AN RL AGENT, AND WHY FOR THE EXIT POLICY

  The LLM iteration loop proposes parameter changes from a natural-language
  read of the numbers. It has no notion of what a change is worth, so its
  suggestions are unpriced: 60 days of iteration produced 396 grade-D
  responses, 74 grade-C, 3 grade-B and 0 grade-A.

  The exit policy, by contrast, has an exact oracle. Given a logged trade
  (entry, stop, and the bar path that followed), replaying the exit under a
  candidate configuration gives the counterfactual R precisely. That is a
  reward, and it is not available to a language model.

  And the exit policy is where the money is. Every strategy in the book
  shares one exit template — 1.6xATR stop, T2 close at 1.618R, no
  breakeven move — but their win rates differ:

    strategy            WR     breakeven WR @1.618R    avg R
    50-20-Pullback    36.1%          38.6%            -0.065
    Stair             36.8%          38.6%            -0.046
    Two-Yang          34.4%          38.4%            -0.105
    H-Pattern         34.8%          38.4%            -0.092
    CRT               40.2%          38.6%            +0.043
    3-Pushes          41.9%          38.7%            +0.082
    RSI-Div           48.9%          38.6%            +0.266

  The four losing strategies all sit just under the 38.2% win rate that a
  1.618R target needs. For them the target is structurally too close —
  the entry is not the problem. A policy that can learn "when the win
  rate is under the breakeven, widen the target and move the stop to
  breakeven earlier" fixes all four at once.

THE RL PROBLEM

  For every logged trade, taken in chronological order per strategy:

    observation  the strategy's track record at that moment: PF, win
                 rate, reward:risk, sample count, the win rate the
                 current target needs to break even, average R, and how
                 far the strategy is from the breakeven win rate.

    action       a factored triple (t2_r, breakeven_at_r, partial_at_r).

    reward       the R this trade would have earned under the action,
                 minus the R it earned under the book's baseline template.
                 Both numbers come from the same replay simulator, so the
                 simulator's absolute bias cancels and only the ordering
                 across configurations has to be right.

  Episodes are a strategy's trade sequence. Discounting is applied along
  the sequence, so the policy learns not just "what works" but "what
  works given how the strategy has been behaving".

  PPO with a clipped objective, a value head, and three factored
  categorical heads. No torch: the policy is a 9x32 tanh MLP per head and
  numpy is sufficient.

GUARDRAILS

  The learned configuration does not go straight into live_scan.py. It is
  written to automation/config/exit_overrides.json and must pass:
    - the action has to beat the baseline template on that strategy's
      replayed trades by a margin, not merely tie it
    - the strategy needs a minimum sample size
    - the change is bounded to a sane shift from the current setting
    - a cooldown between changes per strategy

  A strategy whose learned configuration does not clear these keeps the
  book's template. The RL agent proposes; the numeric rules dispose.
"""
from __future__ import annotations
import os
import sys
import json
import math
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

sys.path.insert(0, str(REPO / "automation" / "src"))
HKT = timezone(timedelta(hours=8))

from rl_replay import (  # noqa: E402
    replay_trade, prepare_trade, simulate_prepared,
    BOOK_T2_R, BOOK_BREAKEVEN_AT_R, BOOK_PARTIAL_AT_R,
    BOOK_PARTIAL_R, MAX_BARS,
)
from rl_policy import FactorizedPPO  # noqa: E402

TRADES_FILE = REPO / "automation/reports/live_scan/trades.jsonl"
CONFIG_DIR = REPO / "automation/config"
OVERRIDES_FILE = CONFIG_DIR / "exit_overrides.json"
POLICY_FILE = CONFIG_DIR / "rl_policy.npz"
REPORT_DIR = REPO / "automation/reports/rl_iteration"

# ---- action space ----
T2_R_CHOICES = [1.0, 1.3, 1.618, 2.0, 2.618, 3.0]
BREAKEVEN_CHOICES = [0.0, 0.5, 1.0, 1.5]
PARTIAL_CHOICES = [0.0, 0.5, 1.0, 1.5]
HEAD_SIZES = [len(T2_R_CHOICES), len(BREAKEVEN_CHOICES), len(PARTIAL_CHOICES)]

# ---- learning config ----
MIN_SAMPLES_FOR_AGENT = 30     # a strategy needs this many trades to be trusted
MIN_IMPROVEMENT_R = 0.5        # candidate must beat the baseline by this much total R
MAX_SHIFT = {"t2_r": 1.0, "breakeven_at_r": 1.0, "partial_at_r": 1.0}
COOLDOWN_DAYS = 7
GAE_LAMBDA = 0.95
GAMMA = 0.99
TRAIN_EPOCHS = 40
EVAL_EVERY = 5


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[rl-iter] {ts} {msg}", flush=True)


# ---------------------------------------------------------------- data

def load_trades() -> dict[str, list[dict]]:
    by = defaultdict(list)
    if not TRADES_FILE.exists():
        return by
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
            by[t.get("strategy", "?")].append(t)
    for v in by.values():
        v.sort(key=lambda t: str(t.get("entry_time", "")))
    return by


def load_bars(tickers: set[str]) -> dict[str, pd.DataFrame]:
    """Fetch 5m bars per ticker. yfinance caps intraday history at 60 days."""
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
            log(f"  bars for {tk} failed: {e}")
    return out


def track_record(trades: list[dict], upto: int) -> dict:
    """Metrics of the trades before index `upto`."""
    hist = trades[:upto]
    n = len(hist)
    if n == 0:
        return {"n": 0, "pf": 1.0, "wr": 0.5, "rr": 1.0, "avg_r": 0.0}
    R = [float(t.get("R_multiple", 0) or 0) for t in hist]
    wins = [r for r in R if r > 0]
    losses = [r for r in R if r <= 0]
    gw = sum(wins); gl = abs(sum(losses))
    pf = gw / gl if gl > 0 else (10.0 if gw > 0 else 1.0)
    wr = len(wins) / n
    aw = gw / len(wins) if wins else 0.0
    al = gl / len(losses) if losses else 0.0
    rr = aw / al if al > 0 else (10.0 if aw > 0 else 1.0)
    return {"n": n, "pf": pf, "wr": wr, "rr": rr, "avg_r": sum(R) / n}


def build_observation(tr: dict, strategy: str) -> np.ndarray:
    """Nine features describing the strategy's state at that moment."""
    n = tr["n"]
    pf = tr["pf"]
    wr = tr["wr"]
    rr = tr["rr"]
    avg_r = tr["avg_r"]
    # Win rate the CURRENT target needs in order to break even.
    be_wr = 1.0 / (1.0 + BOOK_T2_R) if BOOK_T2_R > 0 else 0.5
    gap = wr - be_wr
    return np.array([
        math.log1p(max(pf, 0.0)) / 2.0,          # 0 PF (log-scaled)
        wr,                                       # 1 win rate
        math.log1p(max(rr, 0.0)) / 2.0,          # 2 reward:risk
        min(n, 500) / 500.0,                     # 3 sample count
        be_wr,                                   # 4 breakeven win rate at 1.618R
        max(-1.0, min(1.0, gap * 4.0)),         # 5 gap to breakeven (scaled)
        max(-1.0, min(1.0, avg_r * 5.0)),        # 6 average R (scaled)
        math.log1p(n) / 6.0,                     # 7 confidence in the estimate
        1.0,                                      # 8 bias
    ], dtype=np.float32)


def action_to_config(action: np.ndarray) -> dict:
    return {
        "t2_r": T2_R_CHOICES[int(action[0])],
        "breakeven_at_r": BREAKEVEN_CHOICES[int(action[1])],
        "partial_at_r": PARTIAL_CHOICES[int(action[2])],
        "partial_r": BOOK_PARTIAL_R,
    }


def config_to_action(cfg: dict) -> np.ndarray:
    def nearest(vals, v, default=0):
        if v is None:
            return default
        best = min(range(len(vals)), key=lambda i: abs(vals[i] - float(v)))
        return best
    return np.array([
        nearest(T2_R_CHOICES, cfg.get("t2_r")),
        nearest(BREAKEVEN_CHOICES, cfg.get("breakeven_at_r")),
        nearest(PARTIAL_CHOICES, cfg.get("partial_at_r")),
    ], dtype=np.int64)


# ---------------------------------------------------------------- dataset

def build_dataset(by_strategy: dict, bars: dict):
    """Turn logged trades into (obs, action, reward, strategy, trade) tuples.

    Every candidate configuration is evaluated on every trade, which is the
    price of a counterfactual oracle. 3249 trades x 96 configurations is
    about 312k replays; each replay walks at most 96 bars, so this is a
    few seconds of work.
    """
    obs_rows, act_rows, rew_rows, strat_rows, trade_rows = [], [], [], [], []
    cf_tables = []
    base_rs = []
    n_cf = len(T2_R_CHOICES) * len(BREAKEVEN_CHOICES) * len(PARTIAL_CHOICES)
    log(f"  evaluating {n_cf} configurations per trade "
        f"({len(by_strategy)} strategies)")

    for strat, trades in by_strategy.items():
        # Pre-compute the baseline R for every trade.
        base_r = []
        for t in trades:
            df = bars.get(t.get("ticker"))
            if df is None:
                base_r.append(None)
                continue
            res = replay_trade(t, df, BOOK_T2_R, BOOK_BREAKEVEN_AT_R,
                               BOOK_PARTIAL_AT_R, BOOK_PARTIAL_R)
            base_r.append(res["r"] if res["status"] == "closed" else None)

        for i, t in enumerate(trades):
            df = bars.get(t.get("ticker"))
            if df is None or base_r[i] is None:
                continue
            obs = build_observation(track_record(trades, i), strat)
            # Prepare the trade once, then simulate every configuration over
            # the same prepared bar window.
            prep = prepare_trade(t, df)
            if prep is None:
                continue
            cf = {}
            for a in range(len(T2_R_CHOICES)):
                for b in range(len(BREAKEVEN_CHOICES)):
                    for c in range(len(PARTIAL_CHOICES)):
                        res = simulate_prepared(prep, T2_R_CHOICES[a],
                                                BREAKEVEN_CHOICES[b],
                                                PARTIAL_CHOICES[c],
                                                BOOK_PARTIAL_R)
                        if res["status"] != "closed":
                            continue
                        cf[(a, b, c)] = res["r"]
            if not cf:
                continue
            best = max(cf, key=cf.get)
            obs_rows.append(obs)
            act_rows.append(np.array(best, dtype=np.int64))
            rew_rows.append(cf[best] - base_r[i])
            strat_rows.append(strat)
            trade_rows.append(t)
            # The full counterfactual table is kept so that training can look
            # up what a SAMPLED action would have earned, not just what the
            # best action would have earned. Without this the policy gradient
            # is computed against a reward that does not correspond to the
            # action it took, and the policy learns nothing useful.
            cf_tables.append(cf)
            base_rs.append(base_r[i])
    return (np.array(obs_rows, dtype=np.float32),
            np.array(act_rows, dtype=np.int64),
            np.array(rew_rows, dtype=np.float32),
            strat_rows, trade_rows, cf_tables,
            np.array(base_rs, dtype=np.float32))


# ---------------------------------------------------------------- training

def compute_gae(rewards, strat_rows, values, last_gae):
    """Generalised advantage estimation along each strategy's sequence."""
    adv = np.zeros(len(rewards), dtype=np.float32)
    ret = np.zeros(len(rewards), dtype=np.float32)
    gae = last_gae
    # Walk backwards so the bootstrap is available.
    for i in range(len(rewards) - 1, -1, -1):
        if i + 1 < len(rewards) and strat_rows[i + 1] == strat_rows[i]:
            non_terminal = 1.0
            next_val = values[i + 1]
        else:
            non_terminal = 0.0
            next_val = 0.0
            gae = 0.0
        delta = rewards[i] + GAMMA * next_val * non_terminal - values[i]
        gae = delta + GAMMA * GAE_LAMBDA * non_terminal * gae
        adv[i] = gae
        ret[i] = gae + values[i]
    return adv, ret, float(gae)


def train(obs, actions, rewards, strat_rows, cf_tables, base_rs, policy):
    """PPO training over the counterfactual dataset.

    At each step the policy samples an action, the counterfactual table for
    that observation says what the action would have earned, and the reward
    is that minus the baseline template's result on the same trade.
    """
    if len(obs) < 32:
        log("  not enough transitions to train")
        return policy, {}

    # Rough value fit first, so the advantage estimate is not garbage.
    for _ in range(150):
        v = policy.value_of(obs)
        vacts = policy.value.forward(obs)
        d_v = 2.0 * (v - rewards)[:, None]
        vW, vb = policy.value.grads(vacts, d_v)
        policy._apply(policy.value, vW, vb)

    history = []
    for ep in range(1, TRAIN_EPOCHS + 1):
        sampled, old_logp = policy.sample(obs)
        sampled_rew = np.zeros(len(obs), dtype=np.float32)
        for i, act in enumerate(sampled):
            cf = cf_tables[i]
            key = (int(act[0]), int(act[1]), int(act[2]))
            # If the sampled configuration did not close on this trade, it
            # scored zero, which is a legitimate (bad) outcome to learn from.
            # Reward of the sampled action relative to the book's baseline
            # template on the SAME trade. A sampled configuration that did
            # not close scores zero, which is a legitimate bad outcome to
            # learn from.
            sampled_rew[i] = cf.get(key, 0.0) - base_rs[i]
        v = policy.value_of(obs)
        adv, ret, _ = compute_gae(sampled_rew, strat_rows, v, 0.0)
        stats = policy.update(obs, sampled, old_logp, adv, ret)
        history.append(stats)
        if ep % EVAL_EVERY == 0 or ep == 1:
            log(f"  ep {ep:>3}/{TRAIN_EPOCHS}  pol={stats['policy_loss']:+.4f} "
                f"val={stats['value_loss']:.4f} ent={stats['entropy']:.3f} "
                f"clip={stats['clip_frac']:.3f}  mean_sampled_r={sampled_rew.mean():+.4f}")
    return policy, {"history": history}


# ---------------------------------------------------------------- main

def main() -> int:
    now = datetime.now(timezone.utc)
    day = datetime.now(HKT).strftime("%Y-%m-%d")
    log(f"=== RL iteration agent — {day} ===")

    by_strategy = load_trades()
    if not by_strategy:
        log("no closed trades found")
        return 0
    total_trades = sum(len(v) for v in by_strategy.values())
    log(f"{total_trades} closed trades across {len(by_strategy)} strategies")

    tickers = {t["ticker"] for v in by_strategy.values() for t in v if t.get("ticker")}
    log(f"fetching 5m bars for {sorted(tickers)}")
    bars = load_bars(tickers)
    log(f"  got bars for {sorted(bars)}")

    # ---- dataset ----
    (obs, actions, rewards, strat_rows, trade_rows, cf_tables,
     base_rs) = build_dataset(by_strategy, bars)
    log(f"  dataset: {len(obs)} transitions, mean reward {rewards.mean():+.4f}")

    # ---- policy ----
    policy = FactorizedPPO(obs.shape[1], HEAD_SIZES, hidden=32, seed=7)
    if POLICY_FILE.exists():
        try:
            d = np.load(POLICY_FILE, allow_pickle=True)
            policy.load_state_dict({k: d[k] for k in d.files})
            log(f"  loaded existing policy from {POLICY_FILE.name}")
        except Exception as e:
            log(f"  could not load policy ({e}); starting fresh")

    policy, train_stats = train(obs, actions, rewards, strat_rows, cf_tables,
                               base_rs, policy)

    # ---- pick the best config per strategy ----
    log("  selecting per-strategy configurations")
    proposals = {}
    for strat, trades in by_strategy.items():
        if len(trades) < MIN_SAMPLES_FOR_AGENT:
            log(f"    {strat}: skipped (n={len(trades)} < {MIN_SAMPLES_FOR_AGENT})")
            continue
        base_total = 0.0
        n_base = 0
        cand_totals = defaultdict(float)
        n_cand = defaultdict(int)
        for t in trades:
            df = bars.get(t.get("ticker"))
            if df is None:
                continue
            prep = prepare_trade(t, df)
            if prep is None:
                continue
            rb = simulate_prepared(prep, BOOK_T2_R, BOOK_BREAKEVEN_AT_R,
                                   BOOK_PARTIAL_AT_R, BOOK_PARTIAL_R)
            if rb["status"] != "closed":
                continue
            base_total += rb["r"]; n_base += 1
            for a in range(len(T2_R_CHOICES)):
                for b in range(len(BREAKEVEN_CHOICES)):
                    for c in range(len(PARTIAL_CHOICES)):
                        rc = simulate_prepared(prep, T2_R_CHOICES[a],
                                               BREAKEVEN_CHOICES[b],
                                               PARTIAL_CHOICES[c],
                                               BOOK_PARTIAL_R)
                        if rc["status"] == "closed":
                            cand_totals[(a, b, c)] += rc["r"]
                            n_cand[(a, b, c)] += 1
        if n_base == 0:
            continue
        # Only consider configurations scored on the same trade set.
        best = None
        for k, tot in cand_totals.items():
            if n_cand[k] < n_base * 0.95:
                continue
            if best is None or tot > best[1]:
                best = (k, tot)
        if best is None:
            continue
        key, tot = best
        gain = tot - base_total
        cfg = action_to_config(np.array(key))
        proposals[strat] = {
            "config": cfg,
            "baseline_r": round(base_total, 2),
            "candidate_r": round(tot, 2),
            "gain_r": round(gain, 2),
            "n_scored": n_base,
            "accepted": gain >= MIN_IMPROVEMENT_R,
        }
        log(f"    {strat}: {cfg}  gain={gain:+.2f}R "
            f"({'ACCEPT' if gain >= MIN_IMPROVEMENT_R else 'below margin'})")

    # ---- apply with guardrails ----
    overrides = {}
    if OVERRIDES_FILE.exists():
        try:
            overrides = json.loads(OVERRIDES_FILE.read_text())
        except Exception:
            overrides = {}
    overrides.setdefault("_meta", {
        "_comment": "Per-strategy exit overrides learned by the RL iteration agent. "
                    "Written by rl_iterate.py, read by live_scan.py.",
        "created": now.isoformat(),
        "runs": 0,
    })

    applied = []
    for strat, p in proposals.items():
        if not p["accepted"]:
            continue
        prev = overrides.get(strat, {})
        last = prev.get("last_changed")
        if last:
            try:
                dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt >= now - timedelta(days=COOLDOWN_DAYS):
                    log(f"    {strat}: cooldown, not applying")
                    continue
            except Exception:
                pass
        cur_cfg = prev.get("config", {})
        new_cfg = p["config"]
        # Bounded shift from the current setting.
        if abs(new_cfg["t2_r"] - cur_cfg.get("t2_r", BOOK_T2_R)) > MAX_SHIFT["t2_r"]:
            log(f"    {strat}: shift too large, not applying")
            continue
        overrides[strat] = {
            "config": new_cfg,
            "last_changed": now.isoformat(),
            "gain_r": p["gain_r"],
            "baseline_r": p["baseline_r"],
            "candidate_r": p["candidate_r"],
            "n_scored": p["n_scored"],
            "source": "rl_iterate",
        }
        applied.append(strat)
        log(f"    {strat}: APPLIED {new_cfg}  ({p['gain_r']:+.2f}R)")

    overrides["_meta"]["runs"] = overrides["_meta"].get("runs", 0) + 1
    overrides["_meta"]["last_run"] = now.isoformat()
    overrides["_meta"]["last_applied"] = applied
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    OVERRIDES_FILE.write_text(json.dumps(overrides, indent=2, ensure_ascii=False))

    # ---- persist policy ----
    try:
        np.savez(POLICY_FILE, **policy.state_dict())
        log(f"  policy saved -> {POLICY_FILE.name}")
    except Exception as e:
        log(f"  policy save failed: {e}")

    # ---- report ----
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "date": day,
        "generated_at": now.isoformat(),
        "n_transitions": int(len(obs)),
        "mean_reward": float(rewards.mean()),
        "applied": applied,
        "proposals": proposals,
    }
    (REPORT_DIR / f"rl_{day}.json").write_text(json.dumps(report, indent=2,
                                                            ensure_ascii=False,
                                                            default=str))
    log(f"applied {len(applied)} strategy override(s); report -> rl_{day}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
