# Deep 5m track — 三條樣本交叉驗證

**日期：** 2026-10-21
**目的：** 決定邊個策略值得繼續 tune。準則唔係「邊個 backtest 賺錢」，而係
**喺真實五分鐘粒度、獨立樣本、兩種評估節奏之下都企得穩**。

---

## 1. 三條樣本

| track | 資料來源 | 期間 | 粒度 | 產出 |
|---|---|---|---|---|
| **1h**（原有「第二條獨立 track」） | Yahoo 1h bars | 180 日 | 1h 近似 | 4,332 單 / 9 策略 |
| **deep5m (4h 節奏)** | Polygon 真實 5m | 13 個月（115,200 bars） | **真實 5m** | 2,149 單 / 8 策略 |
| **deep5m (1h 節奏)** | Polygon 真實 5m | 13 個月 | **真實 5m** | 8,396 單 / 8 策略 |

deep5m 係 BTC only，1h track 係 5 個標的。以下比較一律**先限制到 BTC-USD 再限制
到 deep track 嘅期間**，否則比緊兩件唔同嘅事。

> ⚠️ 1h track 同 live track **時間重疊**（deep 4D report SF-11 已指出），所以佢
> 唔係真正獨立樣本。deep5m 先係。

---

## 2. 結果

| 策略 | 1h PF | deep 4h PF | deep 1h PF | deep 4h n | 判定 |
|---|--:|--:|--:|--:|---|
| **Two-Yang** | **1.14** | **1.31** | **1.09** | 291 | ✅ **三個樣本都 > 1** |
| **CRT** | 0.95 | **1.32** | **1.15** | 360 | ✅ 真實粒度先有 edge |
| Stair | 0.91 | 0.98 | 1.10 | 138 | ⚠️ 貼住 1，正負號會 flip |
| 50-20-Pullback | 1.03 | 0.96 | 0.91 | 462 | ❌ 粒度愈真愈差 |
| 3-Pushes | 0.99 | 0.87 | 0.93 | 369 | ❌ |
| Kell-Cycle | 1.02 | 0.90 | 0.87 | 513 | ❌ |
| H-Pattern | 0.96 | 1.62 *(n=10)* | 0.85 *(n=55)* | 10 | ❌ n=10 係雜訊 |
| RSI-Div | 1.62 *(n=24)* | 0.81 *(n=6)* | 0.85 *(n=32)* | 6 | ❌ 5m 樣本太少，判唔到 |
| B1 | 2.43 *(n=20)* | **0 單** | **0 單** | 0 | ❌ 真實 5m 從來冇 fire 過 |

R-multiple 只有 {-1.0, +1.618}（exit level 只有 SL / T2），所以 PF ≈ 勝率映射，
**唯一可調嘅 lever 係勝率**。

---

## 3. 三個結論

### 3.1 Two-Yang 係唯一企得穩嘅策略
PF 喺 1h (1.14)、真實 5m 4h 節奏 (1.31)、真實 5m 1h 節奏 (1.09) 三個樣本都 > 1，
而且勝率最高（40–45%）。值得繼續 tune。

### 3.2 CRT 嘅 edge 淨係存在於真實粒度 —— 1h track 會指錯方向
CRT 喺 1h track PF 0.95（負），喺真實 5m 係 1.32 / 1.15（正）。即係話 **1h track
唔止係弱啲嘅代理，佢可以企喺錯誤嗰邊**。一個喺 1h track 睇落冇 edge 嘅策略，
喺真實粒度反而有。

### 3.3 B1 係而家最誤導人嘅數字
1h track 20 單、PF 2.43、+11.42R；但喺 13 個月真實 5m history 上 **一單都冇**。
B1 嘅偵測器（BBI + KDJ 右侧突破）喺真實 5m bar 上幾乎唔會出訊號。

---

## 4. 沿途修好嘅三個缺陷

1. **`build_trade` 冇 normalise detector direction**（commit `7985f00f`）
   偵測器用緊 `up`/`down`（3-Pushes）、`bullish`/`bearish`（RSI-Div、CRT），
   而 backtest 要求 direction 已經係 `long`/`short` → 三個策略嘅單 **100% 被丟**。
   Live 有 `live_scan._normalize_direction` 兜住，backtest 冇。
   後果：deep track 得 5 個策略有單；1h track 同樣零單；而 2026-10-20 個
   「0 of 9 configurations survive」結論將 3-Pushes 同 CRT 標為 overfit ——
   真實原因係**第二條 track 根本冇佢哋嘅數據**。

2. **每晚嘅 1h track 從來冇入過 git**（commit `32d8814a`）
   `daily_auto_push.py` 嘅 `WATCHED_PATHS` 冇包
   `automation/reports/historical_backtest/`，所以 nightly backtest 計完就丟。
   Repo 個 copy 自從人手 commit 嗰日之後一直係舊嘅。

3. **兩個 script 寫死 `/workspace/YW-concept-ki7409`**（commit `724072b8`）
   `historical_backtest.py` 會喺第一根 bar 都未行就死；`rl_arm_report.py` 會
   印 "no closed trades"（其實有 16 條）。兩者都改為由檔案位置推 repo root。

---

## 5. 建議

- **將 deep5m track 接落 optimiser 做第三條 gate。** 而家 publish 規則要求
  live 5m 同 1h 兩邊 holdout PF 都要改善，但 1h track 時間上同 live 重疊，
  唔構成獨立驗證。13 個月真實 5m 先係。
- **Tune 優先次序：Two-Yang → CRT。** 其餘策略喺真實粒度 PF < 1，唔應該再
  花時間調參（調完只會係喺錯嘅形狀上過擬合）。
- **H-Pattern / RSI-Div 需要更多真實 5m 樣本**（n = 10 / 6），而家判唔到。
- **B1 要決定：係修偵測器，係承認佢喺 5m 唔 work。** 而家佢靠 1h track 嘅
  20 單支撐住一個 2.43 嘅 PF。

---

## 6. 重現

```bash
# deep 5m track（真實 5m，4 小時節奏 / 1 小時節奏）
python3 automation/scripts/historical_backtest.py --mode deep5m --deep-step 48 \
  --tickers BTC-USD --out .../trades_5m_deep.jsonl
python3 automation/scripts/historical_backtest.py --mode deep5m --deep-step 12 \
  --tickers BTC-USD --out .../trades_5m_deep_s12.jsonl

# 1h track（Yahoo 180 日，CI 每晚跑）
python3 automation/scripts/historical_backtest.py --days 180
```

資料：`automation/data/deep_history/BTCUSD/5m/`（115,200 bars，2025-09-15 → 2026-10-19）
