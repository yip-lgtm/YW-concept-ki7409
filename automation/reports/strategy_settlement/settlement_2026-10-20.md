# Daily Settlement — 2026-10-20

## Rule (Symmetric)
For each agent, over the **7d** rolling window:
- **PROMOTE** (升 1 lv) if: **PF > 1.0** AND **WR > 0.5** AND **RR > 1.0** AND **n ≥ 10**
  - cap at **None**
- **DEMOTE** (降 1 lv) if: **PF ≤ 1.0** AND **WR ≤ 0.5** AND **RR ≤ 1.0** AND **n ≥ 10**
  - enabled: **True** (10/07 user directive)
  - floor at **1**
- Otherwise: **stay flat** (neutral zone — 1-2 of 3 conditions fail)

## Promoted (0 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (3 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| 50-20-Pullback | 1 | 43 | 1.17 | 41.9% | 1.62 | NOT promoted: WR 41.9% ≤ 50.0% | NOT demoted: PF 1.17 > 1.0; RR 1.62 > 1.0; at min_level |
| Stair | 1 | 19 | 1.46 | 47.4% | 1.62 | NOT promoted: WR 47.4% ≤ 50.0% | NOT demoted: PF 1.46 > 1.0; RR 1.62 > 1.0; at min_level |
| CRT | 1 | 30 | 0.69 | 30.0% | 1.62 | NOT promoted: PF 0.69 ≤ 1.0; WR 30.0% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0; at min_level |

## Insufficient data (n<10) (12 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| H-Pattern | 1 | 1 | need ≥ 10 trades to settle |
| 3-Pushes | 3 | 8 | need ≥ 10 trades to settle |
| Two-Yang | 1 | 3 | need ≥ 10 trades to settle |
| RSI-Div | 1 | 3 | need ≥ 10 trades to settle |
| B1 | 1 | 2 | need ≥ 10 trades to settle |
| B1-3in1 | 1 | 7 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 1 | need ≥ 10 trades to settle |
| OCS-BTC-5m | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-Fractal | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-L13 | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-L14 | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 0
- **Demoted (⬇)**: 0
- **Held (flat)**: 3
- **Insufficient data**: 12
- **Total evaluated**: 15
