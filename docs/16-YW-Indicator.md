# YW Indicator（YW摸頂底）

TradingView：https://www.tradingview.com/script/VOJy3Uz2-YW-Indicator/  
作者：`ywtraderhk`｜Pine Script v6｜疊加主圖｜手冊版本 v6

核心：ICT／SMC。把「高週期掃流動性 → 反轉確認 → 目標投射 → 延續進場 → 倉位風控」畫在圖上。

- 最佳圖表：1m／3m／5m／15m
- 預設時區：America/New_York
- 適用：NQ／ES／MNQ／MES、外匯、黃金、原油等

---

## 核心名詞

| 名稱 | 含義 |
|------|------|
| **T-Spot** | HTF K 掃破前棒高／低後收回，且收盤越過自身 log 中位 |
| **C1** | 提供流動性的前棒 |
| **C2** | 執行掃單並收回；其極值 = **失效價** |
| **C3** | C2 之後應延續方向 |
| **C4** | 擴張型確認棒 |
| **CISD** | Change in State of Delivery：收盤突破反向序列開盤價極值 |
| **OB+／OB-** | 回踩 T-Spot 後突破最近轉折 |
| **Breaker／Unicorn** | 掃後反包；重疊未補 FVG 則升級 Unicorn |
| **Invalidation** | C2 極值；穿過即形態失敗（停損參考） |
| **FVG／VI／PFVG** | 公允價值缺口／成交量失衡／該 HTF 週期首現 FVG |

---

## 自動 HTF 對齊（Auto）

| 圖表 | HTF1 | HTF2 | HTF3 |
|------|------|------|------|
| 1m | 15m | 30m | 60m |
| 3m | 30m | 60m | 4H |
| **5m** | **60m** | **4H** | **1D** |
| 15m | 4H | 1D | 1W |
| 60m | 1D | 1W | 1M |

可改 Custom 或逐層手動。MNQ 种田建議 **5m + HTF1=60m**。

---

## 訊號生命週期（做多；做空鏡像）

1. **C2 掃單**  
   HTF K 跌破前低後收回，收盤站上 log 中位 → T-Spot 方框 + `Bullish C2 Closed`（C3 開啟）

2. **CISD 確認**  
   收盤突破起跌序列開盤上緣 → CISD 線  
   - 失效價 = C2 最低（灰盒）  
   - Fib：1／2／2.5／3／4R

3. **延續（可選）**  
   回踩 T-Spot 後破轉折高 → **OB+** + `C3 CISD Long`  
   進場 = 確認棒收盤；停損 = 確認段低點；可顯示建議倉位

4. **結束**  
   觸及失效價（失敗）或到達 Fib

**Live Developing**：HTF 未收定會預演，可消失或改向。實盤只信 **收盤確認**。

---

## 圖面元素

| 元素 | 解讀 |
|------|------|
| 右側迷你 K | HTF 狀態 + 收棒倒數 |
| T-Spot 方框 | 反轉區；回踩為觀察重點 |
| 中線／收盤線 | log 中位／C2 收盤 |
| CISD 線 | 訊號正式成立 |
| 灰盒 Invalidation | 停損參考 |
| Fib 虛線 | 風險倍數目標 |
| OB+／OB- | 延續進場 |
| PDH／PDL、Session H/L | 被掃後停止延伸 = 流動性已取 |
| Info Table | 模型名、HTF 倒數、Bias、倉位 |

---

## MNQ 5min 建議設定（种田、圖面乾淨）

### GENERAL
- Monospace Font：開
- HTF Detection Mode：**Auto**
- Manual T-Spot Bias：**None**（或按 1H 方向手動過濾）

### HTF
- Show HTF1：開；Auto-align：開；Max Candles：**4**
- HTF2／HTF3：初學可關

### T-SPOT
- Enable：開；Detect on：**HTF1 Only**
- Show Only Latest T-Spot／Sweep：開
- Show T-Spot Close Line：開
- Box Transparency：90
- Show Silver T-Spot：開（可選）
- Hide T-Spots When Price Trades Against：開
- Use Candle Body for Pivot：開
- Show Live Developing CISD：盯盤可開；怕重繪則關

### LABELS
- C2／C3／C4：開（small）
- HTF Mini-Display Labels：關

### SWEEP & OB
- HTF1 Sweeps on LTF：開；HTF2／3：關
- Continuation OB：開

### BREAKER
- 初學：**關**

### FVG
- FVG：開；PFVG：關；VI：可選

### CISD & FIB
- CISD Lines：開；All CISD：關
- Fib：開；Levels：`1,2,2.5` 或 `1,2,2.5,3`
- Max Projection Sets：**1**

### DISPLAY & ALERTS
- Info Table：開
- Enable Alerts：開
- 實戰只用 **Confirmed**（C2 Closed、CISD Confirmed、C3 CISD）
- Live 類僅適合盯盤

### PDH / SESSIONS
- PDH／PDL：開
- Session H/L：至少 NY（09:30–12:00）
- Position Size：种田可用固定風險約 **$100**；Prop Firm 模式可開

存檔建議：`MNQ 5m YW Clean`

---

## 警報

內建 10 種。建議：

| 用 | 不用（或僅盯盤） |
|----|------------------|
| CISD C2 Long／Short（收盤） | CISD Live |
| C3 CISD Long／Short | — |
| Bullish／Bearish C2 Closed | — |

Webhook 預設：`{"ticker":"{ticker}","interval":"{interval}","alert":"{default}"}`  
Silver 形態只經 Webhook，無內建選單。

---

## Bias 怎麼算

HTF1 最後兩根已收 K：
- 收盤越過前棒高／低 → 多／空
- 掃高回收 → 空；掃低收回 → 多
- 雙向都掃 → 比上下影
- 其餘中性

---

## 同 YW Concept／TTFM／种田

| 指標 | 本倉庫 |
|------|--------|
| HTF T-Spot C2 | TTFM C2；H／Stair 第一段 |
| CISD | BOS／MSS |
| C3／OB+ | C3 入場、50/20 回踩、Kell Crossback |
| Fib 1–2.5R | 种田 RR 1:1.5～2 |
| Invalidation | SL；風險約 $100 |
| PDH／Session | CRT、Killzone |

**建議流程：** 1H／60m 定方向 → 等 **C2 + CISD 收盤** → 5m 回踩 T-Spot 或等 OB+ → 合流 Stair／H／20EMA → 日停利跟种田規則。

---

## FAQ（摘）

- 訊號畫一半消失：Live 未確認、逆向穿中線被藏、只留 Latest → 正常
- PDH／時段線中途停：已被掃，刻意設計
- 倒數 `n/a`：Replay／歷史區不會算倒數
- 倉位建議：只在 C3 CISD 出現；打到停損後清除
- 圖卡：開 Clean Helper、Only Latest，減少 Max Candles

## 限制

- 會重繪：僅 Live Developing CISD 與 Live 警報；收盤確認不重繪
- 手冊註明未接入邏輯：Time Filter、Auto Bias (from HTF sweep)、部分顏色模板等
- 分析輔助，不構成投資建議

## 相關文件

- [13 - TTFM Fractal Model](13-TTFM-Fractal-Model.md)
- [02 - H-Pattern](02-H-Pattern.md)
- [12 - Stair Pattern](12-Stair-Pattern.md)
- [14 - CRT](14-CRT-Candle-Range-Theory.md)
- [10 - 種田實務](10-Zhongtian-Practical-Setup.md)

**更新時間**：2026-08-20
