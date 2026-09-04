"""Signal chart with candlesticks + entry/SL/T1-T5 lines.

Style: 
- Green/Red candles (classic)
- NY time on x-axis (EDT/EST)
- SETUP indicator with entry plan rationale
- Volume bars
- Entry arrow + label
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
import pytz

plt.rcParams['font.sans-serif'] = ['Noto Sans CJK SC', 'Noto Sans CJK TC', 'DejaVu Sans', 'Arial Unicode MS', 'SimHei']
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['axes.unicode_minus'] = False

# Import FontProperties for explicit use
from matplotlib.font_manager import FontProperties
CJK_FONT = FontProperties(family='Noto Sans CJK SC')

REPO = Path("/workspace/YW-concept-ki7409")
SIGNALS_FILE = REPO / "automation/reports/live_scan/signals.jsonl"
CHARTS_DIR = REPO / "automation/reports/signal_charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

# Timezones
NY_TZ = pytz.timezone('America/New_York')  # Auto-handles EDT/EST
HKT_TZ = pytz.timezone('Asia/Hong_Kong')


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
    """Generate candlestick chart for a single signal with NY time + setup indicator."""
    import mplfinance as mpf
    from matplotlib.dates import DateFormatter, HourLocator
    
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
    reason = signal.get("reason", "")
    signal_id = signal.get("position_id", signal.get("signal_id", "?"))
    
    if not ticker or entry <= 0:
        return False
    
    df = fetch_ohlcv(ticker, days=2, interval="5m")
    if df is None or df.empty:
        return False
    
    # Convert index to NY time
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize('UTC')
    df.index = df.index.tz_convert(NY_TZ)
    
    is_long = direction in ("long", "bullish", "up")
    dir_label = "LONG" if is_long else "SHORT"
    arrow = "↑" if is_long else "↓"
    entry_color = '#10b981' if is_long else '#ef4444'
    
    mc = mpf.make_marketcolors(
        up='#10b981', down='#ef4444',
        edge='inherit', wick='inherit', volume='in'
    )
    style = mpf.make_mpf_style(
        marketcolors=mc, gridstyle='--', gridcolor='#374151',
        facecolor='#0f172a', edgecolor='#1e293b', figcolor='#0f172a',
        rc={'axes.labelcolor': '#d1d5db', 'xtick.color': '#d1d5db', 'ytick.color': '#d1d5db'}
    )
    
    title = f"{strategy} [{grade}] {ticker} {dir_label} {arrow} | Conf {conf} | ATR {atr:.2f}"
    
    fig, axes = mpf.plot(
        df, type='candle', style=style,
        title=title, ylabel='Price', ylabel_lower='Volume',
        volume=True, figsize=(16, 9), returnfig=True, tight_layout=True,
    )
    # Apply CJK font to all text elements in the figure
    for text in fig.findobj(plt.Text):
        if any(ord(c) > 127 for c in text.get_text()):
            text.set_fontproperties(CJK_FONT)
    
    ax = axes[0]
    ax.set_facecolor('#0f172a')
    if len(axes) > 2:
        axes[2].set_facecolor('#0f172a')
    
    # Format x-axis as NY time
    from matplotlib.dates import AutoDateLocator; ax.xaxis.set_major_locator(AutoDateLocator(maxticks=8))
    ax.xaxis.set_major_formatter(DateFormatter(r'%H:%M\n%a\n%m/%d', tz=NY_TZ))
    if len(axes) > 2:
        axes[2].xaxis.set_major_formatter(DateFormatter(r'%H:%M\n%a\n%m/%d', tz=NY_TZ))
    
    # Horizontal lines for all levels
    ax.axhline(y=entry, color=entry_color, linestyle='-', linewidth=2.0, alpha=0.9, label=f'Entry ${entry:.2f}')
    ax.axhline(y=sl, color='#ef4444', linestyle='--', linewidth=1.5, alpha=0.8, label=f'SL ${sl:.2f}')
    ax.axhline(y=t1, color='#fbbf24', linestyle=':', linewidth=1.0, alpha=0.7, label=f'T1 ${t1:.2f}')
    ax.axhline(y=t2, color='#10b981', linestyle='-', linewidth=2.5, alpha=1.0, label=f'T2 CLOSE ${t2:.2f}')
    ax.axhline(y=t3, color='#3b82f6', linestyle=':', linewidth=1.0, alpha=0.6, label=f'T3 ${t3:.2f}')
    ax.axhline(y=t4, color='#3b82f6', linestyle=':', linewidth=1.0, alpha=0.6, label=f'T4 ${t4:.2f}')
    ax.axhline(y=t5, color='#3b82f6', linestyle=':', linewidth=1.0, alpha=0.6, label=f'T5 ${t5:.2f}')
    
    # Add strategy-specific moving averages (4 visibility fixes applied)
    ema_period = 20
    sma_period = 50
    if len(df) >= sma_period:
        sma50 = df['Close'].rolling(sma_period).mean()
        # 1. fill_between: shade between close and SMA50
        ax.fill_between(df.index, df['Close'], sma50.values,
                         where=(df['Close'] >= sma50.values), 
                         color='#3b82f6', alpha=0.18, interpolate=True, zorder=2)
        ax.fill_between(df.index, df['Close'], sma50.values,
                         where=(df['Close'] < sma50.values),
                         color='#ef4444', alpha=0.12, interpolate=True, zorder=2)
        # 3+4. Thick dashed SMA50 line (zorder=10 puts above candles)
        ax.plot(df.index, sma50.values, color='#3b82f6', linewidth=4.5, 
                alpha=1.0, linestyle='--', zorder=10, label=f'SMA50 (trend)')
    if len(df) >= ema_period:
        ema20 = df['Close'].ewm(span=ema_period, adjust=False).mean()
        # 1. fill_between: shade between close and EMA20
        ax.fill_between(df.index, df['Close'], ema20.values,
                         where=(df['Close'] >= ema20.values),
                         color='#fbbf24', alpha=0.12, interpolate=True, zorder=3)
        ax.fill_between(df.index, df['Close'], ema20.values,
                         where=(df['Close'] < ema20.values),
                         color='#fbbf24', alpha=0.06, interpolate=True, zorder=3)
        # 3+4. Thick dotted EMA20 line (zorder=11)
        ax.plot(df.index, ema20.values, color='#fbbf24', linewidth=4.0, 
                alpha=1.0, linestyle=':', zorder=11, label=f'EMA20 (pullback target)')
    
    # Add current MA values annotation (right side)
    if len(df) >= sma_period:
        last_sma = sma50.iloc[-1]
        last_ema = ema20.iloc[-1]
        last_close = df['Close'].iloc[-1]
        ma_text = f"\nMAs @ {df.index[-1].strftime('%H:%M')}\nClose: ${last_close:.2f}\nEMA20: ${last_ema:.2f}\nSMA50: ${last_sma:.2f}"
        ax.text(0.98, 0.15, ma_text, transform=ax.transAxes,
                fontsize=9, color='#fbbf24', weight='normal',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='#1e293b', edgecolor='#fbbf24', alpha=0.95),
                verticalalignment='top', horizontalalignment='right')
    
    # Entry arrow
    try:
        if 'ts' in signal:
            ts_str = signal['ts']
            signal_ts = pd.Timestamp(ts_str)
            if signal_ts.tzinfo is None:
                signal_ts = signal_ts.tz_localize('UTC')
            signal_ts_ny = signal_ts.tz_convert(NY_TZ)
            idx = df.index.get_indexer([signal_ts_ny], method='nearest')[0]
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
                # Format NY time for label
                ny_time_str = signal_ts_ny.strftime('%H:%M %Z')
    except Exception:
        ny_time_str = ''
    
    # SETUP indicator box (top-left, detailed entry plan)
    risk = abs(entry - sl)
    r_t1 = abs(t1 - entry) / risk if risk > 0 else 0
    r_t2 = abs(t2 - entry) / risk if risk > 0 else 0
    r_t3 = abs(t3 - entry) / risk if risk > 0 else 0
    setup_text = f"\nSETUP\n{dir_label} {arrow} on {ticker}\nGrade [{grade}] | Conf {conf}\nReason: {reason[:200]}..."
    ax.text(0.02, 0.98, setup_text, transform=ax.transAxes,
            fontsize=8, color='#fbbf24', weight='normal',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#1e293b', edgecolor='#fbbf24', alpha=0.95),
            verticalalignment='top', fontproperties=CJK_FONT)
    
    # Entry plan box (bottom-left)
    plan_text = (f"ENTRY PLAN\n"
                 f"Entry: ${entry:.2f}\n"
                 f"SL: ${sl:.2f} | Risk: ${risk:.2f}\n"
                 f"T1: ${t1:.2f} ({r_t1:.1f}R)\n"
                 f"T2 CLOSE: ${t2:.2f} ({r_t2:.1f}R)  ← exit target\n"
                 f"T3: ${t3:.2f} ({r_t3:.1f}R) runner")
    ax.text(0.02, 0.02, plan_text, transform=ax.transAxes,
            fontsize=9, color='#10b981', weight='bold',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#000000', edgecolor='#10b981', alpha=0.95),
            verticalalignment='bottom', fontproperties=CJK_FONT)
    
    # Legend (TOP-LEFT, below SETUP box, compact 5 cols)
    # SETUP box at (0.02, 0.98), legend at (0.02, 0.78)
    leg = ax.legend(loc='upper left', bbox_to_anchor=(0.02, 0.78),
                    fontsize=6, framealpha=0.85, ncol=5,
                    handlelength=1.0, columnspacing=0.7, labelspacing=0.3)
    leg.get_frame().set_facecolor('#1e293b')
    leg.get_frame().set_edgecolor('#374151')
    for text in leg.get_texts():
        text.set_color('#d1d5db')
    
    # NY time zone label at top
    ny_now = datetime.now(NY_TZ)
    hkt_now = datetime.now(HKT_TZ)
    tz_info = f"NY: {ny_now.strftime('%Y-%m-%d %H:%M %Z')} | HKT: {hkt_now.strftime('%H:%M %Z')}"
    ax.text(0.98, 0.98, tz_info, transform=ax.transAxes,
            fontsize=8, color='#94a3b8',
            ha='right', va='top', fontproperties=CJK_FONT)
    
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
    
    HKT = HKT_TZ
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
