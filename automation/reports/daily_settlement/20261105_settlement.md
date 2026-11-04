# Daily Settlement — 2026-11-05 (HKT)

**Account:** PAAPEX…091  
**Generated:** 2026-11-05 05:02:54 HKT  
**DD state file:** `automation/state/ops_dd_hold.json`  

## Equity / DD
- Equity start: `None`
- Equity end: `None`
- Open P/L: `None` · Working: `None`
- Day P/L: **$+0.00** (source: `paper_allowlisted_pnl_fallback`)
- DD amount: **$+0.00** vs `day_start` · limit **-100.0**
- **dd_hold: `False`** · tp_limit_usd (report-only default): `300.0`

## Fills (allowlist focus)
- Total rows: 1 · allowlisted: 1 · non-allow: 0
- Allowlisted PnL: **$+0.00**

| Strategy | n | wins | losses | pnl |
|----------|---|------|--------|-----|
| stair | 1 | 0 | 0 | $+0.00 |

## Allowlisted signal outcomes
- n=27 · gated=19 · fired/ungated=8

## LLM
- status: **`ok`**
- invoked: `True`
- detail: automation/reports/strategy_ranking/iterations/iteration_scientist_20261105_050245.json

## Ops briefing bullets
- Settlement 2026-11-05 HKT · PAAPEX…091 · day P/L $+0.00 (src=paper_allowlisted_pnl_fallback) · DD +0.00 vs limit -100.0
- ✅ DD unlocked — under −$100 limit.
- Allowlist fills: n=1 pnl=$+0.00; signals allow n=27 gated=19
- By strategy — stair: n=1 pnl=$+0.0
- Policy: QTY=1 Bracket only (NOT Group QTY20); never use Order Ticket Limit as sim last.
- LLM Scientist ran OK; report=automation/reports/strategy_ranking/iterations/iteration_scientist_20261105_050245.json
- Never re-handoff stale/gated/null-position signals; stay quiet if nothing changed.

## Ops lessons (folded)

- Never treat Order Ticket Limit as sim last (MBT 83660 false OUT_OF_GATE) — use chart/DOM/explicit last.
- Bracket SL/TP: prefer paper-anchored absolute levels vs fill-offset when fill ≠ paper; flag drift.
- Handoff text must say QTY=1 Bracket (NOT Group QTY20). Ops-only Tradovate; A皮 coordinates.
- Live allowlist only: 50-20-Pullback, CRT, Stair, H-Pattern.
- Envelope defaults: −$100 DD hold / +$300 TP (historical). Change only with explicit user choice.

## Live scan snapshot
- positions open: 6
- heartbeat: `2026-11-04T17:58:27.784030+00:00`
- circuit_breaker: `{'consecutive_good_scans': 7, 'open': False, 'opened_at': '2026-11-01T23:05:44.450017+00:00', 'until': '2026-11-03T04:30:36.181821+00:00', 'reason': 'analyst charts_failed/charts_total = 30/30 = 100%', 'cleared_at': '2026-11-03T05:20:00+00:00', 'cleared_reason': 'manual: six dependency added (mplfinance needs six.moves); charts verified 5/5 OK on clean venv'}`

## Config defaults (documented)
- DD_LIMIT_USD = -100.0 (hold when day DD ≤ this)
- TP_LIMIT_USD = 300.0 (historical +$300 envelope; not auto-enforced here)

