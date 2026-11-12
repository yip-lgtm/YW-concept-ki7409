# Daily Settlement — 2026-11-12

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
| Stair | 4 → 5 ⬆ | 47 | 1.62 | 42.5% | 2.19 | all 3 conditions met (override: PF>1.0, WR>38%, RR>1.0, n≥10) |
| CRT | 16 → 17 ⬆ | 170 | 1.41 | 45.9% | 1.66 | all 3 conditions met (override: PF>1.0, WR>40%, RR>1.0, n≥50) |

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (6 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| H-Pattern | 6 | 20 | 0.65 | 30.0% | 1.52 | NOT promoted: PF 0.65 ≤ 1.0; WR 30.0% ≤ 50.0% | NOT demoted: RR 1.52 > 1.0 |
| Two-Yang | 5 | 37 | 0.93 | 21.6% | 3.35 | NOT promoted: PF 0.93 ≤ 1.0; WR 21.6% ≤ 50.0% | NOT demoted: RR 3.35 > 1.0 |
| B1-3in1 | 3 | 48 | 1.86 | 54.2% | 1.57 | NOT promoted: — | NOT demoted: PF 1.86 > 1.0; WR 54.2% > 50.0%; RR 1.57 > 1.0 |
| OCS-BTC-5m | 6 | 59 | 0.77 | 32.2% | 1.62 | NOT promoted: PF 0.77 ≤ 1.0; WR 32.2% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |
| TTrades-L13 | 6 | 21 | 1.21 | 42.9% | 1.62 | NOT promoted: WR 42.9% ≤ 50.0% | NOT demoted: PF 1.21 > 1.0; RR 1.62 > 1.0 |
| TTrades-L14 | 2 | 10 | 0.41 | 20.0% | 1.62 | NOT promoted: PF 0.41 ≤ 1.0; WR 20.0% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |

## Insufficient data (n<10) (8 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| 3-Pushes | 2 | 0 | need ≥ 10 trades to settle |
| RSI-Div | 1 | 1 | need ≥ 10 trades to settle |
| 50-20-Pullback | 2 | 0 | need ≥ 10 trades to settle |
| B1 | 1 | 3 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-Fractal | 1 | 7 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 5 | need ≥ 10 trades to settle |
| Argon-Gold | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 2
- **Demoted (⬇)**: 0
- **Held (flat)**: 6
- **Insufficient data**: 8
- **Total evaluated**: 16
