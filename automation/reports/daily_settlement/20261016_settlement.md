# Daily Settlement — 2026-10-16 (HKT)

**Account:** PAAPEX…091  
**Generated:** 2026-10-16 02:52:41 HKT  
**DD state file:** `automation/state/ops_dd_hold.json`  

## Equity / DD
- Equity start: `None`
- Equity end: `None`
- Open P/L: `None` · Working: `None`
- Day P/L: **$+0.00** (source: `paper_allowlisted_pnl_fallback`)
- DD amount: **$+0.00** vs `day_start` · limit **-100.0**
- **dd_hold: `False`** · tp_limit_usd (report-only default): `300.0`

## Fills (allowlist focus)
- Total rows: 1 · allowlisted: 0 · non-allow: 1
- Allowlisted PnL: **$+0.00**

## Allowlisted signal outcomes
- n=10 · gated=8 · fired/ungated=2

## LLM
- status: **`ok`**
- invoked: `True`
- detail: automation/reports/strategy_ranking/iterations/iteration_scientist_20261016_025228.json

## Ops briefing bullets
- Settlement 2026-10-16 HKT · PAAPEX…091 · day P/L $+0.00 (src=paper_allowlisted_pnl_fallback) · DD +0.00 vs limit -100.0
- ✅ DD unlocked — under −$100 limit.
- Allowlist fills: n=0 pnl=$+0.00; signals allow n=10 gated=8
- Policy: QTY=1 Bracket only (NOT Group QTY20); never use Order Ticket Limit as sim last.
- LLM Scientist ran OK; report=automation/reports/strategy_ranking/iterations/iteration_scientist_20261016_025228.json
- Never re-handoff stale/gated/null-position signals; stay quiet if nothing changed.

## Ops lessons (folded)

- Never treat Order Ticket Limit as sim last (MBT 83660 false OUT_OF_GATE) — use chart/DOM/explicit last.
- Bracket SL/TP: prefer paper-anchored absolute levels vs fill-offset when fill ≠ paper; flag drift.
- Handoff text must say QTY=1 Bracket (NOT Group QTY20). Ops-only Tradovate; A皮 coordinates.
- Live allowlist only: 50-20-Pullback, CRT, Stair, H-Pattern.
- Envelope defaults: −$100 DD hold / +$300 TP (historical). Change only with explicit user choice.

## Live scan snapshot
- positions open: 4
- heartbeat: `2026-10-15T18:33:56.387873+00:00`
- circuit_breaker: `{}`

## Config defaults (documented)
- DD_LIMIT_USD = -100.0 (hold when day DD ≤ this)
- TP_LIMIT_USD = 300.0 (historical +$300 envelope; not auto-enforced here)

