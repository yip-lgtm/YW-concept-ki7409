#!/bin/bash
# git_push.sh - one-shot auth + push for YW-concept-ki7409
# Use after sandbox restart (.ssh is wiped, must re-arm HTTPS+PAT)
set -e
cd "$(dirname "$0")/../.."

# PAT is in env (loaded from /workspace/apex-bootcamp/AUTOMATION/.env)
PAT="${APEX_PAT:-${GITHUB_PAT:-${GHP:-}}}"
if [ -z "$PAT" ]; then
    echo "[git_push] ERROR: No PAT in env (set APEX_PAT or GITHUB_PAT)" >&2
    exit 1
fi

# Re-arm remote URL with fresh token
git remote set-url origin "https://x-access-token:${PAT}@github.com/yip-lgtm/YW-concept-ki7409.git"

# Pull rebase to avoid non-fast-forward
git pull --rebase --autostash origin main 2>&1 || echo "[git_push] pull rebase failed, continuing"

# Show what will be pushed
echo
echo "=== Changes to push ==="
git status --short
git diff --stat HEAD 2>/dev/null | head -10
echo

# Commit if dirty (auto-message)
if [ -n "$(git status --porcelain)" ]; then
    git add -A
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S")
    git -c user.name="Mavis" -c user.email="mavis@MiniMax" commit -m "auto(snapshot): ${TIMESTAMP} dirty tree cleanup" 2>&1 | head -2 || true
fi

# Push with force-with-lease (safe force)
GIT_SSL_NO_VERIFY=true git push --force-with-lease origin main 2>&1
