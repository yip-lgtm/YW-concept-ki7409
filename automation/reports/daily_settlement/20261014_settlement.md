# Daily Settlement — 2026-10-14 (HKT)

**Account:** PAAPEX…091  
**Generated:** 2026-10-14 04:30:29 HKT  
**DD state file:** `automation/state/ops_dd_hold.json`  

## Equity / DD
- Equity start: `None`
- Equity end: `None`
- Open P/L: `None` · Working: `None`
- Day P/L: **$+3.92** (source: `paper_allowlisted_pnl_fallback`)
- DD amount: **$+3.92** vs `day_start` · limit **-100.0**
- **dd_hold: `False`** · tp_limit_usd (report-only default): `300.0`

## Fills (allowlist focus)
- Total rows: 1 · allowlisted: 1 · non-allow: 0
- Allowlisted PnL: **$+3.92**

| Strategy | n | wins | losses | pnl |
|----------|---|------|--------|-----|
| crt | 1 | 1 | 0 | $+3.92 |

## Allowlisted signal outcomes
- n=6 · gated=2 · fired/ungated=4

## LLM
- status: **`ok`**
- invoked: `True`
- detail: automation/reports/strategy_ranking/iterations/iteration_scientist_20261014_043021.json

## Ops briefing bullets
- Settlement 2026-10-14 HKT · PAAPEX…091 · day P/L $+3.92 (src=paper_allowlisted_pnl_fallback) · DD +3.92 vs limit -100.0
- ✅ DD unlocked — under −$100 limit.
- Allowlist fills: n=1 pnl=$+3.92; signals allow n=6 gated=2
- By strategy — crt: n=1 pnl=$+3.9
- Policy: QTY=1 Bracket only (NOT Group QTY20); never use Order Ticket Limit as sim last.
- LLM Scientist ran OK; report=automation/reports/strategy_ranking/iterations/iteration_scientist_20261014_043021.json
- Never re-handoff stale/gated/null-position signals; stay quiet if nothing changed.

## Ops lessons (folded)

- Never treat Order Ticket Limit as sim last (MBT 83660 false OUT_OF_GATE) — use chart/DOM/explicit last.
- Bracket SL/TP: prefer paper-anchored absolute levels vs fill-offset when fill ≠ paper; flag drift.
- Handoff text must say QTY=1 Bracket (NOT Group QTY20). Ops-only Tradovate; A皮 coordinates.
- Live allowlist only: 50-20-Pullback, CRT, Stair, H-Pattern.
- Envelope defaults: −$100 DD hold / +$300 TP (historical). Change only with explicit user choice.

## Live scan snapshot
- positions open: 3
- heartbeat: `2026-10-13T18:54:34.875445+00:00`
- circuit_breaker: `{}`

## Config defaults (documented)
- DD_LIMIT_USD = -100.0 (hold when day DD ≤ this)
- TP_LIMIT_USD = 300.0 (historical +$300 envelope; not auto-enforced here)

