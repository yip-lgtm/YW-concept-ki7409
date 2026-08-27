"""B1 战法 3合1 — combined multi-asset detector.

Scans MNQ, MGC, BTC together. Picks strongest signal per scan.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import yfinance as yf

sys.path.insert(0, '/workspace/YW-concept-ki7409/automation/src')
from yw_indicators_b1 import detect_b1


B1_3IN1_TICKERS = ['MNQ=F', 'MGC=F', 'BTC-USD']


def fetch_5m(ticker: str, days: int = 5) -> pd.DataFrame:
    df = yf.download(ticker, period=f'{days}d', interval='5m', progress=False, auto_adjust=True)
    if hasattr(df.columns, 'levels'):
        df.columns = df.columns.get_level_values(0)
    if df.empty:
        return df
    return df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()


def detect_b1_3in1(j_threshold: float = -5, use_volume_filter: bool = False,
                    days: int = 5) -> dict:
    """3合1 B1 detector: scan all 3 tickers, return strongest signal.

    Returns dict with:
      - present: bool (any signal fired)
      - count: int (how many tickers signaled)
      - best: dict (strongest signal details)
      - all_signals: list (all ticker signals)
    """
    signals = []
    for ticker in B1_3IN1_TICKERS:
        df = fetch_5m(ticker, days=days)
        if df.empty or len(df) < 30:
            continue
        sig = detect_b1(df, j_threshold=j_threshold, use_volume_filter=use_volume_filter)
        if sig.get('present'):
            sig['ticker'] = ticker
            signals.append(sig)

    if not signals:
        return {'present': False, 'count': 0, 'best': None, 'all_signals': []}

    # Pick strongest (highest strength, lowest J=most oversold)
    best = max(signals, key=lambda r: (r.get('strength', 0), -r.get('j', 0)))

    return {
        'present': True,
        'count': len(signals),
        'best': best,
        'all_signals': signals,
    }
