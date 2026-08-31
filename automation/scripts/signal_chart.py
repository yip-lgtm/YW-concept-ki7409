"""Signal chart with candlesticks + entry/SL/T1-T5 lines.

Clean, readable style:
- Green/Red candles (classic up/down)
- Full-width chart
- Legend at top-left (small)
- Lines for entry/SL/T1-T5 with right-side price labels
- Volume bars at bottom
"""
from __future__ import annotations
import os
import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial Unicode MS', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

REPO = Path("/workspace/YW-concept-ki7409")
SIGNALS_FILE = REPO / "automation/reports/live_scan/signals.jsonl"
CHARTS_DIR = REPO / "automation/reports/signal_charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)


def fetch_ohlcv(ticker: str, days: int = 2, interval: str = "5m"):
    """Fetch OHLCV from yfinance."""
    import yfinance as yf
    try:
        df = yf.download(ticker, period=f"{days}d", interval=interval, progress=False, auto_adjust=True, timeout=15)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception as e:
        print(f"yfinance error: {e}")
        return None


def make_chart(signal: dict, output_path: Path) -> bool:
    """Generate candlestick chart for a single signal."""
    import mplfinance as mpf
    
    ticker = signal.get("ticker", "")
    strategy = signal.get("strategy", "?")
    grade = signal.get("grade", "?")
    direction = signal.get("direction", "")
    entry = float(signal.get("last_close", 0))
    atr = float(signal.get("atr", 0))
    sl = float(signal.get("sl", 0))
    t1 = float(signal.get("t1", 0))
    t2 = float(signal.get("t2", 0))
    t3 = float(signal.get("t3", 0))
    t4 = float(signal.get("t4", 0))
    t5 = float(signal.get("t5", 0))
    conf = signal.get("confidence", 0)
    signal_id = signal.get("position_id", signal.get("signal_id", "?"))
    
    if not ticker or entry <= 0:
        return False
    
    df = fetch_ohlcv(ticker, days=2, interval="5m")
    if df is None or df.empty:
        return False
    
    is_long = direction in ("long", "bullish", "up")
    dir_label = "LONG" if is_long else "SHORT"
    arrow = "↑" if is_long else "↓"
    entry_color = '#10b981' if is_long else '#ef4444'  # green for long, red for short
    
    # Classic green/red market colors
    mc = mpf.make_marketcolors(
        up='#10b981',      # green
        down='#ef4444',    # red
        edge='inherit',
        wick='inherit',
        volume='in'
    )
    style = mpf.make_mpf_style(
        marketcolors=mc,
        gridstyle='--',
        gridcolor='#374151',
        facecolor='#0f172a',
        edgecolor='#1e293b',
        figcolor='#0f172a',
        rc={'axes.labelcolor': '#d1d5db', 'xtick.color': '#d1d5db', 'ytick.color': '#d1d5db'}
    )
    
    title = f"{strategy} [{grade}] {ticker} {dir_label} {arrow} | Conf {conf} | ATR {atr:.2f}"
    
    fig, axes = mpf.plot(
        df, type='candle', style=style,
        title=title, ylabel='Price', ylabel_lower='Volume',
        volume=True, figsize=(16, 9), returnfig=True,
        tight_layout=True,
    )
    
    ax = axes[0]
    ax.set_facecolor('#0f172a')
    if len(axes) > 2:
        axes[2].set_facecolor('#0f172a')
    
    # Draw horizontal lines for all levels
    ax.axhline(y=entry, color=entry_color, linestyle='-', linewidth=2.0, alpha=0.9, label=f'Entry ${entry:.2f}')
    ax.axhline(y=sl, color='#ef4444', linestyle='--', linewidth=1.5, alpha=0.8, label=f'SL ${sl:.2f}')
    ax.axhline(y=t1, color='#fbbf24', linestyle=':', linewidth=1.0, alpha=0.7, label=f'T1 ${t1:.2f}')
    ax.axhline(y=t2, color='#10b981', linestyle='-', linewidth=2.5, alpha=1.0, label=f'T2 CLOSE ${t2:.2f}')
    ax.axhline(y=t3, color='#3b82f6', linestyle=':', linewidth=1.0, alpha=0.6, label=f'T3 ${t3:.2f}')
    ax.axhline(y=t4, color='#3b82f6', linestyle=':', linewidth=1.0, alpha=0.6, label=f'T4 ${t4:.2f}')
    ax.axhline(y=t5, color='#3b82f6', linestyle=':', linewidth=1.0, alpha=0.6, label=f'T5 ${t5:.2f}')
    
    # Add entry arrow annotation
    try:
        if 'ts' in signal:
            signal_ts = pd.Timestamp(signal['ts']).tz_localize(None) if signal['ts'] else None
            if signal_ts:
                idx = df.index.get_indexer([signal_ts], method='nearest')[0]
                if idx >= 0:
                    x = df.index[idx]
                    ax.annotate(
                        f'ENTRY\n${entry:.2f}', xy=(x, entry),
                        xytext=(0, 35 if is_long else -35),
                        textcoords='offset points',
                        ha='center', fontsize=10, color='white', weight='bold',
                        bbox=dict(boxstyle='round,pad=0.4', facecolor=entry_color, alpha=0.95),
                        arrowprops=dict(arrowstyle='->', color=entry_color, lw=2)
                    )
    except Exception:
        pass
    
    # Legend (top-left, small)
    leg = ax.legend(loc='upper left', fontsize=8, framealpha=0.9, ncol=2)
    leg.get_frame().set_facecolor('#1e293b')
    leg.get_frame().set_edgecolor('#374151')
    for text in leg.get_texts():
        text.set_color('#d1d5db')
    
    ax.tick_params(colors='#d1d5db')
    for spine in ax.spines.values():
        spine.set_color('#374151')
    
    fig.savefig(output_path, dpi=100, bbox_inches='tight', facecolor='#0f172a')
    plt.close(fig)
    return True


def main():
    if not SIGNALS_FILE.exists():
        print(f"Signals file not found: {SIGNALS_FILE}")
        return 1
    
    signals = []
    with SIGNALS_FILE.open() as f:
        for line in f:
            try:
                signals.append(json.loads(line))
            except: pass
    
    if not signals:
        print("No signals to chart")
        return 0
    
    HKT = timezone(timedelta(hours=8))
    now = datetime.now(HKT)
    cutoff = now - timedelta(hours=24)
    
    recent = []
    for s in signals:
        ts_str = s.get('ts', '')
        if not ts_str: continue
        try:
            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00')).astimezone(HKT)
            if ts > cutoff:
                recent.append(s)
        except: pass
    
    recent = recent[-20:]
    print(f"Generating charts for {len(recent)} recent signals...")
    
    success = 0
    for s in recent:
        signal_id = s.get('position_id', s.get('signal_id', 'unknown'))
        safe = signal_id.replace('|', '_').replace(':', '-').replace('/', '_')[:80]
        out = CHARTS_DIR / f"{safe}.png"
        try:
            if make_chart(s, out):
                success += 1
        except Exception as e:
            print(f"  ✗ {signal_id[:50]} ({e})")
    
    print(f"\nDone: {success}/{len(recent)} charts saved to {CHARTS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
