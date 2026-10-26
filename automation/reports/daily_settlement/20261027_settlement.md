# Daily Settlement — 2026-10-27 (HKT)

**Account:** PAAPEX…091  
**Generated:** 2026-10-27 04:17:56 HKT  
**DD state file:** `automation/state/ops_dd_hold.json`  

## Equity / DD
- Equity start: `None`
- Equity end: `None`
- Open P/L: `None` · Working: `None`
- Day P/L: **$-200.00** (source: `paper_allowlisted_pnl_fallback`)
- DD amount: **$-200.00** vs `day_start` · limit **-100.0**
- **dd_hold: `True`** · tp_limit_usd (report-only default): `300.0`

## Fills (allowlist focus)
- Total rows: 3 · allowlisted: 2 · non-allow: 1
- Allowlisted PnL: **$-200.00**

| Strategy | n | wins | losses | pnl |
|----------|---|------|--------|-----|
| crt | 2 | 0 | 2 | $-200.00 |

## Allowlisted signal outcomes
- n=9 · gated=7 · fired/ungated=2

## LLM
- status: **`ok`**
- invoked: `True`
- detail: automation/reports/strategy_ranking/iterations/iteration_scientist_20261027_041746.json

## Ops briefing bullets
- Settlement 2026-10-27 HKT · PAAPEX…091 · day P/L $-200.00 (src=paper_allowlisted_pnl_fallback) · DD -200.00 vs limit -100.0
- ⛔ DD HOLD active — no new entries (state: automation/state/ops_dd_hold.json). Tell Trading desk once. Unlock next session or --clear-hold.
- Allowlist fills: n=2 pnl=$-200.00; signals allow n=9 gated=7
- By strategy — crt: n=2 pnl=$-200.0
- Policy: QTY=1 Bracket only (NOT Group QTY20); never use Order Ticket Limit as sim last.
- LLM Scientist ran OK; report=automation/reports/strategy_ranking/iterations/iteration_scientist_20261027_041746.json
- Never re-handoff stale/gated/null-position signals; stay quiet if nothing changed.

## Ops lessons (folded)

- Never treat Order Ticket Limit as sim last (MBT 83660 false OUT_OF_GATE) — use chart/DOM/explicit last.
- Bracket SL/TP: prefer paper-anchored absolute levels vs fill-offset when fill ≠ paper; flag drift.
- Handoff text must say QTY=1 Bracket (NOT Group QTY20). Ops-only Tradovate; A皮 coordinates.
- Live allowlist only: 50-20-Pullback, CRT, Stair, H-Pattern.
- Envelope defaults: −$100 DD hold / +$300 TP (historical). Change only with explicit user choice.

## Live scan snapshot
- positions open: 0
- heartbeat: `2026-10-26T20:09:22.525068+00:00`
- circuit_breaker: `{'consecutive_good_scans': 40}`

## Config defaults (documented)
- DD_LIMIT_USD = -100.0 (hold when day DD ≤ this)
- TP_LIMIT_USD = 300.0 (historical +$300 envelope; not auto-enforced here)

