# 🛠️ Strategy Optimization Proposals (LLM-driven)

**Generated**: 2026-09-03T02:46:27.397318+08:00
**Based on**: 7d LLM iteration + 7d trade analysis
**Source iteration**: iteration_scientist_20260903_024236.json

## 📋 Summary

- Total trades analyzed: 773
- Strategies optimized: 9
- Auto-apply requires: Grade A/B AND conf ≥60 (LLM-grade)

## H-Pattern (`yw-h-pattern`)

**7d LLM Grade**: D (0%) | **Auto-apply eligible**: ❌ No
**7d Stats**: N=33 WR=24.2% PF=0.31 R=-13.7
**24h Stats**: N=33 | Avg Win R=1.54 | Avg Loss R=-1.00
**Direction**: long 32 trades -11.7R | short 1 trades -1.0R
**By Grade**: {'C': -9.291999999999998, 'B': -3.3819999999999997}
**Action**: 🛑 OPTIMIZE (high priority)

**💡 Optimization Suggestions**:

| Param | Current | Suggested | Reason |
|-------|---------|-----------|--------|
| `weight` | 1.2 | 0.6 | WR=24.2% < 35%, reduce priority (was 1.2, try 0.6) |
| `trend_filter` | none | EMA20_slope (only trade with trend) | Add trend filter to reduce counter-trend losses |
| `cooldown_bars` | 0 | 10 | Add 10-bar cooldown to reduce over-trading after losses |

## 3-Pushes (`yw-3-pushes`)

**7d LLM Grade**: D (0%) | **Auto-apply eligible**: ❌ No
**7d Stats**: N=109 WR=34.9% PF=0.66 R=-1.5
**24h Stats**: N=0 | Avg Win R=1.62 | Avg Loss R=-1.00
**Direction**: long 0 trades +0.0R | short 0 trades +0.0R
**By Grade**: {'B': -3.1339999999999897, 'C': -6.382}
**Action**: 🛑 OPTIMIZE (high priority)

**💡 Optimization Suggestions**:

| Param | Current | Suggested | Reason |
|-------|---------|-----------|--------|
| `weight` | 1.0 | 0.5 | WR=34.9% < 35%, reduce priority (was 1.0, try 0.5) |
| `trend_filter` | none | EMA20_slope (only trade with trend) | Add trend filter to reduce counter-trend losses |
| `cooldown_bars` | 0 | 10 | Add 10-bar cooldown to reduce over-trading after losses |

## Two-Yang (`yw-two-yang`)

**7d LLM Grade**: D (0%) | **Auto-apply eligible**: ❌ No
**7d Stats**: N=52 WR=30.8% PF=0.46 R=-11.1
**24h Stats**: N=52 | Avg Win R=1.62 | Avg Loss R=-1.00
**Direction**: long 52 trades -10.1R | short 0 trades +0.0R
**By Grade**: {'C': -10.291999999999998, 'B': 0.18000000000000105}
**Action**: 🛑 OPTIMIZE (high priority)

**💡 Optimization Suggestions**:

| Param | Current | Suggested | Reason |
|-------|---------|-----------|--------|
| `weight` | 0.5 | 0.3 | WR=30.8% < 35%, reduce priority (was 0.5, try 0.3) |

## RSI-Div (`yw-rsi-div`)

**7d LLM Grade**: B (65%) | **Auto-apply eligible**: ✅ Yes
**7d Stats**: N=44 WR=50.0% PF=1.05 R=+12.7
**24h Stats**: N=44 | Avg Win R=1.53 | Avg Loss R=-1.00
**Direction**: long 24 trades +7.4R | short 20 trades +4.3R
**By Grade**: {'C': 11.124000000000006, 'B': 0.6180000000000001}
**Action**: ✅ KEEP (healthy)

**💡 Optimization Suggestions**:

| Param | Current | Suggested | Reason |
|-------|---------|-----------|--------|
| `cooldown_bars` | 0 | 10 | Add 10-bar cooldown to reduce over-trading after losses |

## 50-20-Pullback (`yw-50-20-pullback`)

**7d LLM Grade**: C (50%) | **Auto-apply eligible**: ❌ No
**7d Stats**: N=226 WR=49.1% PF=0.90 R=+49.4
**24h Stats**: N=226 | Avg Win R=1.56 | Avg Loss R=-1.00
**Direction**: long 106 trades +16.7R | short 120 trades +41.7R
**By Grade**: {'B': 48.00200000000009, 'A': 5.708000000000001, 'C': 4.708}
**Action**: ⚠️ OPTIMIZE (low priority)

**💡 Optimization Suggestions**:

| Param | Current | Suggested | Reason |
|-------|---------|-----------|--------|
| `trend_filter` | none | EMA20_slope (only trade with trend) | Add trend filter to reduce counter-trend losses |
| `cooldown_bars` | 0 | 10 | Add 10-bar cooldown to reduce over-trading after losses |

## Stair (`yw-stair-pattern`)

**7d LLM Grade**: D (0%) | **Auto-apply eligible**: ❌ No
**7d Stats**: N=88 WR=38.6% PF=0.58 R=-7.5
**24h Stats**: N=88 | Avg Win R=1.55 | Avg Loss R=-1.00
**Direction**: long 0 trades +0.0R | short 88 trades -1.5R
**By Grade**: {'B': -2.437999999999997, 'A': 0.9780000000000046}
**Action**: 🛑 OPTIMIZE (high priority)

**💡 Optimization Suggestions**:

| Param | Current | Suggested | Reason |
|-------|---------|-----------|--------|
| `trend_filter` | none | EMA20_slope (only trade with trend) | Add trend filter to reduce counter-trend losses |
| `cooldown_bars` | 0 | 10 | Add 10-bar cooldown to reduce over-trading after losses |

## CRT (`yw-crt`)

**7d LLM Grade**: D (0%) | **Auto-apply eligible**: ❌ No
**7d Stats**: N=160 WR=41.9% PF=0.77 R=+17.8
**24h Stats**: N=160 | Avg Win R=1.61 | Avg Loss R=-1.00
**Direction**: long 66 trades +2.1R | short 94 trades +12.7R
**By Grade**: {'B': 25.753999999999994, 'A': -7.9659999999999975, 'C': -3.0}
**Action**: ⚠️ OPTIMIZE (low priority)

**💡 Optimization Suggestions**:

| Param | Current | Suggested | Reason |
|-------|---------|-----------|--------|
| `grade_threshold` | A/B/C all | A only (filter out B/C) | Grade A underperforms: -8.0R |
| `trend_filter` | none | EMA20_slope (only trade with trend) | Add trend filter to reduce counter-trend losses |
| `cooldown_bars` | 0 | 10 | Add 10-bar cooldown to reduce over-trading after losses |

## Kell-Cycle (`yw-kell-cycle`)

**7d LLM Grade**: D (0%) | **Auto-apply eligible**: ❌ No
**7d Stats**: N=53 WR=37.7% PF=0.54 R=-5.6
**24h Stats**: N=48 | Avg Win R=1.62 | Avg Loss R=-1.00
**Direction**: long 25 trades -4.1R | short 23 trades +8.4R
**By Grade**: {'C': -0.11199999999999544, 'B': -0.5279999999999989}
**Action**: 🛑 OPTIMIZE (high priority)

**💡 Optimization Suggestions**:

| Param | Current | Suggested | Reason |
|-------|---------|-----------|--------|
| `direction_filter` | both | long only (if BTC downtrend) or short only | long: -4.1R (loss), short: +8.4R (win) |
| `trend_filter` | none | EMA20_slope (only trade with trend) | Add trend filter to reduce counter-trend losses |
| `cooldown_bars` | 0 | 10 | Add 10-bar cooldown to reduce over-trading after losses |

## B1 (`yw-b1`)

**7d LLM Grade**: D (0%) | **Auto-apply eligible**: ❌ No
**7d Stats**: N=1 WR=0.0% PF=0.00 R=-8.0
**24h Stats**: N=1 | Avg Win R=0.00 | Avg Loss R=-1.00
**Direction**: long 1 trades -1.0R | short 0 trades +0.0R
**By Grade**: {'B': -1.0}
**Action**: 🛑 OPTIMIZE (high priority)

**💡 Optimization Suggestions**:

| Param | Current | Suggested | Reason |
|-------|---------|-----------|--------|
| `r_multiples` | default | widen T1 (T1=0.5R), tighten T2 close (T2=1.0R), reduce T3-T5 (skip if low conf) | avg_win_R=0.00 < |avg_loss_R|=1.00 (poor R:R) |

## 🎯 Next Steps

1. **Review proposals** above
2. **Apply params**: edit `automation/src/yw_grader.py` STRATEGIES dict
3. **Test in shadow mode** (paper trade for 24h)
4. **Compare metrics**: WR, PF, R before/after
5. **Auto-apply** when LLM returns grade A/B + conf≥60

## ⚠️ Safety Rules

- **NEVER** disable a strategy without 14d+ evidence
- **NEVER** apply more than 2 param changes at once
- **ALWAYS** keep stop-loss and risk rules intact
- **ALWAYS** preserve min_trades filter (≥ 30 for stats)
- **AUTO-APPLY** only grade A/B + conf≥60 (LLM-grade)
