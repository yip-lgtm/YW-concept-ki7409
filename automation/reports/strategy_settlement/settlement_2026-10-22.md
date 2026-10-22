# Daily Settlement — 2026-10-22

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

## Promoted (0 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (7 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| 3-Pushes | 2 | 12 | 2.27 | 58.3% | 1.62 | NOT promoted: — | NOT demoted: PF 2.27 > 1.0; WR 58.3% > 50.0%; RR 1.62 > 1.0 |
| 50-20-Pullback | 2 | 77 | 0.97 | 36.4% | 1.70 | NOT promoted: PF 0.97 ≤ 1.0; WR 36.4% ≤ 50.0% | NOT demoted: RR 1.70 > 1.0 |
| Stair | 2 | 35 | 0.97 | 34.3% | 1.86 | NOT promoted: PF 0.97 ≤ 1.0; WR 34.3% ≤ 50.0% | NOT demoted: RR 1.86 > 1.0 |
| B1-3in1 | 1 | 15 | 0.00 | 0.0% | 0.00 | NOT promoted: PF 0.00 ≤ 1.0; WR 0.0% ≤ 50.0%; RR 0.00 ≤ 1.0 | NOT demoted: at min_level |
| CRT | 1 | 48 | 0.73 | 31.2% | 1.62 | NOT promoted: PF 0.73 ≤ 1.0; WR 31.2% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0; at min_level |
| TTrades-L13 | 2 | 30 | 1.08 | 40.0% | 1.62 | NOT promoted: WR 40.0% ≤ 50.0% | NOT demoted: PF 1.08 > 1.0; RR 1.62 > 1.0 |
| TTrades-L14 | 2 | 12 | 0.81 | 33.3% | 1.62 | NOT promoted: PF 0.81 ≤ 1.0; WR 33.3% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |

## Insufficient data (n<10) (9 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| H-Pattern | 2 | 5 | need ≥ 10 trades to settle |
| Two-Yang | 1 | 8 | need ≥ 10 trades to settle |
| RSI-Div | 1 | 4 | need ≥ 10 trades to settle |
| B1 | 1 | 2 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 2 | need ≥ 10 trades to settle |
| OCS-BTC-5m | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-Fractal | 1 | 1 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 7 | need ≥ 10 trades to settle |
| Argon-Gold | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 0
- **Demoted (⬇)**: 0
- **Held (flat)**: 7
- **Insufficient data**: 9
- **Total evaluated**: 16
