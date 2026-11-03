# Daily Settlement — 2026-11-04

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

## Promoted (0 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (6 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| Two-Yang | 4 | 15 | 2.27 | 46.7% | 2.59 | NOT promoted: WR 46.7% ≤ 50.0% | NOT demoted: PF 2.27 > 1.0; RR 2.59 > 1.0 |
| Stair | 2 | 23 | 1.63 | 30.4% | 3.73 | NOT promoted: WR 30.4% ≤ 50.0% | NOT demoted: PF 1.63 > 1.0; RR 3.73 > 1.0 |
| B1-3in1 | 1 | 22 | 0.38 | 22.7% | 1.27 | NOT promoted: PF 0.38 ≤ 1.0; WR 22.7% ≤ 50.0% | NOT demoted: RR 1.27 > 1.0; at min_level |
| CRT | 12 | 110 | 1.14 | 40.9% | 1.64 | NOT promoted: WR 40.9% ≤ 50.0% | NOT demoted: PF 1.14 > 1.0; RR 1.64 > 1.0 |
| OCS-BTC-5m | 6 | 65 | 1.01 | 38.5% | 1.62 | NOT promoted: WR 38.5% ≤ 50.0% | NOT demoted: PF 1.01 > 1.0; RR 1.62 > 1.0 |
| TTrades-L13 | 6 | 25 | 1.75 | 52.0% | 1.62 | NOT promoted: — | NOT demoted: PF 1.75 > 1.0; WR 52.0% > 50.0%; RR 1.62 > 1.0 |

## Insufficient data (n<10) (10 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| H-Pattern | 4 | 9 | need ≥ 10 trades to settle |
| 3-Pushes | 2 | 0 | need ≥ 10 trades to settle |
| RSI-Div | 1 | 0 | need ≥ 10 trades to settle |
| 50-20-Pullback | 2 | 5 | need ≥ 10 trades to settle |
| B1 | 1 | 2 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-Fractal | 1 | 4 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 4 | need ≥ 10 trades to settle |
| TTrades-L14 | 2 | 4 | need ≥ 10 trades to settle |
| Argon-Gold | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 0
- **Demoted (⬇)**: 0
- **Held (flat)**: 6
- **Insufficient data**: 10
- **Total evaluated**: 16
