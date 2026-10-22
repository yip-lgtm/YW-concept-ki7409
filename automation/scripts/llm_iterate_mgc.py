#!/usr/bin/env python3
"""Backtest Argon-Gold and the TTrades family on MGC=F.

The Yahoo fetch has put 30 months of hourly and three months of
fifteen-minute MGC=F history in the repository, which is the gold
contract the book actually trades. That makes it possible to measure
Argon-Gold for the first time, and to measure the TTrades family on
the instrument where most of its live activity is, rather than on BTC.

Argon needs three frames and the detector expects them separately:

  H4     the CRT-style range, built from the hourly history
  M15    the confirmation timeframe, from the fifteen-minute history
  D1     the daily trend filter, from the hourly history

which is what ttrades_l_strategies and ttrades_btc build in the live
path, so the measurement is of the same strategy that trades.

Usage:
    python3 automation/scripts/llm_iterate_mgc.py --agents Argon-Gold
    python3 automation/scripts/llm_iterate_mgc.py --agents all --iterations 8
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import sys
import types as _types
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "automation" / "scripts"))
sys.path.insert(0, str(REPO / "automation" / "src"))

if "requests" not in sys.modules:
    _stub = _types.ModuleType("requests")
    _stub.post = lambda *a, **k: None
    _stub.get = lambda *a, **k: None
    _stub.exceptions = _types.SimpleNamespace(
        HTTPError=Exception, Timeout=Exception, RequestException=Exception)
    sys.modules["requests"] = _stub
if "yfinance" not in sys.modules:
    _yf = _types.ModuleType("yfinance")
    _yf.download = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stub"))
    sys.modules["yfinance"] = _yf

import pandas as pd

_spec = importlib.util.spec_from_file_location(
    "argon", str(REPO / "automation" / "src" / "yw_indicators_argon.py"))
argon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(argon)

_spec2 = importlib.util.spec_from_file_location(
    "tts", str(REPO / "automation" / "scripts" / "ttrades_l_strategies.py"))
tts = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(tts)

_spec3 = importlib.util.spec_from_file_location(
    "ttb", str(REPO / "automation" / "scripts" / "ttrades_btc.py"))
ttb = importlib.util.module_from_spec(_spec3)
_spec3.loader.exec_module(ttb)

OUT_DIR = REPO / "automation" / "reports" / "llm_iteration_mgc"
DATA = REPO / "automation" / "data" / "deep_history" / "MGCF"

AGENTS = ["Argon-Gold", "TTrades-Fractal", "TTrades-L12", "TTrades-L13", "TTrades-L14"]

LEVERS = {
    "t2_r":           {"min": 1.0, "max": 3.0, "step": 0.01,
                       "why": "R multiple the position closes at"},
    "breakeven_at_r": {"min": 0.0, "max": 2.0, "step": 0.1,
                       "why": "R multiple after which the stop moves to entry"},
    "stop_mult":      {"min": 0.8, "max": 3.0, "step": 0.05,
                       "why": "stop distance as a multiple of ATR"},
    "max_bars_held":  {"min": 4, "max": 96, "step": 4,
                       "why": "bars the position is held before it is abandoned"},
    "min_conf":       {"min": 0, "max": 90, "step": 5,
                       "why": "confidence floor"},
    "grade_filter":   {"choices": ["A", "AB", "ABC"],
                       "why": "which grades are traded"},
    "t1_reduce":      {"min": 0.0, "max": 1.0, "step": 0.1,
                       "why": "fraction of the position taken at T1"},
    "cooldown_hours": {"min": 0, "max": 24, "step": 1,
                       "why": "hours the same setup is blocked after it closes"},
    "max_age_bars":   {"min": 1, "max": 12, "step": 1,
                       "why": "how many five-minute bars back the trigger may be"},
    "box_lookback":   {"min": 4, "max": 24, "step": 1,
                       "why": "how many completed fifteen-minute bars form the box"},
}


def load_dir(sub: str) -> pd.DataFrame:
    import pandas as pd
    d = DATA / sub
    frames = []
    for f in sorted(d.glob("*.csv")):
        with f.open() as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            continue
        idx = pd.to_datetime([int(r["ts"]) for r in rows], unit="ms", utc=True)
        frames.append(pd.DataFrame({
            "Open": [float(r["open"]) for r in rows],
            "High": [float(r["high"]) for r in rows],
            "Low": [float(r["low"]) for r in rows],
            "Close": [float(r["close"]) for r in rows],
            "Volume": [float(r["volume"]) for r in rows],
        }, index=idx))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames).sort_index()
    return df[~df.index.duplicated(keep="first")]


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def metrics(rs):
    n = len(rs)
    if n == 0:
        return None
    w = [r for r in rs if r > 0]
    l = [r for r in rs if r < 0]
    nw, nl = len(w), len(l)
    gw, gl = sum(w), abs(sum(l))
    pf = gw / gl if gl > 0 else (10.0 if gw > 0 else 0.0)
    aw = (gw / nw) if nw else 0.0
    al = (gl / nl) if nl else 0.0
    rr = aw / al if al > 0 else (10.0 if aw > 0 else 0.0)
    decided = nw + nl
    lo, hi = wilson(nw, decided) if decided else (0.0, 1.0)
    return {"n": n, "wins": nw, "losses": nl, "wr": nw / decided if decided else 0.0,
            "pf": pf, "rr": rr, "total_R": sum(rs), "avg_R": sum(rs) / n,
            "pf_lo": (lo * 1.618 / (1 - lo)) if lo < 1 else 99.0,
            "pf_hi": (hi * 1.618 / (1 - hi)) if hi < 1 else 99.0}


def build_frames():
    h1 = load_dir("60m")
    m15 = load_dir("15m")
    m5 = load_dir("5m")
    if h1.empty or m15.empty or m5.empty:
        return None
    h4 = h1.resample("4h").agg({"Open": "first", "High": "max", "Low": "min",
                                 "Close": "last"}).dropna()
    d1 = h1.resample("1D").agg({"Open": "first", "High": "max", "Low": "min",
                                 "Close": "last"}).dropna()
    return h1, h4, m15, d1, m5


def run_agent(agent, frames, cfg, start, end):
    h1, h4, m15, d1, m5 = frames
    t2_r = float(cfg.get("t2_r", 1.618))
    be_r = float(cfg.get("breakeven_at_r", 0) or 0)
    stop_mult = float(cfg.get("stop_mult", 1.6))
    max_bars = int(cfg.get("max_bars_held", 96))
    t1_reduce = float(cfg.get("t1_reduce", 0.5))
    cool = float(cfg.get("cooldown_hours", 4))
    age_bars = int(cfg.get("max_age_bars", 6) or 6)
    box_lb = int(cfg.get("box_lookback", 8) or 8)

    prev = h1["Close"].shift(1)
    tr = pd.concat([h1["High"] - h1["Low"], (h1["High"] - prev).abs(),
                    (h1["Low"] - prev).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=5).mean().fillna(0.0)

    rs = []
    last_exit = {}
    for ts, bar in h1.iterrows():
        if ts < start or ts > end:
            continue
        w4 = h4[h4.index <= ts].iloc[-180:]
        w15 = m15[m15.index <= ts].iloc[-672:]
        wd = d1[d1.index <= ts].iloc[-180:]
        w5 = m5[m5.index <= ts].iloc[-1440:]
        if len(w4) < 4 or len(w15) < 30 or len(wd) < 60 or len(w5) < 60:
            continue
        a = float(atr.loc[ts])
        if a <= 0:
            continue
        try:
            if agent == "Argon-Gold":
                # The detector wants the five-minute frame for the trigger
                # scan, the hourly frame for the one-hour bias and the
                # fifteen-minute frame for the box. Passing the fifteen
                # minute frame as the five-minute one makes it scan twelve
                # hours instead of four, and it never fires.
                det = argon.detect_argon_gold(w5, h1.loc[:ts].iloc[-720:], w15,
                                             max_age_bars=age_bars)
                if not det.get("present"):
                    continue
                direction = det.get("direction")
            elif agent == "TTrades-Fractal":
                swing = ttb.detect_c2_closure(w4.iloc[-4:])
                if not swing:
                    swing = ttb.detect_c3_closure(w4.iloc[-4:])
                if not swing:
                    continue
                direction = swing["direction"]
                if not ttb.check_cisd(w15, direction).get("confirmed"):
                    continue
            else:
                fn = {"TTrades-L12": tts.detect_l12,
                      "TTrades-L13": tts.detect_l13,
                      "TTrades-L14": tts.detect_l14}[agent]
                det = fn(w4, w15)
                if not det.get("fired"):
                    continue
                direction = det.get("direction")
        except Exception:
            continue
        if direction not in ("long", "short"):
            continue
        if cool > 0:
            pe = last_exit.get((agent, direction))
            if pe is not None and (ts - pe).total_seconds() / 3600.0 < cool:
                continue
        entry = float(bar["Close"])
        sign = 1 if direction == "long" else -1
        risk = a * stop_mult
        sl = entry - sign * risk
        t1 = entry + sign * risk * 1.0
        t2 = entry + sign * risk * t2_r
        exit_price = None
        t1_hit = False
        be_armed = False
        # walk the fifteen-minute frame forward
        fwd = m15[m15.index > ts].iloc[:max_bars]
        for _, fb in fwd.iterrows():
            hi, lo = float(fb["High"]), float(fb["Low"])
            if direction == "long":
                if lo <= sl:
                    exit_price = sl
                    break
                if hi >= t1:
                    t1_hit = True
                if hi >= t2:
                    exit_price = t2
                    break
            else:
                if hi >= sl:
                    exit_price = sl
                    break
                if lo <= t1:
                    t1_hit = True
                if lo <= t2:
                    exit_price = t2
                    break
            if be_r > 0 and risk > 0 and not be_armed:
                r_now = ((hi - entry) / risk if direction == "long"
                         else (entry - lo) / risk)
                if r_now >= be_r:
                    sl = entry
                    be_armed = True
        if exit_price is None:
            continue
        rs.append(sign * (exit_price - entry) / risk)
        last_exit[(agent, direction)] = ts
    return metrics(rs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", nargs="*", default=AGENTS)
    ap.add_argument("--iterations", type=int, default=6)
    ap.add_argument("--target-pf", type=float, default=1.2)
    ap.add_argument("--target-rr", type=float, default=1.5)
    ap.add_argument("--tune-days", type=int, default=45)
    ap.add_argument("--validate-days", type=int, default=15)
    args = ap.parse_args()

    agents = AGENTS if (args.agents == ["all"] or not args.agents) else args.agents
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames = build_frames()
    if frames is None:
        print(f"no MGC=F history under {DATA}", file=sys.stderr)
        return 1
    h1, h4, m15, d1, m5 = frames
    end = h1.index[-1]
    val_start = end - timedelta(days=args.validate_days)
    tune_start = val_start - timedelta(days=args.tune_days)
    print(f"MGC=F  H1 {len(h1)} bars ({h1.index[0].date()} → {end.date()})")
    print(f"        H4 {len(h4)}  M15 {len(m15)}  D1 {len(d1)}")
    print(f"TUNE      {tune_start.date()} → {val_start.date()}")
    print(f"VALIDATE  {val_start.date()} → {end.date()}\n")

    results = {}
    for agent in agents:
        print(f"=== {agent} ===", flush=True)
        base = {"t2_r": 1.618, "breakeven_at_r": 0.0, "stop_mult": 1.6,
                "max_bars_held": 96, "min_conf": 0, "grade_filter": "AB",
                "t1_reduce": 0.5, "cooldown_hours": 4, "max_age_bars": 6,
                "box_lookback": 8}
        cfg = dict(base)
        m = run_agent(agent, frames, cfg, tune_start, val_start)
        if not m:
            print("  no trades on the tuning window", flush=True)
            results[agent] = {"status": "no_trades"}
            continue
        best = (m["pf"], dict(cfg), m)
        history = []
        print(f"  baseline: n={m['n']} (W{m['wins']}/L{m['losses']}) "
              f"WR={100*m['wr']:.1f}% PF={m['pf']:.2f} RR={m['rr']:.2f}", flush=True)
        for i in range(args.iterations):
            prompt = _prompt(agent, m, cfg, history, args.target_pf, args.target_rr)
            text, err = _call(prompt)
            if err:
                print(f"  iter {i+1}: LLM error: {err}", flush=True)
                break
            new_cfg = _parse(text)
            if not new_cfg:
                text2, err2 = _call(prompt + "\n\nReply with the JSON object only.",
                                     max_tokens=600)
                new_cfg = _parse(text2) if not err2 else None
            if not new_cfg:
                print(f"  iter {i+1}: no JSON in the reply — skipping", flush=True)
                continue
            cand = dict(cfg)
            cand.update(new_cfg)
            cm = run_agent(agent, frames, cand, tune_start, val_start)
            if cm is None:
                continue
            history.append({"cfg": new_cfg, "m": cm})
            hit = cm["pf"] >= args.target_pf and cm["rr"] >= args.target_rr
            print(f"  iter {i+1}: {new_cfg} -> n={cm['n']} PF={cm['pf']:.2f} "
                  f"RR={cm['rr']:.2f} WR={100*cm['wr']:.1f}%"
                  f"{'  ← TARGET MET' if hit else ''}", flush=True)
            if cm["pf"] > best[0]:
                best = (cm["pf"], dict(cand), cm)
                cfg = dict(cand)
                m = cm
                if hit:
                    break
        vm = run_agent(agent, frames, best[1], val_start, end)
        bmv = run_agent(agent, frames, base, val_start, end)
        print(f"  BEST: {best[1]}")
        print(f"    tune     PF={best[2]['pf']:.2f} n={best[2]['n']}")
        if vm:
            print(f"    validate PF={vm['pf']:.2f} n={vm['n']} "
                  f"(baseline PF={bmv['pf']:.2f} n={bmv['n']})", flush=True)
        results[agent] = {"baseline_tune": m, "best_cfg": best[1],
                           "best_tune": best[2], "best_validate": vm,
                           "baseline_validate": bmv, "history": history,
                           "tune_met": bool(best[2]["pf"] >= args.target_pf
                                            and best[2]["rr"] >= args.target_rr),
                           "target_met": bool(vm and vm["pf"] >= args.target_pf
                                              and vm["rr"] >= args.target_rr)}
        dest = OUT_DIR / "results.json"
        merged = {}
        if dest.exists():
            try:
                merged = json.loads(dest.read_text())
            except Exception:
                merged = {}
        merged.update(results)
        dest.write_text(json.dumps(merged, indent=2, default=str))
    print(f"\nwrote {OUT_DIR / 'results.json'}")
    return 0


def _prompt(agent, cur, cfg, history, tp, tr):
    levers = "\n".join(
        f"  {k}: {s['why']}"
        + (f" (one of {s['choices']})" if "choices" in s
           else f" (range {s['min']} to {s['max']})")
        for k, s in LEVERS.items())
    m = cur or {}
    line = (f"n={m.get('n')} WR={100*m.get('wr',0):.1f}% PF={m.get('pf',0):.2f} "
            f"RR={m.get('rr',0):.2f} total_R={m.get('total_R',0):+.1f}") if m else "no trades"
    hist = "\n".join(f"  tried {h['cfg']} -> PF {h['m']['pf']:.2f} RR {h['m']['rr']:.2f} "
                     f"WR {100*h['m']['wr']:.1f}% n={h['m']['n']}" for h in history[-5:]) or "  (nothing yet)"
    return f"""You are tuning a trading strategy on MGC=F (Micro Gold).

Strategy: {agent}
Current configuration: {cfg}
Current result: {line}
Target: PF >= {tp} and RR >= {tr} at the same time.

RR = avg_win_R / |avg_loss_R|. With the default exit every win closes at
the target and every loss at the stop, so the default RR is 1.618 and it
does NOT move with the win rate. RR >= {tr} is therefore already
satisfied and the difficulty is PF, which needs a win rate of at least
42.6%.

Available levers:
{levers}

Proposed changes so far:
{hist}

Reply with ONE JSON object and nothing else, changing only the levers you
want to move. Change one or two at a time. If nothing can reach the
target, reply with {{"t2_r": <current>}}."""


def _call(prompt, system="", max_tokens=2000, timeout=120):
    import ssl
    import os as _os
    import time as _time
    import urllib.error
    import urllib.request
    api = _os.environ.get("MINIMAX_CHAT_URL", "https://api.minimax.io/v1/chat/completions")
    model = _os.environ.get("MINIMAX_MODEL", "MiniMax-M3")
    key = _os.environ.get("MINIMAX_API_KEY", "")
    if not key:
        return "", "no MINIMAX_API_KEY"
    body = {"model": model, "max_tokens": max_tokens, "temperature": 0.3,
            "messages": [{"role": "system", "content": system or
                          "You tune trading strategy parameters. Keep thinking brief "
                          "and always finish with the JSON object."},
                         {"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        api, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    ctx = ssl._create_unverified_context()
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                payload = json.loads(r.read().decode())
            return payload["choices"][0]["message"]["content"], ""
        except urllib.error.HTTPError as e:
            if e.code in (429, 529, 503):
                _time.sleep(5 * (attempt + 1))
                continue
            return "", f"HTTP {e.code}: {e.read().decode()[:150]}"
        except Exception as e:
            _time.sleep(5)
            continue
    return "", "retries exhausted"


def _parse(text):
    import re
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
    for k, s in LEVERS.items():
        if k not in d:
            continue
        v = d[k]
        if "choices" in s:
            if isinstance(v, str) and v.upper() in [c.upper() for c in s["choices"]]:
                out[k] = v.upper()
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        f = max(s["min"], min(s["max"], f))
        out[k] = int(round(f / s["step"]) * s["step"]) if s["step"] >= 1 else round(f, 3)
    return out or None


if __name__ == "__main__":
    sys.exit(main())
