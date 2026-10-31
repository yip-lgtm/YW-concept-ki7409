# Daily Settlement — 2026-11-01

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

## Promoted (1 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|
| OCS-BTC-5m | 5 → 6 ⬆ | 51 | 1.44 | 47.1% | 1.62 | all 3 conditions met (override: PF>1.0, WR>40%, RR>1.0, n≥10) |

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (6 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| Two-Yang | 3 | 15 | 2.27 | 46.7% | 2.59 | NOT promoted: WR 46.7% ≤ 50.0% | NOT demoted: PF 2.27 > 1.0; RR 2.59 > 1.0 |
| 50-20-Pullback | 2 | 21 | 0.78 | 28.6% | 1.94 | NOT promoted: PF 0.78 ≤ 1.0; WR 28.6% ≤ 50.0% | NOT demoted: RR 1.94 > 1.0 |
| Stair | 2 | 33 | 1.43 | 33.3% | 2.85 | NOT promoted: WR 33.3% ≤ 50.0% | NOT demoted: PF 1.43 > 1.0; RR 2.85 > 1.0 |
| B1-3in1 | 1 | 23 | 0.26 | 17.4% | 1.22 | NOT promoted: PF 0.26 ≤ 1.0; WR 17.4% ≤ 50.0% | NOT demoted: RR 1.22 > 1.0; at min_level |
| CRT | 11 | 117 | 1.04 | 38.5% | 1.66 | NOT promoted: WR 38.5% ≤ 50.0% | NOT demoted: PF 1.04 > 1.0; RR 1.66 > 1.0 |
| TTrades-L13 | 6 | 35 | 1.36 | 45.7% | 1.62 | NOT promoted: WR 45.7% ≤ 50.0% | NOT demoted: PF 1.36 > 1.0; RR 1.62 > 1.0 |

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
- **Promoted (⬆)**: 1
- **Demoted (⬇)**: 0
- **Held (flat)**: 6
- **Insufficient data**: 9
- **Total evaluated**: 16
