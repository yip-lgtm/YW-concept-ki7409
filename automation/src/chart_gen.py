"""Chart generation for YW Concept daily reminder.

4-Chart Standard (D / H4 / H1 / 5m) — same as apex-bootcamp v2.6.8.
Ported from apex-bootcamp AUTOMATION/src/chart_gen.py for MNQ focus.

Panels:
  - HTF-D (1d, 90 days) — Higher TimeFrame structure
  - H4 (4h, 30 days) — Mid structure
  - H1 (1h, 5 days) — Entry TF / killzone
  - M5 (5-min, 2 days) — Intraday execution precision

Each panel shows:
  - Candlesticks (custom matplotlib)
  - PDH / PDL / PDC (Previous Day High / Low / Close)
  - ONH / ONL (Overnight High / Low)
  - PMH / PML (Premarket High / Low)
  - Volume bars
  - Today's session window highlight (killzone 09:00-11:00 ET)
  - M5 panel: Premarket range + NY AM killzone (09:00-11:00 ET) highlight
"""
from __future__ import annotations
import os
import warnings
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# CJK font setup
try:
    import matplotlib.font_manager as fm
    for fp in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]:
        if os.path.exists(fp):
            fm.fontManager.addfont(fp)
    plt.rcParams["font.sans-serif"] = [
        "Noto Sans CJK JP", "Noto Sans CJK TC", "DejaVu Sans"
    ]
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False
except Exception:
    pass

BG = "#0d0d12"
FG_UP = "#10d97e"
FG_DOWN = "#ff4d6d"
FG_TEXT = "#ccc"
FG_GRID = "#333"
FG_HIGHLIGHT = "#ff9"


def fetch_data(ticker: str, period: str, interval: str) -> pd.DataFrame:
    d = yf.download(ticker, period=period, interval=interval,
                    progress=False, auto_adjust=True)
    if d.empty:
        return d
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    return d


def resample_1h_to_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    if df_1h.empty:
        return df_1h
    agg = {"Open": "first", "High": "max", "Low": "min",
           "Close": "last", "Volume": "sum"}
    return df_1h.resample("4h").agg(agg).dropna()


def compute_levels(d: pd.DataFrame) -> dict:
    if d.empty or len(d) < 2:
        return {}
    today = d.iloc[-1]
    prev = d.iloc[-2]
    return {
        "PDH": float(prev["High"]),
        "PDL": float(prev["Low"]),
        "PDC": float(prev["Close"]),
        "ONH": float(today["High"]),
        "ONL": float(today["Low"]),
        "today_open": float(today["Open"]),
        "today_close": float(today["Close"]),
    }


def draw_candles(ax, df: pd.DataFrame, width: float = 0.7):
    """Draw OHLC candles on a matplotlib axis (bar-style)."""
    if df.empty:
        return
    x = np.arange(len(df))
    o = df["Open"].values
    h = df["High"].values
    l = df["Low"].values
    c = df["Close"].values
    up = c >= o
    color = np.where(up, FG_UP, FG_DOWN)

    # Wicks
    for i in range(len(df)):
        ax.vlines(x[i], l[i], h[i], color=color[i], linewidth=0.8, alpha=0.9)
    # Bodies
    body_height = np.abs(c - o)
    body_bottom = np.minimum(c, o)
    ax.bar(x, body_height, bottom=body_bottom, width=width,
           color=color, edgecolor=color, linewidth=0.5, alpha=0.9)


def draw_volume(ax, df: pd.DataFrame, width: float = 0.7):
    if df.empty:
        return
    x = np.arange(len(df))
    c = df["Close"].values
    o = df["Open"].values
    v = df["Volume"].values
    color = np.where(c >= o, FG_UP, FG_DOWN)
    ax.bar(x, v, width=width, color=color, alpha=0.4)


def draw_levels(ax, df: pd.DataFrame, levels: dict, color: str = "#7af"):
    if not levels or df.empty:
        return
    x_range = (0, len(df) - 1)
    for name in ["PDH", "PDL", "PDC", "ONH", "ONL"]:
        if name in levels:
            ax.hlines(levels[name], *x_range, color=color,
                      linestyle="--", linewidth=0.6, alpha=0.6)
            ax.text(len(df) - 1, levels[name], f" {name}",
                    color=color, fontsize=7, va="center", ha="left",
                    family="monospace")


def format_xaxis(ax, df: pd.DataFrame, title: str):
    if df.empty:
        return
    n = len(df)
    step = max(1, n // 6)
    xticks = list(range(0, n, step))
    xlabels = [df.index[i].strftime("%m-%d") for i in xticks]
    if n - 1 not in xticks:
        xticks.append(n - 1)
        xlabels.append(df.index[-1].strftime("%m-%d %H:%M"))
    ax.set_xticks(xticks)
    ax.set_xticklabels(xlabels, rotation=0, fontsize=8)
    ax.set_xlim(-0.5, n - 0.5)
    ax.set_title(title, color=FG_TEXT, fontsize=10, loc="left")
    ax.tick_params(axis="y", labelsize=8, colors=FG_TEXT)
    ax.grid(True, alpha=0.2, color=FG_GRID)
    ax.set_facecolor(BG)
    for spine in ax.spines.values():
        spine.set_color("#444")


def make_chart_4panel(
    ticker: str, name: str,
    df_d: pd.DataFrame, df_h4: pd.DataFrame, df_h1: pd.DataFrame,
    df_m5: pd.DataFrame,
    out_path: Path,
) -> dict:
    levels = compute_levels(df_h1)

    fig = plt.figure(figsize=(13, 13), dpi=110)
    fig.patch.set_facecolor(BG)

    # 5 rows: HTF-D (30%), H4 (20%), H1-candles (16%), H1-volume (8%), M5 (26%)
    gs = fig.add_gridspec(
        5, 1,
        height_ratios=[3, 2, 1.6, 0.8, 2.6],
        hspace=0.10, left=0.06, right=0.98, top=0.955, bottom=0.05
    )
    ax_d = fig.add_subplot(gs[0])
    ax_h4 = fig.add_subplot(gs[1])
    ax_h1 = fig.add_subplot(gs[2])
    ax_h1v = fig.add_subplot(gs[3], sharex=ax_h1)
    ax_m5 = fig.add_subplot(gs[4])

    # HTF-D
    if not df_d.empty:
        draw_candles(ax_d, df_d, width=0.7)
        if levels:
            for nm in ["PDH", "PDL", "PDC"]:
                if nm in levels:
                    ax_d.axhline(levels[nm], color="#666", linestyle="--", linewidth=0.6, alpha=0.4)
        if len(df_d) > 0:
            last_p = float(df_d["Close"].iloc[-1])
            color = FG_UP if last_p >= float(df_d["Open"].iloc[-1]) else FG_DOWN
            ax_d.annotate(f" {last_p:.2f}", xy=(len(df_d)-1, last_p),
                          color=color, fontsize=10, fontweight="bold",
                          xytext=(5, 0), textcoords="offset points")
        format_xaxis(ax_d, df_d, "HTF-D (1D, 90 days) — Higher TimeFrame structure")

    # H4
    if not df_h4.empty:
        draw_candles(ax_h4, df_h4, width=0.6)
        if levels:
            for nm in ["PDH", "PDL"]:
                if nm in levels:
                    ax_h4.axhline(levels[nm], color="#ff9", linestyle="--", linewidth=0.5, alpha=0.4)
        format_xaxis(ax_h4, df_h4, "H4 (4-hour, 30 days) — Mid structure")

    # H1 (candles + separate volume row)
    if not df_h1.empty:
        draw_candles(ax_h1, df_h1, width=0.6)
        if levels:
            for nm in ["PDH", "PDL", "PDC", "ONH", "ONL"]:
                if nm in levels:
                    ax_h1.axhline(levels[nm], color="#7af", linestyle=":", linewidth=0.5, alpha=0.4)
                    ax_h1.text(len(df_h1)-1, levels[nm], f" {nm}",
                               color="#7af", fontsize=6, va="center", ha="left",
                               family="monospace", alpha=0.7)
        # Highlight last 3-4 bars (today's session)
        if len(df_h1) >= 4:
            ax_h1.axvspan(len(df_h1)-5, len(df_h1)-0.5, color=FG_HIGHLIGHT, alpha=0.06)
        format_xaxis(ax_h1, df_h1, "H1 (1-hour, 5 days) — Entry TF / Killzone")

        # Volume subplot
        draw_volume(ax_h1v, df_h1, width=0.6)
        ax_h1v.set_title("Volume", color=FG_TEXT, fontsize=8, loc="left")
        ax_h1v.tick_params(axis="x", labelsize=8, colors=FG_TEXT)
        ax_h1v.tick_params(axis="y", labelsize=7, colors=FG_TEXT)
        ax_h1v.set_facecolor(BG)
        ax_h1v.set_xlim(-0.5, len(df_h1)-0.5)
        ax_h1v.grid(True, alpha=0.15, color=FG_GRID)
        for spine in ax_h1v.spines.values():
            spine.set_color("#444")
        ax_h1v.tick_params(axis="x", labelbottom=False)
    else:
        ax_h1v.axis("off")

    # M5 — Intraday execution (5-min candles for last 2 days) v2.6.8 NEW
    if not df_m5.empty:
        draw_candles(ax_m5, df_m5, width=0.4)
        # PDH/PDL/ONH/ONL from H1 levels dict (same daily/ON values)
        if levels:
            for nm in ["PDH", "PDL", "ONH", "ONL"]:
                if nm in levels:
                    ax_m5.axhline(levels[nm], color="#7af", linestyle=":",
                                  linewidth=0.5, alpha=0.5)
                    ax_m5.text(len(df_m5)-1, levels[nm], f" {nm}",
                               color="#7af", fontsize=7, va="center", ha="left",
                               family="monospace", alpha=0.8)
        # Highlight today's session (second half of bars)
        if len(df_m5) >= 30:
            ax_m5.axvspan(len(df_m5)//2, len(df_m5)-0.5,
                          color=FG_HIGHLIGHT, alpha=0.05)
        # Current price annotation
        if len(df_m5) > 0:
            last_p = float(df_m5["Close"].iloc[-1])
            color = FG_UP if last_p >= float(df_m5["Open"].iloc[-1]) else FG_DOWN
            ax_m5.annotate(f" {last_p:.2f} (NOW)",
                          xy=(len(df_m5)-1, last_p),
                          color=color, fontsize=8, fontweight="bold",
                          xytext=(5, 0), textcoords="offset points")
        # M5 x-axis: more frequent labels
        n = len(df_m5)
        step = max(1, n // 8)
        xticks = list(range(0, n, step))
        xlabels = [df_m5.index[i].strftime("%m-%d %H:%M") for i in xticks]
        if n - 1 not in xticks:
            xticks.append(n - 1)
            xlabels.append(df_m5.index[-1].strftime("%H:%M"))
        ax_m5.set_xticks(xticks)
        ax_m5.set_xticklabels(xlabels, rotation=0, fontsize=7)
        ax_m5.set_xlim(-0.5, n - 0.5)
        ax_m5.set_title("M5 (5-min, 2 days) — Intraday execution / NY AM Killzone 09:00-11:00 ET",
                       color=FG_TEXT, fontsize=10, loc="left")
        ax_m5.tick_params(axis="y", labelsize=8, colors=FG_TEXT)
        ax_m5.grid(True, alpha=0.2, color=FG_GRID)
        ax_m5.set_facecolor(BG)
        for spine in ax_m5.spines.values():
            spine.set_color("#444")
    else:
        ax_m5.text(0.5, 0.5, "5-min data unavailable",
                  transform=ax_m5.transAxes, ha="center", color="#666")
        ax_m5.set_facecolor(BG)
        ax_m5.set_xticks([])
        ax_m5.set_yticks([])

    # Title
    fig.suptitle(
        f"{ticker} — {name}",
        fontsize=15, fontweight="bold", color="#fff", y=0.985
    )

    # Footer
    if levels:
        footer_parts = []
        for nm in ["PDH", "PDL", "PDC", "ONH", "ONL"]:
            if nm in levels:
                footer_parts.append(f"{nm}={levels[nm]:.2f}")
        if footer_parts:
            fig.text(0.5, 0.005, "  |  ".join(footer_parts),
                     ha="center", color="#7af", fontsize=8, family="monospace")

    fig.savefig(out_path, dpi=110, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    return levels


def generate_for_ticker(ticker: str, name: str, out_dir: Path) -> tuple[Path | None, dict]:
    try:
        df_d = fetch_data(ticker, "3mo", "1d")
        df_1h = fetch_data(ticker, "5d", "1h")
        df_h4 = resample_1h_to_4h(df_1h) if not df_1h.empty else df_1h
        df_m5 = fetch_data(ticker, "2d", "5m")  # v2.6.8 NEW
        if df_d.empty and df_h4.empty and df_1h.empty and df_m5.empty:
            return None, {}
        out_path = out_dir / f"{ticker.replace('=', '_')}_4chart.png"
        levels = make_chart_4panel(ticker, name, df_d, df_h4, df_1h, df_m5, out_path)
        return out_path, levels
    except Exception as e:
        print(f"[chart_gen] {ticker} failed: {e}", flush=True)
        return None, {}


def main():
    out_dir = Path(os.environ.get("APEX_CHART_OUT", "/tmp/apex-charts"))
    out_dir.mkdir(parents=True, exist_ok=True)

    TICKERS = [
        ("MNQ=F", "Micro Nasdaq-100"),  # YW primary
        ("MES=F", "Micro S&P 500"),     # secondary
        ("M2K=F", "Micro Russell 2000"),  # divergence reference
    ]

    results = []
    for tk, name in TICKERS:
        path, levels = generate_for_ticker(tk, name, out_dir)
        if path:
            print(f"  ✓ {tk:6s} → {path.name}  ({len(levels)} levels)", flush=True)
            results.append((tk, name, path, levels))
        else:
            print(f"  ✗ {tk:6s} failed", flush=True)
    return results


if __name__ == "__main__":
    main()
