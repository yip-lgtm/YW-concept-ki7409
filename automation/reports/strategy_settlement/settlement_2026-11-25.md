# Daily Settlement — 2026-11-25

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
- `B1-3in1`: PF>1.0, WR>48%, RR>1.0, n≥10
- `CRT`: PF>1.05, WR>35%, RR>1.5, n≥10
- `H-Pattern`: PF>1.0, WR>45%, RR>1.0, n≥10
- `OCS-BTC-5m`: PF>0.85, WR>35%, RR>1.0, n≥30
- `RSI-Div`: PF>1.0, WR>50%, RR>1.0, n≥5
- `Stair`: PF>1.0, WR>38%, RR>1.0, n≥10
- `TTrades-Fractal`: PF>1.0, WR>50%, RR>1.0, n≥5
- `TTrades-L12`: PF>1.0, WR>50%, RR>1.0, n≥5
- `TTrades-L13`: PF>1.0, WR>40%, RR>1.0, n≥10
- `TTrades-L14`: PF>1.2, WR>60%, RR>1.0, n≥10

## Promoted (2 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|
| RSI-Div | 1 → 2 ⬆ | 5 | 2.43 | 60.0% | 1.62 | all 3 conditions met (override: PF>1.0, WR>50%, RR>1.0, n≥5) |
| TTrades-Fractal | 1 → 2 ⬆ | 5 | 2.43 | 60.0% | 1.62 | all 3 conditions met (override: PF>1.0, WR>50%, RR>1.0, n≥5) |

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (7 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| H-Pattern | 6 | 25 | 0.51 | 24.0% | 1.60 | NOT promoted: PF 0.51 ≤ 1.0; WR 24.0% ≤ 50.0% | NOT demoted: RR 1.60 > 1.0 |
| Two-Yang | 5 | 34 | 0.39 | 17.6% | 1.81 | NOT promoted: PF 0.39 ≤ 1.0; WR 17.6% ≤ 50.0% | NOT demoted: RR 1.81 > 1.0 |
| Stair | 7 | 51 | 1.33 | 35.3% | 2.45 | NOT promoted: WR 35.3% ≤ 50.0% | NOT demoted: PF 1.33 > 1.0; RR 2.45 > 1.0 |
| B1-3in1 | 5 | 47 | 1.05 | 46.8% | 1.20 | NOT promoted: WR 46.8% ≤ 50.0% | NOT demoted: PF 1.05 > 1.0; RR 1.20 > 1.0 |
| CRT | 19 | 242 | 1.04 | 33.5% | 2.07 | NOT promoted: WR 33.5% ≤ 50.0% | NOT demoted: PF 1.04 > 1.0; RR 2.07 > 1.0 |
| OCS-BTC-5m | 6 | 38 | 0.50 | 23.7% | 1.62 | NOT promoted: PF 0.50 ≤ 1.0; WR 23.7% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |
| TTrades-L13 | 6 | 18 | 2.54 | 61.1% | 1.62 | NOT promoted: — | NOT demoted: PF 2.54 > 1.0; WR 61.1% > 50.0%; RR 1.62 > 1.0 |

## Insufficient data (n<10) (9 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| 3-Pushes | 2 | 0 | need ≥ 10 trades to settle |
| RSI-Div | 2 | 5 | need ≥ 10 trades to settle |
| 50-20-Pullback | 2 | 0 | need ≥ 10 trades to settle |
| B1 | 1 | 6 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-Fractal | 2 | 5 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 3 | need ≥ 10 trades to settle |
| TTrades-L14 | 2 | 4 | need ≥ 10 trades to settle |
| Argon-Gold | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 2
- **Demoted (⬇)**: 0
- **Held (flat)**: 7
- **Insufficient data**: 9
- **Total evaluated**: 16
