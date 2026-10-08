# Daily Settlement + −$100 DD + LLM Opt

粵語 + English · for A皮 / Ops / Trading desk

## 做咩 / What

每日結算 Tradovate sim book（PAAPEX…091），執行 **−$100 DD hold**，並喺結算後觸發現有 **LLM Iteration Scientist**（有 MiniMax key 先跑；冇就標 `llm_blocked`，結算同 DD 仍然成功）。

| Piece | Path |
|-------|------|
| Script | `automation/scripts/daily_settlement_llm_opt.py` |
| Workflow | `.github/workflows/daily-settlement-llm-opt.yml` |
| DD state (monitors read) | `automation/state/ops_dd_hold.json` |
| Reports | `automation/reports/daily_settlement/YYYYMMDD_settlement.{json,md}` |
| Ops book schema | `docs/ops_daily_book.schema.json` |
| Ops book example | `docs/ops_daily_book.example.json` |

## DD 規則 / Rules

- **Default `DD_LIMIT_USD = -100`**（可 `--dd-limit` 改；唔好 silently 改 live 數字）。
- `day_pnl` 優先用 Ops book：`day_pnl` 或 `equity_end - equity_start`。
- 若 book 冇 equity：fallback 用當日 HKT allowlisted paper `pnl_usd` 總和。
- 若有 `session_high_equity`：DD 可以同 session high 比（取更差嗰邊）。
- **`day_pnl` / DD amount ≤ −100 → `dd_hold: true`**，寫入 `automation/state/ops_dd_hold.json`（`dd: "held"`, `no_new_entries: true`）。
- Unlock：下個 HKT session 結算若未觸發 hold；或 `workflow_dispatch` / CLI `--clear-hold`；或人手改 state 為 `dd: "unlocked"`。
- **TP envelope**：report-only default **`TP_LIMIT_USD = +300`**（歷史 +$300）；本 script **唔會**自動改 live Ops envelope。改 −$100 / +$300 要 user 明示。

## Allowlist

Live Ops book only: **50-20-Pullback, CRT, Stair, H-Pattern**.

Qty policy: **QTY=1 Bracket**（NOT Group QTY20）. Ops-only Tradovate；A皮 coordinates.

## 點跑 / How to run

```bash
# Local (from repo root)
python automation/scripts/daily_settlement_llm_opt.py \
  --date 2026-10-05 \
  --book docs/ops_daily_book.example.json \
  --skip-llm

# Force unlock DD
python automation/scripts/daily_settlement_llm_opt.py --date 2026-10-05 --clear-hold --skip-llm
```

Ops 可以將當日 book 放到：
`automation/reports/daily_settlement/book_YYYYMMDD.json`
（workflow 會自動搵）。

### GitHub Actions

- **Cron:** `57 14 * * 1-5` = **22:57 HKT** weekdays  
- **Native Scientist backup:** `llm-iteration-scientist.yml` @ `0 16 * * 1-5` = **00:00 HKT**
- **Manual:**
  ```text
  Actions → Daily Settlement + $100 DD + LLM Opt → Run workflow
  inputs: date=YYYY-MM-DD, skip_llm=true|false, clear_hold=true|false, book_path=...
  ```
  or:
  ```bash
  gh workflow run daily-settlement-llm-opt.yml -f date=2026-10-05 -f skip_llm=false
  ```

## Secrets

| Secret | Required for |
|--------|----------------|
| `MINIMAX_API_KEY` | Scientist LLM path (conf≥60% auto-apply). Missing → `llm_blocked`. |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Optional ping only when DD hold or llm_blocked/error |

Settlement + DD **never** depend on MiniMax.

## Ops lessons（寫入 report notes）

1. Never treat Order Ticket Limit as sim last（MBT 83660 false OUT_OF_GATE）.
2. Bracket SL/TP：paper-anchored vs fill-anchored — flag drift。
3. Handoff 必須寫 **QTY=1 Bracket**，唔好 Group QTY20。

## Monitor integration

Live monitors / Grok Bot routine 應讀：

```text
automation/state/ops_dd_hold.json
```

Fields: `dd` (`held`|`unlocked`), `dd_hold` (bool), `no_new_entries`, `day_pnl`, `dd_limit_usd`, `unlock` hint.
