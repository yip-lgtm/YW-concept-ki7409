# Git Push Setup (YW-concept-ki7409)

## Sandbox note
- `.ssh/` is wiped between Mavis sandbox restarts
- HTTPS+PAT is the only reliable push method
- PAT is stored at `/workspace/apex-bootcamp/AUTOMATION/.env` as `APEX_PAT`

## One-line push (after sandbox restart)
```bash
# Load env (PAT) + re-arm remote + commit dirty + force-with-lease push
set -a && source /workspace/apex-bootcamp/AUTOMATION/.env && set +a
bash automation/scripts/git_push.sh
```

## What git_push.sh does
1. Re-arm `origin` URL with `https://x-access-token:<PAT>@github.com/...`
2. `git pull --rebase --autostash origin main` (avoid non-fast-forward)
3. Auto-commit dirty tree with timestamped message
4. `git push --force-with-lease origin main` (safe force, no one-else-pushed check)

## Force-with-lease safety
- `--force-with-lease` only succeeds if no one else pushed since last fetch
- If GHA workflow committed + you force-push → push fails (correct, you must `git fetch && rebase`)
- This prevents wiping auto-commits from `live-scan`/`ocs-btc` workflows

## GHA workflow pattern (in every push step)
```bash
git pull --rebase --autostash origin main 2>&1 || echo "pull failed, continuing"
git add automation/reports/<dir>/ || true
git commit -m "auto(<name>): ..." --allow-empty || true
git push --force-with-lease origin main || echo "push failed"
```
