# Daily Settlement — 2026-10-28

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
- `CRT`: PF>0.8, WR>30%, RR>1.0, n≥10
- `H-Pattern`: PF>1.0, WR>50%, RR>1.0, n≥5
- `OCS-BTC-5m`: PF>1.0, WR>40%, RR>1.0, n≥10
- `Stair`: PF>0.85, WR>33%, RR>1.0, n≥10
- `TTrades-L12`: PF>1.2, WR>55%, RR>1.2, n≥15
- `TTrades-L13`: PF>1.0, WR>39%, RR>1.0, n≥10
- `TTrades-L14`: PF>0.8, WR>30%, RR>1.0, n≥10

## Promoted (2 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|
| OCS-BTC-5m | 1 → 2 ⬆ | 31 | 1.17 | 41.9% | 1.62 | all 3 conditions met (override: PF>1.0, WR>40%, RR>1.0, n≥10) |
| TTrades-L13 | 3 → 4 ⬆ | 33 | 1.52 | 48.5% | 1.62 | all 3 conditions met (override: PF>1.0, WR>39%, RR>1.0, n≥10) |

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (5 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| Two-Yang | 1 | 10 | 1.29 | 40.0% | 1.94 | NOT promoted: WR 40.0% ≤ 50.0% | NOT demoted: PF 1.29 > 1.0; RR 1.94 > 1.0; at min_level |
| 50-20-Pullback | 2 | 47 | 0.91 | 34.0% | 1.75 | NOT promoted: PF 0.91 ≤ 1.0; WR 34.0% ≤ 50.0% | NOT demoted: RR 1.75 > 1.0 |
| Stair | 2 | 32 | 0.85 | 31.2% | 1.87 | NOT promoted: PF 0.85 ≤ 1.0; WR 31.2% ≤ 50.0% | NOT demoted: RR 1.87 > 1.0 |
| B1-3in1 | 1 | 17 | 0.10 | 5.9% | 1.62 | NOT promoted: PF 0.10 ≤ 1.0; WR 5.9% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0; at min_level |
| CRT | 7 | 104 | 0.97 | 37.5% | 1.62 | NOT promoted: PF 0.97 ≤ 1.0; WR 37.5% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |

## Insufficient data (n<10) (9 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| H-Pattern | 3 | 6 | need ≥ 10 trades to settle |
| 3-Pushes | 2 | 8 | need ≥ 10 trades to settle |
| RSI-Div | 1 | 3 | need ≥ 10 trades to settle |
| B1 | 1 | 3 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 1 | need ≥ 10 trades to settle |
| TTrades-Fractal | 1 | 3 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 7 | need ≥ 10 trades to settle |
| TTrades-L14 | 2 | 6 | need ≥ 10 trades to settle |
| Argon-Gold | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 2
- **Demoted (⬇)**: 0
- **Held (flat)**: 5
- **Insufficient data**: 9
- **Total evaluated**: 16
