# Daily Settlement — 2026-11-11

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

## Promoted (1 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|
| B1-3in1 | 1 → 2 ⬆ | 36 | 1.40 | 47.2% | 1.56 | all 3 conditions met (override: PF>1.0, WR>30%, RR>1.0, n≥10) |

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (6 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| H-Pattern | 6 | 19 | 0.92 | 36.8% | 1.57 | NOT promoted: PF 0.92 ≤ 1.0; WR 36.8% ≤ 50.0% | NOT demoted: RR 1.57 > 1.0 |
| Two-Yang | 5 | 40 | 1.04 | 22.5% | 3.58 | NOT promoted: WR 22.5% ≤ 50.0% | NOT demoted: PF 1.04 > 1.0; RR 3.58 > 1.0 |
| Stair | 4 | 41 | 1.80 | 43.9% | 2.29 | NOT promoted: WR 43.9% ≤ 50.0% | NOT demoted: PF 1.80 > 1.0; RR 2.29 > 1.0 |
| CRT | 16 | 141 | 1.26 | 43.3% | 1.65 | NOT promoted: WR 43.3% ≤ 50.0% | NOT demoted: PF 1.26 > 1.0; RR 1.65 > 1.0 |
| OCS-BTC-5m | 6 | 59 | 0.83 | 33.9% | 1.62 | NOT promoted: PF 0.83 ≤ 1.0; WR 33.9% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |
| TTrades-L13 | 6 | 24 | 0.81 | 33.3% | 1.62 | NOT promoted: PF 0.81 ≤ 1.0; WR 33.3% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |

## Insufficient data (n<10) (9 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| 3-Pushes | 2 | 0 | need ≥ 10 trades to settle |
| RSI-Div | 1 | 1 | need ≥ 10 trades to settle |
| 50-20-Pullback | 2 | 0 | need ≥ 10 trades to settle |
| B1 | 1 | 4 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-Fractal | 1 | 6 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 7 | need ≥ 10 trades to settle |
| TTrades-L14 | 2 | 7 | need ≥ 10 trades to settle |
| Argon-Gold | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 1
- **Demoted (⬇)**: 0
- **Held (flat)**: 6
- **Insufficient data**: 9
- **Total evaluated**: 16
