#!/usr/bin/env python3
"""Strategy Ranking — 9 strategies daily PnL comparison.

For each of the 9 strategies (8 YW + OCS BTC), runs a backtest over the
same lookback window and produces a comparative ranking.

Ranking criteria:
- Primary: Profit Factor (PF)
- Secondary: Total R
- Tertiary: Win Rate

Output:
  - automation/reports/strategy_ranking/ranking_YYYY-MM-DD.md
  - automation/reports/strategy_ranking/ranking_YYYY-MM-DD.json

Schedule: daily 21:30 HKT (after yw-daily at 21:00 + yw-publish at 21:30)
GHA workflow: strategy-ranking.yml
"""
from __future__ import annotations
import os
import sys
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from contract_specs import trade_pnl_usd  # noqa: E402
import matplotlib.pyplot as plt

# Auto-detect repo
def _find_repo() -> Path:
    """Locate the repo root without hard-coding one machine's path.

    GITHUB_WORKSPACE wins, because that is where CI checks the repo out.
    Otherwise walk up from this file until a directory containing
    "automation" is found, so any clone or worktree works.
    """
    if "GITHUB_WORKSPACE" in os.environ:
        return Path(os.environ["GITHUB_WORKSPACE"])
    for _parent in Path(__file__).resolve().parents:
        if (_parent / "automation").is_dir():
            return _parent
    return Path("/workspace/YW-concept-ki7409")


REPO = _find_repo()


# 9 strategies config
STRATEGIES = [
    {"id": "ocs-btc", "name": "OCS BTC 5m", "ticker": "BTC-USD", "type": "ocs", "weight": 1.0},
    {"id": "h-pattern", "name": "H-Pattern", "ticker": "MNQ=F", "type": "yw", "weight": 1.2},
    {"id": "3-pushes", "name": "3-Pushes", "ticker": "MNQ=F", "type": "yw", "weight": 1.0},
    {"id": "two-yang", "name": "兩陽夾一陰", "ticker": "MNQ=F", "type": "yw", "weight": 0.3, "llm_optimized": True, "optim_date": "2026-08-25 v2"},
    {"id": "rsi-div", "name": "RSI Divergence", "ticker": "MNQ=F", "type": "yw", "weight": 0.7, "llm_optimized": True, "optim_date": "2026-08-25"},
    {"id": "50-20-pullback", "name": "50/20 Pullback", "ticker": "MNQ=F", "type": "yw", "weight": 1.0},
    {"id": "stair-pattern", "name": "Stair Pattern", "ticker": "MNQ=F", "type": "yw", "weight": 1.2, "llm_optimized": True, "optim_date": "2026-08-25 v3"},
    {"id": "crt", "name": "CRT", "ticker": "MNQ=F", "type": "yw", "weight": 1.2, "llm_optimized": True, "optim_date": "2026-08-26 v5"},
    {"id": "kell-cycle", "name": "Kell Cycle", "ticker": "MNQ=F", "type": "yw", "weight": 0.6, "llm_optimized": True, "optim_date": "2026-08-26 v4"},
    {"id": "b1-mnq", "name": "B1 战法 (MNQ)", "ticker": "MNQ=F", "type": "yw", "weight": 0.4, "llm_optimized": True, "optim_date": "2026-08-27"},
    {"id": "b1-mgc", "name": "B1 战法 (MGC)", "ticker": "MGC=F", "type": "yw", "weight": 0.3, "llm_optimized": True, "optim_date": "2026-08-27"},
    {"id": "b1-btc", "name": "B1 战法 (BTC)", "ticker": "BTC-USD", "type": "yw", "weight": 0.3, "llm_optimized": True, "optim_date": "2026-08-27"},
    {"id": "b1-3in1", "name": "B1 战法 3合1 (MNQ+MGC+BTC)", "ticker": "MNQ=F", "type": "yw", "weight": 1.0, "llm_optimized": True, "optim_date": "2026-08-27"},
    # The TTrades family keeps its own trade log and its own levels. It
    # was missing from this board entirely while the settlement tracked it.
    {"id": "ttrades-fractal", "name": "TTrades Fractal", "ticker": "BTC-USD", "type": "yw", "weight": 1.0},
    {"id": "ttrades-l12", "name": "TTrades L12", "ticker": "BTC-USD", "type": "yw", "weight": 1.0},
    {"id": "ttrades-l13", "name": "TTrades L13", "ticker": "BTC-USD", "type": "yw", "weight": 1.0},
    {"id": "ttrades-l14", "name": "TTrades L14", "ticker": "BTC-USD", "type": "yw", "weight": 1.0},
    {"id": "argon-gold", "name": "Argon Gold SOP", "ticker": "GC=F", "type": "yw", "weight": 1.0},
]


# Strategy id → (name in trades.jsonl, ticker filter or None).
# The live records use the display names; the B1 family is one strategy
# traded on three tickers, so it is split per ticker the way the board
# always presented it.
STRATEGY_FILTERS = {
    "h-pattern":        ("H-Pattern", None),
    "3-pushes":         ("3-Pushes", None),
    "two-yang":         ("Two-Yang", None),
    "rsi-div":          ("RSI-Div", None),
    "50-20-pullback":   ("50-20-Pullback", None),
    "stair-pattern":    ("Stair", None),
    "crt":              ("CRT", None),
    "kell-cycle":       ("Kell-Cycle", None),
    "b1-mnq":           ("B1", "MNQ=F"),
    "b1-mgc":           ("B1", "MGC=F"),
    "b1-btc":           ("B1", "BTC-USD"),
    "b1-3in1":          ("B1-3in1", None),
    "ocs-btc":          ("OCS-BTC-5m", None),
    "ttrades-fractal":  ("TTrades-Fractal", None),
    "ttrades-l12":      ("TTrades-L12", None),
    "ttrades-l13":      ("TTrades-L13", None),
    "ttrades-l14":      ("TTrades-L14", None),
    "argon-gold":       ("Argon-Gold", None),
}


def _parse_iso(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return None


def load_closed_trades(days: int) -> dict:
    """Real closed trades per (strategy, ticker) over the lookback window.

    The ranking board used to be built from a hard-coded table of numbers
    left over from an earlier backtest, so every row on it was fabricated
    and nothing on it moved. This reads the trades the system actually
    made.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    paths = [
        (REPO / "automation/reports/live_scan/trades.jsonl", "live"),
        (REPO / "automation/reports/ocs_btc_5m/trades.jsonl", "ocs"),
        (REPO / "automation/reports/ttrades_btc/trades.jsonl", "ttrades"),
    ]
    out = {}
    for path, source in paths:
        if not path.exists():
            continue
        try:
            lines = path.read_text(errors="ignore").splitlines()
        except Exception:
            continue
        for line in lines:
            line = line.strip()
            if not line or line[0] in "<=>":
                continue
            try:
                t = json.loads(line)
            except Exception:
                continue
            if t.get("status") != "closed":
                continue
            et = _parse_iso(t.get("exit_time") or t.get("entry_time"))
            if not et or et < cutoff:
                continue
            name = t.get("strategy") or ("OCS-BTC-5m" if source == "ocs" else None)
            if not name:
                continue
            key = (name, t.get("ticker", ""))
            out.setdefault(key, []).append(t)
    return out


def live_stats(strategy_id: str, trades_by_key: dict, days: int) -> dict:
    """PF, RR, WR and the true dollar result for one strategy row."""
    name, ticker = STRATEGY_FILTERS.get(strategy_id, (None, None))
    trades = []
    for (n, tk), rows in trades_by_key.items():
        if n != name:
            continue
        if ticker and tk != ticker:
            continue
        trades.extend(rows)
    if not trades:
        return {"n_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
                "profit_factor": 0.0, "rr_ratio": 0.0, "total_R": 0.0,
                "total_pnl_usd": 0.0, "_no_data": True}
    rs = [float(t.get("R_multiple", 0) or 0) for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    n_w, n_l = len(wins), len(losses)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_win / gross_loss if gross_loss > 0 else (10.0 if gross_win > 0 else 0.0)
    avg_win = (gross_win / n_w) if n_w > 0 else 0.0
    avg_loss = (abs(sum(losses)) / n_l) if n_l > 0 else 0.0
    rr = avg_win / avg_loss if avg_loss > 0 else (10.0 if avg_win > 0 else 0.0)
    return {"n_trades": len(trades), "wins": n_w, "losses": n_l,
            "win_rate": round(n_w / len(trades), 4),
            "profit_factor": round(pf, 3),
            "rr_ratio": round(rr, 3),
            "avg_win_R": round(avg_win, 3), "avg_loss_R": round(avg_loss, 3),
            "total_R": round(sum(rs), 3),
            "total_pnl_usd": round(sum(trade_pnl_usd(t) for t in trades), 2)}


def run_ocs_backtest(days: int = 20) -> dict:
    """Run OCS BTC 5m backtest using the same script as production."""
    try:
        # Use existing backtest results if available
        backtest_dir = REPO / "automation/reports/ocs_btc_5m/backtest"
        if backtest_dir.exists():
            stats_files = sorted(backtest_dir.glob("stats_*d_*.json"),
                                 key=lambda p: p.stat().st_mtime, reverse=True)
            if stats_files:
                stats = json.loads(stats_files[0].read_text())
                return {
                    "n_trades": stats.get("n_trades", 0),
                    "win_rate": stats.get("win_rate", 0),
                    "profit_factor": stats.get("profit_factor", 0),
                    "total_R": stats.get("total_R", 0),
                    "total_pnl_usd": stats.get("total_pnl_usd", 0),
                    "avg_R": stats.get("avg_R", 0),
                }
    except Exception:
        pass
    return {"n_trades": 0, "win_rate": 0, "profit_factor": 0, "total_R": 0,
            "total_pnl_usd": 0, "avg_R": 0, "_note": "no backtest data"}


def run_yw_backtest(strategy_id: str, days: int = 20) -> dict:
    """Run YW strategy backtest using the same data + simple SL/TP simulation.

    For now, returns historical backtest numbers (from prior 60d backtest).
    Full implementation: run detector on rolling 5m data.
    """
    # Historical backtest results from /workspace/YW-concept-ki7409/automation
    # 60d backtest (Aug 2026), SL $100 TP $150, 1 micro contract
    historical = {
        "h-pattern": {"n_trades": 46, "win_rate": 54.3, "total_R": 25, "profit_factor": 1.4, "total_pnl_usd": 1068},
        "3-pushes": {"n_trades": 85, "win_rate": 47.0, "total_R": 12, "profit_factor": 1.1, "total_pnl_usd": 580},
        "two-yang": {"n_trades": 32, "win_rate": 50.0, "total_R": 5, "profit_factor": 1.05, "total_pnl_usd": 240},
        "rsi-div": {"n_trades": 120, "win_rate": 45.0, "total_R": -8, "profit_factor": 0.92, "total_pnl_usd": -380},
        "50-20-pullback": {"n_trades": 571, "win_rate": 47.6, "total_R": 95, "profit_factor": 1.25, "total_pnl_usd": 3816},
        "stair-pattern": {"n_trades": 383, "win_rate": 43.1, "total_R": 21, "profit_factor": 1.08, "total_pnl_usd": 844},
        "crt": {"n_trades": 78, "win_rate": 48.7, "total_R": 9, "profit_factor": 1.06, "total_pnl_usd": 410},
        "kell-cycle": {"n_trades": 500, "win_rate": 46.2, "total_R": 70, "profit_factor": 1.18, "total_pnl_usd": 2796},
    }
    return historical.get(strategy_id, {"n_trades": 0, "win_rate": 0, "total_R": 0,
                                         "profit_factor": 0, "total_pnl_usd": 0})


def load_ranking_settings():
    """Load ranking settings from config/ranking_settings.json.

    Falls back to defaults if file missing (graceful degradation).
    """
    cfg_path = REPO / "automation" / "config" / "ranking_settings.json"
    if not cfg_path.exists():
        return _DEFAULT_RANKING_SETTINGS
    try:
        return json.loads(cfg_path.read_text())
    except Exception as e:
        print(f"[ranking] WARN: failed to load {cfg_path}: {e}; using defaults", file=sys.stderr)
        return _DEFAULT_RANKING_SETTINGS


_DEFAULT_RANKING_SETTINGS = {
    "sort_criteria": {
        "primary": ["total_pnl_usd"],
        "secondary": ["profit_factor"],
        "tertiary": ["win_rate"],
        "r_role": "footnote",
    },
    "award_eligibility": {
        "min_trades_for_medal": 10,
    },
    "ticker_split": {"enabled": True, "display_column": True},
    "lookback": {"default_days": 20},
}


def compute_ranking(results: list[dict], settings: dict | None = None) -> list[dict]:
    """Sort by total_pnl_usd (primary) + PF (secondary) + WR (tertiary).

    9/22 user feedback: "Total $ + PF 排行，R 只作附註".
    R is excluded from sort key entirely — it's an efficiency metric,
    not a cash-flow metric. 種田要睇$同單筆風險.
    """
    s = settings or load_ranking_settings()
    primary = s["sort_criteria"]["primary"]
    secondary = s["sort_criteria"].get("secondary", [])
    tertiary = s["sort_criteria"].get("tertiary", [])

    min_n = s.get("award_eligibility", {}).get("min_trades_for_ranking", 0)

    def sort_key(r):
        # A row with too few trades cannot be ranked on its profit factor:
        # one trade gives PF 10.0 and a 100% win rate. Those rows go below
        # every row that has enough evidence, whatever their numbers are.
        # Negated, because the sort is ascending: a qualified row (1)
        # must come before an unqualified one (0).
        qualified = -1 if float(r.get("n_trades", 0)) >= min_n else 0
        return (qualified,) + tuple(-float(r.get(k, 0))
                                   for k in (primary + secondary + tertiary))

    return sorted(results, key=sort_key)


def make_ranking_markdown(ranking: list[dict], date_str: str, settings: dict | None = None) -> str:
    """Generate markdown ranking report using 9/22 收緊版 settings.

    Columns: Rank | Ticker | Strategy | Trades | WR | PF | P&L (USD)
    Footnote column: Total R
    n<10 don't get medals.
    """
    s = settings or load_ranking_settings()
    min_medal = s["award_eligibility"]["min_trades_for_medal"]
    show_ticker = s.get("ticker_split", {}).get("display_column", False)
    n_disqualified = sum(1 for r in ranking if r.get("n_trades", 0) < min_medal)

    # Load current levels (per-agent promotion state)
    levels_path = REPO / "automation" / "config" / "strategy_levels.json"
    levels_map = {}
    if levels_path.exists():
        try:
            ldata = json.loads(levels_path.read_text())
            for k, v in ldata.items():
                if k.startswith("_") or not isinstance(v, dict):
                    continue
                # Map by name (case-insensitive)
                levels_map[k.lower()] = v.get("level", 1)
        except Exception:
            pass

    # Strategy-id → level-name mapping (handles "OCS BTC 5m" vs "OCS-BTC-5m" etc.)
    NAME_TO_LEVEL_KEY = {
        "ocs-btc":         "ocs-btc-5m",
        "stair-pattern":   "stair",
        "b1-mnq":          "b1",
        "b1-mgc":          "b1",
        "b1-btc":          "b1",
        "b1-3in1":         "b1-3in1",
        "50-20-pullback":  "50-20-pullback",
        "crt":             "crt",
        "h-pattern":       "h-pattern",
        "3-pushes":        "3-pushes",
        "two-yang":        "two-yang",
        "rsi-div":         "rsi-div",
        "kell-cycle":      "kell-cycle",
        "ttrades-fractal": "ttrades-fractal",
        "ttrades-l12":     "ttrades-l12",
        "ttrades-l13":     "ttrades-l13",
        "ttrades-l14":     "ttrades-l14",
        "argon-gold":      "argon-gold",
    }

    # Build header
    ticker_header = "Ticker |" if show_ticker else ""
    ticker_sep    = "--------|" if show_ticker else ""
    md = f"""# Strategy Ranking — {date_str}

## Summary
**{len(ranking)} strategies** ranked by **PF → RR → WR**.
Sort key: Profit Factor → Risk/Reward → Win Rate. Total R and P&L (USD) are footnotes.
Level: current agent level (auto-promotes by daily settlement).

| Rank | {ticker_header} Strategy | Lv | Trades | PF | RR | WR | R | P&L (USD) |
|------|{ticker_sep}----------|-----|--------|----|----|----|---|-----------|
"""
    min_rank_n = s.get("award_eligibility", {}).get("min_trades_for_ranking", 0)
    for i, r in enumerate(ranking, 1):
        rs = r["strategy"]
        n = r.get("n_trades", 0)
        # Rows without enough trades are not ranked at all; they are listed
        # in their own section further down.
        # Look up level: try mapping table, then id, then name
        sid = rs.get("id", "").lower()
        level_key = NAME_TO_LEVEL_KEY.get(sid, sid)
        lv = levels_map.get(level_key) or levels_map.get(sid) or levels_map.get(rs["name"].lower()) or "?"
        r["_level"] = lv
        if n < min_rank_n:
            continue
        # n<10 唔入獎 — no medal, just position
        if n >= min_medal:
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
        else:
            emoji = "  "  # disqualified from medal
        tk = f" {rs['ticker']} |" if show_ticker else ""
        md += (f"| {i} {emoji} |{tk} {rs['name']} | {lv} | {n} | "
               f"{r['profit_factor']:.2f} | {r.get('rr_ratio', 0):.2f} | "
               f"{r['win_rate']*100:.1f}% | {r.get('total_R', 0):+.1f}R | "
               f"${r['total_pnl_usd']:+,.0f} |\n")

    # Rows without enough trades are shown separately: one trade gives
    # PF 10.0 and a 100% win rate, and leaving those in the same table
    # invites reading them as the best strategies on the board.
    min_rank_n = s.get("award_eligibility", {}).get("min_trades_for_ranking", 0)
    thin = [r for r in ranking if r.get("n_trades", 0) < min_rank_n]
    if thin:
        md += f"\n## 樣本不足（n < {min_rank_n}，唔參與排名）\n"
        md += ("| Strategy | Lv | Trades | PF | RR | WR | R | P&L (USD) |\n"
               "|---|---|---|---|---|---|---|---|\n")
        for r in thin:
            rs = r["strategy"]
            tk = f" {rs['ticker']} |" if show_ticker else ""
            md += (f"|{tk} {rs['name']} | {r.get('_level', '?')} | "
                   f"{r.get('n_trades', 0)} | {r['profit_factor']:.2f} | "
                   f"{r.get('rr_ratio', 0):.2f} | {r['win_rate']*100:.1f}% | "
                   f"{r.get('total_R', 0):+.1f}R | ${r['total_pnl_usd']:+,.0f} |\n")

    # Top 3 / Bottom 3 from ELIGIBLE strategies only
    eligible = [r for r in ranking if r.get("n_trades", 0) >= min_medal]
    md += "\n## Top 3 (eligible, n≥10)\n"
    for i, r in enumerate(eligible[:3], 1):
        rs = r["strategy"]
        tk = f" ({rs['ticker']})" if show_ticker else ""
        md += (f"{i}. **{rs['name']}**{tk} — PF {r['profit_factor']:.2f}, "
               f"RR {r.get('rr_ratio', 0):.2f}, {r['win_rate']*100:.1f}% WR, "
               f"${r['total_pnl_usd']:+,.0f} (n={r.get('n_trades', 0)})\n")

    md += "\n## Bottom 3 (eligible, n≥10)\n"
    for j, r in enumerate(eligible[-3:], len(eligible) - 2):
        if j <= 3:  # don't double-list the top if small N
            continue
        rs = r["strategy"]
        tk = f" ({rs['ticker']})" if show_ticker else ""
        md += (f"{j}. **{rs['name']}**{tk} — PF {r['profit_factor']:.2f}, "
               f"RR {r.get('rr_ratio', 0):.2f}, {r['win_rate']*100:.1f}% WR, "
               f"${r['total_pnl_usd']:+,.0f} (n={r.get('n_trades', 0)})\n")

    # Footnote — Total R as supplementary info
    md += "\n## Footnote — Total R (efficiency, not in sort)\n"
    md += "| Strategy | Total R | n |\n|----------|---------|---|\n"
    for r in ranking:
        rs = r["strategy"]
        md += f"| {rs['name']} | {r['total_R']:+.0f}R | {r.get('n_trades', 0)} |\n"

    # Aggregate
    total_pnl = sum(r["total_pnl_usd"] for r in ranking)
    total_r = sum(r["total_R"] for r in ranking)
    avg_pf = np.mean([r["profit_factor"] for r in ranking])
    md += f"\n## Aggregate\n"
    md += f"- **Total P&L**: ${total_pnl:+,.0f}\n"
    md += f"- **Total R**: {total_r:+.0f}R\n"
    md += f"- **Avg Profit Factor**: {avg_pf:.2f}\n"
    md += f"- **Disqualified (n<{min_medal})**: {n_disqualified}/{len(ranking)} strategies\n"

    return md


def make_ranking_chart(ranking: list[dict], date_str: str, out_path: Path):
    """Generate PnL bar chart."""
    names = [r["strategy"]["name"] for r in ranking]
    pnls = [r["total_pnl_usd"] for r in ranking]
    colors = ["green" if p > 0 else "red" for p in pnls]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    fig.suptitle(f"Strategy PnL Ranking — {date_str}", fontsize=14, fontweight="bold")

    ax1.barh(names, pnls, color=colors, alpha=0.8)
    ax1.set_xlabel("P&L (USD)")
    ax1.set_title("Total P&L by Strategy (20d backtest)")
    ax1.axvline(0, color="black", linewidth=0.5)
    ax1.grid(True, alpha=0.3, axis="x")
    ax1.invert_yaxis()  # Best at top

    # PF comparison
    pfs = [r["profit_factor"] for r in ranking]
    ax2.barh(names, pfs, color="steelblue", alpha=0.8)
    ax2.set_xlabel("Profit Factor")
    ax2.set_title("Profit Factor by Strategy")
    ax2.axvline(1.0, color="red", linestyle="--", alpha=0.5, label="Breakeven (PF=1)")
    ax2.legend()
    ax2.grid(True, alpha=0.3, axis="x")
    ax2.invert_yaxis()

    plt.tight_layout()
    fig.savefig(out_path, dpi=80, bbox_inches="tight")
    plt.close(fig)


def main():
    HKT = timezone(timedelta(hours=8))
    today_hkt = datetime.now(HKT).strftime("%Y-%m-%d")

    # Load settings
    settings = load_ranking_settings()
    days = settings.get("lookback", {}).get("default_days", 20)
    sort_desc = " + ".join(
        settings["sort_criteria"]["primary"]
        + settings["sort_criteria"].get("secondary", [])
    )

    print(f"[ranking] Computing daily strategy ranking for {today_hkt} ({days}d of closed trades)...")
    print(f"[ranking] Sort: {sort_desc}")
    print(f"[ranking] Min trades for medal: {settings['award_eligibility']['min_trades_for_medal']}")

    trades_by_key = load_closed_trades(days)
    results = []
    for strat in STRATEGIES:
        print(f"  - {strat['name']} ({strat['id']})...", end=" ")
        data = live_stats(strat["id"], trades_by_key, days)
        data["strategy"] = strat
        results.append(data)
        if data.get("_no_data"):
            print("no closed trades in window")
        else:
            print(f"n={data['n_trades']}, PF={data['profit_factor']:.2f}, "
                  f"RR={data['rr_ratio']:.2f}, WR={data['win_rate']*100:.1f}%, "
                  f"${data['total_pnl_usd']:+,.0f}")

    # Rank using 9/22 收緊版 sort
    ranking = compute_ranking(results, settings)
    n_eligible = sum(1 for r in ranking if r.get("n_trades", 0) >= settings["award_eligibility"]["min_trades_for_medal"])
    print(f"\n[ranking] Top: {ranking[0]['strategy']['name']} "
          f"(PF {ranking[0]['profit_factor']:.2f}, RR {ranking[0].get('rr_ratio', 0):.2f}, "
          f"WR {ranking[0]['win_rate']*100:.1f}%)")
    print(f"[ranking] Bottom: {ranking[-1]['strategy']['name']} "
          f"(PF {ranking[-1]['profit_factor']:.2f}, RR {ranking[-1].get('rr_ratio', 0):.2f}, "
          f"WR {ranking[-1]['win_rate']*100:.1f}%)")
    print(f"[ranking] Eligible (n≥{settings['award_eligibility']['min_trades_for_medal']}): {n_eligible}/{len(ranking)}")

    # Output dir
    out_dir = REPO / "automation/reports/strategy_ranking"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON
    json_path = out_dir / f"ranking_{today_hkt}.json"
    json_path.write_text(json.dumps({
        "date": today_hkt,
        "days": days,
        "settings_version": "v5.3 (9/22 收緊版: Total$+PF sort, n<10 no medal, ticker column)",
        "ranking": [
            {"rank": i + 1, **r} for i, r in enumerate(ranking)
        ],
    }, indent=2, default=str))
    print(f"[ranking] JSON: {json_path}")

    # Save Markdown
    md_path = out_dir / f"ranking_{today_hkt}.md"
    md_content = make_ranking_markdown(ranking, today_hkt, settings)
    md_path.write_text(md_content)
    print(f"[ranking] MD: {md_path}")

    # Save chart
    chart_path = out_dir / f"ranking_{today_hkt}.png"
    make_ranking_chart(ranking, today_hkt, chart_path)
    print(f"[ranking] Chart: {chart_path}")

    # Trigger daily settlement (level promotion per-agent)
    print(f"\n[ranking] Running daily settlement...")
    try:
        import subprocess
        r = subprocess.run(
            [sys.executable, str(REPO / "automation" / "scripts" / "daily_settlement.py")],
            capture_output=True, text=True, timeout=120
        )
        if r.returncode == 0:
            # Tail last 15 lines
            print("\n".join(r.stdout.splitlines()[-15:]))
        else:
            print(f"[ranking] settlement returned {r.returncode}: {r.stderr[-500:]}")
    except Exception as e:
        print(f"[ranking] settlement call failed: {e}")

    # Cumulative ranking history
    history_path = out_dir / "history.jsonl"
    with history_path.open("a") as f:
        f.write(json.dumps({
            "date": today_hkt,
            "ranking": [
                {"strategy_id": r["strategy"]["id"],
                 "name": r["strategy"]["name"],
                 "rank": i + 1,
                 "pf": r["profit_factor"],
                 "total_R": r["total_R"],
                 "pnl_usd": r["total_pnl_usd"],
                 "win_rate": r["win_rate"],
                 "n_trades": r["n_trades"]}
                for i, r in enumerate(ranking)
            ],
        }, default=str) + "\n")
    print(f"[ranking] History: {history_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
