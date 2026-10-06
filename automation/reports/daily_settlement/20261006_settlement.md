# Daily Settlement — 2026-10-06 (HKT)

**Account:** PAAPEX…091  
**Generated:** 2026-10-06 23:04:28 HKT  
**DD state file:** `automation/state/ops_dd_hold.json`  

## Equity / DD
- Equity start: `None`
- Equity end: `None`
- Open P/L: `None` · Working: `None`
- Day P/L: **$+139.40** (source: `paper_allowlisted_pnl_fallback`)
- DD amount: **$+139.40** vs `day_start` · limit **-100.0**
- **dd_hold: `False`** · tp_limit_usd (report-only default): `300.0`

## Fills (allowlist focus)
- Total rows: 12 · allowlisted: 9 · non-allow: 3
- Allowlisted PnL: **$+139.40**

| Strategy | n | wins | losses | pnl |
|----------|---|------|--------|-----|
| 50-20-pullback | 3 | 1 | 2 | $+66.29 |
| crt | 4 | 3 | 1 | $+77.12 |
| stair | 2 | 0 | 2 | $-4.01 |

## Allowlisted signal outcomes
- n=44 · gated=32 · fired/ungated=12

## LLM
- status: **`llm_blocked`**
- invoked: `False`
- detail: MINIMAX_API_KEY missing/empty — settlement+DD OK; restore secret to enable Scientist

## Ops briefing bullets
- Settlement 2026-10-06 HKT · PAAPEX…091 · day P/L $+139.40 (src=paper_allowlisted_pnl_fallback) · DD +139.40 vs limit -100.0
- ✅ DD unlocked — under −$100 limit.
- Allowlist fills: n=9 pnl=$+139.40; signals allow n=44 gated=32
- By strategy — 50-20-pullback: n=3 pnl=$+66.3; crt: n=4 pnl=$+77.1; stair: n=2 pnl=$-4.0
- Policy: QTY=1 Bracket only (NOT Group QTY20); never use Order Ticket Limit as sim last.
- LLM blocked: MINIMAX_API_KEY missing/empty — settlement+DD OK; restore secret to enable Scientist — remind MiniMax secret once; do not invent parallel optimizer.
- Never re-handoff stale/gated/null-position signals; stay quiet if nothing changed.

## Ops lessons (folded)

- Never treat Order Ticket Limit as sim last (MBT 83660 false OUT_OF_GATE) — use chart/DOM/explicit last.
- Bracket SL/TP: prefer paper-anchored absolute levels vs fill-offset when fill ≠ paper; flag drift.
- Handoff text must say QTY=1 Bracket (NOT Group QTY20). Ops-only Tradovate; A皮 coordinates.
- Live allowlist only: 50-20-Pullback, CRT, Stair, H-Pattern.
- Envelope defaults: −$100 DD hold / +$300 TP (historical). Change only with explicit user choice.

## Live scan snapshot
- positions open: 2
- heartbeat: `2026-10-06T14:22:39.210532+00:00`
- circuit_breaker: `{}`

## Config defaults (documented)
- DD_LIMIT_USD = -100.0 (hold when day DD ≤ this)
- TP_LIMIT_USD = 300.0 (historical +$300 envelope; not auto-enforced here)

