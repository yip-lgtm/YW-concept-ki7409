#!/usr/bin/env python3
"""9 Strategy Live Scanner — runs all 9 detectors every 5 min, 24/7.

Pipeline:
  1. Fetch latest bars (5m + 1h) for each ticker in parallel
  2. Run 9 detectors in parallel (no LLM, pure technical)
  3. If any detector signals → invoke LLM grader for confirmation
  4. If LLM grades A or B → fire signal:
     - Send TG alert
     - Publish to AI-Trader
     - Log to signals.jsonl
  5. Save state for supervisor monitor

Detectors (9):
  1. H-Pattern        (5m)
  2. 3-Pushes         (5m/15m)
  3. Two-Yang-One-Yin (15m)
  4. RSI-Divergence   (5m)
  5. 50-20-Pullback   (5m)
  6. Stair-Pattern    (5m)
  7. CRT              (5m + 4h)
  8. Kell-Cycle       (5m, 5 sub-detectors)
  9. OCS-BTC-5m       (5m, KNN)

Tickers (4):
  - MNQ=F (Micro Nasdaq) — primary
  - MES=F (Micro S&P)    — secondary
  - M2K=F (Micro Russell) — secondary
  - BTC-USD             — crypto

Cost optimization:
  - 9 detectors × 4 tickers × 288 runs/day = 10,368 detector calls/day (no LLM, ~5s)
  - LLM only on detector signal: ~10-30 calls/day
  - Total LLM cost: ~$0.05-0.10/day
"""
from __future__ import annotations
import os
import sys
import json
import time
import traceback
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

sys.path.insert(0, str(REPO / "automation" / "src"))

# YW detectors
from yw_indicators import (
    detect_rsi_divergence, detect_5020_pullback,
    detect_h_pattern, detect_3_pushes, detect_two_yang_one_yin,
)
from yw_indicators_extra import (
    detect_stair_pattern, detect_kell_setups, detect_crt,
)

# OCS BTC 5m
from ocs_btc_5m import compute_signal as ocs_compute_signal, K as OCS_K

# Data source
from data_source import fetch_bars

# Config
LIVE_DIR = REPO / "automation" / "reports" / "live_scan"
LIVE_DIR.mkdir(parents=True, exist_ok=True)
SIGNALS_FILE = LIVE_DIR / "signals.jsonl"
HEARTBEAT_FILE = LIVE_DIR / "heartbeat.json"
POSITIONS_FILE = LIVE_DIR / "positions.json"
TRADES_FILE = LIVE_DIR / "trades.jsonl"
STATS_FILE = LIVE_DIR / "stats.json"
DAILY_DIR = LIVE_DIR / "daily"
DAILY_DIR.mkdir(parents=True, exist_ok=True)

TICKERS = [
    ("MNQ=F", "Micro Nasdaq"),
    ("MES=F", "Micro S&P"),
    ("M2K=F", "Micro Russell"),
    ("MGC=F", "Micro Gold"),
    ("BTC-USD", "BTC USD"),
]

# Market hours filter (skip non-24/7 tickers when market is closed)
# Futures market: Sun-Fri 6pm-5pm ET (closed Sat)
# Crypto: 24/7
def is_market_open(symbol: str) -> bool:
    """Check if market is open for this symbol (in HKT).

    Futures market hours (CME Globex):
    - Opens: Sunday 6pm ET (EDT) = Monday 6am HKT
    - Closes: Friday 5pm ET = Saturday 5am HKT

    Schedule in HKT (UTC+8):
    - Saturday (all day): CLOSED
    - Sunday (all day): CLOSED
    - Monday 0-5:59am: CLOSED
    - Monday 6am - Friday 23:59: OPEN
    """
    # Crypto: 24/7
    if symbol in ("BTC-USD", "BTC=F", "ETH-USD"):
        return True
    # For futures: weekend + Mon early morning closed
    now_hkt = datetime.now(timezone(timedelta(hours=8)))
    weekday = now_hkt.weekday()  # 0=Mon, 5=Sat, 6=Sun
    hour = now_hkt.hour
    if weekday == 5:  # Saturday all day
        return False
    if weekday == 6:  # Sunday all day
        return False
    if weekday == 0 and hour < 6:  # Monday before 6am
        return False
    return True

def get_active_tickers() -> list:
    """Get tickers to scan based on market hours."""
    active = []
    for sym, name in TICKERS:
        if is_market_open(sym):
            active.append((sym, name))
        else:
            print(f"[live_scan] {sym}: market closed, skipping")
    return active

# B1 战法: 右侧交易，专攻 3 个标的 (MNQ, MGC, BTC)
B1_TICKERS = {"MNQ=F", "MGC=F", "BTC-USD"}

# Strategy name → (detector_fn, required_args, weight, timeframe)
STRATEGIES = {
    "H-Pattern":     {"fn": "h_pattern",     "args": {}, "weight": 1.2, "tf": "5m"},
    "3-Pushes":      {"fn": "3_pushes",      "args": {}, "weight": 1.0, "tf": "5m"},
    "Two-Yang":      {"fn": "two_yang",      "args": {}, "weight": 0.8, "tf": "15m"},
    "RSI-Div":       {"fn": "rsi_div",       "args": {"resample_15m": True}, "weight": 0.7, "tf": "15m", "llm_optimized": True},  # LLM-iter 2026-08-25: weight 1.1→0.7, 15min, +EMA+vol
    "50-20-Pullback":{"fn": "pb_5020",       "args": {}, "weight": 1.0, "tf": "5m"},
    "Stair":         {"fn": "stair",         "args": {}, "weight": 0.9, "tf": "5m"},
    "B1":            {"fn": "b1",            "args": {}, "weight": 1.0, "tf": "5m/15min/1h", "llm_optimized": True},
    "B1-3in1":       {"fn": "b1_3in1",       "args": {}, "weight": 1.0, "tf": "5m", "llm_optimized": True, "multi_asset": True},
    "Kell-Cycle":    {"fn": "kell",          "args": {}, "weight": 0.9, "tf": "5m"},
    "CRT":           {"fn": "crt",           "args": {"needs_4h": True}, "weight": 1.1, "tf": "5m+4h"},
    "OCS-BTC-5m":    {"fn": "ocs",           "args": {"needs_btc": True}, "weight": 1.0, "tf": "5m"},
}

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID")
AI_TOKEN = os.environ.get("AI_TRADER_TOKEN")
MINIMAX_KEY = os.environ.get("MINIMAX_API_KEY")
MINIMAX_URL = "https://api.minimax.io/v1/chat/completions"
MINIMAX_MODEL = "MiniMax-M3"

# Min LLM confidence to fire signal (lowered from 55 → 40 to capture more actionables)
LLM_MIN_CONF = 40
LLM_MIN_CONF_BTC = 30  # Lower threshold for BTC (more volatile, fewer A/B signals)
# Min detector strength to invoke LLM
DETECTOR_MIN_PRESENT = True
# Acceptable grades (A=strong, B=actionable, C=marginal but still fire with low conf)
ACCEPTABLE_GRADES = ("A", "B", "C")
# BTC-USD: all 10 strategies must scan it 24/7
BTC_FORCE_MODE = True
# BTC-only detectors (don't restrict other tickers)
BTC_PRIORITY_STRATEGIES = ["50-20-pullback", "crt", "kell-cycle", "two-yang", "h-pattern", "rsi-div"]
# Boost LLM confidence for BTC by +10 (volatility bonus)
BTC_CONFIDENCE_BOOST = 10
# Lower detector strength threshold for BTC (more signals through)
BTC_DETECTOR_MIN_STRENGTH = 40  # vs default 60
# Force fire BTC signals even at C grade
BTC_FORCE_FIRE = True


def fetch_ticker_data(ticker: str) -> dict:
    """Fetch 5m + 1h bars for a ticker. Returns dict with both DataFrames."""
    out = {"ticker": ticker, "ts": datetime.now(timezone.utc).isoformat()}
    try:
        # 5m bars (last 5 days, enough for all 5m detectors)
        df_5m = fetch_bars(ticker, days=5, interval_min=5)
        if df_5m is None or df_5m.empty:
            out["err_5m"] = "empty dataframe"
        else:
            out["df_5m"] = df_5m
            out["n_5m"] = len(df_5m)
    except Exception as e:
        out["err_5m"] = f"{type(e).__name__}: {str(e)[:100]}"
    # 4h bars for CRT (now includes BTC in BTC_FORCE_MODE)
    if BTC_FORCE_MODE or ticker != "BTC-USD":
        try:
            df_1h = fetch_bars(ticker, days=30, interval_min=60)
            if df_1h is not None and not df_1h.empty:
                df_4h = df_1h.resample("4h").agg({
                    "Open": "first", "High": "max", "Low": "min",
                    "Close": "last", "Volume": "sum"
                }).dropna()
                out["df_4h"] = df_4h
                out["n_4h"] = len(df_4h)
                out["df_1h"] = df_1h  # 1h bars for B1 (BBI/KDJ work better on 1h)
                out["n_1h"] = len(df_1h)
        except Exception as e:
            out["err_4h"] = str(e)[:100]
    return out




def compute_atr(df, period=14):
    """Compute ATR from OHLCV DataFrame."""
    if df.empty or len(df) < period:
        return 0.0
    h = df["High"]
    l = df["Low"]
    c = df["Close"]
    tr = pd.concat([
        h - l,
        (h - c.shift()).abs(),
        (l - c.shift()).abs()
    ], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def calc_sl_tp(entry, atr, direction):
    """Calculate SL/TP using 1.6x ATR stop + R-multiple targets.
    
    R multiples: T1=1R, T2=1.618R, T3=2.618R, T4=3.618R, T5=5R (Fib)
    """
    if atr <= 0 or entry <= 0:
        return None
    sl_dist = atr * 1.6
    if direction in ("long", "buy", "up", "bullish", "LONG"):
        sl = entry - sl_dist
        t1 = entry + sl_dist * 1.0
        t2 = entry + sl_dist * 1.618
        t3 = entry + sl_dist * 2.618
        t4 = entry + sl_dist * 3.618
        t5 = entry + sl_dist * 5.0
    elif direction in ("short", "sell", "down", "bearish", "SHORT", "DOWN"):
        sl = entry + sl_dist
        t1 = entry - sl_dist * 1.0
        t2 = entry - sl_dist * 1.618
        t3 = entry - sl_dist * 2.618
        t4 = entry - sl_dist * 3.618
        t5 = entry - sl_dist * 5.0
    else:
        # Unknown direction — default to long but warn
        print(f"[live-scan] WARN: unknown direction '{direction}', defaulting to long")
        sl = entry - sl_dist
        t1 = entry + sl_dist * 1.0
        t2 = entry + sl_dist * 1.618
        t3 = entry + sl_dist * 2.618
        t4 = entry + sl_dist * 3.618
        t5 = entry + sl_dist * 5.0
    return {"sl": sl, "t1": t1, "t2": t2, "t3": t3, "t4": t4, "t5": t5, "sl_dist": sl_dist}


def open_live_position(sig, atr):
    """Open a position from a fired live_scan signal. Returns the position dict."""
    entry = float(sig.get("last_close", 0))
    direction = sig.get("direction", "long")
    sl_tp = calc_sl_tp(entry, atr, direction)
    if not sl_tp:
        return None
    pos = {
        "signal_id": f"{sig['strategy']}|{sig['ticker']}|{sig['ts']}",
        "strategy": sig["strategy"],
        "ticker": sig["ticker"],
        "direction": direction,
        "grade": sig.get("grade", "?"),
        "entry": entry,
        "entry_time": sig["ts"],
        "atr": atr,
        "confidence": sig.get("confidence", 0),
        "reason": sig.get("reason", "")[:200],
        "sl": sl_tp["sl"],
        "t1": sl_tp["t1"],
        "t2": sl_tp["t2"],
        "t3": sl_tp["t3"],
        "t4": sl_tp["t4"],
        "t5": sl_tp["t5"],
        "sl_dist": sl_tp["sl_dist"],
        "status": "open",
    }
    # Load existing + dedupe
    if POSITIONS_FILE.exists():
        positions = json.loads(POSITIONS_FILE.read_text())
    else:
        positions = []
    # DEDUPE: skip if signal_id already in positions or trades
    if any(p.get("signal_id") == pos["signal_id"] for p in positions):
        return None
    if TRADES_FILE.exists():
        existing_trades = [json.loads(line) for line in TRADES_FILE.read_text().splitlines() if line.strip()]
        if any(t.get("signal_id") == pos["signal_id"] for t in existing_trades):
            return None
    positions.append(pos)
    POSITIONS_FILE.write_text(json.dumps(positions, indent=2, default=str))
    return pos


def _normalize_detector(fn_name: str, res: dict) -> tuple:
    """Normalize detector output to (present, direction, strength).

    Different detectors use different output formats. This wrapper unifies them
    to a consistent {present, direction, strength} interface so live_scan and
    the strategy supervisor can reason about them uniformly.

    Returns:
      (present: bool, direction: str, strength: int)
    """
    if not res:
        return False, "none", 0
    # Already in standard format (or has present with optional direction/long_candle)
    if "present" in res:
        # H-Pattern uses "long_candle" = "bullish"/"bearish" as direction
        direction = res.get("direction")
        if not direction or direction == "none":
            direction = res.get("long_candle", "none")
            if direction in ("bullish", "bearish"):
                direction = "long" if direction == "bullish" else "short"
        return (
            bool(res["present"]),
            direction or "none",
            int(res.get("strength", 70 if res["present"] else 0)),
        )
    # 50-20-pullback: {cross_type, pullback, trend, ...}
    if fn_name == "pb_5020":
        pullback_ok = res.get("pullback") == "at_ema20"
        trend = res.get("trend", "sideways")
        if pullback_ok and trend in ("up", "down"):
            return True, ("long" if trend == "up" else "short"), 65
        return False, "none", 0
    # Kell-Cycle: {reversal_extension, wedge_pop_drop, ema_crossback, base_n_break, exhaustion}
    if fn_name == "kell":
        for k, v in res.items():
            if isinstance(v, dict) and v.get("present"):
                return True, v.get("direction", "none"), 70
        return False, "none", 0
    # RSI-Div: {type, strength, ...}
    if fn_name == "rsi_div":
        sig_type = res.get("type", "none")
        if sig_type in ("bullish", "bearish"):
            return True, sig_type, int(res.get("strength", 60))
        return False, "none", 0
    # B1: {present, direction, strength, bbi, k, d, j, ...}
    if fn_name == "b1":
        if res.get("present"):
            return True, res.get("direction", "long"), int(res.get("strength", 70))
        return False, "none", 0
    # B1-3in1: {present, count, best, all_signals}
    if fn_name == "b1_3in1":
        if res.get("present") and res.get("best"):
            best = res["best"]
            return True, best.get("direction", "long"), int(best.get("strength", 70))
        return False, "none", 0
    # Unknown custom format — don't fire
    return False, "none", 0


def run_detector(name: str, cfg: dict, ticker: str, data: dict) -> dict:
    """Run one detector on one ticker. Returns detection result."""
    out = {
        "strategy": name,
        "ticker": ticker,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        if cfg["fn"] == "ocs":
            # OCS only for BTC
            if ticker != "BTC-USD":
                out["present"] = False
                out["skip"] = "BTC only"
                return out
            from ocs_btc_5m import compute_features, label_future, rolling_knn
            df = data.get("df_5m")
            if df is None or len(df) < 200:
                out["present"] = False
                out["skip"] = "insufficient data"
                return out
            feats = compute_features(df)
            labels = label_future(df["Close"], horizon=6)
            knn = rolling_knn(feats, labels, k=OCS_K, train_window=160)
            sig = ocs_compute_signal(knn.iloc[-1], feats, df["Close"], df["ATR"])
            out.update(sig)
            out["present"] = sig.get("signal") in ("buy", "sell")
            return out
        # YW detectors
        df = data.get("df_5m")
        if df is None or len(df) < 20:
            out["present"] = False
            out["skip"] = "insufficient data"
            return out
        if cfg["fn"] == "h_pattern":
            res = detect_h_pattern(df, ticker=ticker)
            out["last_close"] = float(df["Close"].iloc[-1]) if not df.empty else 0
        elif cfg["fn"] == "3_pushes":
            res = detect_3_pushes(df, ticker=ticker)
            out["last_close"] = float(df["Close"].iloc[-1]) if not df.empty else 0
        elif cfg["fn"] == "two_yang":
            res = detect_two_yang_one_yin(df, ticker=ticker)
            out["last_close"] = float(df["Close"].iloc[-1]) if not df.empty else 0
        elif cfg["fn"] == "rsi_div":
            # LLM-iter 2026-08-25: resample 5m → 15m
            if cfg.get("args", {}).get("resample_15m") and df is not None and len(df) >= 30:
                df_rsi = df.resample("15min").agg({
                    "Open": "first", "High": "max", "Low": "min",
                    "Close": "last", "Volume": "sum"
                }).dropna()
                res = detect_rsi_divergence(df_rsi)
            else:
                res = detect_rsi_divergence(df, ticker=ticker)
            out["last_close"] = float(df["Close"].iloc[-1]) if not df.empty else 0
        elif cfg["fn"] == "pb_5020":
            res = detect_5020_pullback(df, ticker=ticker)
            out["last_close"] = float(df["Close"].iloc[-1]) if not df.empty else 0
        elif cfg["fn"] == "stair":
            res = detect_stair_pattern(df, ticker=ticker)
            out["last_close"] = float(df["Close"].iloc[-1]) if not df.empty else 0
        elif cfg["fn"] == "kell":
            res = detect_kell_setups(df, ticker=ticker)
            out["last_close"] = float(df["Close"].iloc[-1]) if not df.empty else 0
        elif cfg["fn"] == "b1":
            # B1 战法只跑 MNQ, MGC, BTC (右侧交易专攻 3 个标的)
            if ticker not in B1_TICKERS:
                out["present"] = False
                out["skip"] = f"B1 only runs on {B1_TICKERS}"
                return out
            from yw_indicators_b1 import detect_b1
            # B1 works best on 1h bars (BBI/KDJ less noise). Use 1h if available, else 5m.
            # j_threshold=20: relaxed from 5 (5 too strict for 24/7 BTC, 30d walk-fwd: j<5:6, j<15:9, j<30:25)
            df_b1 = data.get("df_1h") if data.get("df_1h") is not None and len(data.get("df_1h", [])) >= 30 else df
            res = detect_b1(df_b1, j_threshold=20)
            out["last_close"] = float(df_b1["Close"].iloc[-1]) if not df_b1.empty else 0
            if data.get("df_1h") is not None:
                out["tf_used"] = "1h"
        elif cfg["fn"] == "b1_3in1":
            # B1 3合1: scans MNQ + MGC + BTC, picks strongest
            from yw_indicators_b1_3in1 import detect_b1_3in1
            # j_threshold=20 (same as B1), 30d for walk-fwd
            res = detect_b1_3in1(j_threshold=20, days=30)
            out["last_close"] = float(df["Close"].iloc[-1]) if not df.empty else 0
            out["multi_asset"] = True
            out["b1_3in1_count"] = res.get("count", 0)
            out["b1_3in1_best"] = res.get("best", {}).get("ticker") if res.get("best") else None
        elif cfg["fn"] == "crt":
            df_4h = data.get("df_4h")
            if df_4h is None or len(df_4h) < 5:
                out["present"] = False
                out["skip"] = "no 4h data"
                return out
            res = detect_crt(df_4h, df)
            out["last_close"] = float(df["Close"].iloc[-1]) if not df.empty else 0
        else:
            res = {"present": False, "skip": "unknown"}
        out.update(res)
        # Normalize custom detector outputs to {present, direction, strength} interface
        out["present"], out["direction"], out["strength"] = _normalize_detector(cfg["fn"], res)
    except Exception as e:
        out["err"] = f"{type(e).__name__}: {str(e)[:100]}"
        out["present"] = False
    return out


def llm_grade(strategy: str, ticker: str, detection: dict) -> dict:
    """Invoke LLM to grade the signal. Returns {grade, confidence, reason}."""
    if not MINIMAX_KEY:
        return {"grade": "?", "confidence": 0, "reason": "no api key"}
    direction = detection.get("direction", "long" if detection.get("signal") == "buy" else "short")
    # Get last close from detection or skip
    last = detection.get("last_close", 0)
    if last == 0:
        # Try to get from df
        if 'df_5m' in detection and detection['df_5m'] is not None and len(detection['df_5m']) > 0:
            last = float(detection['df_5m']['Close'].iloc[-1])
            detection['last_close'] = last
    det_summary = {k: v for k, v in detection.items() if k not in ('ts', 'df_5m', 'df_4h', 'df_1h')}
    prompt = f"""你是量化交易員。{strategy} detector on {ticker} 觸發信號。

Direction: {direction}
Last close: {last:.2f}
Detector result: {json.dumps(det_summary, default=str)[:500]}

評估呢個信號嘅 quality (A=強, B=可, C=弱, ?=noise)。
只輸出: GRADE: X | CONFIDENCE: 0-100 | REASON: 50字內

禁止 <think> 標籤。"""
    try:
        r = requests.post(
            MINIMAX_URL,
            headers={"Authorization": f"Bearer {MINIMAX_KEY}"},
            json={
                "model": MINIMAX_MODEL,
                "max_tokens": 1024,
                "messages": [
                    {"role": "system", "content": "你是量化交易員。直接輸出 GRADE/CONFIDENCE/REASON。"},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=30,
        )
        if r.status_code != 200:
            return {"grade": "?", "confidence": 0, "reason": f"http {r.status_code}"}
        content = r.json()["choices"][0]["message"]["content"]
        # Strip thinking
        if "</think>" in content:
            content = content.split("</think>")[-1].strip()
        import re
        m = re.search(r"GRADE:\s*([ABC?])\s*\|\s*CONFIDENCE:\s*(\d+)\s*\|\s*REASON:\s*(.+)", content, re.IGNORECASE)
        if m:
            return {
                "grade": m.group(1).upper(),
                "confidence": int(m.group(2)),
                "reason": m.group(3).strip()[:120],
            }
        # Fallback: try to find any GRADE letter
        gm = re.search(r"GRADE:\s*([ABC?])", content, re.IGNORECASE)
        cm = re.search(r"CONFIDENCE:\s*(\d+)", content, re.IGNORECASE)
        if gm and cm:
            return {
                "grade": gm.group(1).upper(),
                "confidence": int(cm.group(1)),
                "reason": content[:120],
            }
    except Exception as e:
        return {"grade": "?", "confidence": 0, "reason": f"err: {str(e)[:60]}"}
    return {"grade": "?", "confidence": 0, "reason": "no parse"}


def send_telegram(text: str) -> int:
    """Send TG message."""
    if not TG_TOKEN or not TG_CHAT:
        return 0
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": text[:4000], "disable_web_page_preview": True},
            timeout=15,
        )
        return r.status_code
    except Exception:
        return 0


def publish_ai_trader(signal: dict) -> int:
    """Publish signal to AI-Trader. Returns HTTP code."""
    if not AI_TOKEN:
        return 0
    try:
        r = requests.post(
            "https://ai-trader.hkuds.hku.hk/api/signals",
            headers={"Authorization": f"Bearer {AI_TOKEN}"},
            json=signal,
            timeout=20,
        )
        return r.status_code
    except Exception:
        return 0


sys.path.insert(0, str(REPO / "automation/scripts"))
from audit import log_action

# Auto-generate chart for each signal
def generate_signal_chart(sig: dict) -> str:
    """Generate candlestick chart for a single signal. Returns path."""
    try:
        from signal_chart import make_chart
        from pathlib import Path
        CHARTS_DIR = REPO / "automation" / "reports" / "signal_charts"
        CHARTS_DIR.mkdir(parents=True, exist_ok=True)
        signal_id = sig.get("position_id", sig.get("signal_id", "unknown"))
        safe = signal_id.replace("|", "_").replace(":", "-").replace("/", "_")[:80]
        out = CHARTS_DIR / f"{safe}.png"
        if make_chart(sig, out):
            return str(out)
    except Exception as e:
        print(f"  [chart] Error: {e}")
    return ""

def main() -> int:
    t_start = time.time()
    ts_now = datetime.now(timezone.utc).isoformat()
    print(f"[live_scan] === {ts_now} ===")
    # Step 1: Get active tickers (filter by market hours)
    active_tickers = get_active_tickers()
    if not active_tickers:
        print("[live_scan] No markets open, skipping")
        return 0
    print(f"[live_scan] Fetching {len(active_tickers)} tickers in parallel...")
    with ThreadPoolExecutor(min(4, len(active_tickers))) as pool:
        data_futs = {pool.submit(fetch_ticker_data, tk[0]): tk[0] for tk in active_tickers}
        data_map = {}
        for future in data_futs:
            ticker = data_futs[future]
            try:
                data_map[ticker] = future.result()
            except Exception as e:
                data_map[ticker] = {"ticker": ticker, "err": str(e)[:100]}
    for tk, d in data_map.items():
        n5 = d.get("n_5m", 0)
        n4 = d.get("n_4h", 0)
        print(f"  {tk}: 5m={n5} 4h={n4}")
    # Step 2: Run 9 detectors × 4 tickers = 36 in parallel
    print("[live_scan] Running detectors on active tickers...")
    detections = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futs = []
        for ticker, _ in active_tickers:
            data = data_map[ticker]
            for name, cfg in STRATEGIES.items():
                futs.append(pool.submit(run_detector, name, cfg, ticker, data))
        for fut in as_completed(futs):
            r = fut.result()
            detections.append(r)
    n_signals = sum(1 for d in detections if d.get("present"))
    n_errors = sum(1 for d in detections if "err" in d)
    print(f"  Total: {len(detections)} | Signals: {n_signals} | Errors: {n_errors}")
    # Step 3: LLM grading on detector signals
    fired = []
    for det in detections:
        if not det.get("present"):
            continue
        if det.get("skip"):
            continue
        if "err" in det:
            continue
        # OCS already has vote/conf
        if det.get("strategy") == "OCS-BTC-5m":
            grade = "A" if abs(det.get("vote", 0)) >= 4 and det.get("conf", 0) >= 0.55 else "B"
            conf = int(det.get("conf", 0) * 100)
            reason = f"OCS vote={det.get('vote')} conf={det.get('conf'):.2f} layer={det.get('layer_score', 0):.2f}"
        else:
            # Invoke LLM
            grade_data = llm_grade(det["strategy"], det["ticker"], det)
            grade = grade_data["grade"]
            conf = grade_data["confidence"]
            reason = grade_data["reason"]
        # Debug log
        print(f"  [grade] {det['strategy']:15s} {det['ticker']:7s} → {grade} conf={conf} | {reason[:60]}")
        # BTC amplification: boost conf by +10 (volatility bonus)
        ticker = det.get("ticker", "")
        if ticker == "BTC-USD" and BTC_FORCE_MODE:
            conf = min(100, conf + BTC_CONFIDENCE_BOOST)
            print(f"    [BTC-amplify] conf boosted to {conf}")
        # BTC uses lower threshold (more volatile market, fewer A/B signals)
        min_conf = LLM_MIN_CONF_BTC if ticker == "BTC-USD" else LLM_MIN_CONF
        if conf < min_conf:
            print(f"    [skip] conf {conf} < {min_conf} ({'BTC-mode' if ticker == 'BTC-USD' else 'normal'})")
            continue
        if grade not in ACCEPTABLE_GRADES:
            # BTC force fire: if C grade + BTC, allow it through
            if BTC_FORCE_FIRE and ticker == "BTC-USD" and grade == "C":
                print(f"    [BTC-force-fire] C-grade BTC signal accepted")
            else:
                print(f"    [skip] grade {grade} not in {ACCEPTABLE_GRADES}")
                continue
        # Accept: build signal
        signal = {
            "strategy": det["strategy"],
            "ticker": det["ticker"],
            "grade": grade,
            "confidence": conf,
            "reason": reason,
            "direction": det.get("direction", "long" if det.get("signal") == "buy" else "short"),
            "last_close": det.get("last_close", 0),
            "ts": ts_now,
        }
        fired.append(signal)
        print(f"    [FIRED] {grade} {det['ticker']}")
        # Audit: Power 3 accountable for this signal
        log_action("strategy-agent", "signal", f"{det['strategy']} {det['ticker']}", grade,
                  f"conf={conf}% dir={signal.get('direction', '?')}", "Power 3 (Strategy Agent)")
    print(f"[live_scan] LLM-confirmed signals: {len(fired)}")
    # Step 4: Fire each signal — compute SL/TP, open position, send TG
    for sig in fired:
        # Get ATR from the most recent data fetch
        ticker_data = data_map.get(sig["ticker"], {})
        df_5m = ticker_data.get("df_5m")
        atr = compute_atr(df_5m) if df_5m is not None and not df_5m.empty else 0
        sig["atr"] = atr
        # Compute SL/TP
        sl_tp = calc_sl_tp(sig.get("last_close", 0), atr, sig.get("direction", "long"))
        if sl_tp:
            sig.update(sl_tp)
        # Open position (DEDUPED)
        pos = open_live_position(sig, atr) if atr > 0 else None
        if pos:
            sig["position_id"] = pos["signal_id"]
            print(f"  ✓ Opened position: {pos['signal_id'][:30]} @ {pos['entry']:.2f}")
        else:
            sig["position_id"] = None
            print(f"  ⚠️ Position not opened (atr={atr} or duplicate)")
        # Build TG with SL/TP
        emoji = "🟢" if sig["grade"] == "A" else "🟡"
        msg = f"""{emoji} <b>{sig['strategy']}</b> [{sig['grade']}] {sig['ticker']}

💰 Last: ${sig['last_close']:,.2f}
📊 Conf: {sig['confidence']}
🎯 Dir: {sig['direction']}
💬 {sig['reason']}"""
        if sl_tp:
            msg += f"""

<b>Risk Plan</b> (1.6×ATR stop, T2 close mode):
• SL: ${sl_tp['sl']:,.2f} (close if hit)
• T2 (1.618R): ${sl_tp['t2']:,.2f} 🎯 close target
• T3-T5: ${sl_tp['t3']:,.2f} / ${sl_tp['t4']:,.2f} / ${sl_tp['t5']:,.2f} (runner if T2 missed)"""
        if pos:
            msg += "\n\n✅ Position opened (auto-track)"
        msg += f"""

⏰ {sig['ts'][:19]} UTC"""
        tg_code = send_telegram(msg)
        ai_code = publish_ai_trader({
            "symbol": sig["ticker"],
            "action": sig["direction"],
            "confidence": sig["confidence"] / 100,
            "reason": f"{sig['strategy']} [{sig['grade']}]: {sig['reason']}",
            "source": "live_scan",
        })
        sig["tg_code"] = tg_code
        sig["ai_code"] = ai_code
        with SIGNALS_FILE.open("a") as f:
            f.write(json.dumps(sig, default=str) + "\n")
        # Auto-generate chart for this signal
        chart_path = generate_signal_chart(sig)
        if chart_path:
            sig["chart_path"] = chart_path
            print(f"  ✓ {sig['strategy']} {sig['ticker']} [{sig['grade']}] TG={tg_code} AI={ai_code} CHART={chart_path}")
        else:
            print(f"  ✓ {sig['strategy']} {sig['ticker']} [{sig['grade']}] TG={tg_code} AI={ai_code}")
    # Step 5: Heartbeat
    heartbeat = {
        "timestamp": ts_now,
        "n_detections": len(detections),
        "n_signals": n_signals,
        "n_errors": n_errors,
        "n_fired": len(fired),
        "elapsed_sec": round(time.time() - t_start, 1),
        "tickers": list(data_map.keys()),
    }
    HEARTBEAT_FILE.write_text(json.dumps(heartbeat, indent=2, default=str))
    print(f"[live_scan] ✓ Heartbeat saved ({heartbeat['elapsed_sec']}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
