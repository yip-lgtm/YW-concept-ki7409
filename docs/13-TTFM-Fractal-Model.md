# TTFM Fractal Model Indicator（TTrades）

來源：TTrades Fractal Model Indicator – Full Guide（2026-05-09）+ 實盤設定整理

**平台**：TradingView Invite-only · **Fractal Model [Pro+] (TTrades)**

## 是什麼

TTFM 用「高時間框結構 + 低時間框確認」標記 expansion 行情。核心是 **C1–C4** 與 **CISD**：

| 標記 | 含義 |
|------|------|
| C1 | 前一根（提供流動性） |
| C2 | Swing 點（掃高/掃低後收返） |
| C3 | 延續／確認 |
| C4 | 再延續（expansion） |
| CISD | Change in State of Delivery（交貨狀態改變） |

目標：找到可能反轉的 C2，在 C3／C4 跟 HTF 方向做延續。

## 安裝

1. 購買後到 Whop → TTrades Indicator → 連結 TradingView username  
2. TradingView → Indicators → Personal → Invite-only → 載入指標  
3. 建議同步 claim Discord **TTFM Indicator** 角色  

詳見官方：[Full Guide](https://ttrades.com/ttrades-fractal-model-indicator-full-guide/)

## 與 YW Concept 的關係

| TTFM | YW Concept |
|------|------------|
| C2 掃流動性後反轉 | Sweep + 結構轉 |
| CISD | BOS／交貨確認 |
| HTF bias → LTF 執行 | 1H 定方向 → 5m/1m 入場 |
| SMT | RSI Divergence／SMT 類概念 |
| T-Spot / FVG | 可與 Stair、H Pattern、20EMA 合流 |

**用法定位**：TTFM 定「場地與節奏」；YW（H / Stair / 50/20）定「怎麼踩入與怎麼走」。

---

## MNQ 5min 專用 Template 清單

目標：圖面乾淨、种田風控、重點 C2–C4 + CISD + HTF1。

### 1 – GENERAL
- Use Universal Line/Text Color：✅  
- Monospace Font for Labels：✅  
- HTF Detection Mode：**自動**  
- Manual T-Spot Bias：**無**  
- Auto Bias (from HTF sweep)：**Disabled**（先手動定方向）

### 2 – HTF TIMEFRAMES
- Show HTF 1：✅  
- Auto-align HTF 1 to chart：✅  
- Max Candles (HTF 1)：**4**  
- Show HTF 2 / HTF 3：☐ 關（初學）

### 3 – CANDLE APPEARANCE
- Padding：20｜Space between candles：1｜Space between HTF groups：5  
- Show HTF Timeframe Label：✅  
- Show Remaining Time：✅  
- Show Price Labels：☐

### 4 – T-SPOT DETECTION（核心）
- Enable T-Spot Detection：✅  
- Detect T-Spots on：**HTF 1**  
- Show Only Latest T-Spot：✅  
- Show Only Latest Sweep：✅  
- Show T-Spot Close Line：✅  
- Box Transparency：**90**  
- Show Silver T-Spot：✅  
- Hide T-Spots When Price Trades Against：✅  
- Use Candle Body for Pivot Detection：✅  
- Show Live Developing CISD：✅

### 5 – T-SPOT LABELS
- Show C2 / C3 / C4 Labels：✅（Size = small）  
- Show Custom C2 Label：✅  
- HTF Mini-Display Labels：☐

### 6 – SWEEP & CONTINUATION OB
- Show HTF Candle Sweeps (mini-display)：✅  
- HTF1 Sweeps on LTF Chart：✅  
- HTF2 / HTF3 Sweeps：☐  
- Enable Continuation OB Detection：✅  
- Show Continuation OB Lines：✅  
- Show OB Label：☐

### 6B – BREAKER MODEL
- Enable Breaker Model：☐ **關**

### 7 – IMBALANCES & FVG
- Show Fair Value Gaps (FVG)：✅  
- PFVG / All PFVGs：☐  
- Show Volume Imbalance (VI)：可選

### 8 – CISD & FIB PROJECTIONS
- Show CISD Lines：✅  
- Show CISD Label：✅  
- Show All CISD Lines：☐  
- Show Fib Projections：✅  
- Trigger Fib On：**CISD**  
- Keep Both Fibs：✅  
- Fib Levels：`1,2,2.5` 或 `1,2,2.5,3,4`  
- Max Projection Sets：**1**

### 9 – LTF CHART OVERLAYS
- Period Start Lines：☐  
- Clean Mini-Display Helper Lines：✅  
- Midpoint / Trace Lines：☐

### 10 – DISPLAY & ALERTS
- Show Info Table：✅（Top Right）  
- Enable Time Filter：☐ 或只開 NY 09:30–12:00  
- Enable Alerts：✅  
- C2 CISD Live：✅  
- C2 / C3 CISD Confirmed：✅  
- Bullish / Bearish C2 Closed：✅  
- Long / Short Breaker：☐

### 11 – PDH/PDL & SESSIONS
- Show PDH / PDL：✅  
- Show Session High / Low：✅（至少 NY）  
- Position Size 計算：☐（种田用固定約 $100 風險）

### 存檔
TradingView → 指標旁模板圖示 → Save as **`MNQ 5m Clean`** → Favorite。

---

## 實戰節奏（簡）

1. HTF Bias 定好多空  
2. 等灰色有效 **C2** + **CISD**  
3. 在 **C3／C4** 跟方向  
4. 合流：Stair / H Pattern / 收破 20EMA / 50EMA 方向  
5. 風險約 $100、RR 1:1.5、日停利跟种田規則  

## 相關文件

- [02 - H-Pattern](02-H-Pattern.md)  
- [12 - Stair Pattern](12-Stair-Pattern.md)  
- [11 - 50/20](11-50-20.md)  
- [10 - 種田實務 Setup](10-Zhongtian-Practical-Setup.md)

**更新時間**：2026-08-12
