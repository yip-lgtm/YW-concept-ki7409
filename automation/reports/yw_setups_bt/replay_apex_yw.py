#!/usr/bin/env python3
"""Replay YW live_scan trades under live Apex-monitor risk envelope.

Data source preference:
  1) live_scan trades.jsonl / signals.jsonl (faithful attribution)
  2) OCS supplement from ocs_backtest output (no live_scan OCS attribution)

Apex constraints:
  - A/B only (skip C)
  - 1 Micro contract point values
  - Daily kill -$100 / daily TP cap +$300 (no new entries that NY day)
  - Brackets only (use recorded SL/T* exits); no scale/average
  - One open position per strategy at a time
  - Skip chase past T1 at entry
  - Session tags LDLZ 02-05 NY / NYKZ 08:30-11 NY / other
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, time, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REPO = Path("/home/box/repos/YW-concept-ki7409")
LIVE = REPO / "automation/reports/live_scan"
OUT = Path("/workspace/yw_setups_bt")
NY = ZoneInfo("America/New_York")

# Window: live_scan coverage ending 2026-09-21
WINDOW_END = date(2026, 9, 21)
# Prefer max available; live_scan starts ~2026-08-25
WINDOW_START = date(2026, 8, 25)

POINT_VALUE = {
    "MNQ=F": 2.0,
    "MES=F": 5.0,
    "M2K=F": 5.0,
    "MGC=F": 10.0,
    "BTC-USD": 0.1,  # MBT micro proxy ($0.10 / point)
    "MBT=F": 0.1,
}

STRATEGIES_CANON = [
    "H-Pattern",
    "3-Pushes",
    "Two-Yang",
    "RSI-Div",
    "50-20-Pullback",
    "Stair",
    "B1",
    "B1-3in1",
    "Kell-Cycle",
    "CRT",
    "OCS-BTC-5m",
]

# live_scan STRATEGIES dict tickers (from live_scan.py)
STRATEGY_TICKERS = {
    "H-Pattern": ["MNQ=F", "MES=F", "M2K=F", "MGC=F", "BTC-USD"],
    "3-Pushes": ["MNQ=F", "MES=F", "M2K=F", "MGC=F", "BTC-USD"],
    "Two-Yang": ["MNQ=F", "MES=F", "M2K=F", "MGC=F", "BTC-USD"],
    "RSI-Div": ["MNQ=F", "MES=F", "M2K=F", "MGC=F", "BTC-USD"],
    "50-20-Pullback": ["MNQ=F", "MES=F", "M2K=F", "MGC=F", "BTC-USD"],
    "Stair": ["MNQ=F", "MES=F", "M2K=F", "MGC=F", "BTC-USD"],
    "B1": ["MNQ=F", "MGC=F", "BTC-USD"],  # B1_TICKERS only
    "B1-3in1": ["MNQ=F", "MGC=F", "BTC-USD"],  # multi-asset scan of those 3
    "Kell-Cycle": ["MNQ=F", "MES=F", "M2K=F", "MGC=F", "BTC-USD"],
    "CRT": ["MNQ=F", "MES=F", "M2K=F", "MGC=F", "BTC-USD"],
    "OCS-BTC-5m": ["BTC-USD"],  # MBT proxy
}

DAILY_KILL = -100.0
DAILY_TP_CAP = 300.0
KEEP_NET = 3000.0
QUAL_DAY_USD = 250.0
KEEP_QUAL_DAYS = 3
SOLID_SAMPLE = 20  # solid sample for keep via qual-days path


def parse_ts(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t


def to_ny(ts) -> pd.Timestamp:
    return parse_ts(ts).tz_convert(NY)


def tag_session(ts) -> str:
    tm = to_ny(ts).time()
    if time(2, 0) <= tm < time(5, 0):
        return "LDLZ"
    if time(8, 30) <= tm < time(11, 0):
        return "NYKZ"
    return "other"


def is_chase_past_t1(trade: dict) -> bool:
    d = str(trade.get("direction", "")).strip().lower()
    e = float(trade["entry"])
    t1 = float(trade["t1"])
    if d in ("long", "buy", "up", "bullish", "l"):
        return e >= t1
    if d in ("short", "sell", "down", "bearish", "s"):
        return e <= t1
    return False


def micro_pnl(trade: dict) -> float:
    """Convert recorded price-point pnl_usd to 1-micro USD."""
    ticker = trade["ticker"]
    pv = POINT_VALUE.get(ticker)
    if pv is None:
        raise ValueError(f"unknown ticker {ticker}")
    # trades.jsonl pnl_usd = |exit-entry| in price points (signed)
    return round(float(trade["pnl_usd"]) * pv, 2)


def max_dd(pnls: list[float]) -> float:
    peak = 0.0
    eq = 0.0
    dd = 0.0
    for p in pnls:
        eq += p
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return round(dd, 2)


def verdict(net: float, qual_days: int, n: int, wr: float) -> str:
    if n == 0:
        return "drop"
    # overfit / tiny sample with huge WR not trusted alone
    if n < 5 and abs(net) < 500:
        return "drop"
    keep = (net >= KEEP_NET) or (qual_days >= KEEP_QUAL_DAYS and n >= SOLID_SAMPLE)
    if keep and net > 0:
        return "keep"
    if net > 0:
        return "tweak"
    return "drop"


def load_live_trades() -> list[dict]:
    trades = []
    with (LIVE / "trades.jsonl").open() as f:
        for line in f:
            if not line.strip():
                continue
            t = json.loads(line)
            if t.get("status") != "closed":
                continue
            et = to_ny(t["entry_time"]).date()
            if et < WINDOW_START or et > WINDOW_END:
                continue
            trades.append(t)
    return trades


def load_ocs_trades() -> tuple[list[dict], str]:
    """Load newest OCS backtest trades overlapping window; convert to live-like schema."""
    candidates = []
    bt_dir = REPO / "automation/reports/ocs_btc_5m/backtest"
    if bt_dir.exists():
        candidates.extend(sorted(bt_dir.glob("trades_*d_*.json"), key=lambda p: p.stat().st_mtime, reverse=True))
    # also check our run output
    local = OUT / "ocs_raw"
    if local.exists():
        candidates = sorted(local.glob("trades_*.json"), key=lambda p: p.stat().st_mtime, reverse=True) + candidates

    for path in candidates:
        try:
            raw = json.loads(path.read_text())
        except Exception:
            continue
        if not isinstance(raw, list) or not raw:
            continue
        out = []
        for t in raw:
            et = to_ny(t["entry_time"]).date()
            if et < WINDOW_START or et > WINDOW_END:
                continue
            # OCS pnl_usd is per 1 BTC; treat price move as points for MBT
            row = {
                "signal_id": t.get("signal_id"),
                "strategy": "OCS-BTC-5m",
                "ticker": "BTC-USD",
                "direction": t.get("direction"),
                "grade": "B",  # OCS uses own conf gate; treat accepted as B
                "entry": t["entry"],
                "entry_time": t["entry_time"],
                "exit_time": t.get("exit_time"),
                "exit_price": t.get("exit_price"),
                "exit_level": t.get("exit_level"),
                "sl": t["sl"],
                "t1": t["t1"],
                "t2": t.get("t2"),
                "t3": t.get("t3"),
                "t4": t.get("t4"),
                "t5": t.get("t5"),
                "sl_dist": t.get("sl_dist"),
                "R_multiple": t.get("R_multiple"),
                "pnl_usd": t.get("pnl_usd"),  # price points
                "status": "closed",
                "confidence": t.get("conf"),
                "_source_file": str(path),
            }
            out.append(row)
        if out:
            return out, f"re-sim:{path.name} (OCS own gates, graded as B accept)"
    return [], "re-sim:NONE (no OCS trades in window)"


def replay_strategy(name: str, trades: list[dict], data_source: str) -> dict:
    # Filter A/B, chase, known tickers
    filtered = []
    skip_counts = defaultdict(int)
    for t in trades:
        if t.get("grade") not in ("A", "B"):
            skip_counts["grade_C_or_other"] += 1
            continue
        if t["ticker"] not in POINT_VALUE:
            skip_counts["unknown_ticker"] += 1
            continue
        if is_chase_past_t1(t):
            skip_counts["chase_past_t1"] += 1
            continue
        filtered.append(t)

    # Chronological by entry
    filtered.sort(key=lambda x: parse_ts(x["entry_time"]))

    accepted = []
    daily_pnl = defaultdict(float)
    daily_stopped = set()  # days where kill or TP cap hit
    open_until = None  # no overlap / no scale

    for t in filtered:
        entry_ts = parse_ts(t["entry_time"])
        exit_ts = parse_ts(t["exit_time"]) if t.get("exit_time") else entry_ts
        day = to_ny(entry_ts).date().isoformat()

        if day in daily_stopped:
            skip_counts["daily_envelope_block"] += 1
            continue

        # no scale/average: skip if prior trade still open
        if open_until is not None and entry_ts < open_until:
            skip_counts["overlap_no_scale"] += 1
            continue

        pnl = micro_pnl(t)
        # Soft-cap single fill so one trade can't blow past +$300 day target alone
        # (Apex TP bracket design). Preserve sign; clip magnitude to remaining room toward caps.
        room_up = DAILY_TP_CAP - daily_pnl[day]
        room_dn = abs(DAILY_KILL - daily_pnl[day])  # how much loss still allowed
        if pnl > 0:
            pnl_eff = min(pnl, max(0.0, room_up))
        else:
            pnl_eff = max(pnl, -room_dn)
        # If clipped to 0 because already at cap, treat as blocked
        if abs(pnl_eff) < 1e-9 and abs(pnl) > 1e-9 and (daily_pnl[day] <= DAILY_KILL + 1e-9 or daily_pnl[day] >= DAILY_TP_CAP - 1e-9):
            skip_counts["daily_envelope_block"] += 1
            continue

        sess = tag_session(entry_ts)
        row = {
            "strategy": name,
            "ticker": t["ticker"],
            "grade": t.get("grade"),
            "direction": t.get("direction"),
            "entry_time": str(t["entry_time"]),
            "exit_time": str(t.get("exit_time")),
            "exit_level": t.get("exit_level"),
            "R_multiple": t.get("R_multiple"),
            "pnl_price_points": t.get("pnl_usd"),
            "pnl_usd_micro": round(pnl_eff, 2),
            "pnl_usd_micro_raw": round(pnl, 2),
            "session": sess,
            "ny_day": day,
            "point_value": POINT_VALUE[t["ticker"]],
        }
        accepted.append(row)
        daily_pnl[day] += pnl_eff
        open_until = exit_ts

        if daily_pnl[day] <= DAILY_KILL + 1e-9 or daily_pnl[day] >= DAILY_TP_CAP - 1e-9:
            daily_stopped.add(day)

    pnls = [r["pnl_usd_micro"] for r in accepted]
    wins = [p for p in pnls if p > 0]
    n = len(accepted)
    net = round(sum(pnls), 2)
    wr = round(100.0 * len(wins) / n, 1) if n else 0.0
    dd = max_dd(pnls)

    # daily stats
    day_totals = defaultdict(float)
    for r in accepted:
        day_totals[r["ny_day"]] += r["pnl_usd_micro"]
    qual_days = sum(1 for v in day_totals.values() if v >= QUAL_DAY_USD)
    best_day = max(day_totals.items(), key=lambda x: x[1]) if day_totals else None
    worst_day = min(day_totals.items(), key=lambda x: x[1]) if day_totals else None

    # session breakdown
    sess = {"LDLZ": {"n": 0, "pnl": 0.0, "wins": 0},
            "NYKZ": {"n": 0, "pnl": 0.0, "wins": 0},
            "other": {"n": 0, "pnl": 0.0, "wins": 0}}
    for r in accepted:
        s = r["session"]
        sess[s]["n"] += 1
        sess[s]["pnl"] += r["pnl_usd_micro"]
        if r["pnl_usd_micro"] > 0:
            sess[s]["wins"] += 1
    for s, d in sess.items():
        d["pnl"] = round(d["pnl"], 2)
        d["win_rate"] = round(100.0 * d["wins"] / d["n"], 1) if d["n"] else 0.0

    instruments = sorted({r["ticker"] for r in accepted})
    # map BTC-USD display note
    instruments_display = [("MBT≈BTC-USD" if x == "BTC-USD" else x) for x in instruments]

    v = verdict(net, qual_days, n, wr)

    # LDLZ vs NYKZ summary string
    if name == "OCS-BTC-5m" or (instruments == ["BTC-USD"]):
        ldlz_nykz = (
            f"BTC 24h — LDLZ n={sess['LDLZ']['n']} ${sess['LDLZ']['pnl']:+.0f} | "
            f"NYKZ n={sess['NYKZ']['n']} ${sess['NYKZ']['pnl']:+.0f} | "
            f"other n={sess['other']['n']} ${sess['other']['pnl']:+.0f}"
        )
    else:
        ldlz_nykz = (
            f"LDLZ n={sess['LDLZ']['n']} ${sess['LDLZ']['pnl']:+.0f} | "
            f"NYKZ n={sess['NYKZ']['n']} ${sess['NYKZ']['pnl']:+.0f} | "
            f"other n={sess['other']['n']} ${sess['other']['pnl']:+.0f}"
        )

    return {
        "strategy": name,
        "tickers_configured": STRATEGY_TICKERS.get(name, []),
        "instruments_traded": instruments,
        "instruments_display": instruments_display,
        "data_source": data_source,
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
        "n_trades": n,
        "n_wins": len(wins),
        "n_losses": n - len(wins),
        "win_rate_pct": wr,
        "net_pnl": net,
        "max_dd": dd,
        "qual_days_ge_250": qual_days,
        "best_day": {"date": best_day[0], "pnl": round(best_day[1], 2)} if best_day else None,
        "worst_day": {"date": worst_day[0], "pnl": round(worst_day[1], 2)} if worst_day else None,
        "session": sess,
        "ldlz_vs_nykz": ldlz_nykz,
        "skip_counts": dict(skip_counts),
        "n_candidates_ab": len(filtered),
        "verdict": v,
        "trades": accepted,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    live = load_live_trades()
    by_strat = defaultdict(list)
    for t in live:
        by_strat[t["strategy"]].append(t)

    results = []
    for name in STRATEGIES_CANON:
        if name == "OCS-BTC-5m":
            ocs_trades, src = load_ocs_trades()
            # Prefer live if any (there are none historically)
            live_ocs = by_strat.get("OCS-BTC-5m", [])
            if live_ocs:
                res = replay_strategy(name, live_ocs, "signals/trades.jsonl (live_scan)")
            else:
                res = replay_strategy(name, ocs_trades, src)
        else:
            res = replay_strategy(
                name,
                by_strat.get(name, []),
                "live_scan trades.jsonl (A/B replay under Apex envelope)",
            )
        results.append(res)

    # Rank: primary net_pnl, secondary qual_days, tertiary n_trades
    ranked = sorted(
        results,
        key=lambda r: (r["net_pnl"], r["qual_days_ge_250"], r["n_trades"]),
        reverse=True,
    )
    for i, r in enumerate(ranked, 1):
        r["rank"] = i

    # Write trades detail
    all_trades = []
    for r in ranked:
        all_trades.extend(r["trades"])
    (OUT / "trades_replay.json").write_text(json.dumps(all_trades, indent=2, default=str))

    # ranking.json (no full trade lists)
    ranking_payload = {
        "title": "YW-concept strategies under live Apex-monitor constraints",
        "generated_at_hkt": datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat(),
        "window": {
            "start": WINDOW_START.isoformat(),
            "end": WINDOW_END.isoformat(),
            "note": "max available live_scan attribution (~28 calendar days); yfinance 5m ~60d cap",
        },
        "constraints": {
            "grades": "A/B only (skip C)",
            "contracts": "1 Micro",
            "point_values": POINT_VALUE,
            "daily_kill_usd": DAILY_KILL,
            "daily_tp_cap_usd": DAILY_TP_CAP,
            "brackets": True,
            "no_scale_average": True,
            "skip_chase_past_t1": True,
            "sessions_tagged": "LDLZ 02-05 NY, NYKZ 08:30-11 NY, else other",
            "btc_note": "BTC-USD proxy for MBT @ $0.10/pt; 24h tagged other/LDLZ/NYKZ when in window",
        },
        "gates": {
            "keep": "net>=$3000 OR (qual_days>=3 AND n>=20)",
            "tweak": "net>0 but shy of keep",
            "drop": "flat/negative OR n≈0/overfit (n<5 and |net|<500)",
            "qual_day_usd": QUAL_DAY_USD,
        },
        "strategies_from_live_scan_dict": STRATEGIES_CANON,
        "strategy_tickers": STRATEGY_TICKERS,
        "rank_order": [
            {
                "rank": r["rank"],
                "strategy": r["strategy"],
                "net_pnl": r["net_pnl"],
                "max_dd": r["max_dd"],
                "win_rate_pct": r["win_rate_pct"],
                "n_trades": r["n_trades"],
                "qual_days_ge_250": r["qual_days_ge_250"],
                "ldlz_vs_nykz": r["ldlz_vs_nykz"],
                "instruments_traded": r["instruments_display"],
                "data_source": r["data_source"],
                "verdict": r["verdict"],
                "skip_counts": r["skip_counts"],
                "session": r["session"],
                "best_day": r["best_day"],
                "worst_day": r["worst_day"],
            }
            for r in ranked
        ],
        "side_by_side": [
            {
                "strategy": r["strategy"],
                "net_pnl": r["net_pnl"],
                "max_dd": r["max_dd"],
                "WR": r["win_rate_pct"],
                "n": r["n_trades"],
                "qual_days": r["qual_days_ge_250"],
                "verdict": r["verdict"],
                "data_source": r["data_source"],
            }
            for r in ranked
        ],
    }
    (OUT / "ranking.json").write_text(json.dumps(ranking_payload, indent=2))

    # report.md
    lines = []
    lines.append("# YW-concept setups — Apex-constraint backtest")
    lines.append("")
    lines.append(f"- Generated: {ranking_payload['generated_at_hkt']} (HKT)")
    lines.append(f"- Window: **{WINDOW_START} → {WINDOW_END}** (live_scan attribution; yfinance 5m ~60d max)")
    lines.append("- Parent voices final ranking; this file is facts-only.")
    lines.append("")
    lines.append("## Constraints (match live Apex monitor)")
    lines.append("")
    lines.append("| Rule | Value |")
    lines.append("|---|---|")
    lines.append("| Grades | A/B only (skip C) |")
    lines.append("| Size | 1 Micro |")
    lines.append("| Point values | MNQ $2 · MES $5 · M2K $5 · MGC $10 · BTC→MBT $0.10 |")
    lines.append("| Daily envelope | −$100 kill / +$300 TP cap (no new entries that NY day) |")
    lines.append("| Brackets | recorded SL / T* exits; no scale/average; 1 open/strategy |")
    lines.append("| Chase | skip if entry already past T1 |")
    lines.append("| Sessions | tagged LDLZ 02–05 NY · NYKZ 08:30–11 NY · other |")
    lines.append("")
    lines.append("## Verdict gates")
    lines.append("")
    lines.append("- **keep**: net ≥ $3,000 **OR** (≥3 qual days ≥$250 **AND** n≥20)")
    lines.append("- **tweak**: net > 0 but shy of keep")
    lines.append("- **drop**: flat/negative, or n≈0 / overfit (n<5 & |net|<500)")
    lines.append("")
    lines.append("## STRATEGIES dict (live_scan.py) — names + tickers")
    lines.append("")
    lines.append("| Strategy | Configured tickers |")
    lines.append("|---|---|")
    for s in STRATEGIES_CANON:
        lines.append(f"| {s} | {', '.join(STRATEGY_TICKERS[s])} |")
    lines.append("")
    lines.append("Notes: B1 / B1-3in1 restricted to MNQ+MGC+BTC in live_scan. OCS-BTC-5m is BTC-only (no rows in live_scan signals — supplemented via OCS backtest re-sim).")
    lines.append("")
    lines.append("## Side-by-side (rank order by net P&L)")
    lines.append("")
    lines.append("| Rank | Strategy | Net P&L | Max DD | WR | n | Qual≥$250 | LDLZ vs NYKZ | Instruments | Verdict | Data source |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---|---|---|---|")
    for r in ranked:
        lines.append(
            f"| {r['rank']} | {r['strategy']} | ${r['net_pnl']:+,.2f} | ${r['max_dd']:,.2f} | "
            f"{r['win_rate_pct']:.1f}% | {r['n_trades']} | {r['qual_days_ge_250']} | "
            f"{r['ldlz_vs_nykz']} | {', '.join(r['instruments_display']) or '—'} | "
            f"**{r['verdict']}** | {r['data_source']} |"
        )
    lines.append("")
    lines.append("## Per-strategy detail")
    lines.append("")
    for r in ranked:
        lines.append(f"### {r['rank']}. {r['strategy']} — **{r['verdict']}**")
        lines.append("")
        lines.append(f"- Data source: `{r['data_source']}`")
        lines.append(f"- Configured tickers: {', '.join(r['tickers_configured'])}")
        lines.append(f"- Instruments traded (accepted): {', '.join(r['instruments_display']) or 'none'}")
        lines.append(f"- Net P&L: **${r['net_pnl']:+,.2f}** · Max DD: ${r['max_dd']:,.2f} · WR: {r['win_rate_pct']}% · n={r['n_trades']}")
        lines.append(f"- Qual days ≥$250: {r['qual_days_ge_250']}")
        lines.append(f"- Best day: {r['best_day']} · Worst day: {r['worst_day']}")
        lines.append(f"- Sessions: {r['ldlz_vs_nykz']}")
        lines.append(f"- Skips: `{json.dumps(r['skip_counts'])}`")
        lines.append(f"- A/B candidates before envelope/overlap: {r['n_candidates_ab']}")
        lines.append("")

    lines.append("## Method notes (facts)")
    lines.append("")
    lines.append("1. Primary source is `automation/reports/live_scan/trades.jsonl` joined to strategy attribution already present on each row (same signals that fired live Apex/Telegram path).")
    lines.append("2. Recorded `pnl_usd` in trades.jsonl is **price points**, not micro dollars — converted with POINT_VALUE above.")
    lines.append("3. Grade C trades present in the log were excluded (BLOCK_GRADE_C_OPEN live policy).")
    lines.append("4. Daily −$100 / +$300 applied per strategy independently (each strategy as sole account book).")
    lines.append("5. OCS-BTC-5m has **zero** live_scan signal/trade attribution in-window; any OCS rows come from `ocs_backtest` re-sim only.")
    lines.append("6. No invented trades — empty strategies stay n=0.")
    lines.append("")

    (OUT / "report.md").write_text("\n".join(lines))
    print(json.dumps({"ok": True, "out": str(OUT), "ranks": [(r["strategy"], r["net_pnl"], r["verdict"], r["n_trades"]) for r in ranked]}, indent=2))


if __name__ == "__main__":
    main()
