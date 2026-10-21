# Daily Settlement — 2026-10-22 (HKT)

**Account:** PAAPEX…091  
**Generated:** 2026-10-22 03:06:35 HKT  
**DD state file:** `automation/state/ops_dd_hold.json`  

## Equity / DD
- Equity start: `None`
- Equity end: `None`
- Open P/L: `None` · Working: `None`
- Day P/L: **$+15.83** (source: `paper_allowlisted_pnl_fallback`)
- DD amount: **$+15.83** vs `day_start` · limit **-100.0**
- **dd_hold: `False`** · tp_limit_usd (report-only default): `300.0`

## Fills (allowlist focus)
- Total rows: 3 · allowlisted: 3 · non-allow: 0
- Allowlisted PnL: **$+15.83**

| Strategy | n | wins | losses | pnl |
|----------|---|------|--------|-----|
| 50-20-pullback | 3 | 1 | 0 | $+15.83 |

## Allowlisted signal outcomes
- n=23 · gated=16 · fired/ungated=7

## LLM
- status: **`ok`**
- invoked: `True`
- detail: automation/reports/strategy_ranking/iterations/iteration_scientist_20261022_030621.json

## Ops briefing bullets
- Settlement 2026-10-22 HKT · PAAPEX…091 · day P/L $+15.83 (src=paper_allowlisted_pnl_fallback) · DD +15.83 vs limit -100.0
- ✅ DD unlocked — under −$100 limit.
- Allowlist fills: n=3 pnl=$+15.83; signals allow n=23 gated=16
- By strategy — 50-20-pullback: n=3 pnl=$+15.8
- Policy: QTY=1 Bracket only (NOT Group QTY20); never use Order Ticket Limit as sim last.
- LLM Scientist ran OK; report=automation/reports/strategy_ranking/iterations/iteration_scientist_20261022_030621.json
- Never re-handoff stale/gated/null-position signals; stay quiet if nothing changed.

## Ops lessons (folded)

- Never treat Order Ticket Limit as sim last (MBT 83660 false OUT_OF_GATE) — use chart/DOM/explicit last.
- Bracket SL/TP: prefer paper-anchored absolute levels vs fill-offset when fill ≠ paper; flag drift.
- Handoff text must say QTY=1 Bracket (NOT Group QTY20). Ops-only Tradovate; A皮 coordinates.
- Live allowlist only: 50-20-Pullback, CRT, Stair, H-Pattern.
- Envelope defaults: −$100 DD hold / +$300 TP (historical). Change only with explicit user choice.

## Live scan snapshot
- positions open: 2
- heartbeat: `2026-10-21T18:56:57.189040+00:00`
- circuit_breaker: `{'consecutive_good_scans': 1}`

## Config defaults (documented)
- DD_LIMIT_USD = -100.0 (hold when day DD ≤ this)
- TP_LIMIT_USD = 300.0 (historical +$300 envelope; not auto-enforced here)

