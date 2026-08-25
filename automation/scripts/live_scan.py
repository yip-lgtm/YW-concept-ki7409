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
DAILY_DIR = LIVE_DIR / "daily"
DAILY_DIR.mkdir(parents=True, exist_ok=True)

TICKERS = [
    ("MNQ=F", "Micro Nasdaq"),
    ("MES=F", "Micro S&P"),
    ("M2K=F", "Micro Russell"),
    ("BTC-USD", "BTC USD"),
]

# Strategy name → (detector_fn, required_args, weight, timeframe)
STRATEGIES = {
    "H-Pattern":     {"fn": "h_pattern",     "args": {}, "weight": 1.2, "tf": "5m"},
    "3-Pushes":      {"fn": "3_pushes",      "args": {}, "weight": 1.0, "tf": "5m"},
    "Two-Yang":      {"fn": "two_yang",      "args": {}, "weight": 0.8, "tf": "15m"},
    "RSI-Div":       {"fn": "rsi_div",       "args": {"resample_15m": True}, "weight": 0.7, "tf": "15m", "llm_optimized": True},  # LLM-iter 2026-08-25: weight 1.1→0.7, 15min, +EMA+vol
    "50-20-Pullback":{"fn": "pb_5020",       "args": {}, "weight": 1.0, "tf": "5m"},
    "Stair":         {"fn": "stair",         "args": {}, "weight": 0.9, "tf": "5m"},
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
# Min detector strength to invoke LLM
DETECTOR_MIN_PRESENT = True
# Acceptable grades (A=strong, B=actionable, C=marginal but still fire with low conf)
ACCEPTABLE_GRADES = ("A", "B", "C")


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
    # 4h bars only for CRT
    if ticker != "BTC-USD":
        try:
            df_1h = fetch_bars(ticker, days=30, interval_min=60)
            if df_1h is not None and not df_1h.empty:
                df_4h = df_1h.resample("4h").agg({
                    "Open": "first", "High": "max", "Low": "min",
                    "Close": "last", "Volume": "sum"
                }).dropna()
                out["df_4h"] = df_4h
                out["n_4h"] = len(df_4h)
        except Exception as e:
            out["err_4h"] = str(e)[:100]
    return out


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
            res = detect_h_pattern(df)
            out["last_close"] = float(df["Close"].iloc[-1]) if not df.empty else 0
        elif cfg["fn"] == "3_pushes":
            res = detect_3_pushes(df)
            out["last_close"] = float(df["Close"].iloc[-1]) if not df.empty else 0
        elif cfg["fn"] == "two_yang":
            res = detect_two_yang_one_yin(df)
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
                res = detect_rsi_divergence(df)
            out["last_close"] = float(df["Close"].iloc[-1]) if not df.empty else 0
        elif cfg["fn"] == "pb_5020":
            res = detect_5020_pullback(df)
            out["last_close"] = float(df["Close"].iloc[-1]) if not df.empty else 0
        elif cfg["fn"] == "stair":
            res = detect_stair_pattern(df)
            out["last_close"] = float(df["Close"].iloc[-1]) if not df.empty else 0
        elif cfg["fn"] == "kell":
            res = detect_kell_setups(df)
            out["last_close"] = float(df["Close"].iloc[-1]) if not df.empty else 0
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
        out["present"] = res.get("present", False)
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


def main() -> int:
    t_start = time.time()
    ts_now = datetime.now(timezone.utc).isoformat()
    print(f"[live_scan] === {ts_now} ===")
    # Step 1: Fetch all ticker data in parallel
    print("[live_scan] Fetching 4 tickers in parallel...")
    with ThreadPoolExecutor(max_workers=4) as pool:
        data_futs = {pool.submit(fetch_ticker_data, tk[0]): tk[0] for tk in TICKERS}
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
    print("[live_scan] Running 9 detectors × 4 tickers (36 parallel)...")
    detections = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futs = []
        for ticker, _ in TICKERS:
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
        if conf < LLM_MIN_CONF:
            continue
        if grade not in ACCEPTABLE_GRADES:
            continue
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
    print(f"[live_scan] LLM-confirmed signals: {len(fired)}")
    # Step 4: Fire each signal
    for sig in fired:
        emoji = "🟢" if sig["grade"] == "A" else "🟡"
        msg = f"""{emoji} <b>{sig['strategy']}</b> [{sig['grade']}] {sig['ticker']}

💰 Last: ${sig['last_close']:,.2f}
📊 Conf: {sig['confidence']}
🎯 Dir: {sig['direction']}
💬 {sig['reason']}

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
