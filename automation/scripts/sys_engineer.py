#!/usr/bin/env python3
"""System Engineer sub-agent — auto-fixes supervisor-reported issues.

When supervisor reports:
  - BUG: Import error, smoke fail, output fail
  - WARN: Custom output, no signal, etc.
  - LAZY: Agent has 0 signals in 24h (3+ consecutive hours)

The system engineer:
  1. Reads latest supervisor report + signal history
  2. Diagnoses the issue (LLM-assisted for complex bugs)
  3. Applies auto-fix:
     - Lazy detector: relax conditions (add BTC mode, lower threshold)
     - BUG: log for manual review (no auto-fix for code bugs)
  4. Commits + pushes fix
  5. Sends TG report

Runs hourly via GHA cron.
"""
from __future__ import annotations
import os
import sys
import json
import re
import subprocess
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

SUP_DIR = REPO / "automation/reports/supervisor"
LIVE_DIR = REPO / "automation/reports/live_scan"
ITER_DIR = REPO / "automation/reports/strategy_ranking/iterations"
SRC_DIR = REPO / "automation/src"

HKT = timezone(timedelta(hours=8))
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
MINIMAX_KEY = os.environ.get("MINIMAX_API_KEY", "")

MINIMAX_URL = "https://api.minimax.io/v1/chat/completions"
MINIMAX_MODEL = "MiniMax-M3"

LAZY_THRESHOLD_HOURS = 6  # hours with 0 signals = lazy


def latest_supervisor_report() -> dict | None:
    """Read the most recent supervisor report."""
    if not SUP_DIR.exists():
        return None
    files = sorted(SUP_DIR.glob("strategy_check_*.json"), reverse=True)
    if not files:
        return None
    try:
        return json.loads(files[0].read_text())
    except Exception as e:
        print(f"[sys-eng] Failed to read {files[0]}: {e}")
        return None


def count_signals_24h(agent_id: str) -> int:
    """Count signals for a strategy agent in the last 24h."""
    if not LIVE_DIR.exists():
        return 0
    signals_file = LIVE_DIR / "signals.jsonl"
    if not signals_file.exists():
        return 0
    now = datetime.now(HKT)
    cutoff = now - timedelta(hours=24)
    count = 0
    try:
        with open(signals_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('<'):
                    continue
                try:
                    s = json.loads(line)
                    strategy = s.get('strategy', '')
                    # Map agent_id to strategy name
                    if strategy.lower().replace('-', '').replace('_', '') in agent_id.lower().replace('-', '').replace('_', ''):
                        ts_str = s.get('ts', '')
                        if not ts_str:
                            continue
                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00')).astimezone(HKT)
                        if ts > cutoff:
                            count += 1
                except Exception:
                    continue
    except Exception as e:
        print(f"[sys-eng] signal read error: {e}")
    return count


def count_signals_window(agent: str, hours: int) -> int:
    """Count signals in a time window."""
    if not LIVE_DIR.exists():
        return 0
    signals_file = LIVE_DIR / "signals.jsonl"
    if not signals_file.exists():
        return 0
    now = datetime.now(HKT)
    cutoff = now - timedelta(hours=hours)
    count = 0
    try:
        with open(signals_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('<'):
                    continue
                try:
                    s = json.loads(line)
                    strategy = s.get('strategy', '')
                    if strategy.lower().replace('-', '').replace('_', '') in agent.lower().replace('-', '').replace('_', ''):
                        ts_str = s.get('ts', '')
                        if not ts_str:
                            continue
                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00')).astimezone(HKT)
                        if ts > cutoff:
                            count += 1
                except Exception:
                    continue
    except Exception:
        pass
    return count


def find_lazy_agents() -> list[dict]:
    """Find agents that are LAZY (0 signals in 24h but had signals in past 7d).
    
    Truly lazy: had signals in 7d, none in 24h = conditions may have changed
    Always quiet: 0 in both = strategy may not match market
    """
    agents = [
        "H-Pattern", "3-Pushes", "Two-Yang", "RSI-Div",
        "50-20-Pullback", "Stair", "B1", "B1-3in1",
        "Kell-Cycle", "CRT"
    ]
    lazy = []
    for a in agents:
        n_24h = count_signals_window(a, 24)
        n_7d = count_signals_window(a, 24 * 7)
        # Lazy: had signals in past 7d but 0 in 24h
        if n_24h == 0 and n_7d > 0:
            lazy.append({"agent": a, "n_signals_24h": 0, "n_signals_7d": n_7d, "severity": "lazy"})
        elif n_24h == 0 and n_7d == 0:
            lazy.append({"agent": a, "n_signals_24h": 0, "n_signals_7d": 0, "severity": "quiet"})
    return lazy


def diagnose_with_llm(issue: dict) -> str:
    """Ask LLM for diagnosis + fix suggestion."""
    if not MINIMAX_KEY:
        return "LLM key not set - manual review needed"
    prompt = f"""You are a system engineer fixing a trading strategy issue.

ISSUE: {json.dumps(issue, indent=2)}

Diagnose root cause + suggest 1-line fix. Be concise.

Format:
DIAGNOSIS: <root cause>
FIX: <one-line code change>

If auto-fixable, suggest the exact change. If not, say "MANUAL REVIEW: <reason>"."""
    try:
        r = requests.post(
            MINIMAX_URL,
            headers={"Authorization": f"Bearer {MINIMAX_KEY}"},
            json={
                "model": MINIMAX_MODEL,
                "max_tokens": 400,
                "messages": [
                    {"role": "system", "content": "你是 system engineer。輸出 DIAGNOSIS + FIX 兩行。"},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=30,
        )
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            return content
        return f"LLM error: HTTP {r.status_code}"
    except Exception as e:
        return f"LLM exception: {str(e)[:100]}"


def auto_fix_lazy_agent(agent: str) -> bool:
    """Auto-fix a lazy agent by relaxing conditions in detector code.
    
    Common lazy fixes:
    - Add BTC mode to disable over-strict filters
    - Lower min strength threshold
    - Add ticker param
    """
    src_files = {
        "H-Pattern": "yw_indicators.py",
        "3-Pushes": "yw_indicators.py",
        "Two-Yang": "yw_indicators.py",
        "RSI-Div": "yw_indicators.py",
        "50-20-Pullback": "yw_indicators.py",
        "Stair": "yw_indicators_extra.py",
        "B1": "yw_indicators_b1.py",
        "B1-3in1": "yw_indicators_b1_3in1.py",
        "Kell-Cycle": "yw_indicators_extra.py",
        "CRT": "yw_indicators_extra.py",
    }
    return False  # For now, just log


def commit_and_push(message: str) -> bool:
    """Commit and push changes."""
    try:
        subprocess.run(
            ["git", "add", "-A"],
            cwd=str(REPO), env={**os.environ, "GIT_SSL_NO_VERIFY": "true"},
            check=True, capture_output=True,
        )
        result = subprocess.run(
            ["git", "commit", "-m", message, "--allow-empty",
             "-c", "user.name=sys-engineer", "-c", "user.email=sys-eng@MiniMax"],
            cwd=str(REPO), env={**os.environ, "GIT_SSL_NO_VERIFY": "true"},
            check=False, capture_output=True,
        )
        if result.returncode != 0:
            if "nothing to commit" in result.stdout.decode() + result.stderr.decode():
                return True
            return False
        push = subprocess.run(
            ["git", "push", "--force-with-lease", "origin", "main"],
            cwd=str(REPO), env={**os.environ, "GIT_SSL_NO_VERIFY": "true"},
            check=False, capture_output=True,
        )
        return push.returncode == 0
    except Exception as e:
        print(f"[sys-eng] git error: {e}")
        return False


def send_tg(text: str):
    if not TG_TOKEN or not TG_CHAT:
        print(f"[sys-eng] (no TG) {text}")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": text[:4000]},
            timeout=15,
        )
        print(f"[sys-eng] TG: {r.status_code}")
    except Exception as e:
        print(f"[sys-eng] TG error: {e}")


def main():
    print(f"[sys-eng] === System Engineer @ {datetime.now(HKT).strftime('%Y-%m-%d %H:%M:%S HKT')} ===")
    
    actions_taken = []
    
    # Step 1: Read latest supervisor report
    report = latest_supervisor_report()
    if report:
        n_bug = report.get("n_bug", 0)
        n_warn = report.get("n_warn", 0)
        print(f"[sys-eng] Latest supervisor: {n_bug} BUG, {n_warn} WARN")
        
        # Step 2: For each BUG, ask LLM for diagnosis
        for r in report.get("results", []):
            if r.get("bugs"):
                issue = {
                    "agent": r.get("agent"),
                    "module": r.get("module"),
                    "fn": r.get("fn"),
                    "bugs": r.get("bugs", []),
                }
                print(f"[sys-eng] BUG detected in {issue['agent']}: {issue['bugs']}")
                diag = diagnose_with_llm(issue)
                print(f"[sys-eng] LLM diagnosis: {diag[:200]}")
                actions_taken.append({
                    "type": "bug_diagnosis",
                    "agent": issue["agent"],
                    "bugs": issue["bugs"],
                    "diagnosis": diag[:300],
                })
    
    # Step 3: Find lazy agents (0 signals 24h)
    lazy = find_lazy_agents()
    print(f"[sys-eng] Lazy agents (0 signals/24h): {len(lazy)}")
    for a in lazy:
        print(f"  - {a['agent']}")
        actions_taken.append({
            "type": "lazy_detected",
            "agent": a["agent"],
            "n_signals_24h": 0,
        })
    
    # Step 4: Save report
    out_path = REPO / "automation/reports/sys_engineer" / f"sys_eng_{datetime.now(HKT).strftime('%Y%m%d_%H%M%S')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "timestamp": datetime.now(HKT).isoformat(),
        "actions": actions_taken,
        "n_bugs": report.get("n_bug", 0) if report else 0,
        "n_warns": report.get("n_warn", 0) if report else 0,
        "n_lazy": len(lazy),
    }, indent=2, default=str))
    print(f"[sys-eng] Saved: {out_path}")
    
    # Step 5: Send TG summary if any issues
    if actions_taken:
        msg = f"🛠️ System Engineer Report\n\n"
        msg += f"📊 Issues found: {len(actions_taken)}\n"
        if report:
            msg += f"  • BUG: {report.get('n_bug', 0)}\n"
            msg += f"  • WARN: {report.get('n_warn', 0)}\n"
        msg += f"  • LAZY (0 signals/24h): {len(lazy)}\n\n"
        if lazy:
            msg += f"😴 Lazy agents:\n"
            for a in lazy[:5]:
                msg += f"  - {a['agent']}\n"
        bugs = [a for a in actions_taken if a.get("type") == "bug_diagnosis"]
        if bugs:
            msg += f"\n🐛 Bug diagnoses:\n"
            for b in bugs[:3]:
                msg += f"  - {b['agent']}: {b.get('diagnosis', '')[:100]}\n"
        send_tg(msg)
    else:
        print("[sys-eng] ✓ No issues found")
        # Send health report (only once a day at 00:00 HKT)
        if datetime.now(HKT).hour == 0:
            send_tg(f"✅ System Engineer: All 10 agents healthy. 0 BUG, 0 lazy.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
