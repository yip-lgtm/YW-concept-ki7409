#!/bin/bash
# Re-arm git remote with PAT. Source from any script.
# Usage: source automation/scripts/git_push_helper.sh
PAT="${APEX_PAT:-${GITHUB_PAT:-${GHP:-}}}"
if [ -z "$PAT" ]; then
    echo "[git_push_helper] No PAT in env" >&2
    return 1 2>/dev/null || exit 1
fi
git remote set-url origin "https://x-access-token:${PAT}@github.com/yip-lgtm/YW-concept-ki7409.git" 2>/dev/null
