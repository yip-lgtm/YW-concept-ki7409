# Daily Settlement — 2026-10-23 (HKT)

**Account:** PAAPEX…091  
**Generated:** 2026-10-23 03:02:51 HKT  
**DD state file:** `automation/state/ops_dd_hold.json`  

## Equity / DD
- Equity start: `None`
- Equity end: `None`
- Open P/L: `None` · Working: `None`
- Day P/L: **$+323.60** (source: `paper_allowlisted_pnl_fallback`)
- DD amount: **$+323.60** vs `day_start` · limit **-100.0**
- **dd_hold: `False`** · tp_limit_usd (report-only default): `300.0`

## Fills (allowlist focus)
- Total rows: 2 · allowlisted: 2 · non-allow: 0
- Allowlisted PnL: **$+323.60**

| Strategy | n | wins | losses | pnl |
|----------|---|------|--------|-----|
| crt | 2 | 2 | 0 | $+323.60 |

## Allowlisted signal outcomes
- n=37 · gated=32 · fired/ungated=5

## LLM
- status: **`ok`**
- invoked: `True`
- detail: automation/reports/strategy_ranking/iterations/iteration_scientist_20261023_030242.json

## Ops briefing bullets
- Settlement 2026-10-23 HKT · PAAPEX…091 · day P/L $+323.60 (src=paper_allowlisted_pnl_fallback) · DD +323.60 vs limit -100.0
- ✅ DD unlocked — under −$100 limit.
- Allowlist fills: n=2 pnl=$+323.60; signals allow n=37 gated=32
- By strategy — crt: n=2 pnl=$+323.6
- Policy: QTY=1 Bracket only (NOT Group QTY20); never use Order Ticket Limit as sim last.
- LLM Scientist ran OK; report=automation/reports/strategy_ranking/iterations/iteration_scientist_20261023_030242.json
- Never re-handoff stale/gated/null-position signals; stay quiet if nothing changed.

## Ops lessons (folded)

- Never treat Order Ticket Limit as sim last (MBT 83660 false OUT_OF_GATE) — use chart/DOM/explicit last.
- Bracket SL/TP: prefer paper-anchored absolute levels vs fill-offset when fill ≠ paper; flag drift.
- Handoff text must say QTY=1 Bracket (NOT Group QTY20). Ops-only Tradovate; A皮 coordinates.
- Live allowlist only: 50-20-Pullback, CRT, Stair, H-Pattern.
- Envelope defaults: −$100 DD hold / +$300 TP (historical). Change only with explicit user choice.

## Live scan snapshot
- positions open: 3
- heartbeat: `2026-10-22T18:52:24.591276+00:00`
- circuit_breaker: `{'consecutive_good_scans': 20}`

## Config defaults (documented)
- DD_LIMIT_USD = -100.0 (hold when day DD ≤ this)
- TP_LIMIT_USD = 300.0 (historical +$300 envelope; not auto-enforced here)

