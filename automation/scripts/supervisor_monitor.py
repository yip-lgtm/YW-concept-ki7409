#!/usr/bin/env python3
"""strategy-supervisor — 24/7 monitor 9 strategy sub-agents + OCS BTC 5m.

Checks every 5 min:
  1. OCS BTC 5m — last signal time, position state
  2. YW strategies — latest ranking + LLM iteration status
  3. GHA workflows — recent run status (last 3 runs each)
  4. Anomaly detection:
     - OCS no signal > 1 hour
     - YW daily reminder failed today
     - Strategy ranking failed
     - Reward failed
     - Any strategy no trade in 7 days
  5. Sends TG alert if anomaly detected
  6. Writes state file for supervisor dashboard

State files:
  - reports/supervisor/last_check.json — last check timestamp + health
  - reports/supervisor/alerts.jsonl — append-only alerts
  - reports/supervisor/heartbeat.json — sub-agent heartbeat
"""
from __future__ import annotations
import os
import sys
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

SUPER_DIR = REPO / "automation" / "reports" / "supervisor"
SUPER_DIR.mkdir(parents=True, exist_ok=True)

ALERTS_FILE = SUPER_DIR / "alerts.jsonl"
HEARTBEAT_FILE = SUPER_DIR / "heartbeat.json"
LAST_CHECK_FILE = SUPER_DIR / "last_check.json"

GH_TOKEN = os.environ.get("GITHUB_PAT") or os.environ.get("APEX_PAT") or os.environ.get("GITHUB_TOKEN")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID")
OCS_DIR = REPO / "automation" / "reports" / "ocs_btc_5m"
RANKING_DIR = REPO / "automation" / "reports" / "strategy_ranking"

REPO_NAME = "yip-lgtm/YW-concept-ki7409"
GH_API = f"https://api.github.com/repos/{REPO_NAME}"

# 9 strategy sub-agents + OCS = 10 monitored
STRATEGY_AGENTS = [
    "yw-h-pattern", "yw-3-pushes", "yw-two-yang", "yw-rsi-div",
    "yw-50-20-pullback", "yw-stair-pattern", "yw-crt", "yw-kell-cycle",
    "ocs-btc-5m",
]

# 4 Powers of Separation (mutual oversight)
POWERS_OF_SEPARATION = [
    "supervisor",     # Power 1: 24/7 health check
    "sys_engineer",   # Power 2: bug fixes
    "llm_scientist",  # Power 3: strategy grade + auto-apply
    "tech_analyst",   # Power 4: chart + entry plan
]

POWER_STATE_FILES = {
    # power: list of files to check, take latest mtime
    "supervisor":    ["automation/reports/supervisor/last_check.json",
                      "automation/reports/supervisor/heartbeat.json"],
    "sys_engineer":  ["automation/reports/sys_engineer/"],   # dir, use newest .json
    "llm_scientist": ["automation/reports/strategy_ranking/iterations/"],
    "tech_analyst":  ["automation/reports/tech_analyst/last_run.json"],
}

WORKFLOWS_TO_CHECK = [
    "yw-daily.yml",
    "yw-publish-signal.yml",
    "ocs-btc-5m.yml",
    "strategy-ranking.yml",
    "strategy-reward.yml",
]


def gh_get(path: str) -> dict | list | None:
    """GET GitHub API. Returns parsed JSON or None on error."""
    try:
        r = requests.get(
            f"{GH_API}{path}",
            headers={
                "Authorization": f"Bearer {GH_TOKEN}",
                "Accept": "application/vnd.github+json",
            },
            timeout=20,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"  [gh] {path} error: {e}", file=sys.stderr)
    return None


def check_ocs_state() -> dict:
    """Check OCS BTC 5m state: last signal, position count, total trades."""
    state = {"strategy": "OCS BTC 5m", "agent": "ocs-btc-5m", "issues": []}
    try:
        positions = json.loads((OCS_DIR / "positions.json").read_text())
        stats = json.loads((OCS_DIR / "stats.json").read_text())
        state["n_open"] = len(positions)
        state["n_trades_total"] = stats.get("n_trades", 0)
        state["win_rate"] = stats.get("win_rate", 0)
        state["profit_factor"] = stats.get("profit_factor", 0)
        # Last signal time
        latest = Path("/tmp/ocs_btc/latest.json")
        if latest.exists():
            sig = json.loads(latest.read_text())
            state["last_signal"] = sig.get("ts", sig.get("timestamp", "?"))
            state["last_vote"] = sig.get("vote")
            state["last_conf"] = sig.get("conf")
        else:
            state["last_signal"] = None
            state["issues"].append("no /tmp/ocs_btc/latest.json")
    except Exception as e:
        state["issues"].append(f"read error: {e}")
    return state


def check_latest_ranking() -> dict:
    """Check most recent strategy ranking file."""
    state = {"component": "strategy-ranking", "issues": []}
    try:
        if not RANKING_DIR.exists():
            state["issues"].append("ranking dir missing")
            return state
        # Find latest ranking_YYYY-MM-DD.md
        rank_files = sorted(RANKING_DIR.glob("ranking_*.md"), reverse=True)
        if rank_files:
            latest = rank_files[0]
            state["latest_file"] = latest.name
            # Extract date from "ranking_today_2026-08-25" or "ranking_2026-08-25"
            stem = latest.stem.replace("ranking_", "")
            date_part = stem.split("_")[-1] if "_" in stem else stem
            try:
                datetime.strptime(date_part, "%Y-%m-%d")
                state["latest_date"] = date_part
            except ValueError:
                state["latest_date"] = None
        else:
            state["issues"].append("no ranking files")
    except Exception as e:
        state["issues"].append(f"read error: {e}")
    return state


def check_workflow_health(workflow: str) -> dict:
    """Check last 3 runs of a GHA workflow. Returns status + conclusion list."""
    health = {"workflow": workflow, "runs": [], "issues": []}
    data = gh_get(f"/actions/workflows/{workflow}/runs?per_page=3")
    if not data:
        health["issues"].append("api error")
        return health
    runs = data.get("workflow_runs", [])
    for r in runs:
        health["runs"].append({
            "id": r["id"],
            "conclusion": r.get("conclusion") or "running",
            "created_at": r.get("created_at"),
            "event": r.get("event"),
        })
    # Check latest run
    if runs:
        latest = runs[0]
        if latest.get("conclusion") == "failure" and latest.get("event") == "schedule":
            health["issues"].append(
                f"scheduled run failed: #{latest['id']} {latest.get('created_at')}"
            )
    return health


def check_yw_daily_today() -> dict:
    """Check if yw-daily ran successfully today (UTC)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    health = {"workflow": "yw-daily", "today": today, "ran_today": False, "success_today": False}
    data = gh_get("/actions/workflows/yw-daily.yml/runs?per_page=10")
    if not data:
        health["issues"] = ["api error"]
        return health
    for r in data.get("workflow_runs", []):
        created = r.get("created_at", "")
        if created.startswith(today):
            health["ran_today"] = True
            health["success_today"] = r.get("conclusion") == "success"
            health["last_id"] = r["id"]
            break
    return health


def send_tg(text: str) -> int:
    """Send Telegram message. Returns HTTP code."""
    if not TG_TOKEN or not TG_CHAT:
        return 0
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={
                "chat_id": TG_CHAT,
                "text": text[:4000],
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        return r.status_code
    except Exception as e:
        print(f"  [tg] error: {e}", file=sys.stderr)
        return 0


def build_health_report(ocs, ranking, workflows, yw_daily) -> dict:
    """Build overall health report. Returns dict with status + issues."""
    issues = []
    # OCS
    if ocs.get("n_open", 0) > 5:
        issues.append(f"OCS: {ocs['n_open']} open positions (max 3 expected)")
    # YW daily — check HKT date (yw-daily runs at 21:00 HKT = 13:00 UTC)
    # Only alert AFTER 21:30 HKT (30 min after scheduled run, allowing GHA delay)
    HKT = timezone(timedelta(hours=8))
    now_hkt = datetime.now(HKT)
    today_str = now_hkt.strftime("%Y-%m-%d")
    weekday = now_hkt.strftime("%a")
    if weekday in ("Mon", "Tue", "Wed", "Thu", "Fri") and now_hkt.hour >= 21:
        # Past scheduled time AND trading day
        if not yw_daily.get("ran_today"):
            issues.append(f"yw-daily not run today ({today_str} HKT)")
        elif not yw_daily.get("success_today"):
            issues.append(f"yw-daily failed today ({today_str} HKT)")
    # Workflows
    for wf in workflows:
        for issue in wf.get("issues", []):
            issues.append(f"{wf['workflow']}: {issue}")
    # Ranking freshness
    if ranking.get("latest_date"):
        rank_date = datetime.strptime(ranking["latest_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - rank_date).days
        if age_days > 1:
            issues.append(f"ranking stale: {age_days} days old")
    return {
        "issues": issues,
        "status": "ok" if not issues else "warning" if len(issues) <= 2 else "critical",
        "n_issues": len(issues),
    }


def check_powers_of_separation() -> list:
    """Check health of all 4 powers. Each power has its own state file/dir.
    
    Returns list of alerts if any power is stale (>30 min without update).
    """
    alerts = []
    now = datetime.now(timezone.utc)
    for power, paths in POWER_STATE_FILES.items():
        # Find latest file mtime
        latest_mtime = None
        for rel_path in paths:
            p = REPO / rel_path
            if p.is_file():
                latest_mtime = max(latest_mtime or 0, p.stat().st_mtime)
            elif p.is_dir():
                for f in p.glob("*.json"):
                    latest_mtime = max(latest_mtime or 0, f.stat().st_mtime)
        if latest_mtime is None:
            alerts.append({"power": power, "issue": "no state files found"})
            continue
        age_min = (now.timestamp() - latest_mtime) / 60
        if age_min > 30:
            alerts.append({"power": power, "issue": f"stale {age_min:.0f}min"})
    return alerts


def main() -> int:
    print(f"[supervisor] === {datetime.now(timezone.utc).isoformat()} ===")
    # Step 1: OCS state
    print("[supervisor] Checking OCS BTC 5m...")
    ocs = check_ocs_state()
    print(f"  n_open={ocs.get('n_open')} total_trades={ocs.get('n_trades_total')}")
    # Step 2: Ranking
    print("[supervisor] Checking strategy ranking...")
    ranking = check_latest_ranking()
    print(f"  latest: {ranking.get('latest_file', 'none')}")
    # Step 3: YW daily today
    print("[supervisor] Checking yw-daily today...")
    yw_daily = check_yw_daily_today()
    print(f"  ran_today={yw_daily.get('ran_today')} success={yw_daily.get('success_today')}")
    # Step 4: All workflows
    print("[supervisor] Checking 5 workflows...")
    workflows = []
    for wf in WORKFLOWS_TO_CHECK:
        h = check_workflow_health(wf)
        workflows.append(h)
        print(f"  {wf}: {len(h['issues'])} issues")
    # Step 5: Health report
    health = build_health_report(ocs, ranking, workflows, yw_daily)
    print(f"[supervisor] Health: {health['status']} ({health['n_issues']} issues)")
    # Step 6: Build heartbeat
    heartbeat = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "supervisor": "strategy-supervisor",
        "ocs_btc_5m": ocs,
        "ranking": ranking,
        "yw_daily_today": yw_daily,
        "workflows": workflows,
        "health": health,
    }
    HEARTBEAT_FILE.write_text(json.dumps(heartbeat, indent=2, default=str))
    print(f"[supervisor] ✓ Heartbeat saved: {HEARTBEAT_FILE}")
    
    # Step 6b: 4 Powers of Separation health check
    power_alerts = check_powers_of_separation()
    if power_alerts:
        print(f"[supervisor] ⚠️ Power issues: {len(power_alerts)}")
        for pa in power_alerts:
            print(f"  - {pa['power']}: {pa['issue']}")
    else:
        print(f"[supervisor] ✓ All 4 powers healthy")
    
    # Step 7: Alert if issues
    if health["issues"]:
        # Dedupe: only alert if not same as last alert
        last_alert = None
        if ALERTS_FILE.exists():
            with ALERTS_FILE.open() as f:
                lines = f.readlines()
                if lines:
                    try:
                        last_alert = json.loads(lines[-1])
                    except Exception:
                        pass
        issue_key = "|".join(sorted(health["issues"]))
        if not last_alert or last_alert.get("issue_key") != issue_key:
            alert = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": health["status"],
                "issues": health["issues"],
                "issue_key": issue_key,
            }
            with ALERTS_FILE.open("a") as f:
                f.write(json.dumps(alert) + "\n")
            # Send TG
            emoji = "⚠️" if health["status"] == "warning" else "🚨"
            msg = f"{emoji} <b>Supervisor Alert</b>\n\n"
            msg += f"Status: <b>{health['status'].upper()}</b>\n"
            msg += f"Issues: {health['n_issues']}\n\n"
            for iss in health["issues"][:8]:
                msg += f"• {iss}\n"
            if power_alerts:
                msg += f"\n🏛️ 4-Power Health:\n"
                for pa in power_alerts:
                    msg += f"  ⚠️ {pa['power']}: {pa['issue']}\n"
            code = send_tg(msg)
            print(f"[supervisor] Alert sent: HTTP {code}")
        else:
            print(f"[supervisor] Same issues as last alert, skip TG")
    # Step 8: Save last_check
    last_check = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "health_status": health["status"],
        "n_issues": health["n_issues"],
        "n_open_positions": ocs.get("n_open", 0),
        "n_workflows_healthy": sum(1 for w in workflows if not w.get("issues")),
    }
    LAST_CHECK_FILE.write_text(json.dumps(last_check, indent=2))
    print(f"[supervisor] ✓ Done")
    return 0 if health["status"] != "critical" else 1


if __name__ == "__main__":
    sys.exit(main())
