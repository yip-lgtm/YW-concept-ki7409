# Daily Settlement — 2026-11-02

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
- `B1-3in1`: PF>1.2, WR>55%, RR>1.0, n≥10
- `CRT`: PF>0.8, WR>30%, RR>1.0, n≥10
- `H-Pattern`: PF>1.0, WR>40%, RR>1.0, n≥8
- `OCS-BTC-5m`: PF>1.0, WR>40%, RR>1.0, n≥10
- `Stair`: PF>0.85, WR>30%, RR>1.0, n≥10
- `TTrades-L12`: PF>1.2, WR>55%, RR>1.2, n≥15
- `TTrades-L13`: PF>1.0, WR>39%, RR>1.0, n≥10
- `TTrades-L14`: PF>0.8, WR>30%, RR>1.0, n≥10
- `Two-Yang`: PF>1.0, WR>38%, RR>1.0, n≥10

## Promoted (2 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|
| Two-Yang | 3 → 4 ⬆ | 16 | 1.89 | 43.8% | 2.43 | all 3 conditions met (override: PF>1.0, WR>38%, RR>1.0, n≥10) |
| CRT | 11 → 12 ⬆ | 118 | 1.06 | 39.0% | 1.66 | all 3 conditions met (override: PF>0.8, WR>30%, RR>1.0, n≥10) |

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (5 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| 50-20-Pullback | 2 | 15 | 1.06 | 33.3% | 2.12 | NOT promoted: WR 33.3% ≤ 50.0% | NOT demoted: PF 1.06 > 1.0; RR 2.12 > 1.0 |
| Stair | 2 | 33 | 1.43 | 33.3% | 2.85 | NOT promoted: WR 33.3% ≤ 50.0% | NOT demoted: PF 1.43 > 1.0; RR 2.85 > 1.0 |
| B1-3in1 | 1 | 25 | 0.31 | 20.0% | 1.25 | NOT promoted: PF 0.31 ≤ 1.0; WR 20.0% ≤ 50.0% | NOT demoted: RR 1.25 > 1.0; at min_level |
| OCS-BTC-5m | 6 | 61 | 1.05 | 39.3% | 1.62 | NOT promoted: WR 39.3% ≤ 50.0% | NOT demoted: PF 1.05 > 1.0; RR 1.62 > 1.0 |
| TTrades-L13 | 6 | 31 | 1.33 | 45.2% | 1.62 | NOT promoted: WR 45.2% ≤ 50.0% | NOT demoted: PF 1.33 > 1.0; RR 1.62 > 1.0 |

## Insufficient data (n<10) (9 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| H-Pattern | 4 | 9 | need ≥ 10 trades to settle |
| 3-Pushes | 2 | 2 | need ≥ 10 trades to settle |
| RSI-Div | 1 | 0 | need ≥ 10 trades to settle |
| B1 | 1 | 3 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 1 | need ≥ 10 trades to settle |
| TTrades-Fractal | 1 | 3 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 4 | need ≥ 10 trades to settle |
| TTrades-L14 | 2 | 4 | need ≥ 10 trades to settle |
| Argon-Gold | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 2
- **Demoted (⬇)**: 0
- **Held (flat)**: 5
- **Insufficient data**: 9
- **Total evaluated**: 16
