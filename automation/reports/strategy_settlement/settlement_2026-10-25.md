# Daily Settlement — 2026-10-25

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
- `50-20-Pullback`: PF>0.95, WR>35%, RR>1.0, n≥10
- `CRT`: PF>0.8, WR>30%, RR>1.0, n≥10
- `H-Pattern`: PF>1.0, WR>50%, RR>1.0, n≥5
- `Stair`: PF>0.85, WR>33%, RR>1.0, n≥10
- `TTrades-L12`: PF>1.2, WR>55%, RR>1.2, n≥15
- `TTrades-L13`: PF>1.0, WR>39%, RR>1.0, n≥10
- `TTrades-L14`: PF>0.8, WR>30%, RR>1.0, n≥10

## Promoted (1 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|
| CRT | 3 → 4 ⬆ | 73 | 1.07 | 39.7% | 1.62 | all 3 conditions met (override: PF>0.8, WR>30%, RR>1.0, n≥10) |

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (7 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| 3-Pushes | 2 | 11 | 1.94 | 54.5% | 1.62 | NOT promoted: — | NOT demoted: PF 1.94 > 1.0; WR 54.5% > 50.0%; RR 1.62 > 1.0 |
| 50-20-Pullback | 2 | 60 | 0.93 | 35.0% | 1.73 | NOT promoted: PF 0.93 ≤ 1.0; WR 35.0% ≤ 50.0% | NOT demoted: RR 1.73 > 1.0 |
| Stair | 2 | 32 | 0.73 | 28.1% | 1.86 | NOT promoted: PF 0.73 ≤ 1.0; WR 28.1% ≤ 50.0% | NOT demoted: RR 1.86 > 1.0 |
| B1-3in1 | 1 | 17 | 0.10 | 5.9% | 1.62 | NOT promoted: PF 0.10 ≤ 1.0; WR 5.9% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0; at min_level |
| OCS-BTC-5m | 1 | 15 | 0.81 | 33.3% | 1.62 | NOT promoted: PF 0.81 ≤ 1.0; WR 33.3% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0; at min_level |
| TTrades-L13 | 3 | 31 | 1.33 | 45.2% | 1.62 | NOT promoted: WR 45.2% ≤ 50.0% | NOT demoted: PF 1.33 > 1.0; RR 1.62 > 1.0 |
| TTrades-L14 | 2 | 12 | 0.81 | 33.3% | 1.62 | NOT promoted: PF 0.81 ≤ 1.0; WR 33.3% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |

## Insufficient data (n<10) (8 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| H-Pattern | 3 | 7 | need ≥ 10 trades to settle |
| Two-Yang | 1 | 9 | need ≥ 10 trades to settle |
| RSI-Div | 1 | 3 | need ≥ 10 trades to settle |
| B1 | 1 | 2 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 1 | need ≥ 10 trades to settle |
| TTrades-Fractal | 1 | 1 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 7 | need ≥ 10 trades to settle |
| Argon-Gold | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 1
- **Demoted (⬇)**: 0
- **Held (flat)**: 7
- **Insufficient data**: 8
- **Total evaluated**: 16
