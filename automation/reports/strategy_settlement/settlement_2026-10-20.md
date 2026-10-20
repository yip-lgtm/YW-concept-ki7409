# Daily Settlement — 2026-10-20

## Rule (Symmetric)
For each agent, over the **14d** rolling window:
- **PROMOTE** (升 1 lv) if: **PF > 1.0** AND **WR > 0.5** AND **RR > 1.0** AND **n ≥ 10**
  - cap at **None**
- **DEMOTE** (降 1 lv) if: **PF ≤ 1.0** AND **WR ≤ 0.5** AND **RR ≤ 1.0** AND **n ≥ 10**
  - enabled: **True** (10/07 user directive)
  - floor at **1**
- Otherwise: **stay flat** (neutral zone — 1-2 of 3 conditions fail)

## Promoted (1 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|
| 3-Pushes | 1 → 2 ⬆ | 16 | 2.70 | 62.5% | 1.62 | all 3 conditions met |

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (5 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| Two-Yang | 1 | 10 | 0.41 | 20.0% | 1.62 | NOT promoted: PF 0.41 ≤ 1.0; WR 20.0% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0; at min_level |
| 50-20-Pullback | 2 | 78 | 1.01 | 38.5% | 1.62 | NOT promoted: WR 38.5% ≤ 50.0% | NOT demoted: PF 1.01 > 1.0; RR 1.62 > 1.0 |
| Stair | 2 | 33 | 1.35 | 45.5% | 1.62 | NOT promoted: WR 45.5% ≤ 50.0% | NOT demoted: PF 1.35 > 1.0; RR 1.62 > 1.0 |
| B1-3in1 | 1 | 15 | 0.00 | 0.0% | 0.00 | NOT promoted: PF 0.00 ≤ 1.0; WR 0.0% ≤ 50.0%; RR 0.00 ≤ 1.0 | NOT demoted: at min_level |
| CRT | 1 | 45 | 0.89 | 35.6% | 1.62 | NOT promoted: PF 0.89 ≤ 1.0; WR 35.6% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0; at min_level |

## Insufficient data (n<10) (10 agents)
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
| Argon-Gold | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 1
- **Demoted (⬇)**: 0
- **Held (flat)**: 5
- **Insufficient data**: 10
- **Total evaluated**: 16
