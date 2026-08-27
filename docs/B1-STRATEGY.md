# B1 战法 (右侧交易) — Strategy Doc

> **版本**: 2026-08-27 v1  
> **Repo**: https://github.com/yip-lgtm/YW-concept-ki7409

## 1 句话总结

**B1 = BBI 多空指数 + KDJ 拐头 + 右侧突破 — 5 个条件 ALL true 先入场。**

---

## 核心思想

B1 战法是一套在华人交易圈中颇具影响力的**右侧交易系统**，尤其在股票和加密货币市场被广泛讨论。其核心思想可概括为三个关键词：

- **顺势**: 只在明确的上升趋势中寻找机会，不逆势、不抄底
- **右侧**: 拒绝在下跌中"接飞刀"，耐心等待趋势转强的确认信号出现后才行动
- **纪律**: 将交易视为概率游戏，严格执行仓位管理和止损

---

## 指标

### 1. BBI 多空指数

BBI = MA(3, 6, 12, 24) 嘅平均

```python
for p in (3, 6, 12, 24):
    df[f'MA{p}'] = df['Close'].rolling(window=p).mean()
df['BBI'] = df[[f'MA{p}' for p in (3,6,12,24)]].mean(axis=1)
```

### 2. KDJ 随机指标 (9, 3, 3)

```python
low_n = df['Low'].rolling(window=9).min()
high_n = df['High'].rolling(window=9).max()
rsv = (df['Close'] - low_n) / (high_n - low_n) * 100
k = rsv.ewm(alpha=1/3, adjust=False).mean()  # K
d = k.ewm(alpha=1/3, adjust=False).mean()     # D
j = 3 * k - 2 * d                              # J
```

---

## 5 个入场条件 (ALL 必须 true)

| # | 条件 | 解释 |
|---|------|------|
| 1 | `Close > BBI` AND `BBI 向上` | 价格站上多空线 + 趋势转强 |
| 2 | `昨天 J < -20` (坑底) | 超卖区，J 值已被压到底 |
| 3 | `今天 J > 昨天 J` (拐头) | J 值反转向上 (右侧确认) |
| 4 | 阳线 (Close > Open) AND `Close > 昨天最高` | 突破前高 = 右侧突破 |
| 5 | (可选) `Volume > 5d MA` | 成交量确认 |

---

## 持仓规则 (回测默认)

| 项目 | 默认值 |
|------|--------|
| **入场** | 信号次日 Open |
| **持有** | 5 天 |
| **止损** | 信号当日的 Low |
| **出场** | 持有期满收盘 OR 触及止损 (孰先) |

---

## 适用市场

- 股票 (A 股 / 港股 / 美股)
- 加密货币 (BTC, ETH)
- 期货 (NQ, ES) — **本 repo 应用于 micro futures MNQ/MES/M2K**

---

## Detector 实现 (本 repo)

文件: `automation/src/yw_indicators_b1.py`

```python
from yw_indicators_b1 import detect_b1

result = detect_b1(df, j_threshold=-20, use_volume_filter=True)
# → {"present": True, "direction": "long", "strength": 50-100,
#    "bbi": ..., "k": ..., "d": ..., "j": ..., "signal_low": ..., "details": ...}
```

---

## Live Scan 集成

| 字段 | 值 |
|------|---|
| Agent | `yw-b1` |
| Tickers | MNQ=F, MES=F, M2K=F |
| Weight | 1.0 (v1, 起始) |
| Timeframe | 5min / 15min / 1h |
| R-Multiples | [1, 1.618, 2.618, 3.618, 5] |
| LLM Optim | ✅ 2026-08-27 (v1) |

---

## 触发的 TG 消息格式

```
🟢 <b>B1 战法</b> [A] MNQ=F

💰 Last: $29,341.25
📊 Conf: 78
🎯 Dir: bullish
💬 B1: Close 29,341 > BBI 29,250 ↑, prev J -25 < -20 (pit), 
     now J -15 turning up, right-side breakout above 29,300

<b>Risk Plan</b> (1.6×ATR stop, R-multiple targets):
• SL: $29,290 (signal day low)
• T1 (1R): $29,392
• T2 (1.618R): $29,432
• T3 (2.618R): $29,495
• T4 (3.618R): $29,558
• T5 (5R): $29,650

✅ Position opened (auto-track)
⏰ 2026-08-27T01:34:00 UTC
```

---

## 何时 iterate

- 30+ trades 后，WR 明显高/低
- 5d backtest 嘅 PF < 0.9 (考虑调整 j_threshold)
- J 值经常唔落 -20 (考虑放宽到 -15)

---

## Source Files

- 入口: `automation/src/yw_indicators_b1.py` (detect_b1 + calculate_bbi + calculate_kdj)
- Live scan: `automation/scripts/live_scan.py` (B1 branch in run_detector)
- Strategy config: `automation/src/yw_grader.py` (STRATEGIES["B1"])
- 4d Backtest: `automation/scripts/backtest_4d.py` (10th strategy)
- 1st party code (用户共享): reference implementation in 用户消息 (本 file 上方已内嵌)
