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
import json
import time
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

def _find_repo() -> Path:
    """Locate the repo root without hard-coding one machine's path.

    GITHUB_WORKSPACE wins, because that is where CI checks the repo out.
    Otherwise walk up from this file until a directory containing
    "automation" is found, so any clone or worktree works.
    """
    if "GITHUB_WORKSPACE" in os.environ:
        return Path(os.environ["GITHUB_WORKSPACE"])
    for _parent in Path(__file__).resolve().parents:
        if (_parent / "automation").is_dir():
            return _parent
    return Path("/workspace/YW-concept-ki7409")


REPO = _find_repo()

# Paths that should be in every daily auto-push
# Push attempts before giving up. Each attempt re-syncs with origin.
PUSH_ATTEMPTS = 5

WATCHED_PATHS = [
    # Reports
    "automation/reports/strategy_ranking/",
    "automation/reports/strategy_settlement/",
    "automation/reports/llm_iteration/",
    "automation/reports/live_scan/",
    "automation/reports/ocs_btc_5m/",
    "automation/reports/ttrades_btc/",
    # The 180-day one-hour backtest — the optimiser's second independent
    # track. The workflow recomputes it every night, but until this path
    # was watched its output was never committed, so the copy in the repo
    # stayed frozen at whatever was last committed by hand. Anyone reading
    # it (and the optimiser itself, when it is run outside CI) was reading
    # a stale sample.
    "automation/reports/historical_backtest/",
    # Config (state + settings)
    "automation/config/strategy_levels.json",
    "automation/config/ranking_settings.json",
    "automation/config/settlement_overrides.json",
    "automation/config/strategy_overrides.json",
    "automation/config/weight_overrides.json",
    "automation/config/exit_overrides.json",
    "automation/config/rl_policy.npz",
    "automation/config/exit_arm_state.json",
    "automation/reports/rl_iteration/",
    "automation/reports/weight_optimization/",
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


def _porcelain_path(line: str) -> str:
    """Extract the path from a `git status --porcelain` line.

    The status code is two characters plus a space, so the path starts at
    index 3. Renames are "R  old -> new" and the new path is the one that
    exists on disk. Paths with spaces are quoted by git.
    """
    path = line[3:].strip()
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    if path.startswith('"') and path.endswith('"'):
        path = path[1:-1]
    return path


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

    # 3. Fetch + rebase to avoid rejection from concurrent commits.
    #
    # Order matters, and the previous order was actively harmful.
    #
    # It ran `git add -A` and then `git pull --rebase`. A rebase refuses to
    # run with a dirty index ("Your index contains uncommitted changes"), so
    # that rebase ALWAYS failed. The fallback then did
    # `git reset --hard origin/main`, which moves HEAD onto the remote tip
    # and throws away every local commit that had not been pushed yet —
    # including the commit the previous workflow step had just made holding
    # today's ranking files. That is how ranking_<today>.json could be
    # generated, committed, and then vanish from main.
    #
    # The fallback's `git stash pop` then conflicted on
    # docs/dashboard-data.json and left it unmerged ("UU"), and the script
    # went on to `git add` and commit that file — publishing the conflict
    # markers to main and to the public dashboard.
    #
    # The fix: stash the working tree first (a stash preserves local
    # commits, unlike reset --hard), rebase the local commits onto
    # origin/main, then restore the stash. And never commit an unmerged path.
    log("git fetch origin")
    run(["git", "fetch", "origin"], timeout=60)

    stash_ok = False
    if run(["git", "status", "--porcelain"]).stdout.strip():
        log("  working tree dirty -> stashing before rebase")
        st = run(["git", "stash", "push", "--include-untracked",
                  "-m", "auto-push-pre-rebase"], timeout=60)
        stash_ok = st.returncode == 0
        if not stash_ok:
            log(f"WARN: stash failed: {st.stderr[:200]}")

    log("git pull --rebase onto origin")
    pull = run(["git", "pull", "--rebase", "origin", branch], timeout=120)
    if pull.returncode != 0:
        log(f"WARN: pull --rebase failed (rc={pull.returncode}); "
            f"stderr: {pull.stderr[:300]}")
        run(["git", "rebase", "--abort"], timeout=60)
        # Fall back to a mixed reset, NOT a hard one. A mixed reset moves
        # HEAD onto the remote tip and leaves the working tree alone, so
        # the content of the discarded local commits survives as unstaged
        # modifications and gets picked up by the commit below. `reset
        # --hard` would have deleted it.
        log("git reset --mixed origin/<branch> (keep working tree contents)")
        run(["git", "reset", "--mixed", f"origin/{branch}"], timeout=60)
    else:
        log("  rebased onto origin/main")

    if stash_ok:
        pop = run(["git", "stash", "pop"], timeout=60)
        if pop.returncode != 0:
            log(f"WARN: stash pop failed: {pop.stderr[:200]}")

    # 3b. Never publish a conflicted file. A stash pop or a rebase can
    # leave paths unmerged; committing those writes the conflict markers
    # into the file, and for docs/dashboard-data.json that breaks the
    # public dashboard. Restore the conflicted paths from origin instead.
    unmerged = run(["git", "diff", "--name-only", "--diff-filter=U"]).stdout.split()
    if unmerged:
        log(f"  {len(unmerged)} unmerged path(s) - restoring from origin:")
        for p in unmerged:
            log(f"    {p}")
            co = run(["git", "checkout", "--force", f"origin/{branch}", "--", p],
                     timeout=60)
            if co.returncode != 0:
                # Not present in origin (a brand-new file) - drop the
                # conflicted copy instead of committing conflict markers.
                run(["git", "rm", "--force", "--", p], timeout=60)
            else:
                run(["git", "reset", "HEAD", "--", p], timeout=60)

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

    # 4b. Refuse to publish JSON that does not parse. The public dashboard
    # serves docs/dashboard-data.json directly, so a malformed file breaks
    # the site. Restore anything unparseable from origin and carry on with
    # the rest.
    broken = []
    for line in changed:
        path = _porcelain_path(line)
        if not path or not path.endswith(".json"):
            continue
        f = REPO / path
        if not f.exists():
            continue
        try:
            json.loads(f.read_text())
        except Exception as e:
            broken.append(path)
            log(f"  INVALID JSON: {path} ({e})")
    for path in broken:
        co = run(["git", "checkout", "--force", f"origin/{branch}", "--", path],
                 timeout=60)
        if co.returncode != 0:
            run(["git", "rm", "--force", "--", path], timeout=60)
        else:
            run(["git", "reset", "HEAD", "--", path], timeout=60)
    if broken:
        # Re-detect: the restored files are no longer part of the change set.
        res = run(["git", "status", "--porcelain", "--"] + existing_paths)
        changed = [l for l in res.stdout.splitlines() if l.strip()]
        log(f"  {len(changed)} changed entries after dropping invalid JSON")

    if not changed:
        # There may still be local commits that have never been pushed —
        # after the rebase above, the ranking commit (and any other commit
        # made earlier in the same workflow) sits in HEAD, ahead of
        # origin/main, with a clean working tree. Exiting here would leave
        # it unpushed, which is exactly how the daily ranking file went
        # missing. Only stop if there is genuinely nothing to push.
        ahead = run(["git", "rev-list", "--count", f"origin/{branch}..HEAD"]).stdout.strip()
        if ahead and ahead != "0":
            log(f"No new file changes, but {ahead} local commit(s) ahead of "
                f"origin — pushing them.")
        else:
            log("No changes to commit and nothing to push. Exiting cleanly (idempotent).")
            return 0
    else:
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
                log("Nothing to commit (race condition with another workflow). Continuing to push.")
            else:
                log(f"ERROR: git commit failed: {commit.stderr[:500]}")
                return 3

    # 7. Push, with retry.
    #
    # A single push attempt is not enough: other workflows commit to main
    # every few minutes, so a push that is correct when it starts can be
    # rejected as non-fast-forward a second later. Each attempt re-syncs
    # with origin and replays the commit on top.
    #
    # The re-sync here must also preserve the local commit. `git pull
    # --rebase` alone refuses to run with a dirty index, so the old code
    # ran `git add -A` first — and if the rebase then failed, the commit
    # was left in an unmergeable state. Stash, rebase, pop: same shape as
    # step 3, and it keeps the commit intact.
    push = None
    for attempt in range(1, PUSH_ATTEMPTS + 1):
        log(f"git push origin main (attempt {attempt}/{PUSH_ATTEMPTS})")
        push = run(["git", "push", "origin", "main"], timeout=120)
        if push.returncode == 0:
            break
        log(f"  push rejected: {push.stderr.strip().splitlines()[0][:120] if push.stderr.strip() else 'unknown'}")
        if attempt < PUSH_ATTEMPTS:
            log(f"  re-syncing with origin/{branch} and retrying in 5s")
            run(["git", "fetch", "origin"], timeout=60)
            retry_stash = False
            if run(["git", "status", "--porcelain"]).stdout.strip():
                st = run(["git", "stash", "push", "--include-untracked",
                          "-m", "auto-push-pre-retry"], timeout=60)
                retry_stash = st.returncode == 0
            rb = run(["git", "pull", "--rebase", "origin", branch], timeout=120)
            if rb.returncode != 0:
                run(["git", "rebase", "--abort"], timeout=60)
                # Mixed, not hard: keep the working tree contents so the
                # commit is not silently destroyed by the retry.
                run(["git", "reset", "--mixed", f"origin/{branch}"], timeout=60)
            if retry_stash:
                run(["git", "stash", "pop"], timeout=60)
            time.sleep(5)

    if push is None or push.returncode != 0:
        err_log = REPO / "automation" / "reports" / "daily_push_error.log"
        err_log.parent.mkdir(parents=True, exist_ok=True)
        err_log.write_text(
            f"Daily auto-push failed at {ts} after {PUSH_ATTEMPTS} attempts\n\n"
            f"STDOUT:\n{push.stdout if push else ''}\n\n"
            f"STDERR:\n{push.stderr if push else ''}\n"
        )
        log(f"ERROR: git push failed after {PUSH_ATTEMPTS} attempts: "
            f"{(push.stderr[:500] if push else 'unknown')}")
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
