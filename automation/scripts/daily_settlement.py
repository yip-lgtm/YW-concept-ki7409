#!/usr/bin/env python3
"""Daily settlement — per-agent level promotion logic.

User directive (9/22 → 10/07):
  For each strategy (agent), if over the last 7 days:
    PF > 1.0  AND  WR > 0.5  AND  RR > 1.0
  AND n_trades >= 10
  THEN level += 1 (升 1 lv), capped at max_level (default 5).

Output:
  - automation/reports/strategy_settlement/settlement_YYYY-MM-DD.md
  - automation/reports/strategy_settlement/settlement_YYYY-MM-DD.json
  - automation/config/strategy_levels.json (updated state)

Schedule: runs as part of daily strategy-ranking.yml at 00:00 HKT.
"""
from __future__ import annotations
import os
import sys
import json
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from pathlib import Path

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")


def load_agent_overrides() -> dict:
    """Load per-agent threshold overrides (managed by settlement_llm_intervene.py).

    Returns {agent_name: {"min_PF": x, "min_WR": y, "min_RR": z, "min_trades": n}}
    LLM writes these to lower conditions for agents stuck in the neutral zone.
    """
    ov_path = REPO / "automation" / "config" / "settlement_overrides.json"
    if not ov_path.exists():
        return {}
    try:
        data = json.loads(ov_path.read_text())
        out = {}
        for k, v in data.items():
            if k.startswith("_") or not isinstance(v, dict):
                continue
            ov = v.get("overrides")
            if ov and isinstance(ov, dict):
                out[k] = ov
        return out
    except Exception as e:
        print(f"[settlement] WARN: overrides read failed: {e}", file=sys.stderr)
        return {}


def load_ranking_settings() -> dict:
    """Load ranking settings, merging per-agent overrides for each agent."""
    cfg_path = REPO / "automation" / "config" / "ranking_settings.json"
    if not cfg_path.exists():
        return _DEFAULTS
    try:
        s = json.loads(cfg_path.read_text())
        # Merge settlement config with defaults (don't overwrite defaults if missing)
        cfg = s.get("daily_settlement", {})
        merged = {**_DEFAULTS, **cfg}
        return merged
    except Exception as e:
        print(f"[settlement] WARN: load settings failed: {e}; using defaults", file=sys.stderr)
        return _DEFAULTS


_DEFAULTS = {
    "enabled": True,
    "window_days": 7,
    "min_trades": 10,
    "min_PF": 1.0,
    "min_WR": 0.5,
    "min_RR": 1.0,
    "max_level": 5,
    "min_level": 1,
    "default_level": 1,
    "decrement_on_fail": True,
    "log_path": "automation/reports/strategy_settlement/",
    "state_path": "automation/config/strategy_levels.json",
}


# Strategy list — must match live_scan.py STRATEGIES + OCS-BTC-5m
AGENT_NAMES = [
    "H-Pattern", "3-Pushes", "Two-Yang", "RSI-Div", "50-20-Pullback",
    "Stair", "B1", "B1-3in1", "Kell-Cycle", "CRT", "OCS-BTC-5m",
]


def parse_iso(ts: str) -> datetime | None:
    """Parse ISO timestamp with mixed tz → UTC datetime."""
    if not ts:
        return None
    try:
        ts = ts.replace("Z", "+00:00").replace(" ", "T")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def load_strategy_trades(window_days: int) -> dict[str, list[dict]]:
    """Read trades.jsonl from both live_scan + OCS BTC, group by strategy.

    Returns {strategy_name: [trade_dict, ...]} filtered to last window_days.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    by_strat: dict[str, list[dict]] = defaultdict(list)

    paths = [
        (REPO / "automation" / "reports" / "live_scan" / "trades.jsonl", "live_scan"),
        (REPO / "automation" / "reports" / "ocs_btc_5m" / "trades.jsonl", "ocs"),
    ]

    for path, source in paths:
        if not path.exists():
            continue
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith(("<", "=", ">")):
                        continue
                    try:
                        t = json.loads(line)
                    except Exception:
                        continue
                    # Skip open positions
                    if t.get("status") != "closed":
                        continue
                    et = parse_iso(t.get("exit_time", ""))
                    if not et or et < cutoff:
                        continue
                    # Strategy assignment: OCS has no field, mark as OCS-BTC-5m
                    if source == "ocs":
                        t["strategy"] = "OCS-BTC-5m"
                    by_strat[t["strategy"]].append(t)
        except FileNotFoundError:
            pass

    return by_strat


def compute_metrics(trades: list[dict]) -> dict:
    """Compute PF, WR, RR for a list of closed trades.

    - PF = gross_win_R / |gross_loss_R|
    - WR = n_wins / n_trades
    - RR = avg_win_R / |avg_loss_R|

    All in R_multiple terms (R-normalized).
    """
    n = len(trades)
    if n == 0:
        return {"n_trades": 0, "wins": 0, "losses": 0, "win_rate": 0,
                "profit_factor": 0, "rr_ratio": 0,
                "total_pnl_usd": 0, "total_R": 0}

    r_vals = [float(t.get("R_multiple", 0)) for t in trades]
    pnl = sum(float(t.get("pnl_usd", 0)) for t in trades)
    wins = [r for r in r_vals if r > 0]
    losses = [r for r in r_vals if r <= 0]
    n_w = len(wins)
    n_l = len(losses)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))  # losses are negative
    pf = gross_win / gross_loss if gross_loss > 0 else (10.0 if gross_win > 0 else 0.0)
    wr = n_w / n
    avg_win = (gross_win / n_w) if n_w > 0 else 0
    avg_loss = (abs(sum(losses)) / n_l) if n_l > 0 else 0
    rr = avg_win / avg_loss if avg_loss > 0 else (10.0 if avg_win > 0 else 0.0)

    return {
        "n_trades": n,
        "wins": n_w,
        "losses": n_l,
        "win_rate": round(wr, 4),
        "profit_factor": round(pf, 3),
        "rr_ratio": round(rr, 3),
        "avg_win_R": round(avg_win, 3),
        "avg_loss_R": round(avg_loss, 3),
        "total_pnl_usd": round(pnl, 2),
        "total_R": round(sum(r_vals), 3),
    }


def load_levels_state() -> dict:
    """Load current strategy levels (or seed with defaults)."""
    state_path = REPO / "automation" / "config" / "strategy_levels.json"
    if not state_path.exists():
        return {name: {"level": 1, "last_settled": None, "history": []}
                for name in AGENT_NAMES}
    try:
        return json.loads(state_path.read_text())
    except Exception as e:
        print(f"[settlement] WARN: levels state read failed: {e}; using defaults",
              file=sys.stderr)
        return {name: {"level": 1, "last_settled": None, "history": []}
                for name in AGENT_NAMES}


def save_levels_state(state: dict):
    """Persist current levels + history."""
    state_path = REPO / "automation" / "config" / "strategy_levels.json"
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def make_settlement_markdown(results: list[dict], date_str: str,
                            settings: dict) -> str:
    """Generate daily settlement report."""
    min_n = settings["min_trades"]
    min_pf = settings["min_PF"]
    min_wr = settings["min_WR"]
    min_rr = settings["min_RR"]
    max_lv = settings["max_level"]
    min_lv = settings.get("min_level", 1)
    decrement = settings.get("decrement_on_fail", False)

    # Each result has metrics.n_trades — that's where n lives
    def n(r): return r.get("metrics", {}).get("n_trades", 0)

    promoted = [r for r in results if r.get("promoted")]
    demoted = [r for r in results if r.get("demoted")]
    held = [r for r in results if not r.get("promoted") and not r.get("demoted") and n(r) >= min_n]
    insufficient = [r for r in results if n(r) < min_n]

    md = f"""# Daily Settlement — {date_str}

## Rule (Symmetric)
For each agent, over the **{settings['window_days']}d** rolling window:
- **PROMOTE** (升 1 lv) if: **PF > {min_pf}** AND **WR > {min_wr}** AND **RR > {min_rr}** AND **n ≥ {min_n}**
  - cap at **{max_lv}**
- **DEMOTE** (降 1 lv) if: **PF ≤ {min_pf}** AND **WR ≤ {min_wr}** AND **RR ≤ {min_rr}** AND **n ≥ {min_n}**
  - enabled: **{decrement}** (10/07 user directive)
  - floor at **{min_lv}**
- Otherwise: **stay flat** (neutral zone — 1-2 of 3 conditions fail)

## Promoted ({len(promoted)} agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|
"""
    for r in promoted:
        old = r.get("old_level", 1)
        new = r.get("new_level", 2)
        m = r["metrics"]
        md += f"| {r['strategy']} | {old} → {new} ⬆ | {m['n_trades']} | {m['profit_factor']:.2f} | {m['win_rate']*100:.1f}% | {m['rr_ratio']:.2f} | all 3 conditions met |\n"

    if decrement:
        md += f"\n## Demoted ({len(demoted)} agents) ⬇\n"
        md += "| Agent | Old → New | n | PF | WR | RR | Reason |\n"
        md += "|-------|-----------|---|-----|-----|-----|--------|\n"
        for r in demoted:
            old = r.get("old_level", 1)
            new = r.get("new_level", 0)
            m = r["metrics"]
            md += f"| {r['strategy']} | {old} → {new} ⬇ | {m['n_trades']} | {m['profit_factor']:.2f} | {m['win_rate']*100:.1f}% | {m['rr_ratio']:.2f} | all 3 conditions failed (唔達標) |\n"

    md += f"\n## Held (n≥{min_n}, mixed signals — stays flat) ({len(held)} agents)\n"
    md += "| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |\n"
    md += "|-------|-------|---|-----|-----|-----|----------------------------|\n"
    for r in held:
        m = r["metrics"]
        lv = r.get("level", 1)
        # Why not promote?
        why_p = []
        if m["profit_factor"] <= min_pf:
            why_p.append(f"PF {m['profit_factor']:.2f} ≤ {min_pf}")
        if m["win_rate"] <= min_wr:
            why_p.append(f"WR {m['win_rate']*100:.1f}% ≤ {min_wr*100}%")
        if m["rr_ratio"] <= min_rr:
            why_p.append(f"RR {m['rr_ratio']:.2f} ≤ {min_rr}")
        # Why not demote?
        why_d = []
        if m["profit_factor"] > min_pf:
            why_d.append(f"PF {m['profit_factor']:.2f} > {min_pf}")
        if m["win_rate"] > min_wr:
            why_d.append(f"WR {m['win_rate']*100:.1f}% > {min_wr*100}%")
        if m["rr_ratio"] > min_rr:
            why_d.append(f"RR {m['rr_ratio']:.2f} > {min_rr}")
        if r.get("at_max_level"):
            why_p.append("at max_level")
        if r.get("at_min_level"):
            why_d.append("at min_level")
        md += f"| {r['strategy']} | {lv} | {m['n_trades']} | {m['profit_factor']:.2f} | {m['win_rate']*100:.1f}% | {m['rr_ratio']:.2f} | "
        md += f"NOT promoted: {'; '.join(why_p) or '—'} | NOT demoted: {'; '.join(why_d) or '—'} |\n"

    md += f"\n## Insufficient data (n<{min_n}) ({len(insufficient)} agents)\n"
    md += "| Agent | Level | n | Note |\n|-------|-------|---|------|\n"
    for r in insufficient:
        m = r["metrics"]
        md += f"| {r['strategy']} | {r.get('level', 1)} | {m['n_trades']} | need ≥ {min_n} trades to settle |\n"

    # Aggregate
    n_promoted = len(promoted)
    n_demoted = len(demoted)
    n_held = len(held)
    n_insuf = len(insufficient)
    md += f"\n## Aggregate\n"
    md += f"- **Promoted (⬆)**: {n_promoted}\n"
    if decrement:
        md += f"- **Demoted (⬇)**: {n_demoted}\n"
    md += f"- **Held (flat)**: {n_held}\n"
    md += f"- **Insufficient data**: {n_insuf}\n"
    md += f"- **Total evaluated**: {len(results)}\n"

    return md


def main() -> int:
    HKT = timezone(timedelta(hours=8))
    today_hkt = datetime.now(HKT).strftime("%Y-%m-%d")

    settings = load_ranking_settings()
    if not settings.get("enabled", True):
        print("[settlement] DISABLED in settings — exit")
        return 0

    # Load per-agent overrides (LLM-managed, for stuck agents in neutral zone)
    agent_overrides = load_agent_overrides()
    if agent_overrides:
        print(f"[settlement] Per-agent overrides active: {list(agent_overrides.keys())}")

    print(f"[settlement] Daily settlement for {today_hkt}")
    print(f"[settlement] Window: {settings['window_days']}d | Min n: {settings['min_trades']} | "
          f"PF>{settings['min_PF']} & WR>{settings['min_WR']} & RR>{settings['min_RR']} → +1 lv "
          f"(cap {settings['max_level']})")

    # Load trades
    by_strat = load_strategy_trades(settings["window_days"])
    print(f"[settlement] Found {sum(len(v) for v in by_strat.values())} closed trades "
          f"across {len(by_strat)} strategies")

    # Load levels
    state = load_levels_state()
    # Ensure all agents have a state entry
    for name in AGENT_NAMES:
        if name not in state:
            state[name] = {"level": settings["default_level"], "last_settled": None, "history": []}

    # Evaluate each agent
    results = []
    for name in AGENT_NAMES:
        trades = by_strat.get(name, [])
        metrics = compute_metrics(trades)
        cur = state[name]
        old_level = cur.get("level", settings["default_level"])
        new_level = old_level
        promoted = False
        demoted = False
        at_max = (old_level >= settings["max_level"])
        at_min = (old_level <= settings["min_level"])

        # Per-agent overrides (LLM-managed for stuck neutral-zone agents)
        ov = agent_overrides.get(name, {})
        thr_n = ov.get("min_trades", settings["min_trades"])
        thr_pf = ov.get("min_PF", settings["min_PF"])
        thr_wr = ov.get("min_WR", settings["min_WR"])
        thr_rr = ov.get("min_RR", settings["min_RR"])
        has_override = bool(ov)

        # 3-condition promote test (all 3 must hold, using per-agent thresholds)
        promote_ok = (
            metrics["n_trades"] >= thr_n
            and metrics["profit_factor"] > thr_pf
            and metrics["win_rate"] > thr_wr
            and metrics["rr_ratio"] > thr_rr
        )

        # 3-condition demote test (mirror: all 3 must FAIL) — only if decrement_on_fail
        demote_ok = (
            settings.get("decrement_on_fail", False)
            and metrics["n_trades"] >= thr_n
            and metrics["profit_factor"] <= thr_pf
            and metrics["win_rate"] <= thr_wr
            and metrics["rr_ratio"] <= thr_rr
        )

        if promote_ok and not at_max:
            new_level = min(old_level + 1, settings["max_level"])
            promoted = (new_level > old_level)
            if promoted:
                cur["history"].append({
                    "date": today_hkt,
                    "old_level": old_level,
                    "new_level": new_level,
                    "n_trades": metrics["n_trades"],
                    "PF": metrics["profit_factor"],
                    "WR": metrics["win_rate"],
                    "RR": metrics["rr_ratio"],
                    "action": "promote",
                    "reason": "PF>1 & WR>0.5 & RR>1 — promoted",
                })
        elif demote_ok and not at_min:
            new_level = max(old_level - 1, settings["min_level"])
            demoted = (new_level < old_level)
            if demoted:
                cur["history"].append({
                    "date": today_hkt,
                    "old_level": old_level,
                    "new_level": new_level,
                    "n_trades": metrics["n_trades"],
                    "PF": metrics["profit_factor"],
                    "WR": metrics["win_rate"],
                    "RR": metrics["rr_ratio"],
                    "action": "demote",
                    "reason": "PF≤1 & WR≤0.5 & RR≤1 — demoted (唔達標)",
                })
        # else: stay flat (insufficient data, mixed signals, or at floor/ceiling)

        # Cap history at 50 entries
        cur["history"] = cur["history"][-50:]
        cur["level"] = new_level
        cur["last_settled"] = today_hkt

        results.append({
            "strategy": name,
            "level": new_level,
            "old_level": old_level,
            "new_level": new_level,
            "promoted": promoted,
            "demoted": demoted,
            "at_max_level": at_max,
            "at_min_level": at_min,
            "promote_ok": promote_ok,
            "demote_ok": demote_ok,
            "has_override": has_override,
            "thresholds_used": {
                "min_PF": thr_pf, "min_WR": thr_wr,
                "min_RR": thr_rr, "min_trades": thr_n,
            },
            "metrics": metrics,
        })
        # Display marker
        if promoted:
            marker = " ⬆"
        elif demoted:
            marker = " ⬇"
        elif at_max and promote_ok:
            marker = " [max]"
        elif at_min and demote_ok:
            marker = " [min]"
        else:
            marker = ""
        ov_mark = " *" if has_override else ""
        print(f"  {name:<20} lv{old_level}→{new_level}{marker}{ov_mark}  "
              f"n={metrics['n_trades']:>3} PF={metrics['profit_factor']:.2f} "
              f"WR={metrics['win_rate']*100:>5.1f}% RR={metrics['rr_ratio']:.2f}")
        if has_override:
            print(f"      └─ LLM override: PF>{thr_pf} WR>{thr_wr} RR>{thr_rr} n≥{thr_n}")

    # Persist state
    save_levels_state(state)
    print(f"\n[settlement] State updated → {settings['state_path']}")

    # Output dir
    out_dir = REPO / "automation" / "reports" / "strategy_settlement"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON
    json_path = out_dir / f"settlement_{today_hkt}.json"
    json_path.write_text(json.dumps({
        "date": today_hkt,
        "settings": {
            "window_days": settings["window_days"],
            "min_trades": settings["min_trades"],
            "min_PF": settings["min_PF"],
            "min_WR": settings["min_WR"],
            "min_RR": settings["min_RR"],
            "max_level": settings["max_level"],
        },
        "results": results,
        "n_promoted": sum(1 for r in results if r.get("promoted")),
    }, indent=2, ensure_ascii=False, default=str))
    print(f"[settlement] JSON: {json_path}")

    # Save Markdown
    md_path = out_dir / f"settlement_{today_hkt}.md"
    md_content = make_settlement_markdown(results, today_hkt, settings)
    md_path.write_text(md_content, encoding="utf-8")
    print(f"[settlement] MD: {md_path}")

    # Save state-only JSON (machine-readable current levels)
    state_only = {n: {"level": state[n]["level"], "last_settled": state[n]["last_settled"]}
                  for n in AGENT_NAMES}
    state_path = out_dir / "current_levels.json"
    state_path.write_text(json.dumps(state_only, indent=2, ensure_ascii=False))
    print(f"[settlement] Current levels: {state_path}")

    n_promoted = sum(1 for r in results if r.get("promoted"))
    print(f"\n[settlement] Promoted: {n_promoted}/{len(results)} agents")

    # Append to history.jsonl (for LLM intervention stuck-detection)
    hist_path = out_dir / "history.jsonl"
    with hist_path.open("a") as f:
        f.write(json.dumps({
            "date": today_hkt,
            "window_days": settings["window_days"],
            "min_trades": settings["min_trades"],
            "results": [
                {
                    "strategy": r["strategy"],
                    "level": r["level"],
                    "old_level": r["old_level"],
                    "new_level": r["new_level"],
                    "promoted": r["promoted"],
                    "demoted": r["demoted"],
                    "n_trades": r["metrics"]["n_trades"],
                    "profit_factor": r["metrics"]["profit_factor"],
                    "win_rate": r["metrics"]["win_rate"],
                    "rr_ratio": r["metrics"]["rr_ratio"],
                }
                for r in results
            ],
        }, ensure_ascii=False) + "\n")
    print(f"[settlement] History: {hist_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
