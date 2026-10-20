"""Counterfactual exit replay — the reward oracle for the RL exit policy.

The RL iteration agent needs to answer: "if this strategy had used exit
parameters (a, b) instead of the current ones, what would its total R
have been?"  This module computes that exactly, by replaying the logged
trades forward over the bar series under a candidate exit configuration.

WHY THE EXIT POLICY IS THE RIGHT TARGET

  Every strategy in the book currently shares one exit template: 1.6xATR
  stop, T1 at 1.0R, T2 close at 1.618R, T3 at 2.618R, and no breakeven
  move.  But the strategies have very different win-rate profiles:

    strategy            WR     RR     breakeven WR at 1.618R   avg R
    50-20-Pullback    36.1%   1.59          38.6%            -0.065
    Stair             36.8%   1.59          38.6%            -0.046
    Two-Yang          34.4%   1.60          38.4%            -0.105
    H-Pattern         34.8%   1.60          38.4%            -0.092
    CRT               40.2%   1.59          38.6%            +0.043
    3-Pushes          41.9%   1.58          38.7%            +0.082
    RSI-Div           48.9%   1.59          38.6%            +0.266

  The four losing strategies all sit just below the 38.2% win rate that
  the shared 1.618R target needs to break even.  For them the target is
  structurally too close, not the entry wrong.  A per-agent exit policy
  can fix that, and the counterfactual is exact because the entry price,
  the stop and the bar path are all known.

EXIT CONFIGURATION

  t2_r            the R multiple at which the position closes
                  (T1 reduces half, the remainder rides to T2)
  breakeven_at_r  after the trade reaches this R, the stop moves to the
                  entry price; 0 disables the move
  partial_at_r    the trade closes this fraction at this R multiple;
                  0 disables the partial

  A configuration of (1.618, 0, 0.5) is exactly the book's current
  template, so replaying it must reproduce the recorded R.  That identity
  is asserted by the self-check in rl_iterate.py.
"""
from __future__ import annotations

import pandas as pd

# Current book template, used as the baseline for reward comparison.
BOOK_T2_R = 1.618
BOOK_BREAKEVEN_AT_R = 0.0
BOOK_PARTIAL_AT_R = 0.5
BOOK_PARTIAL_R = 1.0

# Replay fidelity: how many bars after entry to consider. The live tracker
# uses 96 five-minute bars for a position; beyond that the position is
# considered expired, so the replay must use the same horizon or it would
# credit the policy with exits the live system would never have taken.
MAX_BARS = 96

# If the first available bar after an entry is more than this far from the
# entry price, the trade predates the bar feed and cannot be replayed.
MAX_ENTRY_DRIFT = 0.02


def _direction_sign(direction: str) -> int:
    return 1 if str(direction).lower() in ("long", "buy", "up", "bullish") else -1


def replay_trade(trade: dict, df: pd.DataFrame,
                 t2_r: float = BOOK_T2_R,
                 breakeven_at_r: float = BOOK_BREAKEVEN_AT_R,
                 partial_at_r: float = BOOK_PARTIAL_AT_R,
                 partial_r: float = BOOK_PARTIAL_R,
                 max_bars: int = MAX_BARS) -> dict:
    """Replay one trade's exit under a candidate configuration.

    Returns {"r": float, "exit_level": str, "bars": int, "status": str}.
    `r` is the realised R multiple under the candidate. `status` is one of
    "closed" (an exit was reached), "expired" (no exit within max_bars) or
    "no_bars" (no usable bar data after the entry).
    """
    entry = float(trade.get("entry") or 0)
    sl = float(trade.get("sl") or 0)
    t1 = float(trade.get("t1") or 0)
    sign = _direction_sign(trade.get("direction", "long"))

    if entry <= 0 or sl <= 0 or t1 <= 0:
        return {"r": 0.0, "exit_level": "invalid", "bars": 0, "status": "invalid"}

    risk = abs(entry - sl)
    if risk <= 0:
        return {"r": 0.0, "exit_level": "invalid", "bars": 0, "status": "invalid"}

    t1_r = abs(t1 - entry) / risk
    t2_price = entry + sign * risk * t2_r
    if partial_at_r and partial_at_r > 0:
        partial_price = entry + sign * risk * partial_at_r
    else:
        partial_price = None

    # Bars strictly after the entry.
    bars = _bars_after(trade, df)
    if bars is None or len(bars) == 0:
        return {"r": 0.0, "exit_level": "no_bars", "bars": 0, "status": "no_bars"}

    # WINDOW GUARD. The intraday feed only goes back so far, and a trade
    # whose entry predates the feed has no bars near its entry. Replaying
    # it would evaluate the stop and target against prices from weeks
    # later, which is how a losing strategy turned into +884R on the first
    # pass. Such a trade cannot be scored and is excluded rather than
    # guessed at.
    first_bar = bars.iloc[0]
    first_price = float(first_bar["Close"])
    if entry > 0:
        drift = abs(first_price - entry) / entry
        if drift > MAX_ENTRY_DRIFT:
            return {"r": 0.0, "exit_level": "out_of_window", "bars": 0,
                    "status": "out_of_window",
                    "detail": f"first bar {first_price:.2f} is {drift*100:.1f}% away from entry {entry:.2f}"}

    current_sl = sl
    partial_taken = False
    remaining = 1.0

    for i, (_, bar) in enumerate(bars.head(max_bars).iterrows(), start=1):
        hi, lo = float(bar["High"]), float(bar["Low"])
        if sign > 0:
            hit_sl = lo <= current_sl
            hit_partial = (partial_price is not None and not partial_taken
                           and hi >= partial_price)
            hit_t2 = hi >= t2_price
        else:
            hit_sl = hi >= current_sl
            hit_partial = (partial_price is not None and not partial_taken
                           and lo <= partial_price)
            hit_t2 = lo <= t2_price

        # Stop first: the conservative assumption.
        if hit_sl:
            r = (current_sl - entry) / risk
            if partial_taken:
                # Half was already banked at the partial price.
                r = 0.5 * (partial_price - entry) / risk + 0.5 * r
            return {"r": round(r, 4), "exit_level": "SL", "bars": i, "status": "closed"}

        if hit_partial:
            partial_taken = True
            remaining = 0.5
            # After the partial, the stop moves to breakeven if configured.
            if breakeven_at_r and breakeven_at_r > 0:
                current_sl = entry
            continue

        if hit_t2:
            r = (t2_price - entry) / risk
            if partial_taken:
                r = 0.5 * (partial_price - entry) / risk + 0.5 * r
            return {"r": round(r, 4), "exit_level": "T2", "bars": i, "status": "closed"}

        # Breakeven move: the trade has reached the breakeven trigger R.
        if breakeven_at_r and breakeven_at_r > 0 and not partial_taken:
            r_now = ((hi - entry) / risk) if sign > 0 else ((entry - lo) / risk)
            if r_now >= breakeven_at_r:
                current_sl = entry

    # No exit within the horizon. The live tracker expires such positions,
    # so the replay must not invent one: mark it expired and let the caller
    # decide how to account for it.
    return {"r": 0.0, "exit_level": "expired", "bars": len(bars.head(max_bars)),
            "status": "expired"}


def _bars_after(trade: dict, df: pd.DataFrame):
    """Rows of df strictly after the trade's entry time."""
    if df is None or df.empty:
        return None
    et = trade.get("entry_time")
    if not et:
        return None
    try:
        ts = str(et).replace("Z", "+00:00").replace(" ", "T")
        entry_dt = pd.Timestamp(ts)
    except Exception:
        return None

    idx = df.index
    try:
        if getattr(idx, "tz", None) is not None and entry_dt.tzinfo is None:
            entry_dt = entry_dt.tz_localize(idx.tz)
        elif getattr(idx, "tz", None) is None and entry_dt.tzinfo is not None:
            entry_dt = entry_dt.tz_localize(None)
        return df[idx > entry_dt]
    except Exception:
        return None


def replay_agent(trades: list[dict], df: pd.DataFrame,
                 t2_r: float = BOOK_T2_R,
                 breakeven_at_r: float = BOOK_BREAKEVEN_AT_R,
                 partial_at_r: float = BOOK_PARTIAL_AT_R,
                 partial_r: float = BOOK_PARTIAL_R,
                 bars_by_ticker: dict | None = None) -> dict:
    """Replay a whole strategy's trade set under one exit configuration.

    `bars_by_ticker` maps a ticker to its own bar frame.  It is required
    because a strategy trades several instruments and each instrument has
    its own price path — replaying a gold trade against the index bars
    produces a confident, completely wrong answer.  Passing a single `df`
    for every trade is only correct when the strategy trades one ticker.

    Returns aggregate stats plus the per-trade rows, so the caller can see
    which trades changed.
    """
    rows = []
    total_r = 0.0
    n_closed = 0
    n_expired = 0
    n_nobars = 0
    n_outwindow = 0
    for t in trades:
        tdf = df
        if bars_by_ticker is not None:
            tdf = bars_by_ticker.get(t.get("ticker"))
            if tdf is None or tdf.empty:
                rows.append({**{k: t.get(k) for k in
                                ("signal_id", "ticker", "direction", "entry",
                                 "entry_time", "exit_time", "exit_level",
                                 "R_multiple", "pnl_usd")},
                             "replay_r": 0.0, "replay_exit_level": "no_bars",
                             "replay_bars": 0, "replay_status": "no_bars"})
                n_nobars += 1
                continue
        res = replay_trade(t, tdf, t2_r, breakeven_at_r, partial_at_r, partial_r)
        rows.append({**{k: t.get(k) for k in
                        ("signal_id", "ticker", "direction", "entry", "entry_time",
                         "exit_time", "exit_level", "R_multiple", "pnl_usd")},
                     **{f"replay_{k}": v for k, v in res.items()}})
        if res["status"] == "closed":
            total_r += res["r"]
            n_closed += 1
        elif res["status"] == "expired":
            n_expired += 1
        elif res["status"] == "out_of_window":
            n_outwindow += 1
        else:
            n_nobars += 1

    n = len(trades)
    return {
        "n": n,
        "n_closed": n_closed,
        "n_expired": n_expired,
        "n_nobars": n_nobars,
        "n_outwindow": n_outwindow,
        "n_scored": n_closed,
        "total_r": round(total_r, 4),
        "avg_r": round(total_r / n_closed, 5) if n_closed else 0.0,
        "trades": rows,
    }


def prepare_trade(trade: dict, df: pd.DataFrame) -> dict | None:
    """Do the per-trade setup once: slice the bars, resolve the levels.

    The counterfactual evaluation calls the simulator once per candidate
    configuration for the same trade, so the expensive part -- filtering the
    bar index -- has to happen once rather than per configuration. 96
    candidates x 3249 trades turns a one-second job into a one-minute one
    otherwise.

    Returns None when the trade cannot be replayed at all.
    """
    entry = float(trade.get("entry") or 0)
    sl = float(trade.get("sl") or 0)
    t1 = float(trade.get("t1") or 0)
    if entry <= 0 or sl <= 0 or t1 <= 0:
        return None
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    bars = _bars_after(trade, df)
    if bars is None or len(bars) == 0:
        return None
    first_price = float(bars.iloc[0]["Close"])
    if entry > 0:
        drift = abs(first_price - entry) / entry
        if drift > MAX_ENTRY_DRIFT:
            return None
    win = bars.head(MAX_BARS)
    # Pull the window into plain arrays. The counterfactual sweep runs the
    # simulator 96 times per trade, and iterating a pandas frame row by row
    # inside that loop is what made the dataset build take minutes.
    return {
        "entry": entry, "sl": sl, "t1": t1, "risk": risk,
        "sign": _direction_sign(trade.get("direction", "long")),
        "hi": win["High"].to_numpy(dtype=float),
        "lo": win["Low"].to_numpy(dtype=float),
        "n_bars": len(win),
    }


def simulate_prepared(prep: dict, t2_r: float, breakeven_at_r: float,
                      partial_at_r: float, partial_r: float) -> dict:
    """Run the exit simulation over a prepared trade."""
    entry = prep["entry"]
    risk = prep["risk"]
    sign = prep["sign"]
    t2_price = entry + sign * risk * t2_r
    partial_price = (entry + sign * risk * partial_at_r) if partial_at_r else None

    current_sl = prep["sl"]
    partial_taken = False
    his = prep["hi"]
    los = prep["lo"]

    for i in range(prep["n_bars"]):
        hi = his[i]
        lo = los[i]
        if sign > 0:
            hit_sl = lo <= current_sl
            hit_partial = (partial_price is not None and not partial_taken
                           and hi >= partial_price)
            hit_t2 = hi >= t2_price
        else:
            hit_sl = hi >= current_sl
            hit_partial = (partial_price is not None and not partial_taken
                           and lo <= partial_price)
            hit_t2 = lo <= t2_price

        if hit_sl:
            r = (current_sl - entry) / risk
            if partial_taken:
                r = 0.5 * (partial_price - entry) / risk + 0.5 * r
            return {"r": round(r, 4), "exit_level": "SL", "bars": i,
                    "status": "closed"}

        if hit_partial:
            partial_taken = True
            if breakeven_at_r and breakeven_at_r > 0:
                current_sl = entry
            continue

        if hit_t2:
            r = (t2_price - entry) / risk
            if partial_taken:
                r = 0.5 * (partial_price - entry) / risk + 0.5 * r
            return {"r": round(r, 4), "exit_level": "T2", "bars": i,
                    "status": "closed"}

        if breakeven_at_r and breakeven_at_r > 0 and not partial_taken:
            r_now = ((hi - entry) / risk) if sign > 0 else ((entry - lo) / risk)
            if r_now >= breakeven_at_r:
                current_sl = entry

    return {"r": 0.0, "exit_level": "expired", "bars": prep["n_bars"],
            "status": "expired"}
