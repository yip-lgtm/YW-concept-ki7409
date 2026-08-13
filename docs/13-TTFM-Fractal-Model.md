# TTFM Fractal Model Indicator（TTrades）

來源：TTrades Fractal Model Indicator – Full Guide（2026-05-09）+ 實盤設定整理 + C3/C4 代理回測

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

## C3 / C4 入場規則（研究用代理）

> 以下為 **5min 同框 C2 代理** 的可回測規則，**不是**官方 HTF 蠟燭模型的完整實現。實盤仍以指標 HTF C2 + CISD 為準。

### C2 代理定義
1. 掃過近 3 根高點（空）或低點（多）
2. 收盤收返該區間內
3. 掃側影線 ≥ 整根 K 的 25%
4. 收盤偏向反轉方向（空：偏下半／陰線；多：偏上半／陽線）

### 規則：C3 入場
1. C2 出現
2. （可選）**EMA50 方向過濾**：空＝收盤低於 EMA50；多＝高於 EMA50
3. **入場**：C2 之後第 **1** 根（C3）收盤
4. 止損：C2 高／低外側，風險上限約 **$100**
5. 止盈：1.5R｜最大持倉約 48 根 5min

### 規則：C4 + EMA50
1. C2 出現
2. **EMA50 方向過濾**（同上）
3. **入場**：C2 之後第 **2** 根（C4）收盤
4. 止損／止盈同上

### 規則：C4 + EMA50 + C3 延續
在 C4+EMA50 之上再加：
- **C3 必須延續 C2 方向** 後，才於 C4 收盤入場

### 實盤對應（官方指標）
| 代理規則 | 官方 TTFM |
|----------|-----------|
| EMA50 方向 | HTF Bias / Auto Bias |
| C3 入場 | C3 確認階段 |
| C3 延續後 C4 | CISD 確認後 expansion |
| C4 收盤入 | C4 expansion 階段 |

---

## 回測結果（約 60 日 5min，Risk $100，RR 1:1.5）

### C3 入場總表

| 標的 | 過濾 | 筆數 | 勝率 | 總 PNL | 均每筆 | MaxDD | 最近50筆 |
|------|------|------|------|--------|--------|-------|----------|
| **MNQ** | 無 | 1348 | 39.7% | -$2,348 | -$1.74 | -$5,798 | 34% |
| **MNQ** | **EMA50** | **517** | **44.1%** | **+$2,842** | **+$5.50** | **-$2,559** | **56%** |
| **MCL** | 無 | 1312 | 46.7% | +$334 | +$0.25 | -$4,403 | 38% |
| **MCL** | **EMA50** | **509** | **47.9%** | **+$923** | **+$1.81** | **-$2,826** | 50% |
| **MBT** | **無** | **1525** | **43.3%** | **+$3,856** | **+$2.53** | -$3,301 | 38% |
| MBT | EMA50 | 614 | 40.2% | -$1,462 | -$2.38 | -$3,233 | 40% |
| M6A | 無 | 942 | 49.6% | +$61 | +$0.06 | -$301 | 52% |
| M6A | EMA50 | 367 | 49.0% | -$30 | -$0.08 | -$254 | 48% |
| MYM | 無 | 1297 | 45.4% | -$2,605 | -$2.01 | -$3,500 | 50% |
| MYM | EMA50 | 482 | 45.0% | -$1,986 | -$4.12 | -$3,915 | 56% |

### C4 入場總表（摘錄）

| 標的 | 過濾 | 筆數 | 勝率 | 總 PNL | 均每筆 | MaxDD |
|------|------|------|------|--------|--------|-------|
| **MNQ** | **C4+EMA50** | **525** | **43.8%** | **+$3,093** | **+$5.89** | **-$2,069** |
| MNQ | EMA50+C3延續 | 253 | 44.3% | +$1,494 | +$5.91 | -$2,487 |
| **MCL** | **C4+EMA50** | **506** | **47.4%** | **+$2,207** | **+$4.36** | -$2,661 |
| MCL | EMA50+C3延續 | 244 | 46.3% | +$488 | +$2.00 | -$1,671 |
| MGC | EMA50+C3延續 | 256 | 42.2% | +$1,068 | +$4.17 | -$1,647 |
| MBT | C4+EMA50 | 617 | 39.1% | -$3,130 | -$5.07 | -$4,363 |
| M6A | C4+EMA50 | 361 | 48.8% | +$46 | +$0.13 | -$248 |
| MYM | C4+EMA50 | 478 | 41.0% | -$3,226 | -$6.75 | -$4,909 |

**數據代理**：MCL←CL=F、MBT←BTC-USD、M6A←6A=F、MYM←YM=F、MNQ←NQ=F。點值按微型合約近似。

### C3 vs C4（有 EMA50 時）

| 標的 | C3 入場 | C4 入場 |
|------|---------|---------|
| **MNQ** | WR 44.1% / **+$2,842** | WR 43.8% / **+$3,093** |
| **MCL** | WR 47.9% / +$923 | WR 47.4% / **+$2,207** |
| MBT | -$1,462 | -$3,130 |
| MYM | -$1,986 | -$3,226 |

### 簡要結論

| 標的 | 較佳代理規則 | 備註 |
|------|--------------|------|
| **MNQ** | **C3 或 C4 + EMA50** | 兩者接近；空頭較強 |
| **MCL** | **C4 + EMA50** | C3 亦可但總盈較少 |
| **MBT** | **C3、無 EMA50** | 加 EMA50 變差（樣本內） |
| **MGC** | **EMA50 + C3 延續 → C4** | 要更嚴過濾 |
| M6A | 勝率高 | 期望接近 0 |
| MYM | — | 本代理下偏弱 |

**限制**：同框 C2 代理 ≠ 官方 HTF C2 + LTF CISD；未計滑價與手續費；僅供研究。

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

研究用代理可參考：**MNQ → C3/C4+EMA50**；**MCL → C4+EMA50**；**MBT → C3 無過濾（樣本內）**。

## 相關文件

- [02 - H-Pattern](02-H-Pattern.md)  
- [12 - Stair Pattern](12-Stair-Pattern.md)  
- [11 - 50/20](11-50-20.md)  
- [10 - 種田實務 Setup](10-Zhongtian-Practical-Setup.md)

**更新時間**：2026-08-13
