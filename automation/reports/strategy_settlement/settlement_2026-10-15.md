# Daily Settlement — 2026-10-15

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

## Held (n≥10, mixed signals — stays flat) (4 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| 50-20-Pullback | 1 | 38 | 0.94 | 36.8% | 1.62 | NOT promoted: PF 0.94 ≤ 1.0; WR 36.8% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0; at min_level |
| Stair | 1 | 17 | 0.88 | 35.3% | 1.62 | NOT promoted: PF 0.88 ≤ 1.0; WR 35.3% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0; at min_level |
| B1-3in1 | 1 | 10 | 0.00 | 0.0% | 0.00 | NOT promoted: PF 0.00 ≤ 1.0; WR 0.0% ≤ 50.0%; RR 0.00 ≤ 1.0 | NOT demoted: at min_level |
| CRT | 1 | 16 | 0.73 | 31.2% | 1.62 | NOT promoted: PF 0.73 ≤ 1.0; WR 31.2% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0; at min_level |

## Insufficient data (n<10) (11 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| H-Pattern | 1 | 4 | need ≥ 10 trades to settle |
| 3-Pushes | 2 | 6 | need ≥ 10 trades to settle |
| Two-Yang | 1 | 5 | need ≥ 10 trades to settle |
| RSI-Div | 1 | 1 | need ≥ 10 trades to settle |
| B1 | 1 | 0 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 1 | need ≥ 10 trades to settle |
| OCS-BTC-5m | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-Fractal | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-L13 | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-L14 | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 0
- **Demoted (⬇)**: 0
- **Held (flat)**: 4
- **Insufficient data**: 11
- **Total evaluated**: 15
