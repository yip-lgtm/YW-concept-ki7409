# Daily Settlement — 2026-11-08

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
- `CRT`: PF>1.0, WR>40%, RR>1.0, n≥50
- `H-Pattern`: PF>1.0, WR>40%, RR>1.0, n≥8
- `OCS-BTC-5m`: PF>1.0, WR>40%, RR>1.0, n≥10
- `Stair`: PF>0.85, WR>30%, RR>1.0, n≥10
- `TTrades-L12`: PF>1.2, WR>55%, RR>1.2, n≥15
- `TTrades-L13`: PF>1.0, WR>39%, RR>1.0, n≥10
- `TTrades-L14`: PF>1.0, WR>50%, RR>1.0, n≥10
- `Two-Yang`: PF>1.0, WR>38%, RR>1.0, n≥10

## Promoted (1 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|
| CRT | 12 → 13 ⬆ | 120 | 1.23 | 42.5% | 1.66 | all 3 conditions met (override: PF>1.0, WR>40%, RR>1.0, n≥50) |

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (6 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| H-Pattern | 6 | 12 | 2.52 | 58.3% | 1.80 | NOT promoted: — | NOT demoted: PF 2.52 > 1.0; WR 58.3% > 50.0%; RR 1.80 > 1.0 |
| Two-Yang | 5 | 26 | 1.03 | 26.9% | 2.79 | NOT promoted: WR 26.9% ≤ 50.0% | NOT demoted: PF 1.03 > 1.0; RR 2.79 > 1.0 |
| Stair | 2 | 33 | 1.63 | 39.4% | 2.50 | NOT promoted: WR 39.4% ≤ 50.0% | NOT demoted: PF 1.63 > 1.0; RR 2.50 > 1.0 |
| B1-3in1 | 1 | 26 | 0.72 | 34.6% | 1.37 | NOT promoted: PF 0.72 ≤ 1.0; WR 34.6% ≤ 50.0% | NOT demoted: RR 1.37 > 1.0; at min_level |
| OCS-BTC-5m | 6 | 62 | 0.89 | 35.5% | 1.62 | NOT promoted: PF 0.89 ≤ 1.0; WR 35.5% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |
| TTrades-L13 | 6 | 26 | 0.86 | 34.6% | 1.62 | NOT promoted: PF 0.86 ≤ 1.0; WR 34.6% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |

## Insufficient data (n<10) (9 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| 3-Pushes | 2 | 0 | need ≥ 10 trades to settle |
| RSI-Div | 1 | 0 | need ≥ 10 trades to settle |
| 50-20-Pullback | 2 | 0 | need ≥ 10 trades to settle |
| B1 | 1 | 3 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-Fractal | 1 | 6 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 4 | need ≥ 10 trades to settle |
| TTrades-L14 | 2 | 6 | need ≥ 10 trades to settle |
| Argon-Gold | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 1
- **Demoted (⬇)**: 0
- **Held (flat)**: 6
- **Insufficient data**: 9
- **Total evaluated**: 16
