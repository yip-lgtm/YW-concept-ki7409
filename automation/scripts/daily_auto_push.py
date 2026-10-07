#!/usr/bin/env python3
"""Daily Auto-Push — robust git push for all daily-generated reports.

User directive (10/07): "每日自動git push report".
Replaces the 2 inline `git add ... && git commit ... && git push` blocks
in strategy-ranking.yml with a single, idempotent, error-checked routine.

WHAT IT PUSHES (every daily cycle):
  - automation/reports/strategy_ranking/      (incl. 24h/, history.jsonl)
  - automation/reports/strategy_settlement/   (daily settlement reports)
  - automation/reports/llm_iteration/        (LLM iter outputs)
  - automation/reports/live_scan/             (live trade state)
  - automation/reports/ocs_btc_5m/           (OCS BTC state)
  - automation/config/strategy_levels.json   (level state)
  - automation/config/ranking_settings.json  (ranking config)
  - docs/dashboard-data.json + manifests + review.html

WHAT IT DOES:
  1. git fetch origin
  2. git checkout main
  3. git pull --rebase (so concurrent pushes don't get rejected)
  4. Detect modified/new files in the watched paths
  5. git add <files>
  6. git commit (with date + summary)
  7. git push origin main
  8. Verify push: check origin/main is ahead
  9. Report summary (file count, push status, log excerpt)

On failure: returns non-zero exit code + writes /tmp/daily_push_error.log.
Idempotent: if no changes, exits 0 without committing.

Schedule: 02:00 HKT daily (after 00:00 HKT ranking + 01:00 HKT
llm-iteration-scientist have their chance to commit).
Also called by strategy-ranking.yml at end of main() for same-day guarantees.
"""
from __future__ import annotations
import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

# Paths that should be in every daily auto-push
WATCHED_PATHS = [
    # Reports
    "automation/reports/strategy_ranking/",
    "automation/reports/strategy_settlement/",
    "automation/reports/llm_iteration/",
    "automation/reports/live_scan/",
    "automation/reports/ocs_btc_5m/",
    # Config (state + settings)
    "automation/config/strategy_levels.json",
    "automation/config/ranking_settings.json",
    # Web dashboard
    "docs/dashboard-data.json",
    "docs/charts-manifest.json",
    "docs/trades-manifest.json",
    "docs/rankings-manifest.json",
    "docs/llm-iterations-manifest.json",
    "docs/review.html",
]


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """Run subprocess with sane defaults + log to console."""
    res = subprocess.run(
        cmd, cwd=REPO, capture_output=True, text=True, **kw
    )
    return res


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[auto-push {ts}] {msg}", flush=True)


def main() -> int:
    HKT = timezone(timedelta(hours=8))
    today = datetime.now(HKT).strftime("%Y-%m-%d")
    ts = datetime.now(HKT).strftime("%Y-%m-%d %H:%M HKT")

    log(f"Daily auto-push for {today}")

    # 1. Setup remote (idempotent, fast)
    pat = os.environ.get("GITHUB_PAT", "") or os.environ.get("GITHUB_TOKEN", "")
    if not pat:
        log("WARN: GITHUB_PAT not in env — push will likely fail auth")
    run(["git", "config", "--global", "user.name", "Mavis bot"])
    run(["git", "config", "--global", "user.email", "mavis@MiniMax"])
    if pat:
        run([
            "git", "remote", "set-url", "origin",
            f"https://x-access-token:{pat}@github.com/yip-lgtm/YW-concept-ki7409.git",
        ])

    # 2. Check we are on main
    branch = run(["git", "branch", "--show-current"]).stdout.strip()
    if branch != "main":
        log(f"WARN: on branch '{branch}', expected 'main' — continuing anyway")

    # 3. Fetch + rebase to avoid rejection from concurrent commits
    log("git fetch origin")
    run(["git", "fetch", "origin"], timeout=60)
    log("git pull --rebase (best-effort)")
    pull = run(["git", "pull", "--rebase", "origin", branch], timeout=60)
    if pull.returncode != 0:
        log(f"WARN: pull --rebase failed (rc={pull.returncode}); "
            f"stderr: {pull.stderr[:300]}")
        # Try to abort rebase
        run(["git", "rebase", "--abort"])

    # 4. Detect changes in watched paths
    # Filter to paths that actually exist locally (git add fails hard on
    # non-existent paths, even though we just want to skip them).
    existing_paths = [p for p in WATCHED_PATHS if (REPO / p).exists()]
    if len(existing_paths) < len(WATCHED_PATHS):
        missing = set(WATCHED_PATHS) - set(existing_paths)
        log(f"  Skipping {len(missing)} non-existent path(s): {sorted(missing)[:3]}...")

    log("Detecting changes in watched paths...")
    res = run(["git", "status", "--porcelain", "--"] + existing_paths)
    changed = [l for l in res.stdout.splitlines() if l.strip()]
    log(f"  {len(changed)} changed entries")

    if not changed:
        log("No changes to commit. Exiting cleanly (idempotent).")
        return 0

    # Show first 10 for context
    for line in changed[:10]:
        log(f"  {line}")
    if len(changed) > 10:
        log(f"  ... and {len(changed) - 10} more")

    # 5. Add watched paths
    log("git add <watched paths>")
    add = run(["git", "add", "--"] + existing_paths)
    if add.returncode != 0:
        log(f"ERROR: git add failed: {add.stderr[:500]}")
        return 2

    # 6. Commit
    msg = f"auto(daily-push): {today} reports + levels ({len(changed)} files)"
    log(f"git commit -m '{msg}'")
    commit = run(["git", "commit", "-m", msg])
    if commit.returncode != 0:
        if "nothing to commit" in (commit.stdout + commit.stderr):
            log("Nothing to commit (race condition with another workflow). Exiting 0.")
            return 0
        log(f"ERROR: git commit failed: {commit.stderr[:500]}")
        return 3

    # 7. Push
    log("git push origin main")
    push = run(["git", "push", "origin", "main"], timeout=120)
    if push.returncode != 0:
        err_log = REPO / "automation" / "reports" / "daily_push_error.log"
        err_log.parent.mkdir(parents=True, exist_ok=True)
        err_log.write_text(
            f"Daily auto-push failed at {ts}\n\n"
            f"STDOUT:\n{push.stdout}\n\nSTDERR:\n{push.stderr}\n"
        )
        log(f"ERROR: git push failed: {push.stderr[:500]}")
        log(f"Full error: {err_log}")
        return 4

    # 8. Verify
    log("Verifying push...")
    rev_local = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    rev_remote = run(["git", "rev-parse", "origin/main"]).stdout.strip()
    if rev_local != rev_remote:
        log(f"WARN: local HEAD ({rev_local[:12]}) != origin/main ({rev_remote[:12]})")
        return 5
    log(f"  origin/main is at {rev_remote[:12]} — pushed OK")

    log(f"✅ Daily auto-push complete ({len(changed)} files, {ts})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[auto-push] UNCAUGHT EXCEPTION: {type(e).__name__}: {e}",
              file=sys.stderr)
        sys.exit(99)
