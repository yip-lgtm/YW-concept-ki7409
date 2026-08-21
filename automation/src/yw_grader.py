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
    },
    "3-Pushes": {
        "name": "3 Pushes",
        "timeframe": "5min/15min",
        "desc": "三推向某方向 + 最後一推收窄 + 有等高/等低可突破",
        "doc": "docs/03-Three-Pushes.md",
        "data_granularity": "15m",
        "data_period": "10d",
    },
    "Two-Yang-One-Yin": {
        "name": "兩陽夾一陰",
        "timeframe": "15min",
        "desc": "盤整尾段 + 兩根陽線實體夾住中間陰線實體 (只看 body)",
        "doc": "docs/04-Two-Yang-One-Yin.md",
        "data_granularity": "15m",
        "data_period": "10d",
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
    return f"""你是 YW Concept 交易員，請評估以下 {summary['ticker']} ({strat['timeframe']}) 數據，
判斷今日是否有「{strat['name']}」Setup。

## YW {strat['name']} 官方定義
{strat['desc']}

## 當前數據
- Ticker: {summary['ticker']}
- Last: {summary['last']:.2f} ({summary['pct']:+.2f}%)
- 20-period MA: {ma20_str}
- Price vs MA20: {pma_str}
- Avg wick % (5 bars): {summary.get('avg_wick_pct', 0):.1f}%
- Range % (5 bars): {summary.get('range_pct', 0):.2f}%

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
                reason = "LLM incomplete response (only thinking)"
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

# Per-strategy priority weight
STRATEGY_WEIGHT = {
    "H-Pattern": 1.2,    # 較精確觸發
    "3-Pushes": 1.0,     # 中頻結構
    "Two-Yang-One-Yin": 0.8,  # confluence 之一
}

GRADE_WEIGHT = {"A": 100, "B": 60, "C": 20, "?": 0}


def rank_candidates(grades: list[dict]) -> list[dict]:
    """Compute priority score for each grade + sort by priority desc.

    priority_score = (grade_weight + confidence) * strategy_weight
    """
    out = []
    for g in grades:
        gw = GRADE_WEIGHT.get(g["grade"], 0)
        conf = g.get("confidence", 0)
        sw = STRATEGY_WEIGHT.get(g["strategy"], 1.0)
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
