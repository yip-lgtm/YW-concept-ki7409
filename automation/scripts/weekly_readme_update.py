#!/usr/bin/env python3
"""Weekly README auto-update.

Generates a weekly strategy ranking + PnL summary section, then prepends
to README.md. Runs every Sunday 13:00 UTC (= 21:00 HKT).

Sections generated:
  - 📊 本週策略排名 (Weekly ranking)
  - 💰 累計 P&L 統計 (Cumulative PnL)
  - 🏆 歷史獎勵 (Lifetime awards)
  - 📈 信號總數 (Total signals this week)
  - 🔄 最新 LLM 優化 (Latest LLM iteration)
"""
from __future__ import annotations
import os
import sys
import json
import re
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

README = REPO / "README.md"
OCS_DIR = REPO / "automation" / "reports" / "ocs_btc_5m"
RANKING_DIR = REPO / "automation" / "reports" / "strategy_ranking"
ITER_DIR = RANKING_DIR / "iterations"
AWARDS_FILE = RANKING_DIR / "awards.jsonl"
LIFETIME_FILE = RANKING_DIR / "lifetime_awards.json"
SUPER_DIR = REPO / "automation" / "reports" / "supervisor"


def fmt_money(x):
    return f"${x:,.0f}" if x >= 0 else f"-${abs(x):,.0f}"


def fmt_R(x):
    return f"{x:+.1f}R" if x else "0.0R"


def get_weekly_ranking(week_start: datetime) -> list[dict]:
    """Aggregate strategy rankings in the last 7 days."""
    weekly = {}
    if not RANKING_DIR.exists():
        return []
    for rank_file in RANKING_DIR.glob("ranking_*.json"):
        try:
            d = json.loads(rank_file.read_text())
            date_str = rank_file.stem.replace("ranking_", "")
            d_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if d_date >= week_start:
                # ranking_*.json has top-level "ranking" key (not "strategies")
                for s in d.get("ranking", d.get("strategies", [])):
                    key = s.get("strategy", {}).get("id", s.get("strategy", "?"))
                    if key not in weekly:
                        weekly[key] = {
                            "strategy": s.get("strategy", {}).get("name", key),
                            "n_days": 0,
                            "total_R": 0,
                            "total_pnl": 0,
                            "best_pf": 0,
                            "avg_wr": [],
                        }
                    weekly[key]["n_days"] += 1
                    weekly[key]["total_R"] += s.get("total_R", 0)
                    weekly[key]["total_pnl"] += s.get("total_pnl_usd", s.get("pnl", 0))
                    weekly[key]["best_pf"] = max(weekly[key]["best_pf"], s.get("profit_factor", 0))
                    weekly[key]["avg_wr"].append(s.get("win_rate", 0))
        except Exception:
            continue
    for k, v in weekly.items():
        v["avg_wr"] = round(sum(v["avg_wr"]) / len(v["avg_wr"]), 1) if v["avg_wr"] else 0
    return sorted(weekly.values(), key=lambda x: x["total_pnl"], reverse=True)


def get_lifetime_awards() -> dict:
    """Read lifetime awards from lifetime_awards.json."""
    if LIFETIME_FILE.exists():
        try:
            return json.loads(LIFETIME_FILE.read_text())
        except Exception:
            pass
    return {"total_points": 0, "by_strategy": {}}


def get_weekly_ocs_signals(week_start: datetime) -> dict:
    """Count OCS BTC 5m signals in the last 7 days from GHA runs."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("APEX_PAT")
    if not token:
        return {"n_signals": 0, "n_runs": 0, "first_signal": None, "last_signal": None}
    try:
        r = requests.get(
            "https://api.github.com/repos/yip-lgtm/YW-concept-ki7409/actions/workflows/ocs-btc-5m.yml/runs?per_page=100",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        if r.status_code != 200:
            return {"n_signals": 0, "n_runs": 0, "first_signal": None, "last_signal": None}
        runs = r.json().get("workflow_runs", [])
        n_runs = sum(
            1 for run in runs
            if datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")) >= week_start
        )
        n_signals = 0
        first, last = None, None
        for run in runs:
            if datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")) >= week_start:
                n_signals += 1
                if not first or run["created_at"] < first:
                    first = run["created_at"]
                if not last or run["created_at"] > last:
                    last = run["created_at"]
        return {
            "n_signals": n_signals,
            "n_runs": n_runs,
            "first_signal": first,
            "last_signal": last,
        }
    except Exception:
        return {"n_signals": 0, "n_runs": 0, "first_signal": None, "last_signal": None}


def get_latest_llm_iteration() -> dict:
    """Get most recent LLM iteration suggestion."""
    if not ITER_DIR.exists():
        return {}
    iter_files = sorted(ITER_DIR.glob("iteration_*.json"), reverse=True)
    if not iter_files:
        return {}
    try:
        return json.loads(iter_files[0].read_text())
    except Exception:
        return {}


def build_weekly_section(week_start: datetime, week_end: datetime) -> str:
    """Build the weekly stats markdown section."""
    md = []
    md.append(f"## 📅 本週策略報告 ({week_start.strftime('%Y-%m-%d')} ~ {week_end.strftime('%Y-%m-%d')})")
    md.append("")
    md.append(f"_Auto-generated by `strategy-supervisor` (weekly Sunday 21:00 HKT)_")
    md.append("")
    # OCS signals
    ocs = get_weekly_ocs_signals(week_start)
    md.append("### 📡 OCS BTC 5m 24/7")
    md.append(f"- 監察 runs: **{ocs['n_runs']}** (expected ~2,016 @ 5min × 7d)")
    md.append(f"- 信號 fired: **{ocs['n_signals']}** (vote >=4 + conf >=0.55)")
    if ocs.get("first_signal"):
        md.append(f"- 首次信號: `{ocs['first_signal'][:19]}`")
    if ocs.get("last_signal"):
        md.append(f"- 末次信號: `{ocs['last_signal'][:19]}`")
    # OCS stats
    if OCS_DIR.exists():
        stats_file = OCS_DIR / "stats.json"
        if stats_file.exists():
            stats = json.loads(stats_file.read_text())
            md.append(f"- 累計 trades: {stats.get('n_trades', 0)} | WR: {stats.get('win_rate', 0)}% | PF: {stats.get('profit_factor', 0)} | Total R: {fmt_R(stats.get('total_R', 0))}")
    md.append("")
    # Strategy ranking
    md.append("### 🏆 本週 9 Strategy 排名 (by 累計 P&L)")
    ranking = get_weekly_ranking(week_start)
    if ranking:
        md.append("| Rank | Strategy | Days | 累計 P&L | Total R | Avg WR | Best PF |")
        md.append("|------|----------|------|----------|---------|--------|---------|")
        medals = ["🥇", "🥈", "🥉"] + [""] * 10
        for i, s in enumerate(ranking[:9]):
            md.append(f"| {medals[i]} #{i+1} | {s['strategy']} | {s['n_days']}d | {fmt_money(s['total_pnl'])} | {fmt_R(s['total_R'])} | {s['avg_wr']}% | {s['best_pf']:.2f} |")
    else:
        md.append("_本週無 ranking 數據_")
    md.append("")
    # Lifetime awards
    lifetime = get_lifetime_awards()
    md.append("### 🎁 累計 AI-Trader 獎勵")
    md.append(f"- 總分: **{lifetime.get('total_points_awarded', lifetime.get('total_points', 0))}** points")
    if lifetime.get("by_strategy"):
        md.append("- By strategy:")
        for s, v in sorted(lifetime["by_strategy"].items(), key=lambda x: -x[1].get("total_points", 0)):
            md.append(f'  - {v.get("name", s)}: {v.get("total_points", 0)} pts ({v.get("wins", 0)} wins)')
    md.append("")
    # LLM iteration
    iter_data = get_latest_llm_iteration()
    if iter_data:
        worst = iter_data.get("worst_strategy", {})
        params = iter_data.get("suggested_params", {})
        rationale = params.get("rationale", iter_data.get("llm_response", "?"))[:300]
        changes = []
        if "weight" in params:
            changes.append(f"weight={params['weight']}")
        if "timeframe" in params:
            changes.append(f"timeframe={params['timeframe']}")
        if "r_multiples" in params:
            changes.append(f"R=[{','.join(map(str, params['r_multiples']))}]")
        if "indicators" in params:
            changes.append(f"indicators={','.join(params['indicators'])}")
        md.append("### 🧠 最新 LLM 策略優化")
        md.append(f"- 目標: `{worst.get('name', '?')}` (rank #{worst.get('rank', '?')}, PF {worst.get('pf', '?')}, -{abs(worst.get('total_R', 0))}R)")
        md.append(f"- 建議: {rationale}")
        if changes:
            md.append(f"- 變更: `{' | '.join(changes)}`")
        md.append("")
    # Supervisor health
    heartbeat = SUPER_DIR / "heartbeat.json"
    if heartbeat.exists():
        try:
            hb = json.loads(heartbeat.read_text())
            h = hb.get("health", {})
            md.append("### 👑 Supervisor Health")
            md.append(f"- Status: **{h.get('status', '?').upper()}**")
            md.append(f"- Issues: {h.get('n_issues', 0)}")
            md.append("")
        except Exception:
            pass
    md.append("---")
    md.append("")
    return "\n".join(md)


def update_readme() -> bool:
    """Generate weekly section and update README.md."""
    if not README.exists():
        print(f"[weekly] README.md not found at {README}", file=sys.stderr)
        return False
    # Week boundaries (Mon-Sun)
    now = datetime.now(timezone.utc)
    week_end = now
    week_start = now - timedelta(days=7)
    # Read current README
    current = README.read_text()
    # Find existing weekly section (or insert after ## 🤖 自動化 Pipeline)
    weekly_section = build_weekly_section(week_start, week_end)
    # Pattern: replace existing "## 📅 本週策略報告" section
    pattern = re.compile(
        r"## 📅 本週策略報告.*?(?=\n## |\Z)",
        re.DOTALL,
    )
    if pattern.search(current):
        new_readme = pattern.sub(weekly_section, current)
    else:
        # Insert after "## 🤖 自動化 Pipeline" section
        insert_after = "## 🤖 自動化 Pipeline"
        if insert_after in current:
            # Find the end of the Pipeline section
            parts = current.split(insert_after, 1)
            # Find next ## heading
            after_pipeline = parts[1]
            m = re.search(r"\n## ", after_pipeline)
            if m:
                # Insert before next heading
                insert_pos = m.start()
                new_readme = (
                    parts[0]
                    + insert_after
                    + after_pipeline[:insert_pos]
                    + "\n"
                    + weekly_section
                    + after_pipeline[insert_pos:]
                )
            else:
                new_readme = current + "\n" + weekly_section
        else:
            # Append at end
            new_readme = current + "\n" + weekly_section
    # Update "最後更新" date
    new_readme = re.sub(
        r"最後更新：\d{4}-\d{2}-\d{2}",
        f"最後更新：{now.strftime('%Y-%m-%d')} (Weekly auto-update)",
        new_readme,
    )
    if new_readme != current:
        README.write_text(new_readme)
        print(f"[weekly] ✓ README updated (week {week_start.strftime('%Y-%m-%d')})")
        return True
    print("[weekly] No changes to README")
    return False


def main() -> int:
    print(f"[weekly] === {datetime.now(timezone.utc).isoformat()} ===")
    changed = update_readme()
    return 0 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
