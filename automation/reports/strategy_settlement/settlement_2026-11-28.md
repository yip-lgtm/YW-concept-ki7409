# Daily Settlement — 2026-11-28

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
- `Stair`: PF>1.0, WR>34%, RR>1.0, n≥10
- `TTrades-Fractal`: PF>1.0, WR>50%, RR>1.0, n≥5
- `TTrades-L12`: PF>1.0, WR>50%, RR>1.0, n≥5
- `TTrades-L14`: PF>1.2, WR>60%, RR>1.0, n≥10

## Promoted (0 agents) ⬆
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Demoted (0 agents) ⬇
| Agent | Old → New | n | PF | WR | RR | Reason |
|-------|-----------|---|-----|-----|-----|--------|

## Held (n≥10, mixed signals — stays flat) (7 agents)
| Agent | Level | n | PF | WR | RR | Why not promoted / demoted |
|-------|-------|---|-----|-----|-----|----------------------------|
| H-Pattern | 6 | 15 | 0.60 | 26.7% | 1.66 | NOT promoted: PF 0.60 ≤ 1.0; WR 26.7% ≤ 50.0% | NOT demoted: RR 1.66 > 1.0 |
| Two-Yang | 5 | 29 | 0.39 | 17.2% | 1.85 | NOT promoted: PF 0.39 ≤ 1.0; WR 17.2% ≤ 50.0% | NOT demoted: RR 1.85 > 1.0 |
| Stair | 7 | 29 | 1.54 | 37.9% | 2.52 | NOT promoted: WR 37.9% ≤ 50.0% | NOT demoted: PF 1.54 > 1.0; RR 2.52 > 1.0 |
| B1-3in1 | 1 | 23 | 0.53 | 34.8% | 1.00 | NOT promoted: PF 0.53 ≤ 1.0; WR 34.8% ≤ 50.0%; RR 1.00 ≤ 1.0 | NOT demoted: at min_level |
| CRT | 19 | 168 | 1.27 | 35.7% | 2.28 | NOT promoted: WR 35.7% ≤ 50.0% | NOT demoted: PF 1.27 > 1.0; RR 2.28 > 1.0 |
| OCS-BTC-5m | 6 | 29 | 0.34 | 17.2% | 1.62 | NOT promoted: PF 0.34 ≤ 1.0; WR 17.2% ≤ 50.0% | NOT demoted: RR 1.62 > 1.0 |
| TTrades-L13 | 6 | 15 | 1.85 | 53.3% | 1.62 | NOT promoted: — | NOT demoted: PF 1.85 > 1.0; WR 53.3% > 50.0%; RR 1.62 > 1.0 |

## Insufficient data (n<10) (9 agents)
| Agent | Level | n | Note |
|-------|-------|---|------|
| 3-Pushes | 2 | 0 | need ≥ 10 trades to settle |
| RSI-Div | 2 | 2 | need ≥ 10 trades to settle |
| 50-20-Pullback | 2 | 0 | need ≥ 10 trades to settle |
| B1 | 1 | 6 | need ≥ 10 trades to settle |
| Kell-Cycle | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-Fractal | 2 | 4 | need ≥ 10 trades to settle |
| TTrades-L12 | 1 | 0 | need ≥ 10 trades to settle |
| TTrades-L14 | 2 | 0 | need ≥ 10 trades to settle |
| Argon-Gold | 1 | 0 | need ≥ 10 trades to settle |

## Aggregate
- **Promoted (⬆)**: 0
- **Demoted (⬇)**: 0
- **Held (flat)**: 7
- **Insufficient data**: 9
- **Total evaluated**: 16
