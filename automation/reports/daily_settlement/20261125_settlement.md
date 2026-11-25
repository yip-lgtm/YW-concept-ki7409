# Daily Settlement — 2026-11-25 (HKT)

**Account:** PAAPEX…091  
**Generated:** 2026-11-25 23:02:31 HKT  
**DD state file:** `automation/state/ops_dd_hold.json`  

## Equity / DD
- Equity start: `None`
- Equity end: `None`
- Open P/L: `None` · Working: `None`
- Day P/L: **$+770.80** (source: `paper_allowlisted_pnl_fallback`)
- DD amount: **$+770.80** vs `day_start` · limit **-100.0**
- **dd_hold: `False`** · tp_limit_usd (report-only default): `300.0`

## Fills (allowlist focus)
- Total rows: 10 · allowlisted: 8 · non-allow: 2
- Allowlisted PnL: **$+770.80**

| Strategy | n | wins | losses | pnl |
|----------|---|------|--------|-----|
| crt | 8 | 6 | 2 | $+770.80 |

## Allowlisted signal outcomes
- n=54 · gated=42 · fired/ungated=12

## LLM
- status: **`ok`**
- invoked: `True`
- detail: automation/reports/strategy_ranking/iterations/iteration_scientist_20261125_230215.json

## Ops briefing bullets
- Settlement 2026-11-25 HKT · PAAPEX…091 · day P/L $+770.80 (src=paper_allowlisted_pnl_fallback) · DD +770.80 vs limit -100.0
- ✅ DD unlocked — under −$100 limit.
- Allowlist fills: n=8 pnl=$+770.80; signals allow n=54 gated=42
- By strategy — crt: n=8 pnl=$+770.8
- Policy: QTY=1 Bracket only (NOT Group QTY20); never use Order Ticket Limit as sim last.
- LLM Scientist ran OK; report=automation/reports/strategy_ranking/iterations/iteration_scientist_20261125_230215.json
- Never re-handoff stale/gated/null-position signals; stay quiet if nothing changed.

## Ops lessons (folded)

- Never treat Order Ticket Limit as sim last (MBT 83660 false OUT_OF_GATE) — use chart/DOM/explicit last.
- Bracket SL/TP: prefer paper-anchored absolute levels vs fill-offset when fill ≠ paper; flag drift.
- Handoff text must say QTY=1 Bracket (NOT Group QTY20). Ops-only Tradovate; A皮 coordinates.
- Live allowlist only: 50-20-Pullback, CRT, Stair, H-Pattern.
- Envelope defaults: −$100 DD hold / +$300 TP (historical). Change only with explicit user choice.

## Live scan snapshot
- positions open: 2
- heartbeat: `2026-11-25T13:44:27.475881+00:00`
- circuit_breaker: `{'consecutive_good_scans': 43, 'open': False, 'opened_at': '2026-11-01T23:05:44.450017+00:00', 'until': '2026-11-03T04:30:36.181821+00:00', 'reason': 'analyst charts_failed/charts_total = 30/30 = 100%', 'cleared_at': '2026-11-03T05:20:00+00:00', 'cleared_reason': 'manual: six dependency added (mplfinance needs six.moves); charts verified 5/5 OK on clean venv'}`

## Config defaults (documented)
- DD_LIMIT_USD = -100.0 (hold when day DD ≤ this)
- TP_LIMIT_USD = 300.0 (historical +$300 envelope; not auto-enforced here)

