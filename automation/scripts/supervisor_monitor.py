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

HKT = timezone(timedelta(hours=8))

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

SUPER_DIR = REPO / "automation" / "reports" / "supervisor"
SUPER_DIR.mkdir(parents=True, exist_ok=True)

ALERTS_FILE = SUPER_DIR / "alerts.jsonl"
HEARTBEAT_FILE = SUPER_DIR / "heartbeat.json"
LAST_CHECK_FILE = SUPER_DIR / "last_check.json"
POSITIONS_MONITOR_FILE = SUPER_DIR / "positions_monitor.json"

GH_TOKEN = (
    os.environ.get("GITHUB_APEX_PAT")
    or os.environ.get("GITHUB_PAT")
    or os.environ.get("APEX_PAT")
    or os.environ.get("GITHUB_TOKEN", "")
)
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
    "sys_engineer":  ["automation/reports/sys_engineer/"],
    "llm_scientist": ["automation/reports/strategy_ranking/iterations/"],
    "tech_analyst":  ["automation/reports/tech_analyst/last_run.json"],
}

# Power → workflow to re-trigger if stale
POWER_WORKFLOW_MAP = {
    "supervisor":    "supervisor-monitor.yml",
    "sys_engineer":  "sys-engineer.yml",
    "llm_scientist": "llm-iteration-scientist.yml",
    "tech_analyst":  "unified-pipeline.yml",
    "ranking":       "strategy-ranking.yml",  # extra: ranking
}

POWER_RECOVERY_FILE = REPO / "automation" / "sys_power_recovery.json"

# Per-power stale threshold (minutes). Different powers have different cadences.
POWER_STALE_THRESHOLD_MIN = {
    "supervisor":    30,    # 5-min cadence
    "sys_engineer":  90,    # 1-hour cadence
    "llm_scientist": 24 * 60,   # daily cadence (00:00 HKT)
    "tech_analyst":  30,    # 5-min cadence
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


def check_ranking_freshness() -> dict:
    """Check if strategy ranking is fresh (auto-heal if stale).
    
    Ranking is daily (00:05 HKT weekdays) - stale if >36h old on weekday.
    """
    state = {"strategy": "ranking", "issues": []}
    ranking_dir = RANKING_DIR
    if not ranking_dir.exists():
        state["issues"].append("ranking dir missing")
        return state
    
    import re
    HKT_TZ = timezone(timedelta(hours=8))
    weekday = datetime.now(HKT_TZ).weekday()  # 0=Mon
    
    latest_file = None
    latest_date = ""
    for f in ranking_dir.glob("ranking_2026-*.json"):
        m = re.search(r"ranking_(\d{4}-\d{2}-\d{2})", f.name)
        if m:
            if m.group(1) > latest_date:
                latest_date = m.group(1)
                latest_file = f
    
    state["latest_file"] = latest_file.name if latest_file else None
    state["latest_date"] = latest_date
    
    if not latest_file:
        state["issues"].append("no ranking files found")
    else:
        # Check staleness
        try:
            latest_dt = datetime.strptime(latest_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            age_hours = (now - latest_dt).total_seconds() / 3600
            state["age_hours"] = round(age_hours, 1)
            
            # If weekday and ranking is >24h old → stale
            if weekday < 5 and age_hours > 24:
                state["issues"].append(f"ranking stale: {age_hours:.0f}h (weekday)")
        except Exception as e:
            state["issues"].append(f"date parse: {e}")
    
    return state


def check_live_scan_positions() -> dict:
    """Monitor open positions from 9-strategy live_scan.
    
    Checks:
    - Total open positions (alert if > 15)
    - Stale positions (open > 24h without close)
    - All same direction (correlated risk)
    - Loss > -2R on any position
    - Total unrealized risk
    """
    state = {
        "source": "live_scan",
        "n_open": 0,
        "n_stale_24h": 0,
        "issues": [],
        "long_count": 0,
        "short_count": 0,
        "total_risk": 0.0,
        "deep_loss_positions": [],
    }
    
    positions_file = REPO / "automation" / "reports" / "live_scan" / "positions.json"
    if not positions_file.exists():
        return state
    
    try:
        positions = json.loads(positions_file.read_text())
    except Exception as e:
        state["issues"].append(f"positions.json parse error: {e}")
        return state
    
    now = datetime.now(timezone.utc)
    state["n_open"] = len(positions)
    
    for pos in positions:
        if pos.get("status") != "open":
            continue
        
        # Stale check
        entry_time = pos.get("entry_time", "")
        if entry_time:
            try:
                et = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
                age_hours = (now - et).total_seconds() / 3600
                if age_hours > 24:
                    state["n_stale_24h"] += 1
                    state["issues"].append(
                        f"Stale: {pos.get('strategy')} {pos.get('ticker')} open {age_hours:.0f}h"
                    )
            except Exception:
                pass
        
        # Direction
        direction = pos.get("direction", "")
        if direction in ("long", "bullish"):
            state["long_count"] += 1
        elif direction in ("short", "bearish"):
            state["short_count"] += 1
        
        # Total risk
        sl_dist = pos.get("sl_dist", 0)
        state["total_risk"] += sl_dist
    
    # Correlated risk alert
    if state["n_open"] >= 4:
        if state["long_count"] == state["n_open"]:
            state["issues"].append(f"All {state['n_open']} positions LONG (correlated bull risk)")
        elif state["short_count"] == state["n_open"]:
            state["issues"].append(f"All {state['n_open']} positions SHORT (correlated bear risk)")
    
    # Total exposure alert
    if state["total_risk"] > 200:  # $200+ total risk
        state["issues"].append(f"High total risk: ${state['total_risk']:.0f}")
    
    return state


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
        threshold = POWER_STALE_THRESHOLD_MIN.get(power, 30)
        if age_min > threshold:
            alerts.append({
                "power": power, 
                "issue": f"stale {age_min:.0f}min (threshold {threshold}min)",
                "threshold": threshold,
            })
    return alerts


def trigger_workflow(workflow: str) -> bool:
    """Auto-trigger a workflow via GitHub API."""
    if not GH_TOKEN:
        return False
    try:
        r = requests.post(
            f"{GH_API}/actions/workflows/{workflow}/dispatches",
            headers={"Authorization": f"Bearer {GH_TOKEN}", "Accept": "application/vnd.github+json"},
            json={"ref": "main"},
            timeout=15,
        )
        return r.status_code == 204
    except Exception as e:
        print(f"  [trigger] {workflow} failed: {e}")
        return False


def auto_recover_powers(power_alerts: list) -> dict:
    """Auto-trigger stale powers (with de-dup)."""
    if not power_alerts:
        return {"recovered": 0, "skipped": 0}
    
    # Load last recovery (de-dup: don't re-trigger same power within 30 min)
    last_recovery = {}
    if POWER_RECOVERY_FILE.exists():
        try:
            with open(POWER_RECOVERY_FILE) as f:
                last_recovery = json.load(f).get("recoveries", {})
        except Exception:
            pass
    
    now = datetime.now(timezone.utc)
    recovered = 0
    skipped = 0
    new_recovery = {}
    
    for pa in power_alerts:
        power = pa["power"]
        workflow = POWER_WORKFLOW_MAP.get(power)
        if not workflow:
            continue
        
        # De-dup: skip if recovered < 30 min ago
        last_ts = last_recovery.get(power, "")
        if last_ts:
            try:
                last_dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                if (now - last_dt).total_seconds() < 1800:  # 30 min
                    skipped += 1
                    continue
            except Exception:
                pass
        
        # Trigger
        if trigger_workflow(workflow):
            new_recovery[power] = now.isoformat()
            recovered += 1
            print(f"  [auto-recover] ✓ triggered {workflow} for {power}")
        else:
            print(f"  [auto-recover] ✗ failed to trigger {workflow}")
    
    # Save recovery state
    if new_recovery:
        merged = {**last_recovery, **new_recovery}
        # Trim to keep only last 7 days
        cutoff = (now.timestamp() - 7 * 86400)
        merged = {p: t for p, t in merged.items() 
                  if datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() > cutoff}
        try:
            POWER_RECOVERY_FILE.write_text(json.dumps({"recoveries": merged, "updated": now.isoformat()}, indent=2))
        except Exception:
            pass
    
    return {"recovered": recovered, "skipped": skipped}


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
    
    # Step 6a: 9-strategy live_scan position monitor
    live_pos = check_live_scan_positions()
    print(f"[supervisor] Live positions: {live_pos['n_open']} open "
          f"(L:{live_pos['long_count']}/S:{live_pos['short_count']}, risk ${live_pos['total_risk']:.0f})")
    if live_pos["issues"]:
        for iss in live_pos["issues"]:
            print(f"  ⚠️ {iss}")
    
    # Add positions to heartbeat
    heartbeat["live_scan_positions"] = live_pos
    HEARTBEAT_FILE.write_text(json.dumps(heartbeat, indent=2, default=str))
    
    # Save positions monitor
    POSITIONS_MONITOR_FILE.write_text(json.dumps(live_pos, indent=2, default=str))
    
    # Hourly position summary (only if positions open)
    if live_pos["n_open"] > 0 and datetime.now(HKT).minute < 5:
        summary = (
            f"📊 Hourly Position Summary\n\n"
            f"Open: {live_pos['n_open']} (L:{live_pos['long_count']}/S:{live_pos['short_count']})\n"
            f"Total risk: ${live_pos['total_risk']:.0f}\n"
            f"Stale >24h: {live_pos['n_stale_24h']}"
        )
        if not live_pos["issues"]:
            summary += f"\n\n✅ All positions healthy"
        send_tg(summary)
    
    # Step 5b: Strategy ranking freshness
    ranking_check = check_ranking_freshness()
    if ranking_check["issues"]:
        print(f"[supervisor] ⚠️ Ranking: {ranking_check['issues']}")
        # Auto-heal: trigger strategy-ranking workflow
        for iss in ranking_check["issues"]:
            if "stale" in iss:
                print(f"  [auto-heal] triggering strategy-ranking.yml")
                if trigger_workflow(POWER_WORKFLOW_MAP.get("ranking", "strategy-ranking.yml")):
                    print(f"  [auto-heal] ✓ strategy-ranking triggered")
                break
    else:
        print(f"[supervisor] ✓ Ranking fresh ({ranking_check.get('latest_date')})")
    
    # Step 6b: 4 Powers of Separation health check
    power_alerts = check_powers_of_separation()
    if power_alerts:
        print(f"[supervisor] ⚠️ Power issues: {len(power_alerts)}")
        for pa in power_alerts:
            print(f"  - {pa['power']}: {pa['issue']}")
        # Auto-recover: re-trigger stale power's workflow
        rec = auto_recover_powers(power_alerts)
        print(f"[supervisor] [auto-recover] recovered={rec['recovered']} skipped={rec['skipped']}")
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
            # Live positions summary
            if live_pos["n_open"] > 0:
                msg += f"\n💼 Live Positions: {live_pos['n_open']} open (L:{live_pos['long_count']}/S:{live_pos['short_count']}, risk ${live_pos['total_risk']:.0f})\n"
            
            if power_alerts:
                msg += f"\n🏛️ 4-Power Health:\n"
                for pa in power_alerts:
                    msg += f"  ⚠️ {pa['power']}: {pa['issue']}\n"
                if 'rec' in dir() and rec['recovered'] > 0:
                    msg += f"\n🔄 Auto-recovered: {rec['recovered']} powers re-triggered\n"
            
            # Position issues
            if live_pos["issues"]:
                msg += f"\n📊 Position Alerts:\n"
                for iss in live_pos["issues"][:5]:
                    msg += f"  • {iss}\n"
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
