"""
Persistent heartbeat cron - runs in background and triggers GHA workflows every 5 min
This is the PRIMARY scheduler; GHA schedules are backups.

Why: GHA free tier has unreliable schedule firing (40+ min stalls observed).
Our own cron service has no such limits.
"""
import os
import time
import json
import requests
from datetime import datetime, timezone, timedelta

GHA_TOKEN = (
    os.environ.get('GITHUB_APEX_PAT')
    or os.environ.get('APEX_PAT')
    or os.environ.get('GITHUB_PAT')
    or os.environ.get('GH_TOKEN', '')
)
REPO = 'yip-lgtm/YW-concept-ki7409'
WORKFLOW = 'unified-pipeline.yml'
BRANCH = 'main'
INTERVAL_SEC = 300  # 5 min

# TG alerts
TG_TOKEN = '8976341017:AAFWVF7HX0rpMJJtd3qzmGqqWY-l3olwOaU'
TG_CHAT = '8475453959'

HKT = timezone(timedelta(hours=8))

def log(msg):
    ts = datetime.now(HKT).strftime('%H:%M:%S HKT')
    line = f"[heartbeat-cron {ts}] {msg}"
    print(line, flush=True)
    with open('/workspace/YW-concept-ki7409/automation/reports/heartbeat_cron.log', 'a') as f:
        f.write(line + '\n')

def trigger_workflow(workflow=WORKFLOW):
    """Trigger a GHA workflow via dispatch API."""
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GHA_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    r = requests.post(
        f"https://api.github.com/repos/{REPO}/actions/workflows/{workflow}/dispatches",
        headers=headers, json={"ref": BRANCH}, timeout=15,
    )
    return r.status_code == 204

def send_tg(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": msg}, timeout=10,
        )
    except: pass

def check_health():
    """Check if last unified-pipeline run was within 10 min."""
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GHA_TOKEN}",
    }
    try:
        r = requests.get(
            f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/runs?per_page=1",
            headers=headers, timeout=15,
        )
        runs = r.json().get('workflow_runs', [])
        if not runs:
            # API returned 0 runs (auth or rate-limit), assume healthy
            return True, 0
        last = runs[0].get('updated_at') or runs[0].get('created_at')
        last_dt = datetime.fromisoformat(last.replace('Z', '+00:00')).astimezone(HKT)
        age_min = (datetime.now(HKT) - last_dt).total_seconds() / 60
        return age_min < 10, age_min
    except Exception as e:
        log(f"Health check error: {e}")
        return True, 0  # Assume healthy on error

def main():
    log(f"Heartbeat cron started (interval={INTERVAL_SEC}s)")
    cycle = 0
    while True:
        cycle += 1
        now = datetime.now(HKT)
        # Trigger at HH:MM:00, HH:MM:05, HH:MM:10, ...
        # Find next 5-min boundary
        sleep_to = (5 - (now.minute % 5)) * 60 - now.second
        if sleep_to < 0:
            sleep_to += 300
        log(f"Cycle {cycle}: next trigger in {sleep_to}s")
        time.sleep(sleep_to)
        # Trigger
        ok = trigger_workflow()
        log(f"Trigger: {'OK' if ok else 'FAILED'}")
        if not ok:
            send_tg(f"⚠️ Heartbeat cron: GHA trigger FAILED at {now.strftime('%H:%M')}")
        # Wait rest of interval
        time.sleep(5)
        # Quick health check
        healthy, age = check_health()
        if not healthy and age > 15:
            log(f"Stall detected ({age:.0f}m) - sending alert")
            send_tg(f"🚨 Pipeline stalled {age:.0f}m. Re-triggering again...")
            trigger_workflow()

if __name__ == '__main__':
    main()
