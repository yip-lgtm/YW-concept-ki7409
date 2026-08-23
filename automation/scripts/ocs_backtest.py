#!/usr/bin/env python3
"""OCS BTC 5m — Backtest mode.

Walks historical 5m bars, runs OCS signal generation at each step,
simulates trades with the same R-multiple targets used in live trading.

Logic per bar:
  1. Compute 8 features from rolling window (last 160 bars)
  2. KNN vote (K=7, Lorentzian distance)
  3. If vote >= 4 AND conf >= 0.55 AND layer_score > 0 + not in_chop + close > KAMA:
       Open LONG
     If vote <= -4 + same conditions + close < KAMA:
       Open SHORT
  4. Track position: check SL / T1 / T2 / T3 / T4 / T5 each bar
  5. First hit closes position, log R-multiple
  6. Skip if position already open

Output:
  - trades.json (full list of closed trades)
  - stats (win rate, avg R, profit factor)
  - pnl_curve.png
  - summary.md

Usage:
  .venv/bin/python scripts/ocs_backtest.py --days 20
"""
from __future__ import annotations
import os
import sys
import json
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Polygon-preferred data source
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from data_source import fetch_bars
import yfinance as yf


def fetch_backtest_data(days=60, interval_min=5):
    """Backtest needs 60d of 5m. yfinance supports up to 60d for 5m.
    Polygon free tier only has 2-3d, so use yfinance for historical.
    """
    print(f"[backtest] Using yfinance for {days}d {interval_min}m historical data...")
    df = yf.download("BTC-USD", period=f"{min(days, 60)}d", interval=f"{interval_min}m",
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty:
        return df
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC")
    return df


# === OCS KNN (re-used from ocs_btc_5m.py) ===
def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """8 normalized features, same as live OCS."""
    out = pd.DataFrame(index=df.index)
    close, high, low, vol = df["Close"], df["High"], df["Low"], df["Volume"]

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.ewm(alpha=1/14, adjust=False).mean() / (loss.ewm(alpha=1/14, adjust=False).mean() + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    out["nRsi"] = (rsi - rsi.rolling(50, min_periods=10).min()) / \
                  (rsi.rolling(50, min_periods=10).max() - rsi.rolling(50, min_periods=10).min() + 1e-9)

    # Stoch K(14)
    stoch = 100 * (close - low.rolling(14).min()) / (high.rolling(14).max() - low.rolling(14).min() + 1e-9)
    out["nSto"] = stoch / 100.0

    # Supertrend offset
    hl2 = (high.rolling(2).max() + low.rolling(2).min()) / 2
    upper = hl2 + 3.0 * atr
    lower = hl2 - 3.0 * atr
    out["nSt"] = (close - lower) / (upper - lower + 1e-9) - 0.5

    # TRIX(15)
    ema1 = close.ewm(span=15, adjust=False).mean()
    ema2 = ema1.ewm(span=15, adjust=False).mean()
    ema3 = ema2.ewm(span=15, adjust=False).mean()
    trix = 100 * (ema3 - ema3.shift(1)) / (ema3.shift(1) + 1e-9)
    out["nTrix"] = (trix - trix.rolling(50, min_periods=10).min()) / \
                   (trix.rolling(50, min_periods=10).max() - trix.rolling(50, min_periods=10).min() + 1e-9)

    # Fisher(10)
    def _fisher(x):
        if len(x) < 2:
            return 0.0
        xmin, xmax = x.min(), x.max()
        if xmax - xmin < 1e-9:
            return 0.0
        n = np.clip((x - xmin) / (xmax - xmin) * 2 - 1, -0.999, 0.999)
        return 0.5 * np.log((1 + n[-1]) / (1 - n[-1]))
    out["nFish"] = close.rolling(10).apply(_fisher, raw=True) / 5 + 0.5
    out["nFish"] = out["nFish"].clip(0, 1)

    # LMS slope proxy
    ema20 = close.ewm(span=20, adjust=False).mean()
    out["nLms"] = ((ema20 - ema20.shift(5)) / (atr + 1e-9) * 100).clip(-3, 3) / 6 + 0.5

    # Vol Z-score
    vol_sma = vol.rolling(20).mean()
    vol_std = vol.rolling(20).std()
    out["nVol"] = ((vol - vol_sma) / (vol_std + 1e-9)).clip(-3, 3) / 6 + 0.5

    # Close vs MA50
    ema50 = close.ewm(span=50, adjust=False).mean()
    out["nCvd"] = ((close - ema50) / (atr * 2 + 1e-9)).clip(-1, 1) * 0.5 + 0.5

    return out


def lorentzian_distance(a, b):
    return float(np.sum(np.log1p(np.abs(a - b))))


def label_future(close, horizon=6):
    future = close.shift(-horizon)
    return (close > future).astype(int) * 2 - 1


def rolling_knn(features, labels, k=7, train_window=160, min_train=30):
    out = pd.DataFrame(index=features.index, columns=["vote", "used", "conf"]).astype(float)
    feat_arr = features.values
    label_arr = labels.values
    horizon = 6
    n = len(feat_arr)
    for i in range(min_train, n):
        if pd.isna(feat_arr[i]).any() or pd.isna(label_arr[i - horizon]):
            continue
        train_end = i - horizon
        if train_end < min_train:
            continue
        train_X = feat_arr[train_end - train_window:train_end]
        train_y = label_arr[train_end - train_window:train_end]
        valid = ~pd.isna(train_X).any(axis=1) & ~pd.isna(train_y)
        train_X = train_X[valid]
        train_y = train_y[valid]
        if len(train_X) < k:
            continue
        dists = np.array([lorentzian_distance(feat_arr[i], x) for x in train_X])
        idx = np.argpartition(dists, k)[:k]
        votes = train_y[idx]
        vote = int(np.sum(votes))
        used = int(k)
        conf = abs(vote) / used
        out.iloc[i] = [vote, used, conf]
    return out


def compute_atr(df, period=14):
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift(1)).abs(),
        (df["Low"] - df["Close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=20, help="Days of history to backtest")
    parser.add_argument("--interval-min", type=int, default=5)
    parser.add_argument("--out-dir", default="automation/reports/ocs_btc_5m/backtest")
    args = parser.parse_args()

    if "GITHUB_WORKSPACE" in os.environ:
        repo = Path(os.environ["GITHUB_WORKSPACE"])
    else:
        repo = Path("/workspace/YW-concept-ki7409")

    out_dir = repo / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[backtest] Loading {args.days}d of BTC-USD {args.interval_min}m data...")
    df = fetch_backtest_data(days=args.days, interval_min=args.interval_min)
    if df.empty or len(df) < 200:
        print(f"[backtest] Insufficient data: {len(df)} bars")
        return 1

    # Trim to requested days
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC")
    cutoff = df.index.max() - timedelta(days=args.days)
    df = df[df.index >= cutoff].copy()
    print(f"[backtest] Using {len(df)} bars from {df.index[0]} to {df.index[-1]}")

    print("[backtest] Computing features...")
    feats = compute_features(df)
    print("[backtest] Computing labels...")
    labels = label_future(df["Close"], horizon=6)
    print("[backtest] Running KNN (this may take a few minutes)...")
    knn = rolling_knn(feats, labels, k=7, train_window=160, min_train=30)

    print("[backtest] Computing ATR...")
    atr = compute_atr(df, 14)

    # Walk forward, simulate trades
    print("[backtest] Simulating trades...")
    trades = []
    position = None
    ema50 = df["Close"].ewm(span=50, adjust=False).mean()
    mean_atr = atr.rolling(50).mean()

    for i, (ts, bar) in enumerate(df.iterrows()):
        if i < 200:
            continue

        # If position open, check exit
        if position is not None:
            high = float(bar["High"])
            low = float(bar["Low"])
            direction = position["direction"]
            sl = position["sl"]
            t1, t2, t3, t4, t5 = position["t1"], position["t2"], position["t3"], position["t4"], position["t5"]

            if direction == "long":
                hit_sl = low <= sl
                hit_t1 = high >= t1
                hit_t2 = high >= t2
                hit_t3 = high >= t3
                hit_t4 = high >= t4
                hit_t5 = high >= t5
            else:
                hit_sl = high >= sl
                hit_t1 = low <= t1
                hit_t2 = low <= t2
                hit_t3 = low <= t3
                hit_t4 = low <= t4
                hit_t5 = low <= t5

            if hit_sl:
                exit_price, exit_level, R = sl, "SL", -1.0
            elif hit_t1:
                exit_price, exit_level, R = t1, "T1", 1.0
            elif hit_t2:
                exit_price, exit_level, R = t2, "T2", 1.618
            elif hit_t3:
                exit_price, exit_level, R = t3, "T3", 2.618
            elif hit_t4:
                exit_price, exit_level, R = t4, "T4", 3.618
            elif hit_t5:
                exit_price, exit_level, R = t5, "T5", 5.0
            else:
                continue  # Still open

            pnl = (exit_price - position["entry"]) * (1 if direction == "long" else -1)
            trade = {
                **position,
                "exit_time": str(ts),
                "exit_price": exit_price,
                "exit_level": exit_level,
                "R_multiple": R,
                "pnl_usd": round(pnl, 2),
                "bars_held": i - position["entry_idx"],
            }
            trades.append(trade)
            position = None

        # If no position, check signal
        if position is None and not pd.isna(knn.iloc[i]["vote"]):
            v = float(knn.iloc[i]["vote"])
            c = float(knn.iloc[i]["conf"])
            f = feats.iloc[i]
            layer_score = (
                f["nRsi"] * 0.15 + f["nSto"] * 0.1 + f["nSt"] * 0.2 + f["nTrix"] * 0.15 +
                f["nFish"] * 0.1 + f["nLms"] * 0.1 + f["nVol"] * 0.1 + f["nCvd"] * 0.1
            ) - 0.5
            close = float(bar["Close"])
            a = float(atr.iloc[i]) if not pd.isna(atr.iloc[i]) else 0
            # Use current 50-bar ATR vs current 50-bar std as chop threshold
            cur_atr = atr.iloc[max(0, i-50):i+1].mean() if i >= 50 else atr.iloc[:i+1].mean()
            cur_vol = df["Close"].iloc[max(0, i-50):i+1].std() if i >= 50 else df["Close"].iloc[:i+1].std()
            in_chop = a < cur_vol * 0.3  # 0.3 threshold (was 0.5, too strict)
            kama = ema50.iloc[i]

            signal = "none"
            if v >= 4 and c >= 0.55 and layer_score > 0 and not in_chop and close > kama:
                signal = "long"
            elif v <= -4 and c >= 0.55 and layer_score < 0 and not in_chop and close < kama:
                signal = "short"

            if signal != "none" and a > 0:
                sl_dist = a * 1.6
                if signal == "long":
                    sl, t1, t2, t3, t4, t5 = close - sl_dist, close + sl_dist, close + sl_dist * 1.618, close + sl_dist * 2.618, close + sl_dist * 3.618, close + sl_dist * 5.0
                else:
                    sl, t1, t2, t3, t4, t5 = close + sl_dist, close - sl_dist, close - sl_dist * 1.618, close - sl_dist * 2.618, close - sl_dist * 3.618, close - sl_dist * 5.0
                position = {
                    "signal_id": f"BT_{ts}",
                    "direction": signal,
                    "entry": close,
                    "entry_time": str(ts),
                    "entry_idx": i,
                    "atr": a,
                    "sl": sl, "t1": t1, "t2": t2, "t3": t3, "t4": t4, "t5": t5,
                    "sl_dist": sl_dist,
                    "vote": int(v), "conf": round(c, 3),
                }

    # Compute stats
    if not trades:
        print("[backtest] No trades generated")
        return 0

    rs = [t["R_multiple"] for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    stats = {
        "n_trades": len(trades),
        "n_wins": len(wins),
        "n_losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "avg_R": round(float(np.mean(rs)), 3),
        "total_R": round(sum(rs), 2),
        "total_pnl_usd": round(sum(t["pnl_usd"] for t in trades), 2),
        "best_R": round(max(rs), 2),
        "worst_R": round(min(rs), 2),
        "profit_factor": round(sum(wins) / (abs(sum(losses)) + 1e-9), 2),
        "t1_hits": sum(1 for t in trades if t["exit_level"] == "T1"),
        "t2_hits": sum(1 for t in trades if t["exit_level"] == "T2"),
        "t3_hits": sum(1 for t in trades if t["exit_level"] == "T3"),
        "t4_hits": sum(1 for t in trades if t["exit_level"] == "T4"),
        "t5_hits": sum(1 for t in trades if t["exit_level"] == "T5"),
        "sl_hits": sum(1 for t in trades if t["exit_level"] == "SL"),
        "long_trades": sum(1 for t in trades if t["direction"] == "long"),
        "short_trades": sum(1 for t in trades if t["direction"] == "short"),
    }

    # Save trades + stats
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    trades_file = out_dir / f"trades_{args.days}d_{ts_str}.json"
    stats_file = out_dir / f"stats_{args.days}d_{ts_str}.json"
    trades_file.write_text(json.dumps(trades, indent=2, default=str))
    stats_file.write_text(json.dumps(stats, indent=2))
    print(f"[backtest] Saved: {trades_file}")
    print(f"[backtest] Saved: {stats_file}")

    # Plot
    cum_r = list(np.cumsum(rs))
    cum_pnl = list(np.cumsum([t["pnl_usd"] for t in trades]))
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    fig.suptitle(f"OCS BTC 5m Backtest — {args.days}d ({len(trades)} trades)", fontsize=14, fontweight="bold")

    ax1.plot(range(1, len(cum_r) + 1), cum_r, marker="o", color="steelblue", linewidth=2)
    ax1.axhline(0, color="gray", linestyle="--", alpha=0.5)
    ax1.set_ylabel("Cumulative R")
    ax1.set_title(f"Total R: {cum_r[-1]:+.2f}  |  WR: {stats['win_rate']}%  |  PF: {stats['profit_factor']}")
    ax1.grid(True, alpha=0.3)

    ax2.plot(range(1, len(cum_pnl) + 1), cum_pnl, marker="o", color="green", linewidth=2)
    ax2.axhline(0, color="gray", linestyle="--", alpha=0.5)
    ax2.set_xlabel("Trade #")
    ax2.set_ylabel("Cumulative P&L (USD per 1 BTC)")
    ax2.set_title(f"Total P&L: ${cum_pnl[-1]:+,.0f}")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    chart_path = out_dir / f"chart_{args.days}d_{ts_str}.png"
    fig.savefig(chart_path, dpi=80, bbox_inches="tight")
    plt.close(fig)
    print(f"[backtest] Chart: {chart_path}")

    # Print summary
    print()
    print("=" * 60)
    print(f"  Backtest {args.days}d BTC 5m: {len(trades)} trades")
    print(f"  Win rate:     {stats['win_rate']}%")
    print(f"  Avg R:        {stats['avg_R']:+.2f}")
    print(f"  Total R:      {stats['total_R']:+.2f}")
    print(f"  Profit factor: {stats['profit_factor']}")
    print(f"  T1: {stats['t1_hits']}  T2: {stats['t2_hits']}  T3: {stats['t3_hits']}  T4: {stats['t4_hits']}  T5: {stats['t5_hits']}  SL: {stats['sl_hits']}")
    print(f"  Long: {stats['long_trades']}  Short: {stats['short_trades']}")
    print("=" * 60)

    # Also write summary.md
    summary = f"""# OCS BTC 5m Backtest — {args.days} days

**Period**: {df.index[0]} to {df.index[-1]}
**Bars**: {len(df)}
**Trades**: {len(trades)}

## Performance
- **Win rate**: {stats['win_rate']}%
- **Avg R**: {stats['avg_R']:+.2f}
- **Total R**: {stats['total_R']:+.2f}
- **Total P&L**: ${stats['total_pnl_usd']:+,.0f} (per 1 BTC)
- **Profit factor**: {stats['profit_factor']}
- **Best trade**: {stats['best_R']:+.2f}R
- **Worst trade**: {stats['worst_R']:+.2f}R

## Exit Breakdown
- T1 (+1.0R): {stats['t1_hits']}
- T2 (+1.618R): {stats['t2_hits']}
- T3 (+2.618R): {stats['t3_hits']}
- T4 (+3.618R): {stats['t4_hits']}
- T5 (+5.0R): {stats['t5_hits']}
- SL (-1.0R): {stats['sl_hits']}

## Direction
- Long: {stats['long_trades']}
- Short: {stats['short_trades']}

## Chart
See `{chart_path.name}` for cumulative P&L curve.
"""
    summary_path = out_dir / f"summary_{args.days}d_{ts_str}.md"
    summary_path.write_text(summary)
    print(f"[backtest] Summary: {summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
