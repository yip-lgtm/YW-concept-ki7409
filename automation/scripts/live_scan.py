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
try:
    from zoneinfo import ZoneInfo
    NY_TZ = ZoneInfo("America/New_York")
except ImportError:
    NY_TZ = timezone(timedelta(hours=-5))  # EST fallback

def to_ny_time(iso_ts: str) -> str:
    """Convert ISO timestamp to NY time string."""
    try:
        dt = datetime.fromisoformat(iso_ts.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ny_dt = dt.astimezone(NY_TZ)
        return ny_dt.strftime('%Y-%m-%d %H:%M %Z')
    except Exception:
        return iso_ts
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    # Prefer real checkout (box: /home/box/repos/...); fall back to legacy sandbox path
    _here = Path(__file__).resolve().parents[2]
    REPO = _here if (_here / "automation").is_dir() else Path("/workspace/YW-concept-ki7409")

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
# Acceptable grades (A=strong, B=actionable, C=marginal but still fire with low conf).
# P0 gate (2026-09-16): Grade C is auto-skipped for OPENING positions (logged to signals.jsonl only).
ACCEPTABLE_GRADES = ("A", "B", "C")

# ===========================================================================================
# P0 OPEN-POSITION GATES (2026-09-16)
# ===========================================================================================
# These are post-LLM-grade hard gates that override LLM accept/dismiss decisions.
# Reason: LLM grading + detector output alone produced too many unviable positions:
#   - H-Pattern firing at pullback 98% ("結構失效 / 似 noise" → still opened C-grade LONG)
#   - Same ticker opening BOTH long + short simultaneously on conflicting setups
#   - Grade C noise piling up with same SL/TP template
# Hard rules win over LLM judgement. Numeric gates, not prompt parsing.

# H-Pattern pullback must be <50% per YW playbook. Above that, H-formation has fully
# collapsed and the signal is structurally invalid (was previously fired as Grade C).
# Apply abs() so -99 (down-trend exhaustion) and +99 (up-trend exhaustion) are both caught.
H_PATTERN_PULLBACK_MAX_PCT = 50.0

# Grade C: keep paper-grade logging for LLM data, but DO NOT auto-open real positions.
# (Paper mode is for testing strategies, not for testing C-grade noise.)
BLOCK_GRADE_C_OPEN = True

# CRT distance_from_mss gate (v3 — 2026-09-17 user review):
#   "文案已寫 MSS 未確認、價仍在雙均線下。Partial CRT ≠ 開倉"
#   "CRT B 級追價係而家最大漏油"
# CRT signal must be within 0.3×range of MSS confirmation. Beyond that = price has
# already traveled past the structure-confirmation level; this is the classic
# "追空 RR 差、等 MSS" pattern (16:32 NY 9/16 cost us −$128 across MES/MNQ CRT shorts).
# CRT detector may emit present=True when raid + MSS are technically satisfied, but
# if last_close has run > 0.3×range past MSS, the entry is chasing, not confirming.
CRT_MSS_DISTANCE_MAX_RATIO = 0.3

# Analyst circuit breaker (v3 — 2026-09-17 user review):
#   "Analyst >50% fail → 理論全停"
#   "Analyst 78/78 failed 仍開倉"
# If Tech Analyst chart generation failure rate > threshold for THIS scan's batch
# (computed live, not 24h cumulative), ALL open positions halt. Persistent state file
# survives concurrent runs. TTL 2h auto-recover; but N consecutive successful scans
# (charts_failed < 20% of charts_total) are required to re-arm.
ANALYST_BREAKER_FAIL_THRESHOLD = 0.50
ANALYST_BREAKER_TTL_HOURS = 2
ANALYST_BREAKER_RECOVERY_SCANS = 3  # need 3 consecutive scans with <20% fail to clear
ANALYST_BREAKER_MIN_SAMPLE = 5      # need ≥5 attempted charts to even consider tripping
ANALYST_BREAKER_STATE_FILE = LIVE_DIR / "circuit_breaker.json"

# P0.5: same ticker + same direction = stacking. Cap at 1 signal per ticker per direction
# to prevent 4 strategies × 1 ticker on the same SL/TP template.
BLOCK_STACKING_PER_TICKER = True

# v5 — Ticker/session-based gates (2026-09-23 user review of 9/21-9/22 trades)
# EVIDENCE (from 7-day rolling, 135 closed trades):
#   Stair BTC: 4 trades -$210 net (1 outlier +$444); 87-bar SL 22:01 = over-night hold
#   Stair MES: 5 trades -$11, no winners
#   Stair RTH Close (14-16 ET): n=1 small; Asia/Late (20-02 ET): n=8 mixed
#   3-Pushes BTC: 7 trades, avg 63.7 bars hold, -$541 — BTC overnight bleed
#   3-Pushes RTH Close (14-16 ET): n=7 -$526, biggest session drag
#   50-20 MGC: 2 trades 0/2 wins, -$8
#   RSI-Div BTC: 4 trades, 25% WR, -$989 — paper filter, not real risk
#
# Hard rules per user directive 2026-09-23:
#   1. Stair: ban BTC + MES tickers entirely; ban RTH Close + Asia/Late + Lunch sessions
#   2. 3-Pushes: ban BTC ticker; ban RTH Close + Asia/Late sessions
#   3. 50-20-Pullback: ban MGC ticker (0/2 wins, low cost)
#   4. RSI-Div: paper-only default; allow Grade A + non-BTC live only
#   5. TTrades: cap units at 0.5 BTC / $43k notional
#   6. Stair: time-windowed stacking (no second same-ticker-same-direction within 4h)

# Tickers to fully ban per strategy (v5)
STAIR_BAN_TICKERS = {"BTC-USD", "MES=F"}
PUSHES_BAN_TICKERS = {"BTC-USD"}
PULLBACK_5020_BAN_TICKERS = {"MGC=F"}

# Session tags to ban per strategy (v5)
STAIR_BAN_SESSIONS = {"RTH_Close", "AsiaLate", "Lunch"}
PUSHES_BAN_SESSIONS = {"RTH_Close", "AsiaLate"}

# RSI-Div paper-only default (v5) — live only when Grade A + non-BTC
RSI_DIV_PAPER_ONLY = True

# Stair time-windowed stacking (v5) — second same-ticker-same-direction within 4h blocks
STAIR_REENTRY_COOLDOWN_HOURS = 4

# 50-20 Pullback EMA-distance gate (v4.1 — 2026-09-21 user review):
#   "已離開早段回踩" / "再貼 EMA 0.06% 係延續單, 唔係新金叉"
#   "唔追 81.5 之上嘅 50-20 多"
# A 50-20 pullback is only valid when price is genuinely pulling back to EMA20.
# Detector emits `distance_to_ema20_pct` in percent; threshold 0.1% (i.e. raw decimal
# 0.001). Past that, the price has drifted too far from the moving average for the
# setup to be a "pullback" — it's a chase into a one-sided trend, identical to the
# CRT chase problem. 9/20 evidence: BTC distance 0.06% (11:28) was the boundary case
# (kept), 21:27 onward price ramped to 81.5 → distance > 0.1% (skipped).
PULLBACK_5020_EMA_DISTANCE_MAX_PCT = 0.1  # percent; detector returns 0.08 = 0.08%

# Grade ranking for stacking resolution: lower = stronger. A wins, B second, others unknown.
GRADE_RANK = {"A": 0, "B": 1}


def parse_dt_any(ts):
    """Robustly parse an ISO timestamp string to a tz-aware datetime (UTC).

    Accepts trailing 'Z' as UTC. Returns None on failure.
    """
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if not isinstance(ts, str):
        return None
    s = ts.strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _ny_session_of(dt_utc) -> str:
    """Classify a UTC datetime into an NY session bucket.
    Used by v5 ticker/session gates. Returns one of:
      LDLZ, AsiaPreMkt, NYKZ_Open, NYKZ_Mid, Lunch, RTH_Close, PostMkt, AsiaLate
    """
    if dt_utc is None:
        return ""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    try:
        ny = dt_utc.astimezone(NY_TZ)
    except Exception:
        ny = dt_utc
    h, m = ny.hour, ny.minute
    if 2 <= h < 5:
        return "LDLZ"
    if 5 <= h < 8 or (h == 8 and m < 30):
        return "AsiaPreMkt"
    if (h == 8 and m >= 30) or h == 9:
        return "NYKZ_Open"
    if 10 <= h < 11:
        return "NYKZ_Mid"
    if 11 <= h < 14:
        return "Lunch"
    if 14 <= h < 16:
        return "RTH_Close"
    if 16 <= h < 20:
        return "PostMkt"
    return "AsiaLate"


def _normalize_direction(direction: str) -> str:
    """Normalize detector / LLM direction strings to long/short/unknown.

    Without normalization, 3-Pushes 'up' would NOT conflict with Stair 'short' (string
    mismatch). All detectors should report direction in {long, short} but the reality
    is that several detectors use {up, down, bullish, bearish, buy, sell} interchangeably.
    Unknown = fail-closed for conflict detection (treated as own class, won't trigger
    conflict against long OR short, but won't stack either).
    """
    if not direction:
        return "unknown"
    d = str(direction).strip().lower()
    if d in ("long", "buy", "up", "bullish", "l"):
        return "long"
    if d in ("short", "sell", "down", "bearish", "s"):
        return "short"
    return "unknown"


def _read_circuit_breaker() -> dict:
    """Read analyst circuit-breaker state file. Returns {} if absent/invalid."""
    try:
        if ANALYST_BREAKER_STATE_FILE.exists():
            return json.loads(ANALYST_BREAKER_STATE_FILE.read_text() or "{}")
    except Exception:
        pass
    return {}


def _check_circuit_breaker() -> tuple:
    """Check analyst circuit breaker state. Returns (allow_open: bool, reason: str).

    State file schema (automation/state/live_scan/circuit_breaker.json):
      {
        "open": bool,
        "opened_at": iso-utc,
        "until": iso-utc,            # TTL expiry
        "reason": str,
        "consecutive_good_scans": int # increments each scan with fail<20%; clears when ≥N
      }

    Returns:
      (True, "ok") — circuit closed or expired; allow opens
      (False, "<why>") — circuit OPEN; reject all opens
    """
    state = _read_circuit_breaker()
    if not state.get("open"):
        return True, "circuit closed (or uninitialized)"
    # Check TTL
    until_str = state.get("until")
    if until_str:
        try:
            from datetime import datetime, timezone
            until = datetime.fromisoformat(until_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            if now >= until:
                # TTL expired — try to auto-clear if recovery counter sufficient
                good = int(state.get("consecutive_good_scans", 0))
                if good >= ANALYST_BREAKER_RECOVERY_SCANS:
                    state["open"] = False
                    state["consecutive_good_scans"] = 0
                    state["cleared_at"] = now.isoformat()
                    state["cleared_reason"] = "TTL expired + N-success recovery"
                    try:
                        ANALYST_BREAKER_STATE_FILE.write_text(json.dumps(state, indent=2))
                    except Exception:
                        pass
                    return True, f"circuit auto-cleared (TTL + {good} good scans)"
                return False, f"circuit open (TTL expired but only {good}/{ANALYST_BREAKER_RECOVERY_SCANS} good scans)"
        except Exception:
            pass
    return False, f"circuit open: {state.get('reason', 'unknown')}"


def _apply_open_gates(fired_signals: list) -> tuple:
    """Apply P0 + P0.5 hard gates to fired signals. Returns (kept, gated_out).

    Hard rules (override any LLM grading, numeric — never parse prompt text):
      1. Grade C: no auto-open. Log to signals.jsonl only. (P0)
      2. H-Pattern:
           - pullback_pct missing  → reject (fail-closed)
           - abs(pullback_pct) > 50 → reject (YW invalid; -99 and +99 both treated)
      3. Direction conflict (per-ticker): if NORMALIZED direction set has BOTH
         long + short in this batch, skip ALL of that ticker. Don't pick a side.
      4. P0.5 Stacking (per-ticker, per-direction): if same ticker has ≥2 strategies
         pointing same direction, keep only the strongest (A > B; ties broken by
         confidence). Prevents 4 strategies × 1 BTC on shared ATR.

    Order matters: C → H-Pattern → conflict → stacking.

    Returns:
        kept: signals that should open positions + send chart + publish AI-Trader
        gated_out: signals that were rejected; still logged to signals.jsonl with
                   gate_skip field set for LLM data collection
    """
    # === PRE-CHECK: Analyst circuit breaker (v3) ===
    # If Tech Analyst charts are mostly failing, ALL opens halt regardless of LLM grade.
    # Reading circuit state file is shared with tech_analyst.py — see _read_circuit_breaker().
    kept = []
    gated = []
    allow_open, breaker_reason = _check_circuit_breaker()
    if not allow_open:
        for sig in fired_signals:
            sig["gate_skip"] = f"CIRCUIT BREAKER: {breaker_reason} — no auto-open while Analyst degraded"
            gated.append(sig)
        print(f"[gate] 🛑 CIRCUIT BREAKER OPEN: {breaker_reason} → {len(fired_signals)} signals gated")
        return [], gated

    for sig in fired_signals:
        strat = sig.get("strategy", "?")
        # === Gate 1: Grade C no auto-open (P0) ===
        if BLOCK_GRADE_C_OPEN and sig.get("grade") == "C":
            sig["gate_skip"] = "Grade C: no auto-open (logged for LLM data only)"
            gated.append(sig)
            continue
        # === Gate 2: H-Pattern pullback (P0) ===
        #   - Missing pullback_pct → fail-closed (reject)
        #   - abs(pullback_pct) > 50 → reject (-99 and +99 both caught)
        if strat == "H-Pattern":
            if "pullback_pct" not in sig or sig.get("pullback_pct") is None:
                sig["gate_skip"] = "H-Pattern missing pullback_pct (fail-closed)"
                gated.append(sig)
                continue
            try:
                pb_f = float(sig["pullback_pct"])
            except (TypeError, ValueError):
                sig["gate_skip"] = "H-Pattern pullback_pct non-numeric (fail-closed)"
                gated.append(sig)
                continue
            if abs(pb_f) >= H_PATTERN_PULLBACK_MAX_PCT:
                sig["gate_skip"] = (
                    f"H-Pattern |pullback| {abs(pb_f):.1f}% >= {H_PATTERN_PULLBACK_MAX_PCT:.0f}% (YW invalid)"
                )
                gated.append(sig)
                continue
        # === Gate 2.5: CRT distance_from_mss (v3 — 2026-09-17) ===
        # "Partial CRT ≠ 開倉" — if price has run > 0.3×range past MSS confirmation,
        # the entry is chasing, not confirming. CRT detector may emit present=True
        # when raid+MSS are technically satisfied, but the chase risk breaks R:R.
        # Numeric: distance_from_mss = |last_close - mss| / range
        # range = raid_size (CRTHigh - CRTLow for bullish, or vice versa).
        if strat == "CRT":
            # CRT detector returns mss_confirm (not mss_price/MSS) — try all keys
            mss = (sig.get("mss_confirm") or sig.get("mss_price")
                   or sig.get("mss") or sig.get("MSS"))
            last = sig.get("last_close", 0)
            # For bullish CRT, raid_high = CRTHigh (above market); raid_low = CRTLow (sweep below)
            # For bearish CRT, raid_high = sweep-above-high; raid_low = CRTLow
            # Either way, range = max(raid_high, crt_high) − min(raid_low, crt_low)
            raid_high = (sig.get("raid_high") or sig.get("CRTHigh")
                         or sig.get("crt_high"))
            raid_low = (sig.get("raid_low") or sig.get("CRTLow")
                        or sig.get("crt_low"))
            if mss is not None and raid_high is not None and raid_low is not None:
                try:
                    mss_f = float(mss)
                    high_f = float(raid_high)
                    low_f = float(raid_low)
                    last_f = float(last) if last else 0
                    rng = abs(high_f - low_f)
                    if rng > 0 and last_f > 0:
                        dist = abs(last_f - mss_f) / rng
                        if dist > CRT_MSS_DISTANCE_MAX_RATIO:
                            sig["gate_skip"] = (
                                f"CRT chasing: distance_from_mss={dist:.2f}×range "
                                f"(> {CRT_MSS_DISTANCE_MAX_RATIO:.1f}); entry too far from MSS"
                            )
                            gated.append(sig)
                            print(f"[gate] CRT chasing {sig.get('ticker','?')} dist={dist:.2f} → SKIP")
                            continue
                except (TypeError, ValueError):
                    pass  # missing/bad data → don't block on this gate (other gates still apply)
        # === Gate 2.10: Stair ticker + session ban (v5 — 2026-09-23) ===
        # 7-day evidence: BTC Stair 4 trades net -$210 + 87-bar overnight; MES 5 trades no
        # winners; RTH_Close/AsiaLate/Lunch sessions net losers. Direction is "short" only.
        if strat == "Stair":
            tk = sig.get("ticker", "")
            if tk in STAIR_BAN_TICKERS:
                sig["gate_skip"] = (
                    f"Stair ban ticker {tk}: 7-day live loss "
                    f"(BTC -$210 net + overnight; MES -$11 no winners)"
                )
                gated.append(sig)
                print(f"[gate] Stair ban ticker {tk} → SKIP")
                continue
            try:
                sess = _ny_session_of(parse_dt_any(sig.get("ts")))
            except Exception:
                sess = ""
            if sess in STAIR_BAN_SESSIONS:
                sig["gate_skip"] = (
                    f"Stair ban session {sess}: 7-day net loss "
                    f"(RTH Close / AsiaLate / Lunch all drag)"
                )
                gated.append(sig)
                print(f"[gate] Stair ban session {sess} → SKIP")
                continue
        # === Gate 2.11: 3-Pushes ticker + session ban (v5 — 2026-09-23) ===
        # 7-day evidence: BTC 3-Pushes 7 trades avg 63.7 bars hold -$541 (overnight bleed);
        # RTH Close 14-16 ET n=7 -$526 (worst session); direction normalize bug fixed in
        # detect_3_pushes but session/ticker still block.
        if strat == "3-Pushes":
            tk = sig.get("ticker", "")
            if tk in PUSHES_BAN_TICKERS:
                sig["gate_skip"] = (
                    f"3-Pushes ban ticker {tk}: 7-day BTC avg 63.7 bars hold, -$541 net"
                )
                gated.append(sig)
                print(f"[gate] 3-Pushes ban ticker {tk} → SKIP")
                continue
            try:
                sess = _ny_session_of(parse_dt_any(sig.get("ts")))
            except Exception:
                sess = ""
            if sess in PUSHES_BAN_SESSIONS:
                sig["gate_skip"] = (
                    f"3-Pushes ban session {sess}: RTH_Close -$526 + AsiaLate bleed"
                )
                gated.append(sig)
                print(f"[gate] 3-Pushes ban session {sess} → SKIP")
                continue
        # === Gate 2.12: 50-20-Pullback ticker ban (v5 — 2026-09-23) ===
        # MGC 2 trades 0/2 wins, low cost ban. Doesn't affect BTC/MNQ engine (+$1066).
        if strat == "50-20-Pullback":
            tk = sig.get("ticker", "")
            if tk in PULLBACK_5020_BAN_TICKERS:
                sig["gate_skip"] = (
                    f"50-20-Pullback ban ticker {tk}: 7-day 0/2 wins, -$8 net"
                )
                gated.append(sig)
                print(f"[gate] 50-20-Pullback ban ticker {tk} → SKIP")
                continue
        # === Gate 2.13: RSI-Div paper-only default (v5 — 2026-09-23) ===
        # 7-day: 6 trades -$1000 (4 BTC + 2 MGC); all 4 BTC losses. Until LLM dumps the
        # actual ticket reasons for the BTC losses, default to paper-only. Allow live only
        # if Grade A AND ticker is non-BTC.
        if RSI_DIV_PAPER_ONLY and strat == "RSI-Div":
            tk = sig.get("ticker", "")
            gr = sig.get("grade", "?")
            if gr != "A" or tk == "BTC-USD":
                sig["gate_skip"] = (
                    f"RSI-Div paper-only (grade={gr}, ticker={tk}); "
                    f"7-day live -$1000; live requires Grade A AND non-BTC"
                )
                gated.append(sig)
                print(f"[gate] RSI-Div paper-only grade={gr} {tk} → SKIP")
                continue
        # === Gate 2.7: 50-20 Pullback EMA-distance (v4.1 — 2026-09-21) ===
        # If price has drifted >0.1% from EMA20, this is no longer a real pullback —
        # it's a chase into a one-sided trend. Detector already classifies >0.5% as
        # "above_ema20" (single-direction), but the 0.1% threshold is a stricter
        # user-defined edge that catches earlier drift (e.g. 21:27 BTC cases where
        # price had ramped past the original pullback window).
        if strat == "50-20-Pullback":
            dist_pct = sig.get("distance_to_ema20_pct")
            if dist_pct is not None:
                try:
                    dist_f = float(dist_pct)
                    # Use abs() — long/short can both drift away from EMA20
                    if abs(dist_f) > PULLBACK_5020_EMA_DISTANCE_MAX_PCT:
                        sig["gate_skip"] = (
                            f"50-20 drift: distance_to_ema20={dist_f:+.3f}% "
                            f"|{abs(dist_f):.3f}% > {PULLBACK_5020_EMA_DISTANCE_MAX_PCT:.3f}%; "
                            f"not a real pullback — price has run past EMA20"
                        )
                        gated.append(sig)
                        print(f"[gate] 50-20 drift {sig.get('ticker','?')} dist={dist_f:+.3f}% → SKIP")
                        continue
                except (TypeError, ValueError):
                    pass  # missing/bad data → don't block (other gates still apply)
        # === Gate 2.6: Stacking (per-ticker, per-direction) (P0.5) ===
        # already handled below; placeholder removed
        kept.append(sig)

    # === Gate 3: Direction conflict (per-ticker, normalized) ===
    # After C + H-Pattern filter, group remaining signals by ticker. If any ticker has
    # NORMALIZED directions covering BOTH 'long' and 'short', skip ALL of that ticker.
    by_ticker = {}
    for sig in kept:
        sig["_normalized_dir"] = _normalize_direction(sig.get("direction", ""))
        by_ticker.setdefault(sig.get("ticker", "?"), []).append(sig)
    post_conflict_kept = []
    for ticker, sigs in by_ticker.items():
        dirs = {s["_normalized_dir"] for s in sigs if s["_normalized_dir"] in ("long", "short")}
        if len(dirs) > 1:
            # Conflict: long + short on same ticker. Skip ALL.
            raw_dirs = sorted({s.get("direction", "?") for s in sigs})
            for s in sigs:
                s["gate_skip"] = (
                    f"Direction conflict on {ticker}: normalized {{{','.join(sorted(dirs))}}} "
                    f"raw {raw_dirs} both fired — skip both"
                )
            gated.extend(sigs)
            print(f"[gate] ⚠️  {ticker}: direction conflict {sorted(dirs)} → skipped both ({len(sigs)} signals)")
        else:
            post_conflict_kept.extend(sigs)

    # === Gate 4: Stacking (per-ticker, per-direction) (P0.5) ===
    # If same ticker + same direction has ≥2 strategies, keep only the strongest grade.
    # Ties (e.g. two B's) broken by confidence desc. Prevents 4 strategies × 1 ticker
    # from sharing one ATR/SL/TP template.
    final_kept = []
    if BLOCK_STACKING_PER_TICKER:
        stack_by_key = {}
        for sig in post_conflict_kept:
            key = (sig.get("ticker", "?"), sig.get("_normalized_dir", "unknown"))
            stack_by_key.setdefault(key, []).append(sig)
        for (ticker, ndir), sigs in stack_by_key.items():
            if len(sigs) <= 1:
                final_kept.extend(sigs)
                continue
            # Sort: best grade first (A=0, B=1, others=2), then confidence desc
            def _stack_key(s):
                return (GRADE_RANK.get(s.get("grade", "?"), 2), -int(s.get("confidence", 0)))
            sigs_sorted = sorted(sigs, key=_stack_key)
            winner = sigs_sorted[0]
            losers = sigs_sorted[1:]
            for s in losers:
                s["gate_skip"] = (
                    f"Stacking on {ticker} {ndir}: kept strongest {winner['strategy']} "
                    f"[{winner.get('grade')}] conf={winner.get('confidence')}; "
                    f"this {s['strategy']} [{s.get('grade')}] conf={s.get('confidence')}"
                )
            gated.extend(losers)
            print(
                f"[gate] ⚖️  {ticker} {ndir}: {len(sigs)} stacked strategies → "
                f"kept {winner['strategy']} [{winner.get('grade')}] "
                f"(skipped {len(losers)}): {[l['strategy'] for l in losers]}"
            )
            final_kept.append(winner)
    else:
        final_kept = post_conflict_kept

    return final_kept, gated
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
        try:
            positions = json.loads(POSITIONS_FILE.read_text())
        except json.JSONDecodeError as e:
            # Corrupted positions.json (e.g., from git merge conflict markers)
            print(f"[open] positions.json corrupt: {e}")
            print(f"[open] Resetting to empty list (auto-recover)")
            try:
                POSITIONS_FILE.write_text("[]\n")
            except Exception:
                pass
            positions = []
    else:
        positions = []
    # === MULTI-LAYER DEDUP ===
    ticker = pos["ticker"]
    sig_direction = pos["direction"]
    
    # Rule 1: Same signal_id → skip
    if any(p.get("signal_id") == pos["signal_id"] for p in positions):
        return None
    
    # Rule 2: One position per ticker max
    same_ticker_open = [p for p in positions if p.get("ticker") == ticker and p.get("status") == "open"]
    if same_ticker_open:
        existing = same_ticker_open[0]
        print(f"[open] SKIP {pos['strategy']} {ticker} {sig_direction}: already have open {existing['strategy']} {existing.get('direction')} @ {existing['entry']}")
        return None
    if TRADES_FILE.exists():
        existing_trades = []
        for line in TRADES_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith(("<", "=", ">")): continue
            try: existing_trades.append(json.loads(line))
            except: pass
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


def send_telegram_photo(photo_path: str, caption: str = "") -> int:
    """Send a photo to TG with optional caption."""
    if not TG_TOKEN or not TG_CHAT:
        return 0
    from pathlib import Path
    p = Path(photo_path)
    if not p.exists():
        return 0
    try:
        with open(p, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                data={"chat_id": TG_CHAT, "caption": caption[:1024]},
                files={"photo": (p.name, f, "image/png")},
                timeout=30,
            )
        return r.status_code
    except Exception as e:
        print(f"  [TG photo] Error: {e}")
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

def is_strategy_allowed_now(strategy: str, ticker: str) -> bool:
    """Check if strategy is allowed to fire based on NY time.
    
    1H/15m-based strategies require RTH (09:30-16:00 ET Mon-Fri).
    """
    try:
        from zoneinfo import ZoneInfo
        NY = ZoneInfo("America/New_York")
        now_ny = datetime.now(NY)
    except ImportError:
        now_ny = datetime.now(timezone(timedelta(hours=-5)))
    
    if ticker == "BTC-USD":
        return True
    
    is_weekday = now_ny.weekday() < 5
    in_rth = is_weekday and (9 < now_ny.hour or (now_ny.hour == 9 and now_ny.minute >= 30)) and now_ny.hour < 16
    
    h1_based = {"H-Pattern", "Two-Yang", "50-20-Pullback", "3-Pushes", "Kell-Cycle"}
    if strategy in h1_based:
        return in_rth
    
    return True


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
        # Accept: build signal — copy detector-specific fields so _apply_open_gates
        # can read them (CRT mss_confirm/crt_high, H-Pattern pullback_pct, etc.).
        # Without this passthrough, v3 gates couldn't see the detector's numeric
        # structure data → CRT chase gate silently never fired.
        signal = {
            "strategy": det["strategy"],
            "ticker": det["ticker"],
            "grade": grade,
            "confidence": conf,
            "reason": reason,
            "direction": det.get("direction", "long" if det.get("signal") == "buy" else "short"),
            "last_close": det.get("last_close", 0),
            "ts": ts_now,
            # Detector raw fields (only the ones v3 gates need)
            "mss_confirm": det.get("mss_confirm"),
            "mss_price": det.get("mss_price"),
            "crt_high": det.get("crt_high"),
            "crt_low": det.get("crt_low"),
            "raid_low": det.get("raid_low"),
            "raid_high": det.get("raid_high"),
            "pullback_pct": det.get("pullback_pct"),
            "strength": det.get("strength"),
            "crt_range_pct": det.get("crt_range_pct"),
            # 50-20 Pullback detector fields (v4.1 — for Gate 2.7 EMA-distance check)
            "distance_to_ema20_pct": det.get("distance_to_ema20_pct"),
            "ema20": det.get("ema20"),
            "sma50": det.get("sma50"),
            "cross_type": det.get("cross_type"),
            "cross_bars_ago": det.get("cross_bars_ago"),
            "pullback_state": det.get("pullback"),
        }
        fired.append(signal)
        print(f"    [FIRED] {grade} {det['ticker']}")
        # Audit: Power 3 accountable for this signal
        log_action("strategy-agent", "signal", f"{det['strategy']} {det['ticker']}", grade,
                  f"conf={conf}% dir={signal.get('direction', '?')}", "Power 3 (Strategy Agent)")
    print(f"[live_scan] LLM-confirmed signals: {len(fired)}")
    # Time-of-day filter
    filtered = []
    for sig in fired:
        strat = sig.get("strategy", "?")
        ticker = sig.get("ticker", "?")
        if not is_strategy_allowed_now(strat, ticker):
            print(f"  ⏰ SKIP {strat} {ticker}: outside RTH")
            continue
        filtered.append(sig)
    fired = filtered

    # === P0 OPEN-POSITION GATES (2026-09-16) ===
    # Hard rules that override LLM grading. See _apply_open_gates() docstring.
    pre_gate = fired
    fired, gated_out = _apply_open_gates(fired)

    # === v5: TIME-WINDOWED STAIR RE-ENTRY STACKING (2026-09-23) ===
    # Per-batch P0.5 stacking only catches same-batch dupes. The 9/21-22 evidence
    # showed Stair BTC 21:00 SL then 22:01 SL (2nd trade 87 bars / 7h later) — first
    # already hit T2 but didn't stop a second same-ticker-same-direction entry.
    # Read positions.json, block new same-(ticker,strategy,normalized_dir) if last
    # closed/closing trade on that combo was within STAIR_REENTRY_COOLDOWN_HOURS.
    if fired:
        try:
            if POSITIONS_FILE.exists():
                _positions_state = json.loads(POSITIONS_FILE.read_text())
            else:
                _positions_state = []
        except Exception:
            _positions_state = []
        now_dt = parse_dt_any(datetime.now(timezone.utc).isoformat())
        cd_filtered = []
        for sig in fired:
            strat = sig.get("strategy", "?")
            if strat != "Stair":
                cd_filtered.append(sig)
                continue
            tk = sig.get("ticker", "")
            ndir = _normalize_direction(sig.get("direction", ""))
            cd_hours = STAIR_REENTRY_COOLDOWN_HOURS
            blocked = False
            for p in _positions_state:
                if p.get("strategy") != "Stair":
                    continue
                if p.get("ticker") != tk:
                    continue
                if _normalize_direction(p.get("direction", "")) != ndir:
                    continue
                # Look at exit_time OR entry_time
                ref_dt = parse_dt_any(p.get("exit_time")) or parse_dt_any(p.get("entry_time"))
                if ref_dt is None or now_dt is None:
                    continue
                age_h = (now_dt - ref_dt).total_seconds() / 3600.0
                if 0 <= age_h <= cd_hours:
                    sig["gate_skip"] = (
                        f"Stair re-entry cooldown: prior Stair {tk} {ndir} closed {age_h:.1f}h ago "
                        f"(cooldown {cd_hours}h); user directive 9/21 'first hit T2 should stop'"
                    )
                    gated_out.append(sig)
                    print(f"[gate] Stair cooldown {tk} {ndir} last {age_h:.1f}h ago → SKIP")
                    blocked = True
                    break
            if not blocked:
                cd_filtered.append(sig)
        fired = cd_filtered
    if gated_out:
        print(f"[live_scan] 🚧 Gate-skipped {len(gated_out)} signals (logged only, no position):")
        for g in gated_out:
            print(f"    - {g['strategy']} [{g['grade']}] {g['ticker']} {g.get('direction', '?')}: {g.get('gate_skip', '?')}")
    
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

⏰ {to_ny_time(sig['ts'])} (NY)"""
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
            # Send chart as photo to TG
            chart_caption = f"📊 {sig['strategy']} [{sig['grade']}] {sig['ticker']} {sig['direction']} | Entry ${sig.get('last_close', 0):,.2f}"
            photo_code = send_telegram_photo(chart_path, chart_caption)
            print(f"  ✓ {sig['strategy']} {sig['ticker']} [{sig['grade']}] TG={tg_code} AI={ai_code} CHART={chart_path} PHOTO={photo_code}")
        else:
            print(f"  ✓ {sig['strategy']} {sig['ticker']} [{sig['grade']}] TG={tg_code} AI={ai_code}")

    # === Step 4.5: Log gated-out signals to signals.jsonl (for LLM data only) ===
    if gated_out:
        with SIGNALS_FILE.open("a") as f:
            for g in gated_out:
                # Mark these so dashboard/strategy_ranking can distinguish "actually fired"
                # from "LLM-graded but gate-skipped" without polluting open-position metrics.
                g["gate_blocked"] = True
                g["position_opened"] = False
                f.write(json.dumps(g, default=str) + "\n")
        print(f"[live_scan] ✓ {len(gated_out)} gated signals logged to signals.jsonl (gate_blocked=True)")

    # Step 5: Heartbeat
    heartbeat = {
        "timestamp": ts_now,
        "n_detections": len(detections),
        "n_signals": n_signals,
        "n_errors": n_errors,
        "n_fired": len(fired),
        "n_gated": len(gated_out) if 'gated_out' in locals() else 0,
        "n_pre_gate": len(pre_gate) if 'pre_gate' in locals() else 0,
        "circuit_breaker": _read_circuit_breaker(),
        "elapsed_sec": round(time.time() - t_start, 1),
        "tickers": list(data_map.keys()),
    }
    HEARTBEAT_FILE.write_text(json.dumps(heartbeat, indent=2, default=str))
    print(f"[live_scan] ✓ Heartbeat saved ({heartbeat['elapsed_sec']}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
