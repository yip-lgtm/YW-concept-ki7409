# Daily Settlement — 2026-11-07 (HKT)

**Account:** PAAPEX…091  
**Generated:** 2026-11-07 04:41:39 HKT  
**DD state file:** `automation/state/ops_dd_hold.json`  

## Equity / DD
- Equity start: `None`
- Equity end: `None`
- Open P/L: `None` · Working: `None`
- Day P/L: **$+61.80** (source: `paper_allowlisted_pnl_fallback`)
- DD amount: **$+61.80** vs `day_start` · limit **-100.0**
- **dd_hold: `False`** · tp_limit_usd (report-only default): `300.0`

## Fills (allowlist focus)
- Total rows: 2 · allowlisted: 2 · non-allow: 0
- Allowlisted PnL: **$+61.80**

| Strategy | n | wins | losses | pnl |
|----------|---|------|--------|-----|
| crt | 1 | 0 | 1 | $-100.00 |
| h-pattern | 1 | 1 | 0 | $+161.80 |

## Allowlisted signal outcomes
- n=6 · gated=4 · fired/ungated=2

## LLM
- status: **`ok`**
- invoked: `True`
- detail: automation/reports/strategy_ranking/iterations/iteration_scientist_20261107_044128.json

## Ops briefing bullets
- Settlement 2026-11-07 HKT · PAAPEX…091 · day P/L $+61.80 (src=paper_allowlisted_pnl_fallback) · DD +61.80 vs limit -100.0
- ✅ DD unlocked — under −$100 limit.
- Allowlist fills: n=2 pnl=$+61.80; signals allow n=6 gated=4
- By strategy — crt: n=1 pnl=$-100.0; h-pattern: n=1 pnl=$+161.8
- Policy: QTY=1 Bracket only (NOT Group QTY20); never use Order Ticket Limit as sim last.
- LLM Scientist ran OK; report=automation/reports/strategy_ranking/iterations/iteration_scientist_20261107_044128.json
- Never re-handoff stale/gated/null-position signals; stay quiet if nothing changed.

## Ops lessons (folded)

- Never treat Order Ticket Limit as sim last (MBT 83660 false OUT_OF_GATE) — use chart/DOM/explicit last.
- Bracket SL/TP: prefer paper-anchored absolute levels vs fill-offset when fill ≠ paper; flag drift.
- Handoff text must say QTY=1 Bracket (NOT Group QTY20). Ops-only Tradovate; A皮 coordinates.
- Live allowlist only: 50-20-Pullback, CRT, Stair, H-Pattern.
- Envelope defaults: −$100 DD hold / +$300 TP (historical). Change only with explicit user choice.

## Live scan snapshot
- positions open: 1
- heartbeat: `2026-11-06T19:53:39.350218+00:00`
- circuit_breaker: `{'consecutive_good_scans': 10, 'open': False, 'opened_at': '2026-11-01T23:05:44.450017+00:00', 'until': '2026-11-03T04:30:36.181821+00:00', 'reason': 'analyst charts_failed/charts_total = 30/30 = 100%', 'cleared_at': '2026-11-03T05:20:00+00:00', 'cleared_reason': 'manual: six dependency added (mplfinance needs six.moves); charts verified 5/5 OK on clean venv'}`

## Config defaults (documented)
- DD_LIMIT_USD = -100.0 (hold when day DD ≤ this)
- TP_LIMIT_USD = 300.0 (historical +$300 envelope; not auto-enforced here)

