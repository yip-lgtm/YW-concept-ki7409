# Daily Settlement — 2026-11-19

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
- `B1-3in1`: PF>1.5, WR>50%, RR>1.2, n≥10
- `CRT`: PF>1.05, WR>35%, RR>1.5, n≥10
- `H-Pattern`: PF>1.0, WR>45%, RR>1.0, n≥10
- `OCS-BTC-5m`: PF>0.85, WR>35%, RR>1.0, n≥30
- `Stair`: PF>1.0, WR>38%, RR>1.0, n≥10
- `TTrades-Fractal`: PF>1.1, WR>55%, RR>1.1, n≥10
- `TTrades-L12`: PF>1.0, WR>50%, RR>1.0, n≥5
- `TTrades-L13`: PF>1.0, WR>40%, RR>1.0, n≥10
- `TTrades-L14`: PF>1.2, WR>60%, RR>1.0, n≥10

## Promoted (1 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|
| Stair | 6 → 7 ⬆ | 72 | 1.37 | 38.9% | 2.15 | all 3 conditions met (override: PF>1.0, WR>38%, RR>1.0, n≥10) |

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (6 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| H-Pattern | 6 | 32 | 0.64 | 28.1% | 1.64 | NOT promoted: PF 0.64 ≤ 1.0; WR 28.1% ≤ 50.0% | NOT demoted: RR 1.64 > 1.0 |
| Two-Yang | 5 | 49 | 0.67 | 20.4% | 2.63 | NOT promoted: PF 0.67 ≤ 1.0; WR 20.4% ≤ 50.0% | NOT demoted: RR 2.63 > 1.0 |
| B1-3in1 | 5 | 66 | 1.34 | 50.0% | 1.34 | NOT promoted: WR 50.0% ≤ 50.0% | NOT demoted: PF 1.34 > 1.0; RR 1.34 > 1.0 |
| CRT | 19 | 282 | 1.05 | 34.8% | 1.98 | NOT promoted: WR 34.8% ≤ 50.0% | NOT demoted: PF 1.05 > 1.0; RR 1.98 > 1.0 |
| OCS-BTC-5m | 6 | 46 | 0.64 | 28.3% | 1.62 | NOT promoted: PF 0.64 ≤ 1.0; WR 28.3% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |
| TTrades-L13 | 6 | 16 | 2.70 | 62.5% | 1.62 | NOT promoted: — | NOT demoted: PF 2.70 > 1.0; WR 62.5% > 50.0%; RR 1.62 > 1.0 |

## Insufficient data (n<10) (9 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| 3-Pushes | 2 | 0 | need ≥ 10 trades to settle |
| RSI-Div | 1 | 6 | need ≥ 10 trades to settle |
| 50-20-Pullback | 2 | 0 | need ≥ 10 trades to settle |
| B1 | 1 | 8 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-Fractal | 1 | 6 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 6 | need ≥ 10 trades to settle |
| TTrades-L14 | 2 | 7 | need ≥ 10 trades to settle |
| Argon-Gold | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 1
- **Demoted (⬇)**: 0
- **Held (flat)**: 6
- **Insufficient data**: 9
- **Total evaluated**: 16
