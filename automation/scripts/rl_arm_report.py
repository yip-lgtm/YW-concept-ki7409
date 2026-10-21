#!/usr/bin/env python3
"""A/B report — realised performance of the RL exit policy vs the control arm.

User directive (2026-10-20): "要" (the control group).

The RL exit policy is judged on replayed trades in rl_iterate.py, which is
necessary for learning but is not proof: replay assumes the entries would
have been the same under a different exit. This report is the realised
check. It groups closed trades by the arm that was frozen into the
position when it was opened, and compares the two arms on the strategies
that both arms have traded.

  RL       the learned per-strategy exit configuration
  CONTROL  the book's shared template (1.6xATR stop, T2 close at 1.618R)

Because the arm alternates inside the same strategy, the comparison is
within-strategy: strategy quality cancels out and what remains is the exit
policy's effect. The market regime is not controlled, so each arm's date
span is printed, and the report says so rather than implying a clean
randomised trial.

A trade is only counted once it has actually closed. Open positions are
reported separately.
"""
from __future__ import annotations
import os
import sys
import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

def _find_repo() -> Path:
    """Locate the repo root without hard-coding one machine's path.

    The hard-coded fallback used to be /workspace/YW-concept-ki7409. On any
    other checkout the trades file was never found, so the A/B report
    printed "no closed trades" and looked like a data problem when it was
    really a path problem. CI sets GITHUB_WORKSPACE and is unaffected.
    """
    if "GITHUB_WORKSPACE" in os.environ:
        return Path(os.environ["GITHUB_WORKSPACE"])
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "automation" / "reports").is_dir():
            return parent
    return Path("/workspace/YW-concept-ki7409")


REPO = _find_repo()

HKT = timezone(timedelta(hours=8))
TRADES_FILE = REPO / "automation/reports/live_scan/trades.jsonl"
POSITIONS_FILE = REPO / "automation/reports/live_scan/positions.json"
REPORT_DIR = REPO / "automation/reports/rl_iteration"

ARM_RL = "RL"
ARM_CONTROL = "CONTROL"


def log(msg: str):
    print(f"[rl-ab] {msg}", flush=True)


def _norm(name: str) -> str:
    return "".join(c for c in str(name).lower() if c.isalnum())


def load_trades() -> list[dict]:
    out = []
    if not TRADES_FILE.exists():
        return out
    with open(TRADES_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line[0] in "<=>":
                continue
            try:
                t = json.loads(line)
            except Exception:
                continue
            if t.get("status") == "closed":
                out.append(t)
    return out


def stats(trades: list[dict]) -> dict:
    n = len(trades)
    if n == 0:
        return {"n": 0, "wins": 0, "wr": 0.0, "pf": 0.0, "total_r": 0.0,
                "avg_r": 0.0, "pnl": 0.0, "first": None, "last": None}
    R = [float(t.get("R_multiple", 0) or 0) for t in trades]
    wins = [r for r in R if r > 0]
    losses = [r for r in R if r <= 0]
    gw = sum(wins); gl = abs(sum(losses))
    pf = gw / gl if gl > 0 else (10.0 if gw > 0 else 0.0)
    dates = sorted(str(t.get("exit_time") or "") for t in trades)
    return {
        "n": n,
        "wins": len(wins),
        "wr": round(len(wins) / n * 100, 1),
        "pf": round(pf, 2),
        "total_r": round(sum(R), 2),
        "avg_r": round(sum(R) / n, 4),
        "pnl": round(sum(float(t.get("pnl_usd", 0) or 0) for t in trades), 2),
        "first": dates[0][:16] if dates else None,
        "last": dates[-1][:16] if dates else None,
    }


def main() -> int:
    day = datetime.now(HKT).strftime("%Y-%m-%d")
    log(f"=== RL exit policy A/B — {day} ===")

    trades = load_trades()
    if not trades:
        log("no closed trades")
        return 0

    # Only trades that carry an arm label are part of the experiment.
    # Everything else predates the A/B or is a strategy with no override.
    armed = [t for t in trades if t.get("exit_arm")]
    unlabelled = len(trades) - len(armed)
    log(f"{len(trades)} closed trades, {len(armed)} carry an arm label "
        f"({unlabelled} predate the A/B)")

    by_arm = defaultdict(list)
    by_strat_arm = defaultdict(lambda: defaultdict(list))
    for t in armed:
        arm = t.get("exit_arm", ARM_CONTROL)
        by_arm[arm].append(t)
        by_strat_arm[_norm(t.get("strategy", ""))][arm].append(t)

    rl = stats(by_arm.get(ARM_RL, []))
    ctl = stats(by_arm.get(ARM_CONTROL, []))
    log(f"  RL arm:      {rl['n']} trades, {rl['total_r']:+.2f}R, WR {rl['wr']}%, PF {rl['pf']}")
    log(f"  CONTROL arm: {ctl['n']} trades, {ctl['total_r']:+.2f}R, WR {ctl['wr']}%, PF {ctl['pf']}")
    if rl["n"] and ctl["n"]:
        log(f"  difference:  {rl['total_r'] - ctl['total_r']:+.2f}R over "
            f"{rl['n']} vs {ctl['n']} trades")

    # Only strategies present in BOTH arms support a fair comparison.
    both = {s: v for s, v in by_strat_arm.items()
            if v.get(ARM_RL) and v.get(ARM_CONTROL)}
    log(f"  strategies traded under both arms: {len(both)}/{len(by_strat_arm)}")
    if both:
        rl_only = sum(stats(v[ARM_RL])["total_r"] for v in both.values())
        ctl_only = sum(stats(v[ARM_CONTROL])["total_r"] for v in both.values())
        log(f"  within-strategy difference: RL {rl_only:+.2f}R vs CONTROL {ctl_only:+.2f}R "
            f"({rl_only - ctl_only:+.2f}R)")

    # Open positions under the arm
    open_by_arm = defaultdict(int)
    if POSITIONS_FILE.exists():
        try:
            pos = json.loads(POSITIONS_FILE.read_text())
            for p in (pos if isinstance(pos, list) else pos.get("positions", [])):
                if p.get("status") == "open":
                    open_by_arm[p.get("exit_arm", "unlabelled")] += 1
        except Exception:
            pass
    if open_by_arm:
        log(f"  open positions: {dict(open_by_arm)}")

    # ---- report ----
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "date": day,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_closed_total": len(trades),
        "n_armed": len(armed),
        "n_unlabelled": unlabelled,
        "rl": rl,
        "control": ctl,
        "difference_r": round(rl["total_r"] - ctl["total_r"], 2),
        "n_strategies_both_arms": len(both),
        "within_strategy": {
            "rl_total_r": round(sum(stats(v[ARM_RL])["total_r"] for v in both.values()), 2),
            "control_total_r": round(sum(stats(v[ARM_CONTROL])["total_r"] for v in both.values()), 2),
        } if both else None,
        "open_by_arm": dict(open_by_arm),
        "per_strategy": {
            s: {a: stats(v[a]) for a in v}
            for s, v in sorted(by_strat_arm.items())
        },
        "caveat": ("The arm alternates inside each strategy, so strategy quality "
                   "cancels out of the comparison. The market regime is NOT "
                   "controlled: the two arms do not see the same price path, and "
                   "each arm's date span is reported so the reader can judge it. "
                   "This is a crossover, not a randomised trial."),
    }
    (REPORT_DIR / f"ab_{day}.json").write_text(json.dumps(report, indent=2,
                                                          ensure_ascii=False,
                                                          default=str))

    md = [f"# RL Exit Policy — A/B — {day}", "",
          f"{len(armed)} closed trades carry an arm label "
          f"({unlabelled} predate the A/B).", "",
          "| Arm | n | Wins | WR | PF | Total R | Avg R | P&L | From | To |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for name, st in (("RL", rl), ("CONTROL", ctl)):
        md.append(f"| {name} | {st['n']} | {st['wins']} | {st['wr']}% | {st['pf']} | "
                  f"{st['total_r']:+.2f}R | {st['avg_r']:+.4f} | ${st['pnl']:+,.0f} | "
                  f"{st['first'] or '—'} | {st['last'] or '—'} |")
    if rl["n"] and ctl["n"]:
        md.append(f"| **Difference** | | | | | **{rl['total_r']-ctl['total_r']:+.2f}R** | | | | |")
    md += ["", "## Within-strategy (both arms)", ""]
    if both:
        md.append("| Strategy | RL n | RL R | CTRL n | CTRL R | Diff |")
        md.append("|---|---|---|---|---|---|")
        for s, v in sorted(both.items()):
            a = stats(v[ARM_RL]); b = stats(v[ARM_CONTROL])
            md.append(f"| {s} | {a['n']} | {a['total_r']:+.2f}R | {b['n']} | "
                      f"{b['total_r']:+.2f}R | {a['total_r']-b['total_r']:+.2f}R |")
    else:
        md.append("_No strategy has traded under both arms yet. The crossover "
                  "needs at least one period per arm before it can say anything._")
    if open_by_arm:
        md += ["", "## Open positions", "",
               "| Arm | Count |", "|---|---|"]
        for a, c in open_by_arm.items():
            md.append(f"| {a} | {c} |")
    md += ["", "## Caveat", "", report["caveat"]]
    (REPORT_DIR / f"ab_{day}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    log(f"report -> ab_{day}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
