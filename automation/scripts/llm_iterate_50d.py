#!/usr/bin/env python3
"""LLM iteration against a 50-day backtest, for every strategy.

Target: PF >= 1.2 and RR >= 1.5.

The objective is measured on a 50-day window of the real five-minute
history — the same resolution the live system trades, so the numbers
mean what they say. A separate 30-day window is held back and used only
to check whether a configuration that improved the objective generalises.
Nothing is selected on the validation window.

The mathematical shape of the target, which the prompt states explicitly
because it decides everything:

  RR = avg_win_R / |avg_loss_R|. With the default exit every win closes
  at the target and every loss at the stop, so avg_win_R is the target
  multiple and avg_loss_R is 1: the default RR is 1.618 and it does not
  move with the win rate. RR >= 1.5 is therefore already satisfied and
  the whole difficulty is PF.

  PF = gross_win / |gross_loss| = 1.618 * (n_win / n_loss), so PF >= 1.2
  needs a win rate of at least 42.6%. That is the number to move.

  breakeven_at_r is the lever that raises both: some losses close at 0R
  instead of -1R, so avg_loss_R falls toward zero. t2_r raises both as
  well but buys the win rate with distance to the target.

The levers are the ones the optimiser already owns, plus the detector
thresholds that were parameterised for CRT and Two-Yang:

  t2_r             the R multiple the position closes at
  breakeven_at_r   the R multiple after which the stop moves to entry
  partial_at_r     the R multiple at which part of the position is taken
  stop_mult        the stop distance as a multiple of ATR
  max_bars_held    how long the position is held before it is abandoned
  min_conf         the confidence floor
  grade_filter     which grades are traded

Usage:
    python3 automation/scripts/llm_iterate_50d.py --iterations 8
    python3 automation/scripts/llm_iterate_50d.py --strategies CRT Two-Yang
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "automation" / "scripts"))
sys.path.insert(0, str(REPO / "automation" / "src"))

DEEP = REPO / "automation" / "data" / "deep_history" / "BTCUSD" / "5m"
OUT_DIR = REPO / "automation" / "reports" / "llm_iteration_50d"

API_URL = os.environ.get("MINIMAX_CHAT_URL", "https://api.minimax.io/v1/chat/completions")
MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M3")
API_KEY = os.environ.get("MINIMAX_API_KEY", "")

T2_R = 1.618
STOP_MULT = 1.6
FORWARD_BARS = 96
STEP = 3                 # every 15 minutes: the live cadence

TUNE_DAYS = 50
VALIDATE_DAYS = 30

STRATEGIES = ["Kell-Cycle", "50-20-Pullback", "3-Pushes", "CRT", "Two-Yang",
              "Stair", "RSI-Div", "H-Pattern", "B1"]

# Detector-level levers. The exit levers cannot raise the profit factor
# much, because they do not change which setups fire — they only change
# how the ones that do fire are closed. Raising PF means raising the win
# rate, and the win rate is set by the detector.
DETECTOR_LEVERS = {
    "CRT": {
        "max_raid_depth_pct": {"min": 0.1, "max": 3.0, "step": 0.05,
                                "why": "reject a raid that ran further than this "
                                       "past the level, in percent"},
        "mss_bars":           {"min": 1, "max": 3, "step": 1,
                                "why": "how many bars after the raid may carry "
                                       "the reclaim"},
        "use_last_raid":      {"bool": True,
                                "why": "use the most recent raid in the window "
                                       "instead of the first one"},
    },
    "Two-Yang": {
        "body_ratio":   {"min": 0.05, "max": 0.8, "step": 0.05,
                         "why": "how large the middle candle's body must be"},
        "allow_short":  {"bool": True, "why": "also trade the mirror pattern"},
        "volume_ratio": {"min": 1.0, "max": 3.0, "step": 0.1,
                         "why": "volume multiple one wrapping candle must reach"},
    },
}

LEVERS = {
    "t2_r":            {"min": 1.0,  "max": 3.0,  "step": 0.01,
                        "why": "R multiple the position closes at"},
    "breakeven_at_r":  {"min": 0.0,  "max": 2.0,  "step": 0.1,
                        "why": "R multiple after which the stop moves to entry"},
    "partial_at_r":    {"min": 0.0,  "max": 2.0,  "step": 0.1,
                        "why": "R multiple at which part of the position is taken"},
    "stop_mult":       {"min": 0.8,  "max": 3.0,  "step": 0.05,
                        "why": "stop distance as a multiple of ATR"},
    "max_bars_held":  {"min": 4,    "max": 96,   "step": 4,
                        "why": "bars the position is held before it is abandoned"},
    "min_conf":       {"min": 0,    "max": 90,   "step": 5,
                        "why": "confidence floor"},
    "grade_filter":   {"choices": ["A", "AB", "ABC"],
                        "why": "which grades are traded"},
}


# ---------------------------------------------------------------- data

def load_deep():
    import pandas as pd
    rows = []
    for f in sorted(DEEP.glob("*.csv")):
        with f.open() as fh:
            for r in csv.DictReader(fh):
                if r.get("ts") and r.get("close"):
                    rows.append((int(r["ts"]), float(r["open"]), float(r["high"]),
                                 float(r["low"]), float(r["close"])))
    rows.sort()
    idx = pd.DatetimeIndex([pd.Timestamp(t, unit="ms", tz="UTC") for t, *_ in rows])
    df = pd.DataFrame({"Open": [x[1] for x in rows], "High": [x[2] for x in rows],
                       "Low": [x[3] for x in rows], "Close": [x[4] for x in rows]},
                      index=idx)
    return df[~df.index.duplicated(keep="first")]


# ---------------------------------------------------------------- metrics

def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def metrics_from(rs):
    n = len(rs)
    if n == 0:
        return None
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    # A trade that closed at 0R — a breakeven stop — is neither a win nor
    # a loss. Counting it as a loss makes the breakeven lever look like
    # it destroys the win rate when in fact it is removing losses.
    scratches = [r for r in rs if r == 0]
    nw, nl, ns = len(wins), len(losses), len(scratches)
    gw, gl = sum(wins), abs(sum(losses))
    pf = gw / gl if gl > 0 else (10.0 if gw > 0 else 0.0)
    aw = (gw / nw) if nw else 0.0
    al = (gl / nl) if nl else 0.0
    rr = aw / al if al > 0 else (10.0 if aw > 0 else 0.0)
    decided = nw + nl
    wr = nw / decided if decided else 0.0
    lo, hi = wilson(nw, decided) if decided else (0.0, 1.0)
    return {"n": n, "wins": nw, "losses": nl, "scratches": ns, "wr": wr,
            "pf": pf, "rr": rr, "avg_win_R": aw, "avg_loss_R": al,
            "total_R": sum(rs), "avg_R": sum(rs) / n,
            "pf_lo": (lo * T2_R / (1 - lo)) if lo < 1 else 99.0,
            "pf_hi": (hi * T2_R / (1 - hi)) if hi < 1 else 99.0,
            "wr_lo": lo, "wr_hi": hi}


# ---------------------------------------------------------------- backtest

def run_strategy(df, strategy, cfg, start, end):
    """One strategy over one window, at the live cadence."""
    import pandas as pd
    from yw_indicators import (detect_3_pushes, detect_5020_pullback,
                               detect_h_pattern, detect_rsi_divergence,
                               detect_two_yang_one_yin)
    from yw_indicators_extra import detect_crt, detect_kell_setups, detect_stair_pattern

    # 50-20 returns {cross_type, trend, ...} and Kell-Cycle returns a dict of
    # sub-setups: neither has a top-level "present". The live system runs
    # every detector through live_scan._normalize_detector; a raw call sees
    # no signal and the strategy looks dead. Use the same normaliser so the
    # backtest and the live system agree.
    import importlib.util as _il
    import types as _types
    if "requests" not in sys.modules:
        # live_scan imports requests at module level; the normaliser does
        # not use it. A minimal stub lets this run where requests is not
        # installed. In CI the real one is there and this is skipped.
        _stub = _types.ModuleType("requests")
        _stub.post = lambda *a, **k: None
        _stub.get = lambda *a, **k: None
        _stub.exceptions = _types.SimpleNamespace(
            HTTPError=Exception, Timeout=Exception, RequestException=Exception)
        sys.modules["requests"] = _stub
    _spec = _il.spec_from_file_location(
        "live_scan_mod", str(REPO / "automation" / "scripts" / "live_scan.py"))
    _ls = _il.module_from_spec(_spec)
    _spec.loader.exec_module(_ls)
    _normalize = _ls._normalize_detector
    _FN = {"CRT": "crt", "Two-Yang": "two_yang", "Stair": "stair",
           "50-20-Pullback": "pb_5020", "3-Pushes": "3_pushes",
           "Kell-Cycle": "kell", "H-Pattern": "h_pattern", "RSI-Div": "rsi_div"}

    df_15m = df.resample("15min").agg({"Open": "first", "High": "max", "Low": "min",
                                        "Close": "last"}).dropna()
    df_1h = df.resample("1h").agg({"Open": "first", "High": "max", "Low": "min",
                                   "Close": "last"}).dropna()
    df_4h = df.resample("4h").agg({"Open": "first", "High": "max", "Low": "min",
                                   "Close": "last"}).dropna()
    prev = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - prev).abs(),
                    (df["Low"] - prev).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=5).mean().fillna(0.0).to_numpy()

    t2_r = float(cfg.get("t2_r", T2_R))
    be_r = float(cfg.get("breakeven_at_r", 0) or 0)
    part_r = float(cfg.get("partial_at_r", 0) or 0)
    stop_mult = float(cfg.get("stop_mult", STOP_MULT))
    max_bars = int(cfg.get("max_bars_held", FORWARD_BARS))
    min_conf = int(cfg.get("min_conf", 0) or 0)
    grades = set(cfg.get("grade_filter", "AB") or "AB")
    if "C" in grades:
        grades.add("C")

    rs = []
    for idx in range(200, len(df) - FORWARD_BARS - 2, STEP):
        ts = df.index[idx]
        if ts < start or ts > end:
            continue
        w5 = df.iloc[idx - 1440 + 1: idx + 1]
        w15 = df_15m[df_15m.index <= ts].iloc[-200:]
        w1 = df_1h[df_1h.index <= ts].iloc[-720:]
        w4 = df_4h[df_4h.index <= ts].iloc[-180:]
        if len(w1) < 12 or len(w15) < 10 or len(w4) < 2:
            continue
        try:
            if strategy == "CRT":
                det = detect_crt(w4, w5,
                                 max_raid_depth_pct=cfg.get("max_raid_depth_pct"),
                                 mss_bars=int(cfg.get("mss_bars", 1) or 1),
                                 use_last_raid=bool(cfg.get("use_last_raid", False)))
            elif strategy == "Two-Yang":
                det = detect_two_yang_one_yin(
                    w5,
                    body_ratio=float(cfg.get("body_ratio", 0.3) or 0.3),
                    volume_ratio=float(cfg.get("volume_ratio", 1.2) or 1.2),
                    allow_short=bool(cfg.get("allow_short", False)))
            elif strategy == "Stair":
                det = detect_stair_pattern(w5)
            elif strategy == "50-20-Pullback":
                det = detect_5020_pullback(w5)
            elif strategy == "3-Pushes":
                det = detect_3_pushes(w5)
            elif strategy == "Kell-Cycle":
                det = detect_kell_setups(w5)
            elif strategy == "H-Pattern":
                det = detect_h_pattern(w5)
            elif strategy == "RSI-Div":
                det = detect_rsi_divergence(w15)
            else:
                return None
        except Exception:
            continue
        present, direction_norm, _strength = _normalize(_FN[strategy], det)
        if not present:
            continue
        d = direction_norm
        if d not in ("long", "short", "bullish", "bearish", "up", "down"):
            continue
        direction = "long" if d in ("long", "bullish", "up") else "short"
        strength = int(det.get("strength", 70) or 70)
        if strength < min_conf:
            continue
        a = float(atr[idx])
        if a <= 0:
            continue
        entry = float(df.iloc[idx + 1]["Close"])
        risk = a * stop_mult
        sl = entry - sign(direction) * risk
        t2 = entry + sign(direction) * risk * t2_r
        exit_price, exit_R = None, None
        t1_hit = False
        be_armed = False
        for _, bar in df.iloc[idx + 2: idx + 2 + max_bars].iterrows():
            hi, lo = float(bar["High"]), float(bar["Low"])
            # The stop is checked as it stands at the start of the bar.
            # The breakeven is armed at the END of a bar, so it protects the
            # rest of the trade rather than firing on the very bar that
            # reached the threshold — otherwise one bar that spikes to
            # 0.5R and comes straight back closes the whole position at
            # 0R, and the win rate collapses.
            if direction == "long":
                if lo <= sl:
                    exit_price, exit_R = sl, (-1.0 if not be_armed else 0.0)
                    break
                if part_r > 0 and not t1_hit and hi >= entry + risk * part_r:
                    t1_hit = True
                if hi >= t2:
                    exit_price = t2
                    exit_R = t2_r
                    break
            else:
                if hi >= sl:
                    exit_price, exit_R = sl, (-1.0 if not be_armed else 0.0)
                    break
                if part_r > 0 and not t1_hit and lo <= entry - risk * part_r:
                    t1_hit = True
                if lo <= t2:
                    exit_price = t2
                    exit_R = t2_r
                    break
            if be_r > 0 and risk > 0 and not be_armed:
                r_now = ((hi - entry) / risk if direction == "long"
                         else (entry - lo) / risk)
                if r_now >= be_r:
                    sl = entry
                    be_armed = True
        if exit_price is None:
            continue
        rs.append(sign(direction) * (exit_price - entry) / risk)
    return metrics_from(rs)


def sign(direction):
    return 1 if direction == "long" else -1


# ---------------------------------------------------------------- LLM

def call_llm(prompt, system="", max_tokens=2000, timeout=120):
    if not API_KEY:
        return "", "no MINIMAX_API_KEY"
    if not system:
        system = ("You tune trading strategy parameters. Keep any thinking "
                  "brief and always finish with the JSON object.")
    body = {"model": MODEL, "max_tokens": max_tokens, "temperature": 0.3,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        API_URL, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"})
    try:
        import ssl
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            payload = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:200]
        if e.code in (429, 529, 503):
            # The endpoint is rate limited or overloaded. Back off and
            # try again rather than losing the iteration.
            for attempt in range(3):
                time.sleep(5 * (attempt + 1))
                try:
                    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                        payload = json.loads(r.read().decode())
                    return payload["choices"][0]["message"]["content"], ""
                except Exception:
                    continue
        return "", f"HTTP {e.code}: {detail}"
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"
    try:
        return payload["choices"][0]["message"]["content"], ""
    except Exception as e:
        return "", f"unparseable reply: {e}"


_current_strategy = ""


def parse_config(text):
    """Pull a JSON object out of the reply. Fails loudly."""
    if not text:
        return None
    if "</think>" in text:
        text = text.split("</think>")[-1]
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    out = {}
    det_levers = DETECTOR_LEVERS.get(_current_strategy, {})
    all_levers = dict(LEVERS)
    for k, spec in det_levers.items():
        all_levers[k] = dict(spec)
        all_levers[k].setdefault("min", 0)
        all_levers[k].setdefault("max", 1)
        all_levers[k].setdefault("step", 0.05)
    for k, spec in all_levers.items():
        if k not in d:
            continue
        v = d[k]
        if "choices" in spec:
            if isinstance(v, str) and v.upper() in [c.upper() for c in spec["choices"]]:
                out[k] = v.upper()
            continue
        if spec.get("bool"):
            if isinstance(v, bool):
                out[k] = v
            elif isinstance(v, str) and v.strip().lower() in ("true", "yes", "1"):
                out[k] = True
            elif isinstance(v, str) and v.strip().lower() in ("false", "no", "0"):
                out[k] = False
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        f = max(spec["min"], min(spec["max"], f))
        if spec["step"] >= 1:
            out[k] = int(round(f / spec["step"]) * spec["step"])
        else:
            out[k] = round(f, 3)
    return out or None


def build_prompt(strategy, cur, cfg, history, target_pf, target_rr):
    lever_lines = "\n".join(
        f"  {k}: {spec['why']}"
        + (f" (one of {spec['choices']})" if "choices" in spec
           else f" (range {spec['min']} to {spec['max']})")
        for k, spec in LEVERS.items())
    det_levers = DETECTOR_LEVERS.get(strategy)
    if det_levers:
        lever_lines += "\n\n  Detection levers (these change WHICH setups fire, "
        lever_lines += "which is what moves the win rate):\n"
        lever_lines += "\n".join(
            f"  {k}: {spec['why']}"
            + (" (true or false)" if spec.get("bool")
               else f" (range {spec['min']} to {spec['max']})")
            for k, spec in det_levers.items())
    m = cur or {}
    cur_line = (f"n={m.get('n')} WR={100*m.get('wr',0):.1f}% PF={m.get('pf',0):.2f} "
                f"RR={m.get('rr',0):.2f} total_R={m.get('total_R',0):+.1f}") if m else "no trades"
    hist = "\n".join(f"  tried {h['cfg']} -> PF {h['m']['pf']:.2f} RR {h['m']['rr']:.2f} "
                     f"WR {100*h['m']['wr']:.1f}% n={h['m']['n']}" for h in history[-6:]) or "  (nothing yet)"
    return f"""You are tuning a trading strategy's EXIT and position parameters.

Strategy: {strategy}
Current configuration: {cfg}
Current 50-day backtest result: {cur_line}
Target: PF >= {target_pf} and RR >= {target_rr} simultaneously.

Here is the arithmetic, because it decides what is worth trying.

  RR = avg_win_R / |avg_loss_R|
  With the default exit every win closes at the target and every loss at
  the stop, so avg_win_R is the target multiple and avg_loss_R is 1. The
  default RR is therefore 1.618 and it does NOT move with the win rate.
  RR >= 1.5 is already satisfied; the whole difficulty is PF.

  PF = gross_win / |gross_loss| = 1.618 * (n_win / n_loss)
  So PF >= 1.2 needs a win rate of at least 42.6%. That is the number to
  move.

Two levers move it, and they pull in opposite directions:
  - t2_r higher: more R per win, so RR and PF rise, but the target is
    further away and the win rate falls.
  - breakeven_at_r above zero: losses that had gone far enough into
    profit close at 0R instead of -1R, so avg_loss_R falls and RR rises.
    BUT the threshold has to be high enough: at 0.5R it was measured
    converting 192 would-be winners into 322 scratches, so PF FELL from
    0.90 to 0.82. Try 1.0R or higher, and check the win count in the
    result before keeping it.
  - stop_mult wider: the stop is reached less often, but when it is it
    costs more, so it hurts both.

Available levers:
{lever_lines}

Proposed changes so far:
{hist}

Reply with ONE JSON object and nothing else, changing only the levers you want
to move. Example:
{{"t2_r": 1.35, "breakeven_at_r": 0.5, "stop_mult": 1.4}}

Change one or two levers at a time so the effect can be attributed. If you
believe no change can reach the target, reply with {{"t2_r": <current>}}."""


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategies", nargs="*", default=STRATEGIES)
    ap.add_argument("--iterations", type=int, default=8)
    ap.add_argument("--target-pf", type=float, default=1.2)
    ap.add_argument("--target-rr", type=float, default=1.5)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_deep()
    end_all = df.index[-1]
    val_start = end_all - timedelta(days=VALIDATE_DAYS)
    tune_start = val_start - timedelta(days=TUNE_DAYS)
    print(f"deep 5m {len(df)} bars, {df.index[0].date()} → {end_all.date()}")
    print(f"TUNE      {tune_start.date()} → {val_start.date()}  ({TUNE_DAYS}d)")
    print(f"VALIDATE  {val_start.date()} → {end_all.date()}  ({VALIDATE_DAYS}d)")
    print(f"target PF>={args.target_pf} RR>={args.target_rr}\n")

    results = {}
    for strategy in args.strategies:
        global _current_strategy
        _current_strategy = strategy
        print(f"=== {strategy} ===", flush=True)
        base_cfg = {"t2_r": T2_R, "breakeven_at_r": 0.0, "partial_at_r": 0.0,
                    "stop_mult": STOP_MULT, "max_bars_held": FORWARD_BARS,
                    "min_conf": 0, "grade_filter": "AB"}
        cfg = dict(base_cfg)
        m = run_strategy(df, strategy, cfg, tune_start, val_start)
        if m is None:
            print("  no trades on the tuning window", flush=True)
            results[strategy] = {"status": "no_trades", "baseline": None}
            continue
        best = (m["pf"], dict(cfg), m)
        history = []
        print(f"  baseline: n={m['n']} (W{m['wins']}/L{m['losses']}) "
              f"WR={100*m['wr']:.1f}% PF={m['pf']:.2f} "
              f"RR={m['rr']:.2f} total_R={m['total_R']:+.1f}", flush=True)
        for it in range(args.iterations):
            prompt = build_prompt(strategy, m, cfg, history, args.target_pf, args.target_rr)
            text, err = call_llm(prompt)
            if err:
                print(f"  iter {it+1}: LLM error: {err}", flush=True)
                break
            new_cfg = parse_config(text)
            if not new_cfg:
                # The model's thinking can eat the whole token budget, so
                # the JSON never arrives. Ask again, with a budget that
                # only has room for the answer.
                text2, err2 = call_llm(
                    prompt + "\n\nReply with the JSON object only. "
                            "Do not explain anything.",
                    max_tokens=600)
                new_cfg = parse_config(text2) if not err2 else None
                if not new_cfg:
                    print(f"  iter {it+1}: reply could not be parsed "
                          f"({err2 or 'no JSON in the reply'}) — skipping",
                          flush=True)
                    history.append({"cfg": cfg, "m": m})
                    continue
            cand = dict(cfg)
            cand.update(new_cfg)
            cm = run_strategy(df, strategy, cand, tune_start, val_start)
            if cm is None:
                print(f"  iter {it+1}: no trades with {new_cfg}", flush=True)
                continue
            history.append({"cfg": new_cfg, "m": cm})
            hit = cm["pf"] >= args.target_pf and cm["rr"] >= args.target_rr
            print(f"  iter {it+1}: {new_cfg} -> n={cm['n']} "
                  f"(W{cm['wins']}/L{cm['losses']}/BE{cm.get('scratches',0)}) "
                  f"PF={cm['pf']:.2f} RR={cm['rr']:.2f} WR={100*cm['wr']:.1f}%"
                  f"{'  ← TARGET MET' if hit else ''}", flush=True)
            if cm["pf"] > best[0]:
                best = (cm["pf"], dict(cand), cm)
                cfg = dict(cand)
                m = cm
                if hit:
                    print("  both targets met — stopping this strategy", flush=True)
                    break
        # validate the best configuration on the held-back window
        vm = run_strategy(df, strategy, best[1], val_start, end_all)
        bmv = run_strategy(df, strategy, base_cfg, val_start, end_all)
        print(f"  BEST on tune: {best[1]}")
        print(f"    tune     PF={best[2]['pf']:.2f} RR={best[2]['rr']:.2f} n={best[2]['n']}")
        if vm:
            print(f"    validate PF={vm['pf']:.2f} RR={vm['rr']:.2f} n={vm['n']} "
                  f"(baseline PF={bmv['pf']:.2f} RR={bmv['rr']:.2f})", flush=True)
        results[strategy] = {
            "baseline_tune": m if m else None,
            "best_cfg": best[1], "best_tune": best[2], "best_validate": vm,
            "baseline_validate": bmv, "history": history,
            "target_met": bool(vm and vm["pf"] >= args.target_pf and vm["rr"] >= args.target_rr),
            "tune_met": bool(best[2]["pf"] >= args.target_pf and best[2]["rr"] >= args.target_rr),
        }
        (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2, default=str))

    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2, default=str))
    print(f"\nwrote {OUT_DIR / 'results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
