# Daily Settlement — 2026-10-20

## Rule (Symmetric)
For each agent, over the **14d** rolling window:
- **PROMOTE** (升 1 lv) if: **PF > 1.0** AND **WR > 0.5** AND **RR > 1.0** AND **n ≥ 10**
  - cap at **None**
- **DEMOTE** (降 1 lv) if: **PF ≤ 1.0** AND **WR ≤ 0.5** AND **RR ≤ 1.0** AND **n ≥ 10**
  - enabled: **True** (10/07 user directive)
  - floor at **1**
- Otherwise: **stay flat** (neutral zone — 1-2 of 3 conditions fail)

## Promoted (2 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|
| 50-20-Pullback | 1 → 2 ⬆ | 78 | 1.01 | 38.5% | 1.62 | all 3 conditions met |
| Stair | 1 → 2 ⬆ | 34 | 1.28 | 44.1% | 1.62 | all 3 conditions met |

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (4 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| 3-Pushes | 3 | 16 | 2.70 | 62.5% | 1.62 | NOT promoted: — | NOT demoted: PF 2.70 > 1.0; WR 62.5% > 50.0%; RR 1.62 > 1.0 |
| Two-Yang | 1 | 10 | 0.41 | 20.0% | 1.62 | NOT promoted: PF 0.41 ≤ 1.0; WR 20.0% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0; at min_level |
| B1-3in1 | 1 | 15 | 0.00 | 0.0% | 0.00 | NOT promoted: PF 0.00 ≤ 1.0; WR 0.0% ≤ 50.0%; RR 0.00 ≤ 1.0 | NOT demoted: at min_level |
| CRT | 1 | 45 | 0.89 | 35.6% | 1.62 | NOT promoted: PF 0.89 ≤ 1.0; WR 35.6% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0; at min_level |

## Insufficient data (n<10) (9 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| H-Pattern | 1 | 5 | need ≥ 10 trades to settle |
| RSI-Div | 1 | 4 | need ≥ 10 trades to settle |
| B1 | 1 | 2 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 3 | need ≥ 10 trades to settle |
| OCS-BTC-5m | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-Fractal | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-L13 | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-L14 | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 2
- **Demoted (⬇)**: 0
- **Held (flat)**: 4
- **Insufficient data**: 9
- **Total evaluated**: 15
