#!/usr/bin/env python3
"""Daily settlement + −$100 DD hold + LLM Scientist opt wrapper.

Produces:
  automation/reports/daily_settlement/YYYYMMDD_settlement.{json,md}
  automation/state/ops_dd_hold.json   ← live monitors read this

DD rule (configurable defaults matching Ops ask):
  day_pnl = equity_end - equity_start   (Ops book preferred)
  if day_pnl is missing: fall back to sum of closed paper pnl_usd for the HKT day
  if day_pnl <= DD_LIMIT_USD (−100 default) → dd_hold=true
  Unlock: next HKT session auto-clear at settlement if day_pnl > DD_LIMIT,
          OR operator sets clear_hold=true / deletes state / writes unlocked.

LLM:
  After settlement, if not --skip-llm and (dd_hold or end-of-day always):
    if MINIMAX_API_KEY present → invoke llm_iteration_scientist.py
    else → llm_status=llm_blocked (settlement + DD still succeed)

Allowlist (live Ops book): 50-20-Pullback, CRT, Stair, H-Pattern only.

CLI:
  python daily_settlement_llm_opt.py --date YYYY-MM-DD [--book book.json] [--skip-llm]
       [--live-dir PATH] [--clear-hold] [--dd-limit -100] [--tp-limit 300]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HKT = timezone(timedelta(hours=8))

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    # Prefer fuller local clone, then primary path used by other scripts
    for cand in (
        Path("/workspace/YW-concept-ki7409-tmp"),
        Path("/workspace/YW-concept-ki7409"),
        Path(__file__).resolve().parents[2],
    ):
        if (cand / "automation").exists():
            REPO = cand
            break
    else:
        REPO = Path("/workspace/YW-concept-ki7409")

LIVE_DIR_DEFAULT = REPO / "automation" / "reports" / "live_scan"
SETTLE_DIR = REPO / "automation" / "reports" / "daily_settlement"
STATE_DIR = REPO / "automation" / "state"
DD_STATE_FILE = STATE_DIR / "ops_dd_hold.json"
SCIENTIST_SCRIPT = REPO / "automation" / "scripts" / "llm_iteration_scientist.py"

# Configurable envelope defaults (do NOT silently change without documenting)
DD_LIMIT_USD_DEFAULT = -100.0   # −$100 daily DD hold
TP_LIMIT_USD_DEFAULT = 300.0    # +$300 historical daily profit stop (report-only unless Ops book sets)

ALLOWLIST = {
    "50-20-pullback",
    "50-20",
    "crt",
    "stair",
    "stair-pattern",
    "h-pattern",
    "hpattern",
}
ALLOWLIST_DISPLAY = ["50-20-Pullback", "CRT", "Stair", "H-Pattern"]

OPS_LESSONS = [
    "Never treat Order Ticket Limit as sim last (MBT 83660 false OUT_OF_GATE) — use chart/DOM/explicit last.",
    "Bracket SL/TP: prefer paper-anchored absolute levels vs fill-offset when fill ≠ paper; flag drift.",
    "Handoff text must say QTY=1 Bracket (NOT Group QTY20). Ops-only Tradovate; A皮 coordinates.",
    "Live allowlist only: 50-20-Pullback, CRT, Stair, H-Pattern.",
    "Envelope defaults: −$100 DD hold / +$300 TP (historical). Change only with explicit user choice.",
]


def _norm_strategy(name: str) -> str:
    s = (name or "").strip().lower().replace("_", "-")
    s = s.replace(" ", "")
    if s.startswith("50-20"):
        return "50-20-pullback"
    if s in ("stair-pattern", "stairpattern"):
        return "stair"
    if s in ("hpattern", "h-pattern"):
        return "h-pattern"
    if s == "crt":
        return "crt"
    return s


def _is_allowlisted(name: str) -> bool:
    n = _norm_strategy(name)
    return n in ALLOWLIST or any(n.startswith(a) for a in ("50-20", "crt", "stair", "h-pattern"))


def _parse_ts(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    s = str(raw).strip()
    try:
        if "T" in s:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            # e.g. "2026-09-22 15:30:00-04:00"
            dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=HKT)
        return dt.astimezone(HKT)
    except Exception:
        return None


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"_error": str(e), "_path": str(path)}


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("<"):
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _day_bounds(date_str: str) -> tuple[datetime, datetime]:
    d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=HKT)
    return d, d + timedelta(days=1)


def load_book(path: Path | None) -> dict:
    if not path:
        return {}
    data = _load_json(path)
    if not isinstance(data, dict):
        return {}
    return data


def filter_day_trades(trades: list[dict], date_str: str) -> list[dict]:
    start, end = _day_bounds(date_str)
    day: list[dict] = []
    for t in trades:
        # Prefer exit_time for closed P/L attribution; else entry_time
        ts = _parse_ts(t.get("exit_time")) or _parse_ts(t.get("entry_time")) or _parse_ts(t.get("ts"))
        if ts is None:
            continue
        if start <= ts < end:
            day.append(t)
    return day


def filter_day_signals(signals: list[dict], date_str: str) -> list[dict]:
    start, end = _day_bounds(date_str)
    day: list[dict] = []
    for s in signals:
        ts = _parse_ts(s.get("ts")) or _parse_ts(s.get("entry_time")) or _parse_ts(s.get("timestamp"))
        if ts is None:
            continue
        if start <= ts < end:
            day.append(s)
    return day


def summarize_fills(trades: list[dict], book_fills: list[dict] | None) -> dict:
    """Merge Ops fills (if any) with paper trades for allowlisted summary."""
    rows: list[dict] = []
    if book_fills:
        for f in book_fills:
            rows.append(
                {
                    "source": "ops_book",
                    "strategy": f.get("strategy") or f.get("setup") or "",
                    "ticker": f.get("ticker") or f.get("symbol") or "",
                    "side": f.get("side") or f.get("direction") or "",
                    "qty": f.get("qty", 1),
                    "pnl_usd": f.get("pnl_usd", f.get("pnl")),
                    "exit_level": f.get("exit_level") or f.get("result"),
                    "note": f.get("note", ""),
                    "allowlisted": _is_allowlisted(str(f.get("strategy") or f.get("setup") or "")),
                }
            )
    for t in trades:
        strat = t.get("strategy", "")
        rows.append(
            {
                "source": "paper_live_scan",
                "strategy": strat,
                "ticker": t.get("ticker", ""),
                "side": t.get("direction", ""),
                "qty": t.get("qty", 1),
                "pnl_usd": t.get("pnl_usd"),
                "R_multiple": t.get("R_multiple"),
                "exit_level": t.get("exit_level"),
                "grade": t.get("grade"),
                "status": t.get("status"),
                "signal_id": t.get("signal_id"),
                "allowlisted": _is_allowlisted(str(strat)),
            }
        )

    allow = [r for r in rows if r.get("allowlisted")]
    non = [r for r in rows if not r.get("allowlisted")]
    pnl_allow = sum(float(r["pnl_usd"]) for r in allow if r.get("pnl_usd") is not None)
    pnl_all = sum(float(r["pnl_usd"]) for r in rows if r.get("pnl_usd") is not None)
    by_strat: dict[str, dict] = defaultdict(lambda: {"n": 0, "pnl": 0.0, "wins": 0, "losses": 0})
    for r in allow:
        k = _norm_strategy(str(r.get("strategy", ""))) or "unknown"
        by_strat[k]["n"] += 1
        if r.get("pnl_usd") is not None:
            p = float(r["pnl_usd"])
            by_strat[k]["pnl"] += p
            if p > 0:
                by_strat[k]["wins"] += 1
            elif p < 0:
                by_strat[k]["losses"] += 1
    return {
        "n_fills_total": len(rows),
        "n_allowlisted": len(allow),
        "n_non_allowlisted": len(non),
        "pnl_allowlisted_usd": round(pnl_allow, 2),
        "pnl_all_sources_usd": round(pnl_all, 2),
        "by_strategy": {k: dict(v) for k, v in sorted(by_strat.items())},
        "rows": rows[:200],  # cap for report size
    }


def summarize_signals(signals: list[dict]) -> dict:
    allow = [s for s in signals if _is_allowlisted(str(s.get("strategy", "")))]
    gated = [s for s in allow if s.get("gate_blocked") or s.get("gate_skip")]
    fired = [s for s in allow if not (s.get("gate_blocked") or s.get("gate_skip"))]
    by_strat: dict[str, dict] = defaultdict(lambda: {"n": 0, "gated": 0, "fired": 0})
    for s in allow:
        k = _norm_strategy(str(s.get("strategy", "")))
        by_strat[k]["n"] += 1
        if s.get("gate_blocked") or s.get("gate_skip"):
            by_strat[k]["gated"] += 1
        else:
            by_strat[k]["fired"] += 1
    outcomes = []
    for s in allow[-50:]:
        outcomes.append(
            {
                "strategy": s.get("strategy"),
                "ticker": s.get("ticker"),
                "grade": s.get("grade"),
                "direction": s.get("direction") or s.get("side"),
                "gate_skip": s.get("gate_skip"),
                "gate_blocked": bool(s.get("gate_blocked") or s.get("gate_skip")),
                "confidence": s.get("confidence"),
            }
        )
    return {
        "n_allowlisted": len(allow),
        "n_gated": len(gated),
        "n_fired_or_ungated": len(fired),
        "by_strategy": {k: dict(v) for k, v in sorted(by_strat.items())},
        "outcomes_tail": outcomes,
    }


def detect_bracket_drift(book: dict, positions: list) -> list[str]:
    flags: list[str] = []
    notes = book.get("ops_notes") or book.get("notes") or []
    if isinstance(notes, str):
        notes = [notes]
    for n in notes:
        low = str(n).lower()
        if "fill-offset" in low or "fill_anchored" in low or "paper-anchored" in low or "drift" in low:
            flags.append(str(n))
    for f in book.get("fills") or []:
        paper_sl = f.get("paper_sl")
        fill_sl = f.get("fill_sl") or f.get("attached_sl")
        if paper_sl is not None and fill_sl is not None:
            try:
                if abs(float(paper_sl) - float(fill_sl)) > 1e-6:
                    flags.append(
                        f"SL drift {f.get('strategy')}/{f.get('ticker')}: paper_sl={paper_sl} vs fill_sl={fill_sl}"
                    )
            except Exception:
                pass
        paper_tp = f.get("paper_t1") or f.get("paper_tp")
        fill_tp = f.get("fill_t1") or f.get("attached_tp")
        if paper_tp is not None and fill_tp is not None:
            try:
                if abs(float(paper_tp) - float(fill_tp)) > 1e-6:
                    flags.append(
                        f"TP drift {f.get('strategy')}/{f.get('ticker')}: paper_t1={paper_tp} vs fill_t1={fill_tp}"
                    )
            except Exception:
                pass
    # Handoff qty policy reminder if book mentions Group QTY20
    handoff = str(book.get("last_handoff") or "")
    if re.search(r"group\s*qty\s*20", handoff, re.I):
        flags.append("Handoff text contains Group QTY20 — live policy is QTY=1 Bracket")
    for p in positions or []:
        # open paper legs — report only
        pass
    if book.get("false_out_of_gate"):
        flags.append(
            f"false_out_of_gate noted: {book.get('false_out_of_gate')} "
            "(never use Order Ticket Limit as sim last)"
        )
    return flags


def compute_equity(book: dict, fills_summary: dict, dd_limit: float) -> dict:
    eq_start = book.get("equity_start")
    eq_end = book.get("equity_end")
    open_pl = book.get("open_pl", book.get("open_pnl"))
    working = book.get("working_count", book.get("working"))
    day_pnl = book.get("day_pnl")
    source = "ops_book"

    if day_pnl is None and eq_start is not None and eq_end is not None:
        try:
            day_pnl = float(eq_end) - float(eq_start)
            source = "ops_book_equity_delta"
        except Exception:
            day_pnl = None

    if day_pnl is None:
        # Fall back to paper allowlisted closed PnL
        day_pnl = float(fills_summary.get("pnl_allowlisted_usd") or 0.0)
        source = "paper_allowlisted_pnl_fallback"
        if eq_start is None:
            eq_start = None
        if eq_end is None and eq_start is not None:
            try:
                eq_end = float(eq_start) + float(day_pnl)
            except Exception:
                pass

    try:
        day_pnl_f = float(day_pnl) if day_pnl is not None else 0.0
    except Exception:
        day_pnl_f = 0.0
        source = "parse_error_zero"

    # Session high vs day-start: if book provides session_high_equity, DD vs peak;
    # else DD vs day-start equity (day_pnl).
    session_high = book.get("session_high_equity")
    dd_vs = "day_start"
    dd_amount = day_pnl_f
    if session_high is not None and eq_end is not None:
        try:
            drop = float(eq_end) - float(session_high)
            # more negative = larger DD from peak
            if drop < day_pnl_f:
                dd_amount = drop
                dd_vs = "session_high"
        except Exception:
            pass

    dd_hold = dd_amount <= float(dd_limit)
    return {
        "equity_start": eq_start,
        "equity_end": eq_end,
        "open_pl": open_pl,
        "working_count": working,
        "day_pnl": round(day_pnl_f, 2),
        "dd_amount": round(float(dd_amount), 2),
        "dd_vs": dd_vs,
        "dd_limit_usd": float(dd_limit),
        "dd_hold": bool(dd_hold),
        "pnl_source": source,
        "account": book.get("account") or book.get("book_id") or "PAAPEX…091",
        "session_high_equity": session_high,
    }


def write_dd_state(
    equity: dict,
    date_str: str,
    clear_hold: bool = False,
) -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(HKT)
    if clear_hold:
        state = {
            "dd": "unlocked",
            "dd_hold": False,
            "cleared_at_hkt": now.strftime("%Y-%m-%d %H:%M HKT"),
            "cleared_by": "daily_settlement_llm_opt --clear-hold",
            "date": date_str,
            "dd_limit_usd": equity.get("dd_limit_usd", DD_LIMIT_USD_DEFAULT),
            "path": str(DD_STATE_FILE.relative_to(REPO)) if DD_STATE_FILE.is_relative_to(REPO) else str(DD_STATE_FILE),
        }
    elif equity["dd_hold"]:
        state = {
            "dd": "held",
            "dd_hold": True,
            "held_at_hkt": now.strftime("%Y-%m-%d %H:%M HKT"),
            "date": date_str,
            "day_pnl": equity["day_pnl"],
            "dd_amount": equity["dd_amount"],
            "dd_vs": equity["dd_vs"],
            "dd_limit_usd": equity["dd_limit_usd"],
            "reason": f"day DD {equity['dd_amount']} <= {equity['dd_limit_usd']} (vs {equity['dd_vs']})",
            "unlock": "next HKT session settlement if day_pnl > limit, or operator --clear-hold / set dd=unlocked",
            "no_new_entries": True,
            "account": equity.get("account"),
            "path": str(DD_STATE_FILE.relative_to(REPO)) if DD_STATE_FILE.is_relative_to(REPO) else str(DD_STATE_FILE),
        }
    else:
        state = {
            "dd": "unlocked",
            "dd_hold": False,
            "updated_at_hkt": now.strftime("%Y-%m-%d %H:%M HKT"),
            "date": date_str,
            "day_pnl": equity["day_pnl"],
            "dd_amount": equity["dd_amount"],
            "dd_limit_usd": equity["dd_limit_usd"],
            "no_new_entries": False,
            "account": equity.get("account"),
            "path": str(DD_STATE_FILE.relative_to(REPO)) if DD_STATE_FILE.is_relative_to(REPO) else str(DD_STATE_FILE),
        }
    DD_STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return state


def minimax_available() -> bool:
    key = (os.environ.get("MINIMAX_API_KEY") or "").strip()
    return bool(key)


def run_scientist(skip: bool) -> dict:
    if skip:
        return {
            "llm_status": "skipped",
            "reason": "--skip-llm",
            "scientist_invoked": False,
        }
    if not minimax_available():
        return {
            "llm_status": "llm_blocked",
            "reason": "MINIMAX_API_KEY missing/empty — settlement+DD OK; restore secret to enable Scientist",
            "scientist_invoked": False,
            "fallback_note": "Scientist rule-based path never auto-applies (conf path requires MiniMax)",
        }
    if not SCIENTIST_SCRIPT.exists():
        return {
            "llm_status": "llm_blocked",
            "reason": f"scientist script not found: {SCIENTIST_SCRIPT}",
            "scientist_invoked": False,
        }
    try:
        proc = subprocess.run(
            [sys.executable, str(SCIENTIST_SCRIPT)],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=600,
            env={**os.environ},
        )
        # Find newest scientist report
        iter_dir = REPO / "automation" / "reports" / "strategy_ranking" / "iterations"
        latest = None
        if iter_dir.exists():
            cands = sorted(iter_dir.glob("iteration_scientist_*.json"), key=lambda p: p.stat().st_mtime)
            if cands:
                latest = str(cands[-1].relative_to(REPO)) if cands[-1].is_relative_to(REPO) else str(cands[-1])
        status = "ok" if proc.returncode == 0 else "llm_error"
        return {
            "llm_status": status,
            "scientist_invoked": True,
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-1500:],
            "stderr_tail": (proc.stderr or "")[-800:],
            "latest_report": latest,
        }
    except subprocess.TimeoutExpired:
        return {
            "llm_status": "llm_error",
            "reason": "scientist timeout (>600s)",
            "scientist_invoked": True,
        }
    except Exception as e:
        return {
            "llm_status": "llm_error",
            "reason": str(e),
            "scientist_invoked": True,
        }


def ops_briefing(
    equity: dict,
    fills: dict,
    signals: dict,
    llm: dict,
    drift_flags: list[str],
    date_str: str,
) -> list[str]:
    bullets: list[str] = []
    bullets.append(
        f"Settlement {date_str} HKT · {equity.get('account')} · "
        f"day P/L ${equity['day_pnl']:+.2f} (src={equity['pnl_source']}) · "
        f"DD {equity['dd_amount']:+.2f} vs limit {equity['dd_limit_usd']}"
    )
    if equity["dd_hold"]:
        bullets.append(
            f"⛔ DD HOLD active — no new entries (state: automation/state/ops_dd_hold.json). "
            f"Tell Trading desk once. Unlock next session or --clear-hold."
        )
    else:
        bullets.append("✅ DD unlocked — under −$100 limit.")
    bullets.append(
        f"Allowlist fills: n={fills['n_allowlisted']} pnl=${fills['pnl_allowlisted_usd']:+.2f}; "
        f"signals allow n={signals['n_allowlisted']} gated={signals['n_gated']}"
    )
    by = fills.get("by_strategy") or {}
    if by:
        parts = [f"{k}: n={v['n']} pnl=${v['pnl']:+.1f}" for k, v in by.items()]
        bullets.append("By strategy — " + "; ".join(parts))
    if drift_flags:
        bullets.append("Flags: " + " | ".join(drift_flags[:5]))
    bullets.append(
        "Policy: QTY=1 Bracket only (NOT Group QTY20); never use Order Ticket Limit as sim last."
    )
    ls = llm.get("llm_status")
    if ls == "llm_blocked":
        bullets.append(
            f"LLM blocked: {llm.get('reason')} — remind MiniMax secret once; do not invent parallel optimizer."
        )
    elif ls == "skipped":
        bullets.append("LLM step skipped (--skip-llm).")
    elif ls == "ok":
        bullets.append(f"LLM Scientist ran OK; report={llm.get('latest_report')}")
    else:
        bullets.append(f"LLM status={ls}: {llm.get('reason') or llm.get('returncode')}")
    bullets.append("Never re-handoff stale/gated/null-position signals; stay quiet if nothing changed.")
    return bullets


def render_markdown(report: dict) -> str:
    eq = report["equity"]
    llm = report["llm"]
    fills = report["fills"]
    sig = report["signals"]
    lines = [
        f"# Daily Settlement — {report['date_hkt']} (HKT)",
        "",
        f"**Account:** {eq.get('account')}  ",
        f"**Generated:** {report['generated_at_hkt']}  ",
        f"**DD state file:** `{report['dd_state_path']}`  ",
        "",
        "## Equity / DD",
        f"- Equity start: `{eq.get('equity_start')}`",
        f"- Equity end: `{eq.get('equity_end')}`",
        f"- Open P/L: `{eq.get('open_pl')}` · Working: `{eq.get('working_count')}`",
        f"- Day P/L: **${eq['day_pnl']:+.2f}** (source: `{eq['pnl_source']}`)",
        f"- DD amount: **${eq['dd_amount']:+.2f}** vs `{eq['dd_vs']}` · limit **{eq['dd_limit_usd']}**",
        f"- **dd_hold: `{eq['dd_hold']}`** · tp_limit_usd (report-only default): `{report.get('tp_limit_usd')}`",
        "",
        "## Fills (allowlist focus)",
        f"- Total rows: {fills['n_fills_total']} · allowlisted: {fills['n_allowlisted']} · "
        f"non-allow: {fills['n_non_allowlisted']}",
        f"- Allowlisted PnL: **${fills['pnl_allowlisted_usd']:+.2f}**",
        "",
    ]
    if fills.get("by_strategy"):
        lines.append("| Strategy | n | wins | losses | pnl |")
        lines.append("|----------|---|------|--------|-----|")
        for k, v in fills["by_strategy"].items():
            lines.append(f"| {k} | {v['n']} | {v['wins']} | {v['losses']} | ${v['pnl']:+.2f} |")
        lines.append("")
    lines += [
        "## Allowlisted signal outcomes",
        f"- n={sig['n_allowlisted']} · gated={sig['n_gated']} · fired/ungated={sig['n_fired_or_ungated']}",
        "",
        "## LLM",
        f"- status: **`{llm.get('llm_status')}`**",
        f"- invoked: `{llm.get('scientist_invoked')}`",
        f"- detail: {llm.get('reason') or llm.get('latest_report') or llm.get('returncode')}",
        "",
        "## Ops briefing bullets",
    ]
    for b in report["ops_briefing"]:
        lines.append(f"- {b}")
    lines += ["", "## Ops lessons (folded)", ""]
    for lesson in report["ops_lessons"]:
        lines.append(f"- {lesson}")
    if report.get("drift_flags"):
        lines += ["", "## Drift / ticket flags", ""]
        for f in report["drift_flags"]:
            lines.append(f"- {f}")
    lines += [
        "",
        "## Live scan snapshot",
        f"- positions open: {report['live_scan'].get('n_positions')}",
        f"- heartbeat: `{report['live_scan'].get('heartbeat_ts')}`",
        f"- circuit_breaker: `{report['live_scan'].get('circuit_breaker')}`",
        "",
        "## Config defaults (documented)",
        f"- DD_LIMIT_USD = {report['dd_limit_usd']} (hold when day DD ≤ this)",
        f"- TP_LIMIT_USD = {report['tp_limit_usd']} (historical +$300 envelope; not auto-enforced here)",
        "",
    ]
    return "\n".join(lines) + "\n"


def build_report(
    date_str: str,
    book: dict,
    live_dir: Path,
    skip_llm: bool,
    clear_hold: bool,
    dd_limit: float,
    tp_limit: float,
) -> dict:
    SETTLE_DIR.mkdir(parents=True, exist_ok=True)
    trades = _load_jsonl(live_dir / "trades.jsonl")
    signals = _load_jsonl(live_dir / "signals.jsonl")
    positions = _load_json(live_dir / "positions.json") or []
    if isinstance(positions, dict):
        positions = positions.get("positions") or positions.get("open") or []
    heartbeat = _load_json(live_dir / "heartbeat.json") or {}
    circuit = _load_json(live_dir / "circuit_breaker.json")
    if circuit is None:
        circuit = heartbeat.get("circuit_breaker") or {}

    day_trades = filter_day_trades(trades, date_str)
    day_signals = filter_day_signals(signals, date_str)
    fills = summarize_fills(day_trades, book.get("fills"))
    sig_sum = summarize_signals(day_signals)
    equity = compute_equity(book, fills, dd_limit)
    if clear_hold:
        equity["dd_hold"] = False
    dd_state = write_dd_state(equity, date_str, clear_hold=clear_hold)
    drift = detect_bracket_drift(book, positions if isinstance(positions, list) else [])

    # End-of-day settlement always attempts LLM unless skipped
    llm = run_scientist(skip=skip_llm)

    now = datetime.now(HKT)
    ymd = date_str.replace("-", "")
    dd_path = "automation/state/ops_dd_hold.json"
    report = {
        "date_hkt": date_str,
        "date_ymd": ymd,
        "generated_at_hkt": now.strftime("%Y-%m-%d %H:%M:%S HKT"),
        "repo": str(REPO),
        "account": equity.get("account"),
        "equity": equity,
        "dd_hold": equity["dd_hold"] if not clear_hold else False,
        "dd_state": dd_state,
        "dd_state_path": dd_path,
        "dd_limit_usd": dd_limit,
        "tp_limit_usd": tp_limit,
        "fills": fills,
        "signals": sig_sum,
        "llm": llm,
        "drift_flags": drift,
        "ops_lessons": OPS_LESSONS,
        "ops_briefing": [],
        "live_scan": {
            "live_dir": str(live_dir),
            "n_positions": len(positions) if isinstance(positions, list) else 0,
            "positions": positions if isinstance(positions, list) else [],
            "heartbeat_ts": heartbeat.get("timestamp") if isinstance(heartbeat, dict) else None,
            "heartbeat": heartbeat if isinstance(heartbeat, dict) else {},
            "circuit_breaker": circuit,
            "n_day_trades": len(day_trades),
            "n_day_signals": len(day_signals),
        },
        "allowlist": ALLOWLIST_DISPLAY,
        "book_path": book.get("_path"),
    }
    report["ops_briefing"] = ops_briefing(equity, fills, sig_sum, llm, drift, date_str)

    json_path = SETTLE_DIR / f"{ymd}_settlement.json"
    md_path = SETTLE_DIR / f"{ymd}_settlement.md"
    # Avoid huge nested rows in committed JSON? Keep but cap already applied.
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    report["_outputs"] = {
        "json": str(json_path),
        "md": str(md_path),
        "dd_state": str(DD_STATE_FILE),
    }
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Daily settlement + $100 DD + LLM Scientist wrap")
    ap.add_argument("--date", required=True, help="Settlement date YYYY-MM-DD (HKT)")
    ap.add_argument("--book", default=None, help="Ops daily book JSON path")
    ap.add_argument("--skip-llm", action="store_true", help="Skip Scientist invoke")
    ap.add_argument("--clear-hold", action="store_true", help="Force unlock DD hold state")
    ap.add_argument("--live-dir", default=None, help="Override live_scan artifacts dir")
    ap.add_argument("--dd-limit", type=float, default=DD_LIMIT_USD_DEFAULT, help="DD hold threshold (default -100)")
    ap.add_argument("--tp-limit", type=float, default=TP_LIMIT_USD_DEFAULT, help="TP envelope report-only (default +300)")
    ap.add_argument("--out-copy", default=None, help="Optional extra directory to copy reports into")
    args = ap.parse_args(argv)

    # Validate date
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print(f"ERROR: --date must be YYYY-MM-DD, got {args.date}", file=sys.stderr)
        return 2

    book: dict = {}
    if args.book:
        bp = Path(args.book)
        book = load_book(bp)
        book["_path"] = str(bp)

    live_dir = Path(args.live_dir) if args.live_dir else LIVE_DIR_DEFAULT
    # Fallback: workspace live_scan_check root copies
    if not (live_dir / "trades.jsonl").exists():
        alt = Path("/workspace/live_scan_check")
        if (alt / "trades.jsonl").exists() or (alt / "trades_full.jsonl").exists():
            live_dir = alt

    report = build_report(
        date_str=args.date,
        book=book,
        live_dir=live_dir,
        skip_llm=args.skip_llm,
        clear_hold=args.clear_hold,
        dd_limit=args.dd_limit,
        tp_limit=args.tp_limit,
    )

    if args.out_copy:
        out = Path(args.out_copy)
        out.mkdir(parents=True, exist_ok=True)
        ymd = report["date_ymd"]
        for src in (
            SETTLE_DIR / f"{ymd}_settlement.json",
            SETTLE_DIR / f"{ymd}_settlement.md",
            DD_STATE_FILE,
        ):
            if src.exists():
                dest = out / src.name
                dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "date_hkt": report["date_hkt"],
        "day_pnl": report["equity"]["day_pnl"],
        "dd_hold": report["dd_hold"],
        "llm_status": report["llm"].get("llm_status"),
        "outputs": report.get("_outputs"),
        "ops_briefing": report["ops_briefing"][:4],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
