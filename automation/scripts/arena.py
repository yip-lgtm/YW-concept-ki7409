#!/usr/bin/env python3
"""Arena — the 15 strategy agents trade each other on virtual accounts.

What this is
------------
Every strategy in the book gets an agent with its own account, its own
positions and its own level counter. The agents compete on a daily board:
the target is one level per day, and the only way up is a day that
qualifies on the numbers.

How it differs from the live book
---------------------------------
The live book is careful: one position per strategy, a fixed ticker per
strategy, session gates, an LLM grade on every signal, and a promotion
ladder that needs ten trades over a fortnight. The arena drops all of that
on purpose — it is a competition, and a competition needs volume:

  - every agent may hold several positions at once, across every instrument
  - the live detector functions are reused unchanged, so the arena measures
    the same entries the live system would take
  - there is no LLM in the loop. The detector's own strength is the grade,
    the same approximation the historical backtest labels `detector_proxy`
  - the live ticker bans (Stair on BTC, 3-Pushes on BTC, 50-20 on MGC, CRT
    on GC) are NOT applied. The user asked for all instruments; the arena
    records the outcome per instrument so a ban can be judged on evidence
    instead of inherited

The engine is a rolling simulator. Every run walks the bars that arrived
since the last run, bar by bar: open positions are resolved against each
bar's high and low, and the detectors are evaluated at every bar, so an
agent that fires four times in a day trades four times. The first run
bootstraps from the last BOOTSTRAP_BARS bars so the arena starts with a
book instead of an empty sheet.

What it is not
--------------
It never places a broker order. The Longbridge client in this repo only
reads quotes; there is no order-submission call anywhere in the tree. The
arena moves numbers in its own account files and nothing else. The live
governance ladder (`strategy_levels.json`) is not touched either — the arena
keeps its own level counter, so the production promotion rules stay intact.

Outputs
-------
  automation/reports/arena/leaderboard.json          the board
  automation/reports/arena/arena_YYYY-MM-DD.md       the day's report
  automation/reports/arena/agents/<slug>/account.json   per-agent state
  automation/reports/arena/agents/<slug>/trades.jsonl   per-agent trades
"""
from __future__ import annotations
import os
import sys
import json
import argparse
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

try:
    from zoneinfo import ZoneInfo
    NY_TZ = ZoneInfo("America/New_York")
except Exception:                                          # pragma: no cover
    NY_TZ = timezone(timedelta(hours=-4))


def _find_repo() -> Path:
    """Locate the repo root without hard-coding one machine's path."""
    if "GITHUB_WORKSPACE" in os.environ:
        return Path(os.environ["GITHUB_WORKSPACE"])
    for parent in Path(__file__).resolve().parents:
        if (parent / "automation").is_dir():
            return parent
    return Path("/workspace/YW-concept-ki7409")


REPO = _find_repo()
sys.path.insert(0, str(REPO / "automation" / "scripts"))
sys.path.insert(0, str(REPO / "automation" / "src"))

from contract_specs import usd_per_point, size_position, true_pnl   # noqa: E402

ARENA_DIR = REPO / "automation" / "reports" / "arena"
# Where the per-agent accounts and trade logs live. Overridable so a test
# run cannot pollute the book that the CI commits.
STATE_DIR = ARENA_DIR / "agents"
RULES_PATH = REPO / "automation" / "config" / "arena_rules.json"

# How many bars the first run replays to give the agents a book.
BOOTSTRAP_BARS = 288          # 24 hours of five-minute bars
DETECTOR_WINDOW = 500         # bars of history a detector sees (live_scan's)

ALL = None                    # None means "the whole arena universe"
ARENA_AGENTS = [
    {"name": "H-Pattern",       "family": "live_scan", "instruments": ALL},
    {"name": "3-Pushes",        "family": "live_scan", "instruments": ALL},
    {"name": "Two-Yang",        "family": "live_scan", "instruments": ALL},
    {"name": "RSI-Div",         "family": "live_scan", "instruments": ALL},
    {"name": "50-20-Pullback",  "family": "live_scan", "instruments": ALL},
    {"name": "Stair",           "family": "live_scan", "instruments": ALL},
    {"name": "CRT",             "family": "live_scan", "instruments": ALL},
    {"name": "Kell-Cycle",      "family": "live_scan", "instruments": ALL},
    {"name": "B1",              "family": "live_scan", "instruments": ALL},
    {"name": "Argon-Gold",      "family": "live_scan", "instruments": ["GC=F"]},
    {"name": "OCS-BTC-5m",      "family": "live_scan", "instruments": ["BTC-USD"]},
    {"name": "TTrades-Fractal", "family": "ttrades",   "instruments": ["MNQ=F", "MGC=F", "BTC-USD"]},
    {"name": "TTrades-L12",     "family": "ttrades",   "instruments": ["MNQ=F", "MGC=F", "BTC-USD"]},
    {"name": "TTrades-L13",     "family": "ttrades",   "instruments": ["MNQ=F", "MGC=F", "BTC-USD"]},
    {"name": "TTrades-L14",     "family": "ttrades",   "instruments": ["MNQ=F", "MGC=F", "BTC-USD"]},
]


def log(msg: str):
    print(f"[arena] {datetime.now(timezone.utc).strftime('%H:%M:%S')} {msg}", flush=True)


def slug(name: str) -> str:
    return name.lower().replace("-", "_").replace(" ", "_")


def now_ny() -> datetime:
    return datetime.now(NY_TZ)


def today_ny() -> str:
    return now_ny().strftime("%Y-%m-%d")


# --------------------------------------------------------------------- rules

def load_rules() -> dict:
    if RULES_PATH.exists():
        return json.loads(RULES_PATH.read_text())
    return {
        "risk_budget_usd": 100.0,
        "universe": ["MNQ=F", "MES=F", "M2K=F", "MGC=F", "GC=F", "BTC-USD"],
        "max_positions_per_agent": 5,
        "cooldown_bars": 12,
        "levels": {
            "start": 1, "floor": 0,
            "promote": {"min_trades": 1, "min_PF": 1.0, "min_WR": 0.5,
                        "min_RR": 1.0, "min_pnl_usd": 0.0, "delta": 1},
            "demote": {"min_trades": 3, "max_PF": 0.7, "max_pnl_usd": 0.0, "delta": -1},
        },
    }


# ------------------------------------------------------------------- account

def account_dir(name: str) -> Path:
    return STATE_DIR / slug(name)


def load_account(name: str, rules: dict) -> dict:
    path = account_dir(name) / "account.json"
    if path.exists():
        try:
            acct = json.loads(path.read_text())
            acct.setdefault("cursors", {})
            acct.setdefault("cooldowns", {})
            acct.setdefault("days", {})
            return acct
        except Exception:
            pass
    return {
        "agent": name,
        "level": rules.get("levels", {}).get("start", 1),
        "realised_usd": 0.0,
        "last_day": None,
        "positions": [],
        "cursors": {},
        "cooldowns": {},
        "days": {},
    }


def save_account(name: str, acct: dict):
    d = account_dir(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "account.json").write_text(json.dumps(acct, indent=2, default=str))


def append_trade(name: str, trade: dict):
    d = account_dir(name)
    d.mkdir(parents=True, exist_ok=True)
    with (d / "trades.jsonl").open("a") as f:
        f.write(json.dumps(trade, default=str) + "\n")


def read_trades(name: str) -> list:
    p = account_dir(name) / "trades.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


# --------------------------------------------------------------------- data

class DataHub:
    """Fetches each instrument's frames once and shares them across agents."""

    def __init__(self, rules: dict):
        self.rules = rules
        self._frames: dict[str, dict] = {}
        self._ttrades: dict[str, dict] = {}

    def frames(self, ticker: str) -> dict | None:
        if ticker in self._frames:
            return self._frames[ticker]
        try:
            from data_source import fetch_bars
            df_5m = fetch_bars(ticker, days=15, interval_min=5)
            df_1h = fetch_bars(ticker, days=60, interval_min=60)
            if df_5m is None or df_5m.empty:
                log(f"  data {ticker}: no 5m bars")
                self._frames[ticker] = None
                return None
            for d in (df_5m, df_1h):
                if d is not None and d.index.tz is not None:
                    d.index = d.index.tz_convert("UTC")
            if df_1h is None or df_1h.empty:
                df_1h = df_5m.resample("1h").agg({
                    "Open": "first", "High": "max", "Low": "min",
                    "Close": "last", "Volume": "sum"}).dropna()
            df_4h = df_1h.resample("4h").agg({
                "Open": "first", "High": "max", "Low": "min",
                "Close": "last", "Volume": "sum"}).dropna()
            prev = df_5m["Close"].shift(1)
            tr = pd.concat([df_5m["High"] - df_5m["Low"],
                            (df_5m["High"] - prev).abs(),
                            (df_5m["Low"] - prev).abs()], axis=1).max(axis=1)
            atr = tr.rolling(14, min_periods=5).mean()
            log(f"  data {ticker}: {len(df_5m)} 5m bars "
                f"({df_5m.index[0].date()} → {df_5m.index[-1].date()}), "
                f"{len(df_1h)} 1h, {len(df_4h)} 4h")
            out = {"df_5m": df_5m, "df_1h": df_1h, "df_4h": df_4h,
                   "atr": atr, "last_close": float(df_5m["Close"].iloc[-1])}
            self._frames[ticker] = out
            return out
        except Exception as e:
            log(f"  data {ticker} failed: {type(e).__name__}: {e}")
            self._frames[ticker] = None
            return None

    def ttrades_frames(self, ticker: str) -> dict | None:
        if ticker in self._ttrades:
            return self._ttrades[ticker]
        try:
            import ttrades_btc as base
            h1 = base.fetch_ohlcv(ticker, "1h", "30d")
            m15 = base.fetch_ohlcv(ticker, "15m", "7d")
            if h1 is None or m15 is None or h1.empty or m15.empty:
                log(f"  ttrades data {ticker}: empty")
                self._ttrades[ticker] = None
                return None
            h4 = h1.resample("4h").agg({
                "Open": "first", "High": "max", "Low": "min",
                "Close": "last"}).dropna()
            daily = base.fetch_ohlcv(ticker, "1d", "2y")
            out = {"h1": h1, "m15": m15, "h4": h4, "daily": daily}
            self._ttrades[ticker] = out
            return out
        except Exception as e:
            log(f"  ttrades data {ticker} failed: {type(e).__name__}: {e}")
            self._ttrades[ticker] = None
            return None


# ---------------------------------------------------------------- detection

def _live_detector(name: str, ticker: str, data: dict):
    import live_scan as ls
    cfg = ls.STRATEGIES.get(name)
    if not cfg:
        return None
    det = ls.run_detector(name, cfg, ticker, data)
    if not det.get("present"):
        return None
    direction = ls._normalize_direction(det.get("direction", ""))
    if direction not in ("long", "short"):
        return None
    strength = det.get("strength")
    if strength is None:
        strength = det.get("confidence", 0)
    try:
        strength = float(strength)
    except (TypeError, ValueError):
        strength = 0.0
    return {"direction": direction, "strength": strength,
            "sl_tp_preset": det.get("sl_tp_preset"),
            "reason": str(det.get("reason", ""))[:200]}


def detect_at(spec: dict, ticker: str, fr: dict, hub: "DataHub",
              idx: int, rules: dict) -> dict | None:
    """Evaluate one agent's detector at one bar of one instrument."""
    name = spec["name"]
    ts = fr["df_5m"].index[idx]
    if spec["family"] == "live_scan":
        df5 = fr["df_5m"]
        lo = max(0, idx - DETECTOR_WINDOW + 1)
        win = df5.iloc[lo: idx + 1]
        if len(win) < 60:
            return None
        df1 = fr["df_1h"]
        df4 = fr["df_4h"]
        w1 = df1[df1.index <= ts]
        w4 = df4[df4.index <= ts]
        data = {"df_5m": win, "df_1h": w1, "df_4h": w4,
                "n_5m": len(win), "n_1h": len(w1), "n_4h": len(w4)}
        try:
            det = _live_detector(name, ticker, data)
        except Exception as e:
            log(f"  {name} {ticker} {ts}: detector failed {type(e).__name__}: {e}")
            return None
        if not det:
            return None
        floor = float(rules.get("signal", {}).get("min_strength", 0))
        if det["strength"] < floor:
            return None
        entry = float(fr["df_5m"]["Close"].iloc[idx])
        atr_series = fr["atr"]
        atr = float(atr_series.iloc[idx]) if idx < len(atr_series) else 0.0
        if atr <= 0 or entry <= 0:
            return None
        import live_scan as ls
        exit_cfg, _arm = ls.resolve_exit_config(name, ticker)
        sl_tp = det.get("sl_tp_preset") or ls.calc_sl_tp(entry, atr,
                                                         det["direction"], exit_cfg)
        if not sl_tp:
            return None
        sl_tp = dict(sl_tp)
        sl = float(sl_tp["sl"])
        risk = abs(entry - sl)
        if risk <= 0:
            return None
        return {"strategy": name, "ticker": ticker, "direction": det["direction"],
                "entry": entry, "sl": sl, "t1": sl_tp.get("t1"),
                "t2": sl_tp.get("t2"), "t3": sl_tp.get("t3"),
                "sl_dist": risk, "atr": atr, "strength": det["strength"],
                "reason": det.get("reason", "")}

    # --- the TTrades family works on its own frames
    if ts.minute % 15 != 0:
        return None
    tf = hub.ttrades_frames(ticker)
    if not tf:
        return None
    # Slice the family's own frames to the bar being replayed. Without this
    # the bootstrap replay would let a 4H structure formed later in the day
    # leak into an earlier bar's decision.
    h4 = tf["h4"][tf["h4"].index <= ts]
    m15 = tf["m15"][tf["m15"].index <= ts]
    if len(h4) < 20 or len(m15) < 20:
        return None
    entry = float(fr["df_5m"]["Close"].iloc[idx])
    try:
        if name == "TTrades-Fractal":
            import ttrades_btc as base
            swing = base.detect_c2_closure(h4) or base.detect_c3_closure(h4)
            if swing is None:
                return None
            direction = swing["direction"]
            if not base.check_cisd(m15, direction).get("confirmed"):
                return None
            if not base.check_eq_respect(swing, m15):
                return None
            daily = tf.get("daily")
            if daily is not None and not daily.empty:
                if not base.check_d1_trend(daily, direction).get("aligned"):
                    return None
            atr_vals = (h4["High"].tail(14) - h4["Low"].tail(14))
            atr = float(atr_vals.mean()) if len(atr_vals) else 0.0
            levels = base.calculate_trade_levels(swing, atr)
            if not levels:
                return None
            sl = float(levels["sl"])
            risk = abs(entry - sl)
            if risk <= 0:
                return None
            return {"strategy": name, "ticker": ticker, "direction": direction,
                    "entry": entry, "sl": sl, "t1": levels.get("t1"),
                    "t2": levels.get("t2_close"), "t3": levels.get("t3"),
                    "sl_dist": risk, "atr": atr, "strength": 100.0,
                    "reason": f"Fractal {swing.get('side','')} CISD".strip()}

        import ttrades_l_strategies as tl
        fn = {"TTrades-L12": tl.detect_l12, "TTrades-L13": tl.detect_l13,
              "TTrades-L14": tl.detect_l14}[name]
        r = fn(h4, m15)
        if not r.get("fired"):
            return None
        r = tl._attach_levels(dict(r, strategy=name), h4)
        if not r.get("has_levels"):
            return None
        direction = r.get("direction")
        if direction not in ("long", "short"):
            return None
        sl = float(r["sl"])
        risk = abs(entry - sl)
        if risk <= 0:
            return None
        return {"strategy": name, "ticker": ticker, "direction": direction,
                "entry": entry, "sl": sl, "t1": r.get("t1"), "t2": r.get("t2"),
                "t3": r.get("t3"), "sl_dist": risk, "atr": r.get("atr_h4", 0.0),
                "strength": 100.0, "reason": str(r.get("stage") or "fired")}
    except Exception as e:
        log(f"  {name} {ticker} {ts}: ttrades failed {type(e).__name__}: {e}")
        return None


# ------------------------------------------------------------- position ops

def close_positions_against(acct: dict, agent: str, ticker: str,
                             bar, ts) -> list:
    """Resolve this agent's open positions on this instrument against one bar."""
    closed = []
    hi, lo = float(bar["High"]), float(bar["Low"])
    for pos in list(acct["positions"]):
        if pos["ticker"] != ticker:
            continue
        sign = 1 if pos["direction"] == "long" else -1
        exit_price = None
        exit_level = None
        if sign > 0:
            if lo <= pos["sl"]:
                exit_price, exit_level = pos["sl"], "SL"
            elif pos.get("t2") is not None and hi >= pos["t2"]:
                exit_price, exit_level = pos["t2"], "T2"
        else:
            if hi >= pos["sl"]:
                exit_price, exit_level = pos["sl"], "SL"
            elif pos.get("t2") is not None and lo <= pos["t2"]:
                exit_price, exit_level = pos["t2"], "T2"
        if exit_price is None:
            continue
        risk = pos["sl_dist"]
        r = sign * (exit_price - pos["entry"]) / risk if risk else 0.0
        # Dollars come from the R-multiple and the dollar risk the position
        # carried, never from the raw price move: a short's price move has
        # the opposite sign to its profit, and reading it directly turned
        # this arena's short winners into losers. Same rule as
        # contract_specs.trade_pnl_usd.
        pnl = r * float(pos.get("risk_usd", 0.0))
        trade = {
            "strategy": agent, "ticker": ticker, "direction": pos["direction"],
            "entry": pos["entry"], "exit": exit_price, "exit_level": exit_level,
            "sl": pos["sl"], "t2": pos.get("t2"), "units": pos["units"],
            "usd_per_point": pos["usd_per_point"], "risk_usd": pos["risk_usd"],
            "R_multiple": round(float(r), 4), "pnl_usd": round(float(pnl), 2),
            "opened": pos["opened"], "closed": str(ts),
            "day": ts.tz_convert(NY_TZ).strftime("%Y-%m-%d") if ts.tzinfo else today_ny(),
        }
        acct["positions"].remove(pos)
        acct["realised_usd"] = round(acct.get("realised_usd", 0.0) + pnl, 2)
        closed.append(trade)
        append_trade(agent, trade)
    return closed


def mark_to_market(acct: dict, ticker: str, last_close: float):
    """Mark this agent's open positions on one instrument to the last close."""
    for pos in acct["positions"]:
        if pos["ticker"] != ticker:
            continue
        sign = 1 if pos["direction"] == "long" else -1
        pos["mark"] = last_close
        pos["unrealised_usd"] = sign * true_pnl(
            ticker, last_close - pos["entry"], pos["units"])


def open_position(agent: str, sig: dict, acct: dict, ts, rules: dict):
    units, risk_usd, why = size_position(sig["ticker"], sig["sl_dist"],
                                          rules.get("risk_budget_usd", 100.0))
    if units is None:
        return None
    pos = {
        "id": f"{agent}|{sig['ticker']}|{sig['direction']}|{ts}",
        "strategy": agent, "ticker": sig["ticker"], "direction": sig["direction"],
        "entry": sig["entry"], "sl": sig["sl"], "t1": sig.get("t1"),
        "t2": sig.get("t2"), "t3": sig.get("t3"),
        "sl_dist": sig["sl_dist"], "units": units,
        "usd_per_point": usd_per_point(sig["ticker"]),
        "risk_usd": risk_usd, "atr": sig.get("atr", 0.0),
        "opened": str(ts), "opened_bar": str(ts),
        "reason": sig.get("reason", ""),
    }
    acct["positions"].append(pos)
    return pos


def replay_agent(spec: dict, acct: dict, hub: "DataHub", rules: dict) -> dict:
    """Walk the bars that arrived since the last run for every instrument."""
    agent = spec["name"]
    universe = rules.get("universe", [])
    max_pos = int(rules.get("max_positions_per_agent", 5))
    cooldown = int(rules.get("cooldown_bars", 12))
    cursors = acct.setdefault("cursors", {})
    cooldowns = acct.setdefault("cooldowns", {})
    stats = {"opened": 0, "closed": 0, "bars": 0}

    for ticker in (spec["instruments"] or universe):
        if ticker not in universe:
            continue
        fr = hub.frames(ticker)
        if not fr:
            continue
        df5 = fr["df_5m"]
        last = cursors.get(ticker)
        if last:
            try:
                start = int(df5.index.searchsorted(pd.Timestamp(last)))
            except Exception:
                start = max(0, len(df5) - BOOTSTRAP_BARS)
        else:
            start = max(0, len(df5) - BOOTSTRAP_BARS)
        if start >= len(df5):
            continue
        for idx in range(start, len(df5)):
            ts = df5.index[idx]
            stats["bars"] += 1
            closed = close_positions_against(acct, agent, ticker,
                                              df5.iloc[idx], ts)
            stats["closed"] += len(closed)
            if len(acct["positions"]) >= max_pos:
                continue
            cd_key = f"{ticker}|{spec['family']}"
            cd = cooldowns.get(cd_key)
            if cd is not None and idx - int(cd) < cooldown:
                continue
            try:
                sig = detect_at(spec, ticker, fr, hub, idx, rules)
            except Exception:
                log(f"  {agent} {ticker} {ts}: crash\n{traceback.format_exc()}")
                continue
            if not sig:
                continue
            if any(p["ticker"] == ticker and p["direction"] == sig["direction"]
                   for p in acct["positions"]):
                continue
            pos = open_position(agent, sig, acct, ts, rules)
            if pos:
                stats["opened"] += 1
                cooldowns[cd_key] = idx
        cursors[ticker] = str(df5.index[-1])
        mark_to_market(acct, ticker, float(fr["df_5m"]["Close"].iloc[-1]))
    return stats


# ---------------------------------------------------------------- settlement

def day_metrics(trades: list) -> dict:
    rs = [float(t.get("R_multiple", 0.0)) for t in trades]
    wins = [x for x in rs if x > 0]
    losses = [x for x in rs if x <= 0]
    gw = sum(wins)
    gl = abs(sum(losses))
    # A single winner has no loss to divide by. The profit factor is then
    # genuinely infinite, and it must not be read as zero — a day with one
    # winner and no loser is a good day, not a missing one.
    pf = (gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0)
    wr = (len(wins) / len(rs)) if rs else 0.0
    avg_win = (gw / len(wins)) if wins else 0.0
    avg_loss = (gl / len(losses)) if losses else 0.0
    rr = (avg_win / avg_loss) if avg_loss > 0 else (99.0 if avg_win else 0.0)
    return {
        "n": len(rs), "PF": round(min(pf, 99.0), 3), "WR": round(wr, 4),
        "RR": round(min(rr, 99.0), 3),
        "pnl_usd": round(sum(float(t.get("pnl_usd", 0.0)) for t in trades), 2),
        "wins": len(wins), "losses": len(losses),
    }


def settle(acct: dict, metrics: dict, rules: dict) -> dict:
    """Apply the arena's daily promotion / demotion rules."""
    lv = rules.get("levels", {})
    promote = lv.get("promote", {})
    demote = lv.get("demote", {})
    old = acct.get("level", 1)
    action = "hold"
    reason = "no qualifying evidence"
    pf = metrics["PF"]
    rr = metrics["RR"]
    if metrics["n"] >= int(promote.get("min_trades", 1)) \
            and pf > float(promote.get("min_PF", 1.0)) \
            and metrics["WR"] >= float(promote.get("min_WR", 0.5)) \
            and rr > float(promote.get("min_RR", 1.0)) \
            and metrics["pnl_usd"] > float(promote.get("min_pnl_usd", 0.0)):
        action = "promote"
        acct["level"] = old + int(promote.get("delta", 1))
        reason = (f"PF {pf} > {promote.get('min_PF', 1.0)}, "
                  f"WR {metrics['WR']:.0%}, n={metrics['n']}")
    elif metrics["n"] >= int(demote.get("min_trades", 3)) \
            and pf < float(demote.get("max_PF", 0.7)) \
            and metrics["pnl_usd"] < float(demote.get("max_pnl_usd", 0.0)):
        action = "demote"
        acct["level"] = max(int(lv.get("floor", 0)), old + int(demote.get("delta", -1)))
        reason = (f"PF {pf} < {demote.get('max_PF', 0.7)} over "
                  f"n={metrics['n']}, pnl ${metrics['pnl_usd']}")
    else:
        acct["level"] = max(int(lv.get("floor", 0)), old)
        reason = ("no trades closed today" if metrics["n"] == 0 else
                  f"n={metrics['n']}, PF {pf}, WR {metrics['WR']:.0%} — did not qualify")
    return {"old_level": old, "new_level": acct["level"], "action": action,
            "reason": reason}


def equity(acct: dict) -> float:
    unreal = sum(float(p.get("unrealised_usd", 0.0)) for p in acct["positions"])
    return round(acct.get("realised_usd", 0.0) + unreal, 2)


# --------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ARENA_DIR))
    ap.add_argument("--state-dir", default=str(ARENA_DIR / "agents"))
    args = ap.parse_args()

    global STATE_DIR
    STATE_DIR = Path(args.state_dir)
    rules = load_rules()
    if not rules.get("enabled", True):
        log("arena disabled by rules")
        return 0
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    day = today_ny()
    log(f"=== arena day {day} ===")

    hub = DataHub(rules)
    accounts = {a["name"]: load_account(a["name"], rules) for a in ARENA_AGENTS}

    for a in ARENA_AGENTS:
        name = a["name"]
        acct = accounts[name]
        try:
            stats = replay_agent(a, acct, hub, rules)
        except Exception:
            log(f"  {name} replay crashed:\n{traceback.format_exc()}")
            stats = {"opened": 0, "closed": 0, "bars": 0}
        if stats["opened"] or stats["closed"]:
            log(f"  {name}: +{stats['opened']} opened, {stats['closed']} closed "
                f"over {stats['bars']} bars")
        save_account(name, acct)

    board = []
    for a in ARENA_AGENTS:
        name = a["name"]
        acct = accounts[name]
        trades_today = [t for t in read_trades(name) if t.get("day") == day]
        metrics = day_metrics(trades_today)
        result = settle(acct, metrics, rules)
        acct["days"][day] = {**metrics, **result}
        acct["last_day"] = day
        for d in list(acct["days"])[:-30]:
            acct["days"].pop(d)
        save_account(name, acct)
        board.append({
            "agent": name, "level": acct["level"],
            "level_before": result["old_level"], "action": result["action"],
            "reason": result["reason"], "equity_usd": equity(acct),
            "realised_usd": round(acct.get("realised_usd", 0.0), 2),
            "open_positions": len(acct["positions"]),
            "unrealised_usd": round(sum(float(p.get("unrealised_usd", 0.0))
                                        for p in acct["positions"]), 2),
            "today": metrics,
            "instruments": sorted({p["ticker"] for p in acct["positions"]}),
        })

    # Level is the score. Inside a level, the agent that actually traded
    # today ranks above one that sat out — otherwise an idle agent with zero
    # equity would top the board for doing nothing.
    board.sort(key=lambda r: (-r["level"], -r["today"]["n"], -r["equity_usd"]))
    for i, row in enumerate(board, 1):
        row["rank"] = i

    payload = {"day": day, "generated_at": datetime.now(timezone.utc).isoformat(),
               "rules": rules, "board": board}
    (out_dir / "leaderboard.json").write_text(json.dumps(payload, indent=2, default=str))

    md = [f"# Arena — {day}", "",
          "Fifteen strategy agents, each on its own virtual account. "
          "Paper only: no broker order is ever placed.", "",
          "| # | agent | lv | day action | n | PF | WR | day P&L | equity | open |",
          "|---:|---|--:|---|--:|--:|--:|--:|--:|--:|"]
    for row in board:
        m = row["today"]
        pf = "—" if m["PF"] is None else f"{m['PF']:.2f}"
        md.append(
            f"| {row['rank']} | **{row['agent']}** | {row['level']} | "
            f"{row['action']} | {m['n']} | {pf} | {m['WR']:.0%} | "
            f"${m['pnl_usd']:+,.2f} | ${row['equity_usd']:+,.2f} | "
            f"{row['open_positions']} |")
    md += ["", "## Why each level moved", ""]
    for row in board:
        md.append(f"- **{row['agent']}** — {row['action']}: {row['reason']}")
    (out_dir / f"arena_{day}.md").write_text("\n".join(md) + "\n")

    log(f"wrote {out_dir / 'leaderboard.json'}")
    for row in board:
        log(f"  {row['rank']:>2}. {row['agent']:<18} lv{row['level']:<3} "
            f"{row['action']:<8} ${row['equity_usd']:+,.2f} "
            f"({row['today']['n']} trades today)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
