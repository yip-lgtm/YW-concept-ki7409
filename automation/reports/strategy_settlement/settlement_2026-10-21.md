# Daily Settlement — 2026-10-21

## Rule (Symmetric)
For each agent, over the **14d** rolling window:
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

## Held (n≥10, mixed signals — stays flat) (6 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| 3-Pushes | 2 | 14 | 2.16 | 57.1% | 1.62 | NOT promoted: — | NOT demoted: PF 2.16 > 1.0; WR 57.1% > 50.0%; RR 1.62 > 1.0 |
| Two-Yang | 1 | 10 | 0.41 | 20.0% | 1.62 | NOT promoted: PF 0.41 ≤ 1.0; WR 20.0% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0; at min_level |
| 50-20-Pullback | 2 | 75 | 0.91 | 36.0% | 1.62 | NOT promoted: PF 0.91 ≤ 1.0; WR 36.0% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |
| Stair | 3 | 32 | 0.97 | 37.5% | 1.62 | NOT promoted: PF 0.97 ≤ 1.0; WR 37.5% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |
| B1-3in1 | 1 | 15 | 0.00 | 0.0% | 0.00 | NOT promoted: PF 0.00 ≤ 1.0; WR 0.0% ≤ 50.0%; RR 0.00 ≤ 1.0 | NOT demoted: at min_level |
| CRT | 1 | 48 | 0.81 | 33.3% | 1.62 | NOT promoted: PF 0.81 ≤ 1.0; WR 33.3% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0; at min_level |

## Insufficient data (n<10) (10 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| H-Pattern | 2 | 5 | need ≥ 10 trades to settle |
| RSI-Div | 1 | 4 | need ≥ 10 trades to settle |
| B1 | 1 | 2 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 2 | need ≥ 10 trades to settle |
| OCS-BTC-5m | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-Fractal | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-L13 | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-L14 | 1 | 0 | need ≥ 10 trades to settle |
| Argon-Gold | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 0
- **Demoted (⬇)**: 0
- **Held (flat)**: 6
- **Insufficient data**: 10
- **Total evaluated**: 16
