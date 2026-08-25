# 9 Strategy Sub-Agents — Latest Setup (auto-generated)

> **Auto-updated** from `automation/scripts/strategy_ranking.py` + `automation/src/yw_grader.py`
> **Last iter**: `20260826_003514`

## 9 Strategies Current Config

| # | Strategy | Agent | Ticker | Weight | Timeframe | R-Multiples | LLM Optim |
|---|----------|-------|--------|--------|-----------|-------------|-----------|
| 1 | **OCS BTC 5m** | `yw-ocs-btc` | BTC-USD | **1.0** | 5min | `[1, 1.618, 2.618, 3.618, 5]` | — |
| 2 | **H-Pattern** | `yw-h-pattern` | MNQ=F | **1.2** | 3min/5min | `[1, 1.618, 2.618, 3.618, 5]` | — |
| 3 | **3-Pushes** | `yw-3-pushes` | MNQ=F | **1.0** | 5min/15min | `[1, 1.618, 2.618, 3.618, 5]` | — |
| 4 | **兩陽夾一陰** | `yw-two-yang` | MNQ=F | **0.3** | 5min/15min | `[1.5, 2.5, 4.0, 6.0, 8.0]` | ✅ 2026-08-25 v2 |
| 5 | **RSI Divergence** | `yw-rsi-div` | MNQ=F | **0.7** | 15min | `[1.5, 2.0, 3.0, 4.0, 5.0]` | ✅ 2026-08-25 |
| 6 | **50/20 Pullback** | `yw-50-20-pullback` | MNQ=F | **1.0** | 5min/15min/60min | `[1, 1.618, 2.618, 3.618, 5]` | — |
| 7 | **Stair Pattern** | `yw-stair-pattern` | MNQ=F | **1.2** | 5min/15min/1hr | `[1, 1.618, 2.618, 3.618, 5]` | ✅ 2026-08-25 v3 |
| 8 | **CRT** | `yw-crt` | MNQ=F | **1.1** | 4H range / 5min execution | `[1, 1.618, 2.618, 3.618, 5]` | — |
| 9 | **Kell Cycle** | `yw-kell-cycle` | MNQ=F | **0.6** | 5min/15min/1H/Daily | `[1, 1.618, 2.618, 3.618, 5]` | ✅ 2026-08-26 v4 |

## LLM Iterations Applied (cumulative)

| Iter | Strategy | Before → After | Conf | LLM Reason |
|------|----------|----------------|------|------------|
| v1 2026-08-25 17:00 | RSI-Divergence | `w=1.1, tf=1/3/5min` → `w=0.7, tf=15min` | ~80% | Live PF 0.92 < 1, wider R targets |
| v2 2026-08-25 20:22 | Two-Yang-One-Yin | `w=0.8, tf=15min, R=[1,1.618,2.618]` → `w=0.3, tf=5/15min, R=[1.5,2.5,4,6,8]` | 72% | Live PF 0.67 = no edge, wider R |
| v2 2026-08-25 20:22 | Kell-Cycle | `w=0.9, tf=5min` → `w=0.5, tf=5min` | 72% | 5 sub-detectors noisy, lower exposure |
| v3 2026-08-25 20:36 | Stair-Pattern | `w=0.9, tf=5min` → `w=1.2, tf=15min` | 85% | 20d 383 trades PF 1.08 = solid edge, raise |
| v4 2026-08-26 00:35 | Kell-Cycle | `w=0.5, tf=5min` → `w=0.6, tf=15min` | 72% | 4d 16 trades WR 56% R +2.36 = edge confirmed, raise |

## Latest Iteration (20260826_003514)

| # | Strategy | Grade | Conf | Current | LLM Suggests | Status |
|---|----------|-------|------|---------|--------------|--------|
| 1 | OCS BTC 5m | D | 25% | w=1.0 tf=5min | w=0.3 tf=15min R=[1.5, 2.0, 3.0, 4.0, 5.0] | ⏭️ skip |
| 2 | H-Pattern | C | 30% | w=1.2 tf=3min/5min | w=0.9 tf=5min/15min R=[1.0, 1.5, 2.0, 2.5, 3.0] | ⏭️ skip |
| 3 | 3-Pushes | D | 20% | w=1.0 tf=5min/15min | w=0.4 tf=5min/15min R=[1.0, 1.5, 2.0, 3.0, 4.0] | ⏭️ skip |
| 4 | 兩陽夾一陰 | C | 25% | w=0.5 tf=5min | w=0.7 tf=5min/15min R=[1.0, 1.5, 2.0, 2.5, 3.0] | ⏭️ skip |
| 5 | RSI Divergence | C | 35% | w=0.7 tf=15min | w=0.5 tf=15min R=[1.0, 1.5, 2.0, 2.5, 3.0] | ⏭️ skip |
| 6 | 50/20 Pullback | D | 35% | w=1.0 tf=5min | w=0.5 tf=5min/15min R=[1.0, 1.5, 2.0, 2.5, 3.0] | ⏭️ skip |
| 7 | Stair Pattern | D | 15% | w=0.9 tf=5min | w=0.3 tf=5min/15min R=[1.5, 2.5, 3.5, 5.0, 7.0] | ⏭️ skip |
| 8 | CRT | C | 25% | w=1.1 tf=5min+4H | w=0.9 tf=5min+4H R=[1.0, 2.0, 3.0, 4.0, 5.0] | ⏭️ skip |
| 9 | Kell Cycle | D | 72% | w=0.9 tf=5min | w=0.6 tf=15min R=[1.5, 2.0, 3.0, 4.0, 6.0] | ✅ APPLIED |
