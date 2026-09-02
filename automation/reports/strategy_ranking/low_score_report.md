# 🎯 Low Score Setup Report (7d + 24h)

**Generated**: 2026-09-03T02:43:21.946395+08:00
**Window**: 7-day iteration + 24h live

## 📊 Summary

- Total agents: 10
- Underperformers (Grade D): 8 of 10
- Auto-applied: 0 (LLM API used rule-based fallback)
- 24h fresh trades: 191

## 🚨 Underperformers Detail

| Agent | 7d Stats | 24h Stats | Action |
|-------|----------|-----------|--------|
| h pattern | N=34 WR=24% PF=0.31 R=-14 | N=7 WR=14% R=-4.4 | 🛑 **PAUSE** |
| two yang | N=57 WR=32% PF=0.46 R=-11 | N=18 WR=33% R=-2.3 | ⚠️ **WEIGHT DOWN** |
| b1 | N=8 WR=0% PF=0.00 R=-8 | N=1 WR=0% R=-1.0 | 🛑 **PAUSE** |
| stair pattern | N=98 WR=37% PF=0.58 R=-7 | N=14 WR=43% R=+1.7 | ⚠️ **WEIGHT DOWN** |
| kell cycle | N=60 WR=35% PF=0.54 R=-6 | N=17 WR=59% R=+9.2 | ⚠️ **WEIGHT DOWN** |
| 3 pushes | N=121 WR=40% PF=0.66 R=-2 | N=14 WR=43% R=+1.7 | ⚠️ **WEIGHT DOWN** |
| ocs btc 5m | N=0 WR=0% PF=0.00 R=+0 | N=0 WR=0% R=+0.0 | 🛑 **PAUSE** |
| crt | N=177 WR=44% PF=0.77 R=+18 | N=53 WR=43% R=+7.2 | ⚡ Watch |

## ✅ Keepers (Grade B/C)

| Agent | Stats | Notes |
|-------|-------|-------|
| 50 20 pullback [C] | 7d: N=251 WR=47% R=+49 | 24h: N=58 R=-3.0 | Solid performance |
| rsi div [B] | 7d: N=45 WR=51% R=+13 | 24h: N=9 R=-3.8 | Solid performance |

## 🎯 Recommendations

1. **🛑 PAUSE H-Pattern**: WR 23.5%, PF 0.31, -13.7R 7d. Severe underperformer.
2. **🛑 PAUSE B1**: 0% WR, structural condition (BTC j<20) not met. Auto-skip when j≥20.
3. **⚠️ WEIGHT DOWN Two-Yang**: 31.6% WR, PF 0.46, -11.1R 7d.
4. **⚠️ WEIGHT DOWN Kell-Cycle**: 35% WR 7d but +9.2R 24h. Volatile, monitor.
5. **✅ KEEP 50-20-Pullback**: 47.4% WR, +49.4R 7d. Best by R total.
6. **✅ KEEP CRT**: 43.5% WR, +17.8R 7d, +8.8R 24h. Consistent.
7. **✅ KEEP RSI-Div**: 51.1% WR, +12.7R 7d. Best WR. Volatile but positive.
8. **✅ KEEP Stair**: 36.7% WR but PF 0.58. Borderline, monitor.

## ⚠️ LLM Status

API returned fallback for most agents. Re-run with healthy LLM for
more detailed diagnosis (param suggestions, regime analysis).
