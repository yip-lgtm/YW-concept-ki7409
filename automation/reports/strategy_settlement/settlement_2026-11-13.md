# Daily Settlement — 2026-11-13

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
- `TTrades-L12`: PF>1.0, WR>50%, RR>1.0, n≥5
- `TTrades-L13`: PF>1.0, WR>39%, RR>1.0, n≥10
- `TTrades-L14`: PF>1.0, WR>50%, RR>1.0, n≥10
- `Two-Yang`: PF>1.0, WR>38%, RR>1.0, n≥10

## Promoted (1 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|
| B1-3in1 | 3 → 4 ⬆ | 50 | 1.69 | 52.0% | 1.56 | all 3 conditions met (override: PF>1.0, WR>30%, RR>1.0, n≥10) |

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (6 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| H-Pattern | 6 | 23 | 0.56 | 26.1% | 1.60 | NOT promoted: PF 0.56 ≤ 1.0; WR 26.1% ≤ 50.0% | NOT demoted: RR 1.60 > 1.0 |
| Two-Yang | 5 | 40 | 0.63 | 17.5% | 2.97 | NOT promoted: PF 0.63 ≤ 1.0; WR 17.5% ≤ 50.0% | NOT demoted: RR 2.97 > 1.0 |
| Stair | 6 | 59 | 1.54 | 40.7% | 2.25 | NOT promoted: WR 40.7% ≤ 50.0% | NOT demoted: PF 1.54 > 1.0; RR 2.25 > 1.0 |
| CRT | 18 | 182 | 1.25 | 43.4% | 1.64 | NOT promoted: WR 43.4% ≤ 50.0% | NOT demoted: PF 1.25 > 1.0; RR 1.64 > 1.0 |
| OCS-BTC-5m | 6 | 57 | 0.69 | 29.8% | 1.62 | NOT promoted: PF 0.69 ≤ 1.0; WR 29.8% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |
| TTrades-L13 | 6 | 21 | 1.47 | 47.6% | 1.62 | NOT promoted: WR 47.6% ≤ 50.0% | NOT demoted: PF 1.47 > 1.0; RR 1.62 > 1.0 |

## Insufficient data (n<10) (9 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| 3-Pushes | 2 | 0 | need ≥ 10 trades to settle |
| RSI-Div | 1 | 1 | need ≥ 10 trades to settle |
| 50-20-Pullback | 2 | 0 | need ≥ 10 trades to settle |
| B1 | 1 | 3 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-Fractal | 1 | 7 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 6 | need ≥ 10 trades to settle |
| TTrades-L14 | 2 | 7 | need ≥ 10 trades to settle |
| Argon-Gold | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 1
- **Demoted (⬇)**: 0
- **Held (flat)**: 6
- **Insufficient data**: 9
- **Total evaluated**: 16
