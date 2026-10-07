# lgtm-trade security cleanup script
# Run this from E:\lgtm-trade as Administrator in PowerShell 7
# Date: 2026-10-07
# Source: post-incident audit dump from user

# === STEP 0: PRE-FLIGHT ===
# Before running anything:
# 1. ROTATE THE POLYMARKET WALLET KEY (move funds to fresh wallet)
# 2. ROTATE POLYMARKET CLOB API KEYS (apiKey, apiSecret, apiPassphrase)
# 3. ROTATE ALL TELEGRAM BOT TOKENS via @BotFather (/revoke)
# 4. ROTATE GITHUB PAT
# 5. ROTATE POLYGON API KEY
# 6. ROTATE MINIMAX API KEY
#
# THEN come back and run this script. The values in your files are now
# all invalid; the script just removes them from the working tree.

# === STEP 1: BACKUP EVERYTHING ===
Write-Host "[1/8] Creating backup of current state..." -ForegroundColor Cyan
$backupDir = "E:\lgtm-trade-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
Copy-Item -Path "E:\lgtm-trade" -Destination $backupDir -Recurse -Force
Write-Host "  Backup created at $backupDir" -ForegroundColor Green

# === STEP 2: ADD .gitignore PATTERNS ===
Write-Host "[2/8] Updating .gitignore to prevent future leaks..." -ForegroundColor Cyan
$gitignorePath = "E:\lgtm-trade\.gitignore"
$newPatterns = @"

# === SECURITY (2026-10-07) ===
*.env
.env.*
*.env.local
*.env.production
*.env.development
*.env.test
seoul_config.json
seoul_config*.json
skills/*/config/.env
skills/*/config/*.env
btc_5m_bot.env
deploy_secrets.json
secrets/
secrets.json
secrets.yaml
secrets.toml
*.pem
*.key
*.p12
*.pfx
*id_rsa*
*id_dsa*
*id_ed25519*
*known_hosts*
.credentials/
"@
Add-Content -Path $gitignorePath -Value $newPatterns
Write-Host "  .gitignore hardened" -ForegroundColor Green

# === STEP 3: REPLACE HARDCODED TOKENS WITH ENV VAR READS ===
Write-Host "[3/8] Replacing hardcoded tokens with env var reads..." -ForegroundColor Cyan

# 3a) Python files - replace TG_TOKEN hardcodes with os.environ reads
Get-ChildItem -Path "E:\lgtm-trade" -Recurse -Include *.py -Exclude *.venv*,__pycache__* |
    ForEach-Object {
        $content = Get-Content $_.FullName -Raw
        $original = $content
        # Replace TG_TOKEN = '<actual>' with os.environ
        $content = $content -replace "TG_TOKEN\s*=\s*['""][0-9]{8,10}:AA[A-Za-z0-9_-]{30,}['""]", "TG_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')"
        $content = $content -replace "TG_TOKEN\s*=\s*['""]\d+['""]", "TG_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')"
        # Replace TG_CHAT = '<id>' with env
        $content = $content -replace "TG_CHAT\s*=\s*['""]\d{8,12}['""]", "TG_CHAT = os.environ.get('TELEGRAM_CHAT_ID', '')"
        if ($content -ne $original) {
            Set-Content -Path $_.FullName -Value $content -NoNewline
            Write-Host "  Patched: $($_.FullName.Replace('E:\lgtm-trade\', ''))" -ForegroundColor Yellow
        }
    }

# 3b) CJS/JS files - replace TG token hardcodes with process.env reads
Get-ChildItem -Path "E:\lgtm-trade" -Recurse -Include *.cjs,*.js -Exclude node_modules*,*.min.js |
    ForEach-Object {
        $content = Get-Content $_.FullName -Raw
        $original = $content
        $content = $content -replace "TG_TOKEN\s*[:=]\s*['""][0-9]{8,10}:AA[A-Za-z0-9_-]{30,}['""]", "TG_TOKEN: process.env.TELEGRAM_BOT_TOKEN || ''"
        $content = $content -replace "TG_TOKEN\s*[:=]\s*['""]\d+['""]", "TG_TOKEN: process.env.TELEGRAM_BOT_TOKEN || ''"
        $content = $content -replace "token\s*[:=]\s*['""][0-9]{8,10}:AA[A-Za-z0-9_-]{30,}['""]", "token: process.env.TELEGRAM_BOT_TOKEN || ''"
        if ($content -ne $original) {
            Set-Content -Path $_.FullName -Value $content -NoNewline
            Write-Host "  Patched: $($_.FullName.Replace('E:\lgtm-trade\', ''))" -ForegroundColor Yellow
        }
    }

# === STEP 4: SCRUB SEOL_CONFIG.JSON + BIF_CONFIG.JSON ===
Write-Host "[4/8] Scrubbing JSON config files..." -ForegroundColor Cyan

$seoulConfigPath = "E:\lgtm-trade\seoul_config.json"
if (Test-Path $seoulConfigPath) {
    $config = Get-Content $seoulConfigPath -Raw | ConvertFrom-Json
    # Blank out sensitive fields
    $config.privateKey = "<set via env var: POLYMARKET_PRIVATE_KEY>"
    $config.apiKey = "<set via env var: POLYMARKET_API_KEY>"
    $config.apiSecret = "<set via env var: POLYMARKET_API_SECRET>"
    $config.apiPassphrase = "<set via env var: POLYMARKET_API_PASSPHRASE>"
    # Write back with sensitive data replaced
    $config | ConvertTo-Json -Depth 10 | Set-Content $seoulConfigPath
    Write-Host "  Scrubbed: seoul_config.json (placeholders added)" -ForegroundColor Green
}

# === STEP 5: CREATE .env TEMPLATE ===
Write-Host "[5/8] Creating .env.template (committed) + .env (gitignored)..." -ForegroundColor Cyan
$envTemplate = @"
# === Polymarket ===
POLYMARKET_PRIVATE_KEY=
POLYMARKET_API_KEY=
POLYMARKET_API_SECRET=
POLYMARKET_API_PASSPHRASE=

# === Telegram ===
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# === Data ===
POLYGON_API_KEY=
MINIMAX_API_KEY=

# === GitHub ===
GITHUB_PAT=

# === Longbridge (paper) ===
LBP_APP_KEY=
LBP_APP_SECRET=
LBP_ACCESS_TOKEN=
"@
$envTemplatePath = "E:\lgtm-trade\.env.template"
Set-Content -Path $envTemplatePath -Value $envTemplate

$envPath = "E:\lgtm-trade\.env"
if (-not (Test-Path $envPath)) {
    Set-Content -Path $envPath -Value $envTemplate
    Write-Host "  Created .env (gitignored) — FILL IN your new rotated values" -ForegroundColor Green
} else {
    Write-Host "  .env already exists, leaving alone" -ForegroundColor Yellow
}

# === STEP 6: DELETE THE LEAKED FILES (or move to .gitignore + history purge) ===
Write-Host "[6/8] Identifying files containing real secrets to remove from git tracking..." -ForegroundColor Cyan

$filesToUntrack = @(
    "E:\lgtm-trade\btc_5m_bot.env",
    "E:\lgtm-trade\seoul_config.json",
    "E:\lgtm-trade\deploy_seoul.sh",
    "E:\lgtm-trade\skills\btc_5m_trader\config\.env"
)

foreach ($file in $filesToUntrack) {
    if (Test-Path $file) {
        # Don't actually delete the file — just remove from git tracking
        # and the local file gets .gitignored going forward
        Write-Host "  Untracking from git: $file" -ForegroundColor Yellow
        Push-Location "E:\lgtm-trade"
        try {
            git rm --cached "$file" 2>&1 | Out-Null
        } catch {
            # file may already be untracked
        }
        Pop-Location
    }
}

# === STEP 7: PURGE GIT HISTORY (BFG approach) ===
Write-Host "[7/8] PURGING GIT HISTORY — this rewrites all commits..." -ForegroundColor Cyan
Write-Host "  This step is DESTRUCTIVE. Notify all collaborators first." -ForegroundColor Red
Write-Host "  Use BFG Repo-Cleaner: https://rtyley.github.io/bfg-repo-cleaner/" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. Download BFG:  java -jar bfg.jar --version" -ForegroundColor Yellow
Write-Host "  2. Create a secrets.txt file with all 5 leaked values (one per line)" -ForegroundColor Yellow
Write-Host "  3. Run:  java -jar bfg.jar --replace-text secrets.txt --no-blob-protection lgtm-trade.git" -ForegroundColor Yellow
Write-Host "  4. Cleanup:  cd lgtm-trade.git && git reflog expire --expire=now --all && git gc --prune=now --aggressive" -ForegroundColor Yellow
Write-Host "  5. Force-push:  git push --force --all" -ForegroundColor Yellow
Write-Host "  6. Notify collaborators to reclone" -ForegroundColor Yellow
Write-Host ""
Write-Host "  OR use git-filter-repo (Python):" -ForegroundColor Cyan
Write-Host "  pip install git-filter-repo" -ForegroundColor Yellow
Write-Host "  cd E:\lgtm-trade" -ForegroundColor Yellow
Write-Host "  git filter-repo --invert-paths --path btc_5m_bot.env --path seoul_config.json --path deploy_seoul.sh --path skills/btc_5m_trader/config/.env --force" -ForegroundColor Yellow
Write-Host "  git remote add origin https://github.com/yip-lgtm/lgtm-trade.git  # if not set" -ForegroundColor Yellow
Write-Host "  git push --force-with-lease origin master  # CAUTION: rewrites history" -ForegroundColor Yellow

# === STEP 8: VERIFY ===
Write-Host "[8/8] Verification..." -ForegroundColor Cyan
Push-Location "E:\lgtm-trade"
Write-Host "  Current branch: $(git branch --show-current)" -ForegroundColor White
Write-Host "  Tracked files containing TG tokens (should be 0):"
$tgMatches = git grep -E "[0-9]{8,10}:AA[A-Za-z0-9_-]{30,}" -- '*.py' '*.cjs' '*.js' '*.json' '*.sh' '*.md' 2>$null
if ($tgMatches) {
    Write-Host "  STILL LEAKED:" -ForegroundColor Red
    $tgMatches | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
} else {
    Write-Host "    0 — clean!" -ForegroundColor Green
}

Write-Host ""
Write-Host "  Tracked files containing ghp_ PATs (should be 0):"
$patMatches = git grep -E "ghp_[A-Za-z0-9]{30,}" -- '*.py' '*.cjs' '*.js' '*.json' '*.sh' '*.md' 2>$null
if ($patMatches) {
    Write-Host "  STILL LEAKED:" -ForegroundColor Red
    $patMatches | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
} else {
    Write-Host "    0 — clean!" -ForegroundColor Green
}

Write-Host ""
Write-Host "  Tracked .env files (should be 0):"
$envFiles = git ls-files | Where-Object { $_ -match '\.env$|secrets\.json|seoul_config\.json' }
if ($envFiles) {
    Write-Host "  STILL TRACKED:" -ForegroundColor Red
    $envFiles | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
} else {
    Write-Host "    0 — clean!" -ForegroundColor Green
}
Pop-Location

Write-Host ""
Write-Host "=== CLEANUP COMPLETE ===" -ForegroundColor Green
Write-Host "Backup at: $backupDir" -ForegroundColor Cyan
Write-Host ""
Write-Host "NEXT STEPS:" -ForegroundColor Yellow
Write-Host "  1. Verify all new secrets are filled in .env" -ForegroundColor White
Write-Host "  2. Test that all scripts still work (re-run btc_5m_bot.py etc.)" -ForegroundColor White
Write-Host "  3. Run git history purge (Step 7 above) if you want to remove from history" -ForegroundColor White
Write-Host "  4. Force-push rewritten history" -ForegroundColor White
Write-Host "  5. Notify all collaborators to reclone" -ForegroundColor White
