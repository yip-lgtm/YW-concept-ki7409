"""MT5-style signal chart with candlesticks + entry/SL/T1-T5 lines.

Visual style:
- Dark background (like MT5 night theme)
- Orange/red candlesticks
- Yellow dashed lines for SL/TP (visible)
- Colored line for entry with annotation
- Right-side price labels in colored boxes
- Position info annotation
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

# Set CJK font
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial Unicode MS', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

REPO = Path("/workspace/YW-concept-ki7409")
SIGNALS_FILE = REPO / "automation/reports/live_scan/signals.jsonl"
CHARTS_DIR = REPO / "automation/reports/signal_charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)


def fetch_ohlcv(ticker: str, days: int = 1, interval: str = "5m"):
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
    """MT5-style candlestick chart for a single signal."""
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
    dir_label = "BUY" if is_long else "SELL"
    arrow = "↑" if is_long else "↓"
    
    # MT5-style market colors: orange/gray candles on dark background
    mc = mpf.make_marketcolors(
        up='#f59e0b',      # amber/orange for up
        down='#9ca3af',    # gray for down
        edge='inherit',
        wick='inherit',
        volume='in'
    )
    style = mpf.make_mpf_style(
        marketcolors=mc,
        gridstyle=':',
        gridcolor='#374151',
        facecolor='#000000',
        edgecolor='#1f2937',
        figcolor='#000000',
        rc={'axes.labelcolor': '#d1d5db', 'xtick.color': '#d1d5db', 'ytick.color': '#d1d5db'}
    )
    
    # Title - MT5-style header
    title = f"{strategy}  {dir_label}  {arrow}  {ticker}  |  Grade [{grade}]  Conf {conf}"
    
    # Plot candlesticks
    fig, axes = mpf.plot(
        df, type='candle', style=style,
        title=title,
        ylabel='Price',
        ylabel_lower='Volume',
        volume=True,
        figsize=(16, 10),
        returnfig=True,
        tight_layout=False,
    )
    
    ax = axes[0]
    ax_vol = axes[2] if len(axes) > 2 else None
    
    # Set dark background
    ax.set_facecolor('#000000')
    if ax_vol:
        ax_vol.set_facecolor('#000000')
    
    # Add MA line (calculate from close)
    ma_period = 20
    if len(df) >= ma_period:
        ma = df['Close'].rolling(ma_period).mean()
        ax.plot(df.index, ma.values, color='#10b981', linewidth=1.5, alpha=0.8, label=f'MA{ma_period}')
    
    # MT5-style line colors
    sl_color = '#fbbf24'  # yellow for SL
    tp_color = '#fbbf24'  # yellow for TP
    entry_color = '#ef4444' if is_long else '#ef4444'  # red for entry
    
    # Draw horizontal lines (MT5 dashed style)
    line_kwargs = {'linestyle': '--', 'linewidth': 1.0, 'alpha': 0.9, 'dashes': (6, 4)}
    
    ax.axhline(y=entry, color='#ef4444', label=f'Entry ${entry:.2f}', **line_kwargs)
    ax.axhline(y=sl, color=sl_color, label=f'SL ${sl:.2f}', **line_kwargs)
    ax.axhline(y=t1, color='#a78bfa', label=f'T1 ${t1:.2f}', linestyle=':', linewidth=0.8, alpha=0.7)
    ax.axhline(y=t2, color='#10b981', label=f'T2 CLOSE ${t2:.2f}', **line_kwargs)  # green dashed for T2
    ax.axhline(y=t3, color='#3b82f6', label=f'T3 ${t3:.2f}', linestyle=':', linewidth=0.8, alpha=0.7)
    ax.axhline(y=t4, color='#3b82f6', label=f'T4 ${t4:.2f}', linestyle=':', linewidth=0.8, alpha=0.7)
    ax.axhline(y=t5, color='#3b82f6', label=f'T5 ${t5:.2f}', linestyle=':', linewidth=0.8, alpha=0.7)
    
    # Add price labels on right side (MT5-style)
    ymin, ymax = ax.get_ylim()
    xlim = ax.get_xlim()
    x_label = xlim[1] + (xlim[1] - xlim[0]) * 0.005  # slightly past right edge
    
    def add_price_label(y, text, color):
        ax.annotate(text, xy=(x_label, y), xytext=(5, 0),
                   textcoords='offset points', ha='left', va='center',
                   fontsize=10, color='#000000', weight='bold',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor=color, edgecolor=color, alpha=0.95))
    
    add_price_label(entry, f'  ${entry:.2f}', '#ef4444')
    add_price_label(sl, f'  ${sl:.2f}', '#fbbf24')
    add_price_label(t1, f'  ${t1:.2f}', '#a78bfa')
    add_price_label(t2, f'  ${t2:.2f}', '#10b981')
    
    # Add entry arrow annotation
    try:
        if 'ts' in signal:
            signal_ts = pd.Timestamp(signal['ts']).tz_localize(None) if signal['ts'] else None
            if signal_ts:
                idx = df.index.get_indexer([signal_ts], method='nearest')[0]
                if idx >= 0:
                    x = df.index[idx]
                    direction_text = f'{dir_label} {signal.get("size", 0.15)}, ATR {atr:.2f}'
                    ax.annotate(
                        direction_text, xy=(x, entry),
                        xytext=(0, 40 if is_long else -40),
                        textcoords='offset points',
                        ha='center', fontsize=10,
                        color='#ffffff', weight='bold',
                        bbox=dict(boxstyle='round,pad=0.4',
                                 facecolor='#ef4444' if not is_long else '#10b981',
                                 edgecolor='white', alpha=0.95),
                        arrowprops=dict(arrowstyle='->', color='white', lw=1.5)
                    )
    except Exception as e:
        pass
    
    # Add strategy info at bottom right
    info_text = f'Risk: ${abs(entry-sl):.2f} | T1: {abs(t1-entry):.2f} ({abs(t1-entry)/abs(entry-sl):.1f}R) | T2: {abs(t2-entry):.2f} ({abs(t2-entry)/abs(entry-sl):.1f}R)'
    ax.text(0.02, 0.02, info_text, transform=ax.transAxes,
            fontsize=9, color='#fbbf24', weight='bold',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#1f2937', edgecolor='#fbbf24', alpha=0.9),
            verticalalignment='bottom')
    
    # Legend (top left, MT5-style)
    leg = ax.legend(loc='lower left', fontsize=8, facecolor='#1f2937',
                    edgecolor='#374151', labelcolor='#d1d5db', framealpha=0.8, ncol=2)
    leg.get_frame().set_linewidth(0.5)
    
    # Tick colors
    ax.tick_params(colors='#d1d5db')
    for spine in ax.spines.values():
        spine.set_color('#374151')
    
    # Expand xlim to make room for price labels
    ax.set_xlim(xlim[0], xlim[1] + (xlim[1] - xlim[0]) * 0.08)
    
    # Save
    fig.savefig(output_path, dpi=100, bbox_inches='tight', facecolor='#000000')
    plt.close(fig)
    return True


def main():
    """Generate MT5-style charts for recent signals."""
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
    print(f"Generating MT5-style charts for {len(recent)} recent signals...")
    
    success = 0
    for s in recent:
        signal_id = s.get('position_id', s.get('signal_id', 'unknown'))
        safe = signal_id.replace('|', '_').replace(':', '-').replace('/', '_')[:80]
        out = CHARTS_DIR / f"{safe}.png"
        try:
            if make_chart(s, out):
                success += 1
                print(f"  ✓ {signal_id[:50]}")
            else:
                print(f"  ✗ {signal_id[:50]} (no data)")
        except Exception as e:
            print(f"  ✗ {signal_id[:50]} ({e})")
    
    print(f"\nDone: {success}/{len(recent)} charts saved to {CHARTS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
