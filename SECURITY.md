# Security Policy

> **Last updated**: 2026-10-07 (post-incident response)
> **Scope**: yip-lgtm/YW-concept-ki7409 + sibling repos under yip-lgtm org

This document codifies how secrets, credentials, and access tokens are
handled across the YW concept trading platform. It exists because a
2026-10-07 audit surfaced historical credential leaks; the rules below
are the remediation + prevention contract.

---

## 🚨 TL;DR — 4 absolute rules

1. **NEVER hardcode credentials** in code, comments, JSON, or markdown
   that is committed to git. Even test/dev keys must come from env or a
   secret manager.
2. **NEVER paste secrets into chat, PR comments, or issue bodies.**
   Not even temporarily. Not even with a `REDACTED` placeholder. Use
   the official secret store instead.
3. **Treat any secret that has ever been committed as compromised.**
   Rotate it. Do not rely on a future history rewrite to "un-leak" it.
4. **All live tokens live in GitHub Actions secrets, `.env` outside
   the repo, or a proper secret manager.** See [§ Where secrets live](#where-secrets-live).

---

## Where secrets live

| Repo / system            | Mechanism              | Reference                              |
| ------------------------ | ---------------------- | -------------------------------------- |
| **YW-concept-ki7409**    | GitHub Actions secrets | repo → Settings → Secrets → Actions    |
| **lgtm-trade** (private) | Local `.env` files     | `E:\lgtm-trade\.env` (NOT in git)     |
| **Polymarket / CLOB**    | `.env` +1Password CLI  | API keys never in repo                 |
| **Telegram bots**        | `@BotFather` + GHA     | token rotated via `/revoke`            |
| **Longbridge**           | GHA secrets            | `LBP_APP_KEY` / `LBP_APP_SECRET` / `LBP_ACCESS_TOKEN` |
| **AWS / VPS SSH**        | `~/.ssh/` outside repo | keys rotated separately                |

---

## 2026-10-07 incident — what happened

A security audit discovered the following exposed credentials:

| # | Type                    | Locations                                                                                                | Status (post-remediation)               |
| - | ----------------------- | -------------------------------------------------------------------------------------------------------- | --------------------------------------- |
| 1 | Polymarket wallet key   | `E:\lgtm-trade\seoul_config.json` line 51–55 (committed to `origin/master`)                              | **ROTATE NOW**; funds should be moved to fresh wallet immediately |
| 2 | Polymarket CLOB API key | same file + `btc_5m_bot.env` line 2 + `deploy_seoul.sh` line 23 + `skills/btc_5m_trader/config/.env` line 4 | **ROTATE NOW**; revoke via Polymarket UI |
| 3 | Telegram bot #8606567428| 15+ Python/CJS files in `lgtm-trade`                                                                      | **ROTATE via @BotFather**; replace with env var reads |
| 4 | Telegram bot #8976341017| `E:\YW-concept-ki7409\automation\scripts\heartbeat_cron.py` lines 26–27 (now patched, but **still in git history**) | **ROTATE** + BFG/filter-repo history purge |
| 5 | Telegram bot #818851…   | `lgtm-trade` git history (no current file)                                                                | BFG history purge sufficient             |
| 6 | Polygon API key         | `lgtm-trade\memory\2026-06-10.md` line 119 + `dl_polygon.cjs`                                              | **ROTATE**; remove from memory files     |
| 7 | GitHub PAT + gateway    | `lgtm-trade\memory\2026-06-10.md` line 117–118; `yw_daily.py` rebuilds URL at runtime                    | **ROTATE GitHub PAT**; audit gateway ACLs |
| 8 | MiniMax key             | VPS `.env`                                                                                                | Audit VPS access; rotate if exposed     |
| 9 | VPS SSH keys + IPs      | `lgtm-trade\memory\2026-06-10.md` lines 108, 114–115, 210–215                                              | Rotate keypair on Seoul + California VPS |
| 10 | GHA secrets (live)      | `YW-concept-ki7409/.github/workflows/*.yml` → 7 secrets                                                   | **Rotate all 7**                        |

---

## What was fixed in this commit (v5.3)

| File                                       | Change                                                                   |
| ------------------------------------------ | ------------------------------------------------------------------------ |
| `automation/scripts/heartbeat_cron.py`     | Removed hardcoded `TG_TOKEN` + `TG_CHAT`; now reads `os.environ.get(...)` |
| `.gitignore`                               | Added patterns: `*.pem`, `*.key`, `*id_rsa*`, `secrets/`, `.credentials/`, `secrets.{json,yaml,toml}`, etc. |
| `SECURITY.md` (this file)                  | Codifies the policy + lists the 2026-10-07 incident + remediation steps  |

---

## Outstanding actions for the user (cannot be done from this sandbox)

These require either the user's local machine, the GHA UI, or a manual
provider-side rotation:

### P0 — within 1 hour

1. **Rotate Telegram bot #8976341017** (`@BotFather` → `/revoke` → mint new)
   - This token was hardcoded in `heartbeat_cron.py` and is now in `main`
     branch git history. Even after the file patch, anyone with the history
     can use it.
2. **Rotate Telegram bot #8606567428** (also hardcoded in many files)
3. **Rotate Polymarket wallet private key**
   - Move all funds out of current wallet to a fresh wallet.
   - Old private key is permanently compromised — assume drained.
4. **Revoke + re-mint Polymarket CLOB API key pair** (apiKey, apiSecret,
   apiPassphrase).
5. **Rotate GitHub PAT** (the one currently used for `git push` to this repo)
   - Generate new fine-grained PAT with minimal scopes.
6. **Rotate all 7 GHA secrets** in `yip-lgtm/YW-concept-ki7409`:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `MINIMAX_API_KEY`
   - `POLYGON_API_KEY`
   - `AI_TRADER_TOKEN`
   - `APEX_PAT`
   - `LBP_APP_KEY` / `LBP_APP_SECRET` / `LBP_ACCESS_TOKEN` (3)

### P1 — within 24 hours

7. **BFG / git-filter-repo history purge** for:
   - `YW-concept-ki7409` — `8976341017:AA...` (TG token)
   - `lgtm-trade` — all 5 hardcoded credentials + the `#818851` from history
   - Force-push rewritten history; **notify all collaborators** of the reset.

8. **VPS keypair rotation** (Seoul + California):
   - Generate new ED25519 keypair.
   - Update `authorized_keys` on both VPSes.
   - Remove old public key from `~/.ssh/authorized_keys`.
   - Audit VPS access logs for any unauthorized entry since first exposure.

9. **MiniMax API key** (if you find a leak): rotate via MiniMax dashboard.

### P2 — within 1 week

10. **Move all `lgtm-trade` secrets out of repo files**:
    - Add `*.env`, `seoul_config.json`, `secrets.json` to `lgtm-trade/.gitignore`.
    - Migrate values to a proper secret manager (1Password CLI, Doppler, AWS SM).
    - Create a `E:\lgtm-trade\secrets\` directory outside the repo + symlink.

11. **Replace all hardcoded TG tokens in `lgtm-trade/*.py/*.cjs`** with
    `process.env.TG_TOKEN` / `os.environ.get("TG_TOKEN")` reads.

12. **Add pre-commit + CI secret scanning**:
    - `gitleaks` pre-commit hook on both repos.
    - `gitleaks` GitHub Action on every PR.

---

## Reporting new leaks

If you discover a new leak:
1. **Don't** paste the secret into chat, even in a private channel.
2. **Do** rotate the credential immediately, then investigate the scope
   of historical exposure.
3. **Do** add the leak pattern to the [Outstanding actions](#outstanding-actions-for-the-user-cannot-be-done-from-this-sandbox)
   section above.
4. **Do** notify all collaborators of the rotation.
5. **Do** update this `SECURITY.md` with a new incident row.

---

## Verifying a fix

After rotating + history-purging, verify by:
```bash
# 1. Confirm no secret present in working tree
git grep -E "(8976341017|8606567428|ghp_)[A-Za-z0-9]"   # should return nothing

# 2. Confirm no secret in any branch's full history
git log --all -p | grep -E "8976341017"                    # should return nothing

# 3. Confirm new value in GHA secrets UI
#    GitHub → repo → Settings → Secrets → Actions → check updated_at
```

---

*This file is part of the YW concept trading platform's compliance with
the 4-power separation + audit-trail + accountability policy.*
