# 各策略最強參數 setup（2026-10-22）

以 **live 實際生效** 嘅參數為準，逐策略拆解。每一個都標明三件事：
生效值、證據（三樣本 PF）、以及**值唔值得再 tune**。

---

## 第 0 部分：參數其實分四層，三層半係死嘅

睇 `live_scan.py` 嘅參數流向之前，先要分清楚邊個掣真係有效。呢個分錯咗，
點 tune 都冇效果。

| 層 | 位置 | 有冇生效 | 說明 |
|---|---|---|---|
| **L0** 偵測器內部閾值 | `automation/src/yw_indicators*.py` | ✅ **唯一真正決定 signal 嘅地方** | 全部 hardcode，冇 config 覆寫機制 |
| **L1** `strategy_overrides.json` | weight / min_strength / resample_tf | ⚠️ 只有 `weight` 生效，而且有陷阱 | 見下 |
| **L2** `agent_params.json` | optimiser 學到嘅 per-cell exit | ❌ **全部 DORMANT** | 9 個策略 `validated_on_holdout` 全部 `False` |
| **L3** `exit_overrides.json` | RL 學到嘅 exit policy | ⚠️ 只喺 A/B 嘅 **RL arm** 生效 | CONTROL arm 沿用書本 template |
| 書本級常數 | `live_scan.py` | ✅ | 1.6×ATR stop、R 階梯、$1/point |

### L1 三個陷阱（每個都害過人）

**`weight` 生效，但生效位置喺閘後面。** 實際流程係：

```
偵測器 fire → LLM 評分（用原始偵測輸出，weight 未參與）
            → BTC +10 增幅
            → conf < min_conf ? skip        (40；BTC 30)
            → grade ∉ (A,B,C) ? skip
            → 然後先 conf = round(conf × weight)
```

即係 **weight 改唔到 LLM 評分、改唔到 min_conf 閘、改唔到 grade 閘**。
佢只係令下游（開倉閘、RL、settlement）見到一個縮放過嘅信心值。
想用 weight 擋住一個策略開倉，做唔到。

**`min_strength` 完全係死 config。** 喺 `live_scan.py:208` 載入落 `_cfg`，
之後全個 runtime **冇任何地方讀過**。

**`resample_tf` 同樣係死 config。** 喺 `live_scan.py:210` 寫入 `args`，
之後冇人讀。（`resample_15m` 唔同，嗰個 `RSI-Div` 真係有用。）

### 書本級常數（全部策略共用，冇得逐策略調）

| 項目 | 值 | 位置 |
|---|---|---|
| 止損 | **1.6 × ATR** | `calc_sl_tp()` |
| R 階梯 | T1=1R · T2=1.618R · T3=2.618R · T4=3.618R · T5=5R | `calc_sl_tp()` |
| 最小信心 | 40（BTC 30） | `LLM_MIN_CONF` / `LLM_MIN_CONF_BTC` |
| 可接受 grade | A / B / C（C 可收單但唔開倉） | `ACCEPTABLE_GRADES` + `BLOCK_GRADE_C_OPEN` |
| 倉位 | **1 張合約，$1/point** | 見下 |
| 出場 R 值 | 只有 **-1.0 / +1.0 / +1.618** | 實測 `trades.jsonl` |

### ⚠️ 倉位冇 sizing：R 單位跨標的完全唔可比

實測 3,252 筆已平倉交易，每筆 -1R 損失嘅 `$ ÷ 止損距離`：

| 標的 | 中位 | p10 | p90 |
|---|--:|--:|--:|
| M2K=F | 1.000 | 0.998 | 1.002 |
| MES=F | 1.000 | 0.999 | 1.001 |
| BTC-USD | 1.000 | 1.000 | 1.000 |
| MNQ=F | 1.000 | 0.999 | 1.001 |
| MGC=F | 1.000 | 0.999 | 1.001 |
| GC=F | 0.999 | 0.999 | 1.000 |

**全部都係 1 張、$1/point。** MNQ 實際乘數係 $2/point、MGC 係 $10/point，
系統一律當 $1 計。於是同一個「1R」：

| 標的 | 止損距離中位 | **每單實際蝕** |
|---|--:|--:|
| BTC-USD | 140.27 點 | **~$140** |
| MNQ=F | 30.76 點 | ~$31 |
| MGC=F | 6.72 點 | ~$6.7 |
| MES=F | 5.14 點 | ~$5.1 |
| GC=F | 4.78 點 | ~$4.8 |
| M2K=F | 2.39 點 | ~$2.4 |

**BTC 每單嘅美元風險係 M2K 嘅 60 倍。** 所以「邊個策略最強」呢個問題，
喺美元層面同喺 R 層面答案完全唔同：本文件全部用 **R / PF** 比較，
因為 PF 係唯一跨標的可比指標。

---

## 第 1 部分：逐策略 setup

三樣本 PF 來自 `automation/reports/historical_backtest/deep5m_track_review_2026-10-21.md`：
1h = Yahoo 1h bars 180 日；deep 4h / deep 1h = Polygon **真實 5m** 13 個月（BTC only，已限制到同一期間）。
n = 真實 5m track 嘅樣本數。

---

### 1. Two-Yang（兩陽夾一陰）— ⭐ 唯一全樣本企穩

**生效參數**

| 項目 | 值 |
|---|---|
| weight | 0.8 |
| 時框 | 15m |
| 方向 | 只做 long |
| detector args | 無 |
| 閘 | 無額外閘 |
| cooldown | 無 |
| 標的限制 | 全部標的（但 M2K=F 已被 optimiser 標記 drop，未生效） |

**偵測邏輯（L0 閾值）** — `detect_two_yang_one_yin(df, volume_filter=False)`

- 睇最後 5 支 K，由後往前搵 3 支一組
- 中間 K 必須陰燭，實體 ≥ 該 3 支收盤高低差 × **0.3**
- 左右兩支必須陽燭，各自實體 ≥ 中間實體 × **0.3**
- **包裹條件**：中 K 實體上界 ≤ 左 K 實體上界，且下界 ≥ 右 K 實體下界
- volume filter：c1 或 c3 量 > 10 支均量 × **1.2**（BTC 自動關閉，24/7 形態唔同）
- strength 固定 70
- 方向**只做 long**（唔會出 short）

**三樣本證據**

| track | n | WR | PF | total R |
|---|--:|--:|--:|--:|
| 1h | 87 | 41.4% | **1.14** | +7.25 |
| deep 4h | 291 | 44.7% | **1.31** | +49.34 |
| deep 1h | 1123 | 40.2% | **1.09** | +60.34 |

**判定：✅ 唯一三個樣本 PF 全部 > 1 嘅策略。勝率亦係全場最高（40–45%）。**

**值得 tune 嘅位**：L0 嘅 **0.3 實體比**同 **1.2 量能比**係兩個未曝光嘅 lever。
而家 trade 只有 long——加一個 short 對稱版本（陰夾兩陽）係最直接嘅擴容。
注意 `volume_filter` 預設 False，即係個量能閘根本冇行。

**反證**：optimiser 對 Two-Yang 試過 4 組 cell config（t2_r 1.3/3.0、breakeven 0.5/1.0、
partial 1.5、stop_mult 1.0/1.3、max_bars 12），train PF 高見 5.069，但
holdout PF 只有 0.651（baseline 0.809）→ 典型過擬合，已全部拒絕。
**即係話 exit 層冇得救，edge 係喺 detection 層，唔係喺 exit 層。**

---

### 2. CRT（Candle Range Theory）— ⭐ edge 淨係存在於真實粒度

**生效參數**

| 項目 | 值 |
|---|---|
| weight | **1.3**（全場最高） |
| 時框 | 5m 執行 + 4h 範圍 |
| detector args | `needs_4h: True` |
| 閘 | **MSS 距離 ≤ 0.3 × range**（追價閘）、cooldown、**禁 GC=F**（新加） |
| 標的限制 | 除 GC=F 全部標的 |
| strength | 80 |

**偵測邏輯（L0）** — `detect_crt(df_4h, df_5m)`

- CRT-H / CRT-L = 上一支**已收** 4H K 嘅高 / 低
- 喺最近 **48 支 5m bar**（一個 4H 節點）搵 raid：Low 穿 CRT-L（做多）或 High 穿 CRT-H（做空）
- 確認（MSS）：raid 之後**第一支** 5m 收盤穿過 raid K 嘅 High（做多）/ Low（做空）
- direction 輸出 `bullish` / `bearish`（**非標準格式**，見 OPS-NOTES）

**三樣本證據**

| track | n | WR | PF | total R |
|---|--:|--:|--:|--:|
| 1h | 278 | 37.1% | 0.95 | -8.35 |
| deep 4h | 360 | 45.0% | **1.32** | +64.12 |
| deep 1h | 1274 | 41.5% | **1.15** | +110.92 |

**判定：✅ 真實粒度有 edge，1h track 反而係負。** 呢個係今輪最有趣嘅結果：
**1h track 唔止係弱啲嘅代理，佢可以企喺錯誤嗰邊。** 任何只靠 1h track 篩策略嘅流程，
會錯殺 CRT。

**值得 tune 嘅位**：目前 raid 深度無上限——**掃穿幾深都接受**。加一個
「raid 深度 ≤ 某個 range 比例」嘅閘，大概率提高 PF（因為深掃 = 追價 = 差）。
另外 MSS 只要求「下一支收盤穿 raid K 高」，無時間上限，可以改成「N 支內」。

**注意**：CRT 喺 1h track 0.95 但喺真實 5m 1.32，意味住**CRT 嘅參數只喺真實粒度調得落**。
用 1h track 調出嚟嘅參數一定係錯嘅。

---

### 3. Stair — ⚠️ 貼住 1，正負號會 flip

**生效參數**

| 項目 | 值 |
|---|---|
| weight | 1.1 |
| 時框 | 5m |
| 方向 | **只做 short** |
| 閘 | 禁 BTC-USD + MES=F；session 閘（RTH_Close / AsiaLate / Lunch） |
| 標的限制 | MNQ=F / M2K=F / MGC=F |
| strength | `min(100, 50 + 上影根數 × 15)` |

**偵測邏輯（L0）** — `detect_stair_pattern(df)`

- 最後 10 支入面搵**大陰燭**：實體/range ≥ **0.5**、上影/range ≤ **0.2**、range ≥ **1.2 × ATR**、收盤喺下半部（close_pct ≤ **0.5**）
- 陰燭之後 4 支入面，上影/range ≥ **0.2** 嘅 K 棒**至少 2 根**
- 確認：最後一支收盤 **< EMA20**
- 只做空

**三樣本證據**

| track | n | WR | PF | total R |
|---|--:|--:|--:|--:|
| 1h | 125 | 36.0% | 0.91 | -7.19 |
| deep 4h | 138 | 37.7% | 0.98 | -1.86 |
| deep 1h | 574 | 40.4% | 1.10 | +33.38 |

**判定：⚠️ 三個樣本夾喺 1 上下，方向唔穩。** deep 4h 係 0.98，deep 1h 係 1.10。

**值得 tune 嘅位**：1.2 × ATR 嘅大陰燭門檻同 0.2 嘅上影門檻係兩個直接 lever；
另外**只做 short**——加做多版本（階梯向上）係低成本擴容試驗。
optimiser 曾經建議 drop BTC-USD + M2K=F（因為咁樣樣本 PF 由 0.907 升到 1.136），
但喺 1h track 上反而變差 → 典型 overfit，已拒絕。

---

### 4. 50-20-Pullback — ❌ 粒度愈真愈差

**生效參數**

| 項目 | 值 |
|---|---|
| weight | 0.948 |
| 時框 | 5m |
| 閘 | **禁 MGC=F**、EMA 距離 ≤ **0.1%**、cooldown |
| 標的限制 | 除 MGC=F 全部 |
| strength | 固定 65 |

**偵測邏輯（L0）** — `detect_5020_pullback(df, lookback=30)`

- EMA20 穿 SMA50（金叉多 / 死叉空），喺**最近 30 支**內
- 價格回踩 EMA20（`pullback == "at_ema20"`）
- 趨勢要 up / down（sideways 唔收）—— BTC 模式放寬趨勢要求
- 需要 ≥ 50 支 K
- strength 固定 65

**三樣本證據**

| track | n | WR | PF | total R |
|---|--:|--:|--:|--:|
| 1h | 134 | 38.8% | 1.03 | +2.14 |
| deep 4h | 462 | 37.2% | 0.96 | -11.70 |
| deep 1h | 1907 | 36.1% | 0.91 | -105.82 |

**判定：❌ PF 隨粒度變真單調下降（1.03 → 0.96 → 0.91）。** 1h track 睇落
「貼近有 edge」，真實粒度就係負。呢個係最典型嘅「粒度幻覺」。

**值得 tune 嘅位**：唔值得再 tune exit。倒係值得試 **lookback 由 30 縮短**
（回踩窗口愈短愈貼近均線，會少好多低質回踩）—— 呢個係 L0 層嘅直接 lever。

---

### 5. 3-Pushes — ❌ 兩個樣本都 < 1

**生效參數**

| 項目 | 值 |
|---|---|
| weight | 1.2 |
| 時框 | 5m（`resample_tf: 15min` 係死 config） |
| 閘 | **禁 BTC-USD**、cooldown |
| 標的限制 | MNQ=F / M2K=F / MGC=F（BTC 已被 ban） |

**偵測邏輯（L0）** — `detect_3_pushes(df)`

- 至少 **3 個**局部高點（每個高點都大過左右兩支）或 3 個局部低點
- 連續 3 個高點**依次降低** = 熊市 exhaustion（做空）；連續 3 個低點**依次升高** = 牛市 exhaustion（做多）
- 有 `narrowing` 變體（波幅收窄）同 `loose` 變體
- direction 輸出 `up` / `down`（**非標準格式**）

**三樣本證據**

| track | n | WR | PF | total R |
|---|--:|--:|--:|--:|
| 1h | 176 | 38.1% | 0.99 | -0.59 |
| deep 4h | 369 | 35.0% | 0.87 | -31.28 |
| deep 1h | 1477 | 36.5% | 0.93 | -65.90 |

**判定：❌ 三個樣本都 < 1。** 特別留意：呢個策略**喺今輪之前，從來冇出現喺任何
backtest track 入面**（因為 direction 格式 bug 成批被丟），所以佢嘅真實粒度表現
係第一次被量度。

**值得 tune 嘅位**：`narrowing` 變體係最有希望嘅分支——3 個高點逐步降低同時波幅收窄，
比「loose」版本緊密得多。值得將 `narrowing` 設為唯一准入條件試多次。

---

### 6. Kell-Cycle — ❌ 明確負 edge

**生效參數**

| 項目 | 值 |
|---|---|
| weight | 0.7 |
| 時框 | 5m（`resample_tf: 15min` 係死 config） |
| 閘 | 無 |
| 標的限制 | 全部 6 個標的 |
| strength | 固定 70 |

**偵測邏輯（L0）** — `detect_kell_setups(df)`，5 個 sub-setup

| sub-setup | 觸發條件 |
|---|---|
| reversal_extension | 距 EMA10 > **1.2 ATR** 且 距 EMA50 < **1.5 ATR** |
| ema_crossback | EMA10-EMA20 收窄（tight_ratio < **0.55**）且 6 支前收喺 EMA20 另一邊而家收返 |
| wedge_pop_drop | 之前有 wedge（tight_ratio < 0.55）且 回踩 EMA10 距離 < **0.35 ATR** |
| base_n_break | — |
| exhaustion | — |

方向由 `dist_ema10_atr` 符號決定；`direction` 可以係 `none`（39/65 嘅命中）。

**三樣本證據**

| track | n | WR | PF | total R |
|---|--:|--:|--:|--:|
| 1h | 209 | 38.8% | 1.02 | +3.06 |
| deep 4h | 513 | 35.9% | 0.90 | -31.29 |
| deep 1h | 1952 | 34.9% | 0.87 | -166.52 |

**判定：❌ 明確負 edge，而且 n 越大越差。** 1h track 嘅 1.02 完全係樣本噪音。

**值得 tune 嘅位**：**唔值得 tune 個別 sub-setup。** 5 個 sub-setup 冇一個
要求共振（confluence），所以 70 分 strength 好似一路都有。真正嘅問題係
**應該要求幾多個 sub-setup 同時成立** —— 例如 ≥2 個先出 signal。呢個係
L0 層嘅結構性改動，值得試。

---

### 7. H-Pattern — ❌ n 太少，判唔到

**生效參數**

| 項目 | 值 |
|---|---|
| weight | 1.2 |
| 時框 | 5m |
| 閘 | pullback ≤ **50%**（BTC ≤ 70% 且唔好 broke_low）、pullback_pct 必須存在（fail-closed） |
| 標的限制 | 全部 |

**偵測邏輯（L0）** — `detect_h_pattern(df)`

- 搵長直 K：range > **1.5 ×** 平均 range
- 轉折點要有上影（賣壓）：**上影 > 實體 × 0.2**（BTC 放寬到 **× 0.1**）
- 回踩深度 `pullback_depth` = （長 K 開盤 − 之後最低點）÷ 長 K 實體
- **非 BTC**：pullback_depth < **0.5** 且 必須 `broke_low`（之後真係穿穿長 K 低位）
- **BTC**：pullback_depth < **0.7**，唔要求 `broke_low`

**三樣本證據**

| track | n | WR | PF | total R |
|---|--:|--:|--:|--:|
| 1h | 188 | 37.2% | 0.96 | -4.74 |
| deep 4h | **10** | 50.0% | 1.62 *(n=10 係雜訊)* | +3.09 |
| deep 1h | 55 | 34.5% | 0.85 | -5.26 |

**判定：❌ 真實 5m 只有 10 / 55 單，太少判唔到。** 之前 n=10 嗰個 PF 1.62
令人誤以為有 edge——加到 55 單就跌返 0.85。

**值得 tune 嘅位**：**先要解決偵測率**。1.2 × 平均 range 嘅長 K 條件喺真實
5m bar 上幾乎唔出現。放寬 1.5 → 1.2 值得試，但**唔好喺 n=10 嘅基礎上調**。

---

### 8. RSI-Div — ❌ 樣本太少 + 已經係 paper-only

**生效參數**

| 項目 | 值 |
|---|---|
| weight | 0.6 |
| 時框 | 15m（`resample_15m: True` **係生效嘅**） |
| 閘 | **paper-only**：只准 Grade A 且非 BTC；否則只記錄唔開倉 |
| 標的限制 | 除 BTC 全部（但 BTC 被 paper-only 擋） |

**偵測邏輯（L0）** — `detect_rsi_divergence(df, lookback=20, ema_filter=True, volume_filter=True)`

- RSI 背離：lookback 20 內
- 價差比門檻 **1.0005 / 0.9995**（0.05%）
- EMA filter、volume filter
- direction 輸出 `bullish` / `bearish`（**非標準格式**）

**三樣本證據**

| track | n | WR | PF | total R |
|---|--:|--:|--:|--:|
| 1h | 24 | 50.0% | 1.62 *(n=24)* | +7.42 |
| deep 4h | **6** | 33.3% | 0.81 *(n=6)* | -0.76 |
| deep 1h | 32 | 34.4% | 0.85 | -3.20 |

**判定：❌ 真實 5m 樣本太少（6–32 單），而 1h track 嘅 1.62 係 n=24 嘅噪音。**

**值得 tune 嘅位**：之前 6 單嘅 0.05% 價差門檻（1.0005/0.9995）相對 BTC
5m bar 太緊。放寬到 1.001 / 0.999 可以提高偵測率——**但要同時接受 n 仍舊好細**
（呢個係同一個 trade-off：偵測率上去了，樣本仍然唔夠判斷）。

---

### 9. B1 战法 — ❌ 真實 5m 從來冇 fire 過

**生效參數**

| 項目 | 值 |
|---|---|
| weight | 0.9 |
| 時框 | 5m/15m/1h（`resample_tf: 15min` 係死 config） |
| 閘 | **只跑 BTC-USD / MNQ=F / MGC=F** |
| 標的限制 | `B1_TICKERS` |

**偵測邏輯（L0）** — `detect_b1(df, j_threshold=5, use_volume_filter=False, vol_ma_period=5)`

- BBI + KDJ 右侧突破
- `j_threshold` = 5（由 5 放寬自 A 股嘅 -5）
- 只做 long
- 5 個條件全部成立先出 signal

**三樣本證據**

| track | n | WR | PF | total R |
|---|--:|--:|--:|--:|
| 1h | 20 | 60.0% | **2.43** | +11.42 |
| deep 4h | **0** | — | — | — |
| deep 1h | **0** | — | — | — |

**判定：❌ 1h track 20 單 PF 2.43，但真實 5m 13 個月一單都冇。**
呢個係全系統最誤導嘅數字。偵測器（BBI+KDJ 右侧突破）喺真實 5m bar 上
基本上唔會出訊號。

**值得 tune 嘅位**：唔係 tune 嘅問題，係**偵測器喺 5m 粒度失效**。
`j_threshold` 可以由 5 再放寬，但一個喺真實 bar 上一單都出唔到嘅策略，
放寬門檻之前應該先確認訊號數唔係零。

---

### 10. B1-3in1 — ❌ 機械式缺陷，已知

**生效參數**

| 項目 | 值 |
|---|---|
| weight | 1.0 |
| 時框 | 5m |
| detector args | `j_threshold = -5`（同 B1 嘅 5 **唔同**）、`use_volume_filter = False`、`days = 5` |
| 標的限制 | 內部自己 fetch BTC/MNQ/MGC |

**三樣本證據**：deep 4h / deep 1h 都係 **0 單**。

Live 實測：39 單全部 -1.0R stop-out、direction 全部 `none`、-39R。
`direction: none` 意味住 tracker 根本唔知方向。

**判定：❌ 已知機械式缺陷，任何參數都救唔到。**

---

### 11. OCS-BTC-5m — ❌ BTC only，而且係走 OCS 分支

**生效參數**

| 項目 | 值 |
|---|---|
| weight | 1.0 |
| 時框 | 5m |
| detector args | `needs_btc: True` |
| 標的限制 | 只 BTC-USD |
| 評分 | **唔經 LLM**：vote ≥ 4 且 conf ≥ 0.55 → A，否則 B；conf = conf × 100 |

`run_detector` 對 OCS 特判：唔呼叫 `llm_grade`，直接用 KNN 嘅 vote/conftest。
所以 OCS 唔受 LLM 429 影響——**呢個係佢而家仲有訊號嘅原因**。

**判定：❌ backtest track 冇覆蓋**（OCS 需要自己 fetch 數據同 rolling KNN，
backtest harness 唔支援）。live 訊號量長期係 0。

---

### 12. Argon-Gold — 設計正確但極少開火

**生效參數**

| 項目 | 值 |
|---|---|
| weight | 1.0 |
| 時框 | 5m/15m/1h |
| detector args | `gold_only: True` |
| 標的限制 | **只 GC=F**（刻意唔跑 MGC=F） |
| 止損 | **≤ $5.00**（`SPOT_STOP_CAP_USD`），MGC 報價 1:1 對應現貨 |
| 風險 | $50 / 單（`SPOT_RISK_USD`，**但實際倉位無 sizing，所以呢個值冇用到**） |
| 出場 | 1R 移保本、1.5R 止盈（SOP 原文） |
| strength | 跟 1H 偏向結構判定 |

**偵測邏輯（L0）** — `detect_argon_gold(df_5m, df_1h, df_15m, max_age_bars=6)`

- 1H 偏向：HH+HL → long，LH+LL → short（`none` 即 reject）
- 15M 箱體：最近 **8** 支已收 15M K 嘅高低
- 觸發窗：掃最近 **6** 支 5m bar（30 分鐘），因為 live 每 15 分鐘掃一次會漏掉 2/3 觸發機會
- **模型 A**：影線掃穿箱體低 + 同一/下一支 Pin Bar（影線 > 2/3 全長）或 Bullish Engulfing
- **模型 B**：M5 雙底 + MSB（收盤穿前一個 Lower High）
- 實體突破箱體高（做多）/ 破箱體低（做空），**只影線突破唔收**
- 止損距離 > $5 直接放棄

**實測開火率**：CI log 10 個 run 每個都有 Argon 嘅 `[gated]` 記錄，
即偵測器行得到。拒絕原因分布：

| 原因 | 比例 |
|---|--:|
| `no clear 1H bias (need HH+HL or LH+LL)` | 6/10 |
| `M5 body did not break the box low` | 3/10 |
| `M5 body did not clear the box high` | 1/10 |

`signals.jsonl` 由 8/25 至今 6,162 條，Argon 一條都冇（gated 唔入檔）。

**判定：✅ 邏輯同 SOP 一致，冇開火係設計使然。**

**但要睇清楚邊個閘先擋住人。** `_evaluate_bar` 嘅次序係：body 突破測試 →
模型 A → 模型 B。CI log 顯示嘅拒絕原因全部係 body 層
（`M5 body did not clear the box high` / `did not break the box low`），
**即係話兩個確認模型根本未曾成為決定因素**——bar 未夠膽實體突破箱體就已經出局。

真正嘅樽頸係：

| 閘 | 擋走幾多 | 位置 |
|---|--:|---|
| 1H 偏向（HH+HL / LH+LL） | 6/10 | 喺 body 測試**之前** |
| M5 實體突破箱體 | 4/10 | body 測試 |
| 模型 A / B | 0（未曾行到） | body 測試之後 |

所以「調換模型 A / B 順序」**唔係**有效 lever。真正值得試嘅係：

1. **1H 偏向定義**：SOP 原文寫「1H 多頭 HH + HL」，而家係用最近 6 支對
   前 6 支比。放寬到 8 對 8，或者改用 EMA20 方向（你 EA 嘅做法），
   先有機會讓更多 bar 行到 body 測試。
2. **實體突破要求**：SOP 場景 A 要求「M5 收盤實體突破箱體高」，而箱體係用
   **最近 8 支已收 15M K**（約 2 小時）嘅高低砌出嚟，觸發 K 嘅實體要穿過
   呢個箱體高，喺 5m bar 上係嚴格條件。放寬成「收盤 ≥ 箱體高 × 0.995」
   值得試一次。

---

## 第 2 部分：跨策略結論

### 最值得做嘅三件事（按期望值排序）

1. **CRT 加 raid 深度上限。** 唯一一個「1h track 睇落冇 edge、真實粒度有 edge」嘅
   策略，而且係全場 weight 最高（1.3）。而家掃穿幾深都收，加個深度比例閘
   係最低成本、最高期望值嘅改動。

2. **Two-Yang 開 short 對稱版本 + 試 0.3 實體比。** 唯一三樣本全企穩嘅策略，
   而家只做一半方向（long）。加做多 = 樣本即時翻倍。

3. **Kell-Cycle 要求 ≥2 個 sub-setup 共振。** 而家 5 個 sub-setup 冇一個要求
   共振，70 分 strength 好似一路都有。改成共振後出 signal，PF 有機會由
   0.87 拉返 1 以上。

### 唔值得做嘅事

- **唔好再 tune exit 層。** 9 個策略嘅 `agent_params.json` 全部 DORMANT，
  而 exit_overrides 嘅 RL 估算（+217.85R）同實盤 A/B（-7.24R）方向相反。
  Exit 層暫時冇可信證據支持任何改動。
- **唔好喺 1h track 上調參數。** CRT 嘅反例已經證明佢可以指錯方向。
  真實 5m track（deep5m）先係可信嗰條。
- **唔好信 n < 50 嘅 PF。** H-Pattern n=10 PF 1.62、RSI-Div n=24 PF 1.62、
  B1 n=20 PF 2.43 —— 三個全部係噪音，全部已經被更大樣本推翻。

### 一個結構性問題（影響所有策略）

**倉位無 sizing。** 所有策略、所有標的，一律 1 張、$1/point。
BTC 每單蝕 ~$140，M2K 每單只蝕 ~$2.4。呢個唔係某個策略嘅參數問題，
但佢決定咗「策略排名」喺美元層面會同 R 層面完全唔同：
**優化 R/PF 唔等於優化美元。** 如果目標係實際盈虧，要先加 sizing
（用 Argon 個 $50 / 單做標準），然後用**每單期望美元**重新排 12 個策略。

---

## 附錄：點重現

```bash
# 生效參數 dump（已疊加所有 override）
python3 - << 'EOF'
import importlib.util, sys
from pathlib import Path
R = Path(".").resolve()
sys.path[:0] = [str(R/"automation/scripts"), str(R/"automation/src")]
spec = importlib.util.spec_from_file_location("live_scan", R/"automation/scripts/live_scan.py")
ls = importlib.util.module_from_spec(spec); spec.loader.exec_module(ls)
for k, v in ls.STRATEGIES.items():
    print(k, v)
EOF

# 三樣本對比
python3 automation/scripts/compare_backtest_tracks.py

# 偵測器輸出格式審計
python3 automation/scripts/audit_detector_formats.py

# 單筆風險（$1/point 驗證）
python3 - << 'EOF'
import json
from collections import defaultdict
d = defaultdict(list)
for l in open("automation/reports/live_scan/trades.jsonl"):
    t = json.loads(l)
    if t.get("status") == "closed" and t.get("R_multiple") == -1.0 and t.get("sl_dist"):
        d[t["ticker"]].append(abs(t["pnl_usd"]) / t["sl_dist"])
for k, v in d.items():
    print(k, len(v), round(sorted(v)[len(v)//2], 3))
EOF
```
