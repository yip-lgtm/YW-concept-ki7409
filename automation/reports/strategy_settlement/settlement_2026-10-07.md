# Daily Settlement — 2026-10-07

## Rule
For each agent, over the **7d** rolling window:
- **PF > 1.0**  AND  **WR > 0.5**  AND  **RR > 1.0**  AND  **n ≥ 10**
- → **level +1** (升 1 lv), capped at **5**
- Decrement on fail: **False** (manual via LLM iter)

## Promoted (0 agents)
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10 but not promoted) (3 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted |
|-------|-------|---|-----|-----|-----|------------------|
| 50-20-Pullback | 1 | 44 | 1.02 | 38.6% | 1.62 | WR 38.6% ≤ 50.0% |
| Stair | 1 | 16 | 0.54 | 25.0% | 1.62 | PF 0.54 ≤ 1.0; WR 25.0% ≤ 50.0% |
| CRT | 1 | 16 | 1.26 | 43.8% | 1.62 | WR 43.8% ≤ 50.0% |

## Insufficient data (n<10) (8 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| H-Pattern | 1 | 2 | need ≥ 10 trades to settle |
| 3-Pushes | 1 | 6 | need ≥ 10 trades to settle |
| Two-Yang | 1 | 6 | need ≥ 10 trades to settle |
| RSI-Div | 1 | 1 | need ≥ 10 trades to settle |
| B1 | 1 | 1 | need ≥ 10 trades to settle |
| B1-3in1 | 1 | 4 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 1 | need ≥ 10 trades to settle |
| OCS-BTC-5m | 1 | 0 | need ≥ 10 trades to settle |
