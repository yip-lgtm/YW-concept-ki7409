# Daily Settlement — 2026-10-22

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

## Held (n≥10, mixed signals — stays flat) (5 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| 3-Pushes | 2 | 12 | 2.27 | 58.3% | 1.62 | NOT promoted: — | NOT demoted: PF 2.27 > 1.0; WR 58.3% > 50.0%; RR 1.62 > 1.0 |
| 50-20-Pullback | 2 | 78 | 0.95 | 35.9% | 1.70 | NOT promoted: PF 0.95 ≤ 1.0; WR 35.9% ≤ 50.0% | NOT demoted: RR 1.70 > 1.0 |
| Stair | 3 | 32 | 0.97 | 37.5% | 1.62 | NOT promoted: PF 0.97 ≤ 1.0; WR 37.5% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |
| B1-3in1 | 1 | 15 | 0.00 | 0.0% | 0.00 | NOT promoted: PF 0.00 ≤ 1.0; WR 0.0% ≤ 50.0%; RR 0.00 ≤ 1.0 | NOT demoted: at min_level |
| CRT | 2 | 46 | 0.78 | 32.6% | 1.62 | NOT promoted: PF 0.78 ≤ 1.0; WR 32.6% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |

## Insufficient data (n<10) (11 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| H-Pattern | 2 | 5 | need ≥ 10 trades to settle |
| Two-Yang | 1 | 9 | need ≥ 10 trades to settle |
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
- **Held (flat)**: 5
- **Insufficient data**: 11
- **Total evaluated**: 16
