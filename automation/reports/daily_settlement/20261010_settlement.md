# Daily Settlement — 2026-10-10 (HKT)

**Account:** PAAPEX…091  
**Generated:** 2026-10-10 03:59:21 HKT  
**DD state file:** `automation/state/ops_dd_hold.json`  

## Equity / DD
- Equity start: `None`
- Equity end: `None`
- Open P/L: `None` · Working: `None`
- Day P/L: **$+353.10** (source: `paper_allowlisted_pnl_fallback`)
- DD amount: **$+353.10** vs `day_start` · limit **-100.0**
- **dd_hold: `False`** · tp_limit_usd (report-only default): `300.0`

## Fills (allowlist focus)
- Total rows: 3 · allowlisted: 2 · non-allow: 1
- Allowlisted PnL: **$+353.10**

| Strategy | n | wins | losses | pnl |
|----------|---|------|--------|-----|
| 50-20-pullback | 1 | 1 | 0 | $+433.01 |
| stair | 1 | 0 | 1 | $-79.91 |

## Allowlisted signal outcomes
- n=2 · gated=1 · fired/ungated=1

## LLM
- status: **`ok`**
- invoked: `True`
- detail: automation/reports/strategy_ranking/iterations/iteration_scientist_20261010_035912.json

## Ops briefing bullets
- Settlement 2026-10-10 HKT · PAAPEX…091 · day P/L $+353.10 (src=paper_allowlisted_pnl_fallback) · DD +353.10 vs limit -100.0
- ✅ DD unlocked — under −$100 limit.
- Allowlist fills: n=2 pnl=$+353.10; signals allow n=2 gated=1
- By strategy — 50-20-pullback: n=1 pnl=$+433.0; stair: n=1 pnl=$-79.9
- Policy: QTY=1 Bracket only (NOT Group QTY20); never use Order Ticket Limit as sim last.
- LLM Scientist ran OK; report=automation/reports/strategy_ranking/iterations/iteration_scientist_20261010_035912.json
- Never re-handoff stale/gated/null-position signals; stay quiet if nothing changed.

## Ops lessons (folded)

- Never treat Order Ticket Limit as sim last (MBT 83660 false OUT_OF_GATE) — use chart/DOM/explicit last.
- Bracket SL/TP: prefer paper-anchored absolute levels vs fill-offset when fill ≠ paper; flag drift.
- Handoff text must say QTY=1 Bracket (NOT Group QTY20). Ops-only Tradovate; A皮 coordinates.
- Live allowlist only: 50-20-Pullback, CRT, Stair, H-Pattern.
- Envelope defaults: −$100 DD hold / +$300 TP (historical). Change only with explicit user choice.

## Live scan snapshot
- positions open: 1
- heartbeat: `2026-10-09T19:40:25.617676+00:00`
- circuit_breaker: `{}`

## Config defaults (documented)
- DD_LIMIT_USD = -100.0 (hold when day DD ≤ this)
- TP_LIMIT_USD = 300.0 (historical +$300 envelope; not auto-enforced here)

