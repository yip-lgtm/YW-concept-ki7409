# Daily Settlement — 2026-11-10

## Rule (Symmetric)
For each agent, over the **14d** rolling window:
- **PROMOTE** (升 1 lv) if: **PF > 1.0** AND **WR > 0.5** AND **RR > 1.0** AND **n ≥ 10**
  - cap at **None**
- **DEMOTE** (降 1 lv) if: **PF ≤ 1.0** AND **WR ≤ 0.5** AND **RR ≤ 1.0** AND **n ≥ 10**
  - enabled: **True** (10/07 user directive)
  - floor at **1**
- Otherwise: **stay flat** (neutral zone — 1-2 of 3 conditions fail)

**Per-agent overrides in force** (LLM-managed, settlement_llm_intervene.py):

- `3-Pushes`: PF>1.0, WR>35%, RR>1.0, n≥5
- `50-20-Pullback`: PF>1.0, WR>35%, RR>1.0, n≥10
- `B1-3in1`: PF>1.0, WR>30%, RR>1.0, n≥10
- `CRT`: PF>1.0, WR>40%, RR>1.0, n≥50
- `H-Pattern`: PF>1.0, WR>45%, RR>1.0, n≥10
- `OCS-BTC-5m`: PF>0.85, WR>35%, RR>1.0, n≥30
- `Stair`: PF>1.0, WR>38%, RR>1.0, n≥10
- `TTrades-Fractal`: PF>1.1, WR>55%, RR>1.1, n≥10
- `TTrades-L12`: PF>1.2, WR>55%, RR>1.2, n≥15
- `TTrades-L13`: PF>1.0, WR>39%, RR>1.0, n≥10
- `TTrades-L14`: PF>1.0, WR>50%, RR>1.0, n≥10
- `Two-Yang`: PF>1.0, WR>38%, RR>1.0, n≥10

## Promoted (2 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|
| Stair | 2 → 3 ⬆ | 39 | 1.63 | 41.0% | 2.34 | all 3 conditions met (override: PF>1.0, WR>38%, RR>1.0, n≥10) |
| CRT | 14 → 15 ⬆ | 134 | 1.44 | 46.3% | 1.67 | all 3 conditions met (override: PF>1.0, WR>40%, RR>1.0, n≥50) |

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (5 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| H-Pattern | 6 | 18 | 1.30 | 44.4% | 1.63 | NOT promoted: WR 44.4% ≤ 50.0% | NOT demoted: PF 1.30 > 1.0; RR 1.63 > 1.0 |
| Two-Yang | 5 | 33 | 0.75 | 18.2% | 3.36 | NOT promoted: PF 0.75 ≤ 1.0; WR 18.2% ≤ 50.0% | NOT demoted: RR 3.36 > 1.0 |
| B1-3in1 | 1 | 35 | 1.00 | 40.0% | 1.50 | NOT promoted: PF 1.00 ≤ 1.0; WR 40.0% ≤ 50.0% | NOT demoted: RR 1.50 > 1.0; at min_level |
| OCS-BTC-5m | 6 | 59 | 0.83 | 33.9% | 1.62 | NOT promoted: PF 0.83 ≤ 1.0; WR 33.9% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |
| TTrades-L13 | 6 | 27 | 0.95 | 37.0% | 1.62 | NOT promoted: PF 0.95 ≤ 1.0; WR 37.0% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |

## Insufficient data (n<10) (9 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| 3-Pushes | 2 | 0 | need ≥ 10 trades to settle |
| RSI-Div | 1 | 1 | need ≥ 10 trades to settle |
| 50-20-Pullback | 2 | 0 | need ≥ 10 trades to settle |
| B1 | 1 | 3 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-Fractal | 1 | 7 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 7 | need ≥ 10 trades to settle |
| TTrades-L14 | 2 | 7 | need ≥ 10 trades to settle |
| Argon-Gold | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 2
- **Demoted (⬇)**: 0
- **Held (flat)**: 5
- **Insufficient data**: 9
- **Total evaluated**: 16
