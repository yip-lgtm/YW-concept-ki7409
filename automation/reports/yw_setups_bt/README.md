# YW Concept — 11 setups backtest + LLM iteration (2026-09-22)

Window: **2026-08-25 → 2026-09-21** under Apex live constraints (A/B, 1 Micro, daily −$100/+ $300, skip chase past T1).

## Files

| Path | What |
|------|------|
| `report.md` / `ranking.json` | Baseline side-by-side of all 11 |
| `trades_replay.json` | Replay trades used |
| `crt_llm_analysis.md` | Deep CRT LLM write-up |
| `iteration/report.md` | **Before/after** after filter tweaks |
| `iteration/ranking_after.json` | Machine-readable after ranking |
| `iteration/per_strategy/*.md` | Per-setup analysis + filter experiments |

## Headline AFTER iteration

- **Keep:** CRT (baseline), 50-20-Pullback (filtered: skip MGC; MNQ all sessions; others LDLZ/NYKZ)
- **Near-keep / paper:** Stair (skip NYKZ+BTC+MES) — highest net but qual days = 2
- **Do not arm live yet:** 3-Pushes / RSI-Div salvages (drop→tweak only)

## Live arm (Tradovate)

CRT on MNQ + **MGCZ6**; optional paper Stair / 50-20 filters. See `iteration/report.md`.
