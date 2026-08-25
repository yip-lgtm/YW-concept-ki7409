"""LLM grader for YW Concept strategies.

Detects + grades 3 core YW strategies on MNQ (Micro Nasdaq) intraday:
  1. H-Pattern (3min/5min)
  2. 3 Pushes (5min/15min)
  3. 兩陽夾一陰 (15min) — "Two Yang One Yin"

Each strategy gets:
  - Strategy-specific prompt
  - LLM grade (A/B/C) + reason
  - Confidence score (0-100)
  - Actionable: A or B only

Composite priority ranking across all 3 strategies.
"""
from __future__ import annotations
import os
import json
import time
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Load env
from env_loader import load_env
load_env()

API_URL = os.environ.get("MINIMAX_API_URL", "https://api.minimax.io/v1")
API_KEY = os.environ.get("MINIMAX_API_KEY", "") or os.environ.get("MINIMAX_CN_API_KEY", "")
MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M3")

# YW strategies
STRATEGIES = {
    "H-Pattern": {
        "name": "H-Pattern",
        "timeframe": "3min/5min",
        "desc": "長直 K 線 + top wick 顯示賣壓 + <50% pullback + 穿底完成形態",
        "doc": "docs/02-H-Pattern.md",
        "data_granularity": "5m",
        "data_period": "5d",
        "weight": 1.2,
    },
    "3-Pushes": {
        "name": "3 Pushes",
        "timeframe": "5min/15min",
        "desc": "三推向某方向 + 最後一推收窄 + 有等高/等低可突破",
        "doc": "docs/03-Three-Pushes.md",
        "data_granularity": "15m",
        "data_period": "10d",
        "weight": 1.0,
    },
    "Two-Yang-One-Yin": {
        "name": "兩陽夾一陰",
        "timeframe": "5min/15min",
        "desc": "盤整尾段 + 兩根陽線實體夾住中間陰線實體 (只看 body, LLM-iter v2 (2026-08-25 20:22, conf 72%): 5min/15min, weight 0.3, R-multiples wider)",
        "doc": "docs/04-Two-Yang-One-Yin.md",
        "data_granularity": "5m",
        "data_period": "5d",
        "weight": 0.5,  # LLM-iter 2026-08-25: 0.8→0.5 (PF 0.67 live)
        "llm_optimized": True,
        "llm_iteration_date": "2026-08-25",
        "r_multiples": [1.5, 2.5, 4.0, 6.0, 8.0],  # LLM-iter v2: wider R-multiples (higher targets)
        "trend_filter": "EMA20_slope",
        "adx_filter": 20,
        "volume_filter": "1.2x_SMA20",
        "cooldown_bars": 10,
        "atr_stop_mult": 1.0,  # 自適應 SL
    },
    "RSI-Divergence": {
        "name": "RSI Divergence",
        "timeframe": "15min",
        "desc": "價格 Lower Low + RSI Higher Low (看漲背離) / 價格 Higher High + RSI Lower High (看跌背離)",
        "doc": "docs/08-RSI-Divergence.md",
        "data_granularity": "15m",
        "data_period": "5d",
        "weight": 0.7,  # LLM-suggested: drop from 1.1 (PF 0.92)
        "llm_optimized": True,
        "llm_iteration_date": "2026-08-25",
        "r_multiples": [1.5, 2.0, 3.0, 4.0, 5.0],  # asymmetric R targets
        "trend_filter": "EMA50",  # trade only with trend
        "volume_required": True,  # confirm with volume
    },
    "50-20-Pullback": {
        "name": "50/20 Pullback",
        "timeframe": "5min/15min/60min",
        "desc": "20 EMA / 50 SMA 黃金交叉 + 價格回踩 EMA20 + 順勢上車 (1-1.5 RR, SL $100)",
        "doc": "docs/11-50-20.md",
        "data_granularity": "5m",
        "data_period": "5d",
        "weight": 1.0,
    },
    "Stair-Pattern": {
        "name": "Stair Pattern",
        "timeframe": "5min/15min/1hr",
        "desc": "大陰啟動 (收下半部 + 上影細) → ≥2 根上影階梯 → 收破 20EMA 確認空方延續 (H Pattern 變體)",
        "doc": "docs/12-Stair-Pattern.md",
        "data_granularity": "5m",
        "data_period": "5d",
        "weight": 0.9,
    },
    "CRT": {
        "name": "CRT (Candle Range Theory)",
        "timeframe": "4H range / 5min execution",
        "desc": "4H K 做 CRT range，5min 掃 CRT-L/H 收返 + MSS 確認 → 跑向另一邊",
        "doc": "docs/14-CRT-Candle-Range-Theory.md",
        "data_granularity": "5m",
        "data_period": "5d",
        "weight": 1.1,
    },
    "Kell-Cycle": {
        "name": "Kell Cycle 5 Setups",
        "timeframe": "5min/15min/1H/Daily",
        "desc": "5 個 Oliver Kell Setups: Reversal Extension + Wedge Pop/Drop + EMA Crossback + Base n' Break + Exhaustion",
        "doc": "docs/15-Oliver-Kell-Cycle.md",
        "data_granularity": "5m",
        "data_period": "5d",
        "weight": 0.9,
    },
}

# Per-ticker watchlist (YW trader focus)
WATCHLIST = [
    ("MNQ=F", "Micro Nasdaq-100"),  # primary
    ("MES=F", "Micro S&P 500"),     # secondary
    ("M2K=F", "Micro Russell 2000"), # divergence reference
]


def fetch_data(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """Fetch OHLCV from yfinance."""
    d = yf.download(ticker, period=period, interval=interval,
                    progress=False, auto_adjust=True)
    if d.empty:
        return d
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    return d


def compute_summary(df: pd.DataFrame, ticker: str) -> dict:
    """Build compact summary for LLM prompt."""
    from yw_indicators import (
        compute_rsi, compute_ma,
        detect_rsi_divergence, detect_5020_pullback,
        detect_h_pattern, detect_3_pushes,
    )
    if df.empty or len(df) < 5:
        return {"ticker": ticker, "error": "insufficient data"}
    last = df.iloc[-1]
    prev = df.iloc[-2]
    chg = float(last["Close"] - prev["Close"])
    pct = float(chg / prev["Close"] * 100) if prev["Close"] else 0.0

    # 20-period MA
    ma20 = float(df["Close"].tail(20).mean()) if len(df) >= 20 else None

    # Last 5 candles (most recent action)
    recent = df.tail(8)[["Open", "High", "Low", "Close", "Volume"]].copy()
    recent.index = recent.index.strftime("%m-%d %H:%M")

    # Wick stats for H-Pattern detection
    last5 = df.tail(5)
    avg_wick_pct = ((last5["High"] - last5["Low"]) - abs(last5["Close"] - last5["Open"])) / (last5["High"] - last5["Low"] + 1e-9) * 100

    # Pre-computed technical indicators (for LLM context)
    rsi_series = compute_rsi(df["Close"])
    rsi_last = float(rsi_series.iloc[-1]) if not rsi_series.empty else None
    rsi_prev = float(rsi_series.iloc[-2]) if len(rsi_series) > 1 else None

    ema20 = compute_ma(df["Close"], 20, "ema")
    sma50 = compute_ma(df["Close"], 50, "sma")
    ema20_last = float(ema20.iloc[-1]) if not ema20.empty else None
    sma50_last = float(sma50.iloc[-1]) if not sma50.empty else None

    # Pre-detected signals
    rsi_div = detect_rsi_divergence(df)
    pb_5020 = detect_5020_pullback(df)
    h_pat = detect_h_pattern(df)
    pushes = detect_3_pushes(df)

    # Extended detectors (Stair, CRT, Kell)
    stair = {}
    kell = {}
    crt = {}
    try:
        from yw_indicators_extra import detect_stair_pattern, detect_kell_setups, detect_crt
        stair = detect_stair_pattern(df)
        kell = detect_kell_setups(df)
        # CRT needs 4h data
        if STRATEGIES.get(strategy_key, {}).get("needs_4h") or strategy_key == "CRT":
            import yfinance as yf
            df_4h_raw = yf.download(ticker, period="1mo", interval="1h", progress=False, auto_adjust=True)
            if isinstance(df_4h_raw.columns, __import__("pandas").MultiIndex):
                df_4h_raw.columns = df_4h_raw.columns.get_level_values(0)
            df_4h = df_4h_raw.resample("4h").agg({
                "Open": "first", "High": "max", "Low": "min",
                "Close": "last", "Volume": "sum"
            }).dropna()
            crt = detect_crt(df_4h, df)
    except Exception as e:
        stair = {"present": False, "err": str(e)[:60]}
        kell = {"present": False, "err": str(e)[:60]}
        crt = {"present": False, "err": str(e)[:60]}

    return {
        "ticker": ticker,
        "last": float(last["Close"]),
        "chg": chg,
        "pct": pct,
        "ma20": ma20,
        "above_ma20": last["Close"] > ma20 if ma20 else None,
        "recent_candles": recent.to_dict("index"),
        "avg_wick_pct": float(avg_wick_pct.mean()),
        "range_pct": float((last5["High"].max() - last5["Low"].min()) / last5["Close"].mean() * 100),
        "rsi_last": rsi_last,
        "rsi_prev": rsi_prev,
        "ema20_last": ema20_last,
        "sma50_last": sma50_last,
        "rsi_div": rsi_div,
        "pb_5020": pb_5020,
        "h_pat": h_pat,
        "pushes": pushes,
        "stair": stair,
        "kell": kell,
        "crt": crt,
    }


def build_strategy_prompt(strategy_key: str, summary: dict) -> str:
    """Build strategy-specific prompt for LLM."""
    strat = STRATEGIES[strategy_key]
    ma20_str = f"{summary['ma20']:.2f}" if summary.get('ma20') else 'N/A'
    pma = summary.get('above_ma20')
    if pma is True:
        pma_str = 'ABOVE'
    elif pma is False:
        pma_str = 'BELOW'
    else:
        pma_str = 'N/A'

    # RSI + EMA data (used by RSI-Divergence, 50-20-Pullback, H-Pattern, 3-Pushes)
    rsi = summary.get('rsi_last', 0) or 0
    rsi_prev = summary.get('rsi_prev', 0) or 0
    ema20_v = summary.get('ema20_last', 0) or 0
    sma50_v = summary.get('sma50_last', 0) or 0

    # Pre-detected signals
    rsi_div = summary.get('rsi_div', {})
    pb_5020 = summary.get('pb_5020', {})
    h_pat = summary.get('h_pat', {})
    pushes = summary.get('pushes', {})
    stair = summary.get('stair', {})
    kell = summary.get('kell', {})
    crt = summary.get('crt', {})

    return f"""你是 YW Concept 交易員，請評估以下 {summary['ticker']} ({strat['timeframe']}) 數據，
判斷今日是否有「{strat['name']}」Setup。

## YW {strat['name']} 官方定義
{strat['desc']}

## 當前數據
- Ticker: {summary['ticker']}
- Last: {summary['last']:.2f} ({summary['pct']:+.2f}%)
- 20-period MA: {ma20_str}
- Price vs MA20: {pma_str}
- EMA20: {ema20_v:.2f} | SMA50: {sma50_v:.2f}
- RSI(14): {rsi:.1f} (prev {rsi_prev:.1f})
- Avg wick % (5 bars): {summary.get('avg_wick_pct', 0):.1f}%
- Range % (5 bars): {summary.get('range_pct', 0):.2f}%

## 預先偵測信號 (indicators)
- H-Pattern detector: {h_pat}
- 3-Pushes detector: {pushes}
- RSI Divergence: {rsi_div}
- 50/20 Pullback: {pb_5020}
- Stair Pattern: {stair}
- Kell Cycle 5 Setups: {kell}
- CRT (4H range): {crt}

## 最近 8 根 K 線
{json.dumps(summary.get('recent_candles', {}), indent=2, default=str)[:1500]}

## 評估任務
1. 識別 {strat['name']} 形態是否存在（特徵匹配度）
2. 評估 confluence（20 EMA 方向、HTF bias、session timing）
3. 給出 grade:
   - A = 形態 + confluence 都齊，high-probability Setup
   - B = 形態 partially present，marginal
   - C = 冇形態或逆大方向，skip

## 輸出格式 (EXACTLY 兩行)
GRADE: A | CONFIDENCE: 85 | REASON: 一句話繁中講形態 + confluence
GRADE: B | CONFIDENCE: 60 | REASON: ...
GRADE: C | CONFIDENCE: 20 | REASON: ...

唔好 <think>。直接 output 結果。
"""


def grade_strategy(strategy_key: str, ticker: str) -> dict:
    """Grade one strategy on one ticker. Returns {strategy, ticker, grade, confidence, reason, summary}."""
    strat = STRATEGIES[strategy_key]

    try:
        df = fetch_data(ticker, strat["data_period"], strat["data_granularity"])
        summary = compute_summary(df, ticker)
    except Exception as e:
        return {
            "strategy": strategy_key,
            "ticker": ticker,
            "grade": "?",
            "confidence": 0,
            "reason": f"data error: {str(e)[:60]}",
            "summary": {"ticker": ticker, "error": str(e)[:80]},
        }

    if "error" in summary:
        return {
            "strategy": strategy_key,
            "ticker": ticker,
            "grade": "?",
            "confidence": 0,
            "reason": summary["error"],
            "summary": summary,
        }

    prompt = build_strategy_prompt(strategy_key, summary)

    try:
        r = requests.post(
            f"{API_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": "你是 YW Concept 機械化交易員。專注 NQ 日內價格行為。"},
                    {"role": "user", "content": prompt + "\n\n請勿使用 <think> 標籤。直接輸出結果。"},
                ],
                "temperature": 0.1,
                "max_tokens": 2500,
            },
            timeout=60,
        )
        if r.status_code != 200:
            return {
                "strategy": strategy_key,
                "ticker": ticker,
                "grade": "?",
                "confidence": 0,
                "reason": f"http {r.status_code}",
                "summary": summary,
            }
        content = r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return {
            "strategy": strategy_key,
            "ticker": ticker,
            "grade": "?",
            "confidence": 0,
            "reason": f"api error: {str(e)[:60]}",
            "summary": summary,
        }

    # Parse "GRADE: X | CONFIDENCE: N | REASON: ..."
    # First strip <think>...</think> blocks
    import re
    after_think = re.split(r"</think>", content, maxsplit=1)
    search_text = after_think[-1].strip() if len(after_think) > 1 else content.strip()
    # Remove leading dashes / bullets
    search_text = re.sub(r"^[-\s]+", "", search_text)

    m = re.search(
        r"GRADE:\s*([ABC])\s*\|\s*CONFIDENCE:\s*(\d+)\s*\|\s*REASON:\s*(.+?)(?:\n|$)",
        search_text, re.IGNORECASE
    )
    if m:
        grade = m.group(1).upper()
        confidence = int(m.group(2))
        reason = m.group(3).strip()[:120]
    else:
        # Loose match
        m2 = re.search(r"GRADE:\s*([ABC])", search_text, re.IGNORECASE)
        grade = m2.group(1).upper() if m2 else "?"
        mc = re.search(r"CONFIDENCE:\s*(\d+)", search_text, re.IGNORECASE)
        confidence = int(mc.group(1)) if mc else 0
        if grade != "?":
            reason = search_text[:120]
        else:
            # Incomplete response
            if "<think>" in content and len(search_text) < 10:
                # LLM only returned thinking — try one retry with stronger prompt
                try:
                    retry_r = requests.post(
                        "https://api.minimax.io/v1/chat/completions",
                        headers={"Authorization": f"Bearer {MINIMAX_API_KEY}"},
                        json={
                            "model": "MiniMax-M3",
                            "max_tokens": 1024,
                            "messages": [
                                {"role": "system", "content": "你是 YW Concept 機械化交易員。直接輸出 GRADE: X | CONFIDENCE: N | REASON: ... 一行結果。"},
                                {"role": "user", "content": prompt + "\n\n**重要**: 只輸出 GRADE/CONFIDENCE/REASON 一行，禁止使用 <think> 標籤，禁止解釋。"},
                            ],
                        },
                        timeout=45,
                    )
                    if retry_r.status_code == 200:
                        rcontent = retry_r.json()["choices"][0]["message"]["content"].strip()
                        rm = re.search(r"GRADE:\s*([ABC])\s*\|\s*CONFIDENCE:\s*(\d+)\s*\|\s*REASON:\s*(.+?)(?:\n|$)", rcontent, re.IGNORECASE)
                        if rm:
                            return {
                                "strategy": strategy_key,
                                "ticker": ticker,
                                "grade": rm.group(1).upper(),
                                "confidence": int(rm.group(2)),
                                "reason": rm.group(3).strip()[:120],
                                "summary": summary,
                            }
                except Exception:
                    pass
                reason = "LLM incomplete response (only thinking, retry failed)"
            else:
                reason = search_text[:120] if search_text else "no parse"

    return {
        "strategy": strategy_key,
        "ticker": ticker,
        "grade": grade,
        "confidence": confidence,
        "reason": reason,
        "summary": summary,
    }


# --- Ranking ---

# Per-strategy priority weight (from STRATEGIES dict)
def get_strategy_weight(strategy_key: str) -> float:
    return STRATEGIES.get(strategy_key, {}).get("weight", 1.0)

# Backward-compat: static mapping
STRATEGY_WEIGHT = {
    "H-Pattern": 1.2,
    "3-Pushes": 1.0,
    "Two-Yang-One-Yin": 0.3,  # LLM-iter v2 2026-08-25 20:22 (conf 72%)
    "RSI-Divergence": 0.7,  # LLM-optimized 2026-08-25
    "50-20-Pullback": 1.0,
    "Stair-Pattern": 0.9,
    "CRT": 1.1,
    "Kell-Cycle": 0.9,
}

GRADE_WEIGHT = {"A": 100, "B": 60, "C": 20, "?": 0}


def rank_candidates(grades: list[dict]) -> list[dict]:
    """Compute priority score for each grade + sort by priority desc.

    priority_score = (grade_weight + confidence) × strategy_weight
    """
    out = []
    for g in grades:
        gw = GRADE_WEIGHT.get(g["grade"], 0)
        conf = g.get("confidence", 0)
        # Prefer per-strategy weight from STRATEGIES dict
        sw = STRATEGIES.get(g["strategy"], {}).get("weight") or STRATEGY_WEIGHT.get(g["strategy"], 1.0)
        score = (gw + conf) * sw
        out.append({
            **g,
            "priority_score": round(score, 1),
            "actionable": g["grade"] in ("A", "B"),
        })
    out.sort(key=lambda x: x["priority_score"], reverse=True)
    return out


if __name__ == "__main__":
    import sys
    strategy = sys.argv[1] if len(sys.argv) > 1 else "H-Pattern"
    ticker = sys.argv[2] if len(sys.argv) > 2 else "MNQ=F"
    g = grade_strategy(strategy, ticker)
    print(json.dumps({k: v for k, v in g.items() if k != "summary"}, ensure_ascii=False, indent=2))
