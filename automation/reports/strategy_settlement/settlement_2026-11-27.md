# Daily Settlement — 2026-11-27

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
- `CRT`: PF>1.0, WR>30%, RR>1.0, n≥10
- `H-Pattern`: PF>1.0, WR>45%, RR>1.0, n≥10
- `OCS-BTC-5m`: PF>0.85, WR>35%, RR>1.0, n≥30
- `RSI-Div`: PF>1.0, WR>50%, RR>1.0, n≥5
- `Stair`: PF>1.0, WR>38%, RR>1.0, n≥10
- `TTrades-Fractal`: PF>1.0, WR>50%, RR>1.0, n≥5
- `TTrades-L12`: PF>1.0, WR>50%, RR>1.0, n≥5
- `TTrades-L14`: PF>1.2, WR>60%, RR>1.0, n≥10

## Promoted (0 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Demoted (1 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|
| B1-3in1 | 2 → 1 ⬇ | 31 | 0.72 | 41.9% | 1.00 | all 3 conditions failed (override: PF≤1.0, WR≤48%, RR≤1.0, n≥10) |

## Held (n≥10, mixed signals — stays flat) (6 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| H-Pattern | 6 | 18 | 0.64 | 27.8% | 1.65 | NOT promoted: PF 0.64 ≤ 1.0; WR 27.8% ≤ 50.0% | NOT demoted: RR 1.65 > 1.0 |
| Two-Yang | 5 | 31 | 0.35 | 16.1% | 1.83 | NOT promoted: PF 0.35 ≤ 1.0; WR 16.1% ≤ 50.0% | NOT demoted: RR 1.83 > 1.0 |
| Stair | 7 | 35 | 1.32 | 34.3% | 2.53 | NOT promoted: WR 34.3% ≤ 50.0% | NOT demoted: PF 1.32 > 1.0; RR 2.53 > 1.0 |
| CRT | 19 | 192 | 1.18 | 34.9% | 2.20 | NOT promoted: WR 34.9% ≤ 50.0% | NOT demoted: PF 1.18 > 1.0; RR 2.20 > 1.0 |
| OCS-BTC-5m | 6 | 29 | 0.34 | 17.2% | 1.62 | NOT promoted: PF 0.34 ≤ 1.0; WR 17.2% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |
| TTrades-L13 | 6 | 15 | 1.85 | 53.3% | 1.62 | NOT promoted: — | NOT demoted: PF 1.85 > 1.0; WR 53.3% > 50.0%; RR 1.62 > 1.0 |

## Insufficient data (n<10) (9 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| 3-Pushes | 2 | 0 | need ≥ 10 trades to settle |
| RSI-Div | 2 | 5 | need ≥ 10 trades to settle |
| 50-20-Pullback | 2 | 0 | need ≥ 10 trades to settle |
| B1 | 1 | 6 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-Fractal | 2 | 5 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-L14 | 2 | 0 | need ≥ 10 trades to settle |
| Argon-Gold | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 0
- **Demoted (⬇)**: 1
- **Held (flat)**: 6
- **Insufficient data**: 9
- **Total evaluated**: 16
