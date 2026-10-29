# Daily Settlement — 2026-10-29

## Rule (Symmetric)
For each agent, over the **14d** rolling window:
- **PROMOTE** (升 1 lv) if: **PF > 1.0** AND **WR > 0.5** AND **RR > 1.0** AND **n ≥ 10**
  - cap at **None**
- **DEMOTE** (降 1 lv) if: **PF ≤ 1.0** AND **WR ≤ 0.5** AND **RR ≤ 1.0** AND **n ≥ 10**
  - enabled: **True** (10/07 user directive)
  - floor at **1**
- Otherwise: **stay flat** (neutral zone — 1-2 of 3 conditions fail)

**Per-agent overrides in force** (LLM-managed, settlement_llm_intervene.py):

- `3-Pushes`: PF>1.0, WR>45%, RR>1.0, n≥10
- `50-20-Pullback`: PF>1.0, WR>35%, RR>1.0, n≥10
- `B1-3in1`: PF>1.2, WR>55%, RR>1.0, n≥10
- `CRT`: PF>0.8, WR>30%, RR>1.0, n≥10
- `H-Pattern`: PF>1.0, WR>50%, RR>1.0, n≥5
- `OCS-BTC-5m`: PF>1.0, WR>40%, RR>1.0, n≥10
- `Stair`: PF>0.85, WR>30%, RR>1.0, n≥10
- `TTrades-L12`: PF>1.2, WR>55%, RR>1.2, n≥15
- `TTrades-L13`: PF>1.0, WR>39%, RR>1.0, n≥10
- `TTrades-L14`: PF>0.8, WR>30%, RR>1.0, n≥10
- `Two-Yang`: PF>1.0, WR>38%, RR>1.0, n≥10

## Promoted (2 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|
| Two-Yang | 1 → 2 ⬆ | 14 | 1.94 | 42.9% | 2.59 | all 3 conditions met (override: PF>1.0, WR>38%, RR>1.0, n≥10) |
| CRT | 7 → 8 ⬆ | 106 | 0.98 | 37.7% | 1.62 | all 3 conditions met (override: PF>0.8, WR>30%, RR>1.0, n≥10) |

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (5 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| 50-20-Pullback | 2 | 38 | 0.82 | 31.6% | 1.79 | NOT promoted: PF 0.82 ≤ 1.0; WR 31.6% ≤ 50.0% | NOT demoted: RR 1.79 > 1.0 |
| Stair | 2 | 27 | 0.67 | 25.9% | 1.90 | NOT promoted: PF 0.67 ≤ 1.0; WR 25.9% ≤ 50.0% | NOT demoted: RR 1.90 > 1.0 |
| B1-3in1 | 1 | 17 | 0.10 | 5.9% | 1.62 | NOT promoted: PF 0.10 ≤ 1.0; WR 5.9% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0; at min_level |
| OCS-BTC-5m | 3 | 39 | 1.25 | 43.6% | 1.62 | NOT promoted: WR 43.6% ≤ 50.0% | NOT demoted: PF 1.25 > 1.0; RR 1.62 > 1.0 |
| TTrades-L13 | 4 | 28 | 1.05 | 39.3% | 1.62 | NOT promoted: WR 39.3% ≤ 50.0% | NOT demoted: PF 1.05 > 1.0; RR 1.62 > 1.0 |

## Insufficient data (n<10) (9 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| H-Pattern | 3 | 8 | need ≥ 10 trades to settle |
| 3-Pushes | 2 | 5 | need ≥ 10 trades to settle |
| RSI-Div | 1 | 3 | need ≥ 10 trades to settle |
| B1 | 1 | 4 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 1 | need ≥ 10 trades to settle |
| TTrades-Fractal | 1 | 3 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 3 | need ≥ 10 trades to settle |
| TTrades-L14 | 2 | 0 | need ≥ 10 trades to settle |
| Argon-Gold | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 2
- **Demoted (⬇)**: 0
- **Held (flat)**: 5
- **Insufficient data**: 9
- **Total evaluated**: 16
