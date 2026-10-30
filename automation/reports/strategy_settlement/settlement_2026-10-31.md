# Daily Settlement — 2026-10-31

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

## Promoted (4 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|
| H-Pattern | 3 → 4 ⬆ | 9 | 1.17 | 44.4% | 1.46 | all 3 conditions met (override: PF>1.0, WR>40%, RR>1.0, n≥8) |
| Two-Yang | 2 → 3 ⬆ | 15 | 2.27 | 46.7% | 2.59 | all 3 conditions met (override: PF>1.0, WR>38%, RR>1.0, n≥10) |
| CRT | 9 → 10 ⬆ | 116 | 1.04 | 38.8% | 1.64 | all 3 conditions met (override: PF>0.8, WR>30%, RR>1.0, n≥10) |
| TTrades-L13 | 4 → 5 ⬆ | 34 | 1.28 | 44.1% | 1.62 | all 3 conditions met (override: PF>1.0, WR>39%, RR>1.0, n≥10) |

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (4 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| 50-20-Pullback | 2 | 32 | 0.71 | 28.1% | 1.82 | NOT promoted: PF 0.71 ≤ 1.0; WR 28.1% ≤ 50.0% | NOT demoted: RR 1.82 > 1.0 |
| Stair | 2 | 33 | 1.43 | 33.3% | 2.85 | NOT promoted: WR 33.3% ≤ 50.0% | NOT demoted: PF 1.43 > 1.0; RR 2.85 > 1.0 |
| B1-3in1 | 1 | 19 | 0.10 | 5.3% | 1.71 | NOT promoted: PF 0.10 ≤ 1.0; WR 5.3% ≤ 50.0% | NOT demoted: RR 1.71 > 1.0; at min_level |
| OCS-BTC-5m | 5 | 46 | 1.48 | 47.8% | 1.62 | NOT promoted: WR 47.8% ≤ 50.0% | NOT demoted: PF 1.48 > 1.0; RR 1.62 > 1.0 |

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
- **Promoted (⬆)**: 4
- **Demoted (⬇)**: 0
- **Held (flat)**: 4
- **Insufficient data**: 9
- **Total evaluated**: 16
