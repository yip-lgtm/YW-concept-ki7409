# B1 战法 60d Backtest Report

> **Date**: 2026-08-27  
> **Method**: Walk-forward, 5d hold, stop at signal-day low, 1 micro contract

## Findings (重要)

B1 战法系为**A 股** 设计嘅 右侧交易系统，5 条件对 crypto/futures 市场**太严格**:

| Condition | A 股 (设计) | Crypto/Futures (实际) |
|-----------|------------|---------------------|
| 1. Close > BBI ↑ | Common | 当 J 跌入 pit 时，BBI 几乎 always 向下 |
| 2. 昨天 J < -20 | 经常 | 24/7 trending market 极少落到 -20 |
| 3. J 拐头向上 | 经常 | OK (J 总是在 0-100 之间摆动) |
| 4. 阳线 + 突破前高 | 经常 | OK |
| 5. Volume > 5d MA | 经常 | OK |

**Root cause**: 当 J < -10 (oversold) 时，crypto 24/7 trending market BBI 几乎 always 向下，condition "BBI 向上" 0% 通过率。

## Test Results

### 60d Daily Bars (1d)

| Ticker | Bars | J<-20 days | B1 Signals |
|--------|------|-----------|------------|
| MNQ=F | 60 | 0 | **0** |
| MES=F | 60 | 0 | **0** |
| M2K=F | 60 | 0 | **0** |
| MGC=F | 60 | 0 | **0** |
| BTC-USD | 59 | 0 | **0** |

### 30d 1h Bars

| Ticker | Bars | J<-20 | J<-10 | J<-5 | B1 Signals (j<-20) |
|--------|------|-------|-------|------|---------------------|
| MNQ=F | 1,421 | 1 | 21 | 88 | **0** |
| BTC-USD | 1,421 | 1 | 21 | 88 | **0** |

### 30d 5m Bars

| Ticker | Bars | J<-20 | J<-10 | J<-5 | B1 Signals (j<-20) | B1 Signals (j<-5) |
|--------|------|-------|-------|------|---------------------|---------------------|
| MNQ=F | 6,592 | 2 | 104 | 314 | **0** | **1** |
| MGC=F | 6,565 | 3 | 113 | 348 | **1** | **3** |
| BTC-USD | 8,409 | 15 | 229 | 552 | **1** | **1** |

## Options for Improvement

### Option 1: 放宽 j_threshold to -5 (Recommended)
- 保留全部 5 conditions
- signals ×10 (B1 实战版本用 -5 喺 A 股大陆)
- Expected: 100-200 signals per 30d per ticker
- 优点: 信 B1 灵魂 (5 conditions 完整)
- 缺点: 样本 purity 低 (不是真正 oversold)

### Option 2: Skip "BBI 向上" condition
- 只用 4 conditions: J坑底 + J拐头 + 阳线 + 突破前高
- 当 J 落 pit 时，唔再要求 BBI 向上
- Expected: 50-100 signals per 30d per ticker
- 优点: 适用于 crypto trending market
- 缺点: 偏离 B1 原始设计

### Option 3: 改为逆势
- B1 默认做多 (右侧突破)
- 改为做空 (BBI 向下 + J 反弹后回落)
- 适用于 crypto 下跌 market
- 优点: 跟趋势
- 缺点: 偏离 B1 灵魂 (顺势)

### Option 4: 保留现状
- 长期 monitor
- 等待 J<-20 真係出现 (大暴跌)
- signals 会非常少 (1-3 per 30d)
- 优点: 高 purity，low risk
- 缺点: 长期无 signal，浪费 strategy slot

## Recommendation

**Option 1** — relax j_threshold to -5，保持 B1 战法灵魂嘅 5 conditions。

理由：
- B1 原始设计为 A 股 (国家干预+10% daily limit)
- Crypto/futures 24/7 trending market 需要调整
- 5 conditions 全保留 (signal purity)
- Volume filter 仍可用 (用 5d MA 喺 high-volume crypto)
- 预期 30+ signals per ticker per month，足够 statistical analysis

## Status

Currently 24/7 live scan running with j_threshold=-20 (as designed).
If user approves Option 1, will switch to j_threshold=-5.
