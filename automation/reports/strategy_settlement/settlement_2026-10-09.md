# Daily Settlement — 2026-10-09

## Rule (Symmetric)
For each agent, over the **7d** rolling window:
- **PROMOTE** (升 1 lv) if: **PF > 1.0** AND **WR > 0.5** AND **RR > 1.0** AND **n ≥ 10**
  - cap at **5**
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
| 50-20-Pullback | 1 | 45 | 1.18 | 42.2% | 1.62 | NOT promoted: WR 42.2% ≤ 50.0% | NOT demoted: PF 1.18 > 1.0; RR 1.62 > 1.0; at min_level |
| Stair | 1 | 12 | 1.16 | 41.7% | 1.62 | NOT promoted: WR 41.7% ≤ 50.0% | NOT demoted: PF 1.16 > 1.0; RR 1.62 > 1.0; at min_level |
| CRT | 1 | 19 | 1.18 | 42.1% | 1.62 | NOT promoted: WR 42.1% ≤ 50.0% | NOT demoted: PF 1.18 > 1.0; RR 1.62 > 1.0; at min_level |

## Insufficient data (n<10) (12 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| H-Pattern | 1 | 1 | need ≥ 10 trades to settle |
| 3-Pushes | 1 | 8 | need ≥ 10 trades to settle |
| Two-Yang | 1 | 7 | need ≥ 10 trades to settle |
| RSI-Div | 1 | 0 | need ≥ 10 trades to settle |
| B1 | 1 | 1 | need ≥ 10 trades to settle |
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
