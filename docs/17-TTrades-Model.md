# 17. TTrades Model（OSOK + Fractal）

來源：TTrades / ICT Fractal Model Handbook（課程筆記整理，非原文複製）  
關聯：[13-TTFM-Fractal-Model.md](13-TTFM-Fractal-Model.md)、YW H-Pattern / Stair  
更新：2026-09-01

兩套用法同一骨架：

| | OSOK | Fractal |
|--|------|---------|
| 定位 | 一日一槍，跟日線 + 週 profile | 任意週期可嵌套，偏 scalp |
| 骨架 | Daily swing → Weekly profile → H1 CISD → Daily profile → 15m/5m 進 |
| 骨架 | HTF C1–C4 → LTF CISD + 投影 → 喺擴張燭入 |

---

## 1. 燭編號（所有 setup 共用）

| 燭 | 定義 |
|----|------|
| **C1** | 轉折前一根 |
| **C2** | 做出高低點嗰根 |
| **C3** | 轉折後第一根 |
| **C4** | 跟住 C3 嘅延續 |

市場要轉，必須先形成 swing high/low。機會主要喺 **C3 / C4**。

---

## 2. 兩種 swing 收法

### C2 Closure（理想）

- **多**：C2 掃 C1 low，收返上 C1 low 之內  
- **空**：C2 掃 C1 high，收返落 C1 high 之內  
- 大影線更理想；C3 沿 C2 影線半倉（EQ）擴張；C4 再沿 C3 range EQ 延續  
- 進場：C3 開盤；SL = C2 swing

### C3 Closure（條件）

- C2 **未**收返入 C1 range → 唔參與 C2，等 C3  
- C3 強勢陽/陰收盤先確認 swing  
- 之後只喺 **C4** 做延續  
- 進場：C4；SL = 轉折點

**理想形態**：C2 大影收回 C1 → C3 離影線強收（確認 opposing close）→ C4 守 C3 EQ 去目標。

專案舊回測：`EMA50+C3`、`C4+EMA50` 係呢套嘅簡化機械版。

---

## 3. 基礎零件

### Opposing candles

擴張時預期尊重反向收盤燭。

- 一連串陰：用 **最高那枝陰的開盤**  
- 一連串陽：用 **最低那枝陽的開盤**  
- 大系列裏面嘅細 opposing 忽略  
- 必須叠 **POI**（高低、FVG、另一組 opposing），否則唔用

### FVG（手冊只用兩件事）

1. 定義 order block  
2. 作為 swing 形成嘅 POI  

唔當「見洞就入」。

### Equilibrium

- **打入 range**：EQ 係目標  
- **打出 range**：EQ 係 POI  
- C2 影線半倉：C3 要守住先繼續  
- C3 range EQ：C4 框架

### 投影（Fib 設定）

顯示：`1, 0, -1, -2, -2.5, -4, -4.5`

- **Manipulation**：多 = 低點拉到做出最高嗰個前高；空相反  
- **Failure swing**：manipulation 腳過長、C3/C4 到唔到邏輯目標時改錨  
  - 多：最低低 → 做出 failure 嘅高  
  - 空：最高高 → 做出 failure 嘅低  
- 常見第一目標 **-2**（C3），延伸 **-4**（C4）

---

## 4. CISD 配對

Swing 用 **低一級 CISD** 確認（多數喺 C2 內完成，亦可拖到 C3）。

| Swing | CISD |
|-------|------|
| W1 | H4 |
| D1 | H1 |
| H4 | M15 |
| H1 | M5 |
| M30 | M3 |
| M15 | M1 |

CISD 實務：空 = 收破「一連串陽裏面最低陽嘅開盤」；多相反。確認後先錨 manipulation 投影。

---

## 5. OSOK 流程（一日一槍）

只喺以下齊先考慮進場：

1. **日線** 有 C2 或 C3 closure，且喺 POI  
2. 對上四種 **週 profile 之一**  
3. **H1 CISD** 確認 + 投影  
4. **日內 profile**（倫敦反轉 / 紐約反轉）對齊  
5. 15m / 5m / 更細：opposing 或再做一層 C2

### 日曆（OSOK）

- 只睇紅摺：CPI、NFP、FOMC Press；中等：Core PCE、PPI  
- 高衝擊 **前一日唔開**  
- 中衝擊 **前一個 session 唔開**  
- **唔持倉過** 高/中衝擊  
- **星期一全避**（平均波幅最細、無重要新聞、週 profile 未成形）

指數／加密：日曆焦點 USD。

### 週 Profile（四種）

| Profile | 條件 | 預期 |
|---------|------|------|
| Classic Expansion（逆勢週五） | 一/二已反向並擴到四 | 五回週 range 20–50%；唯一可喺預期 swing 嘅 **C2** 做 |
| Midweek Reversal | 一、二相對週開盤盤整或反向 | 三 = C2 反轉，四／五擴張 |
| Consolidation Reversal | 一至三盤整 | 四反轉，五擴張 |
| Thursday Counter | 一至三同向擴張 | 四反轉，五擴張 |

唔符就收工，等下週。

### 日 Profile（兩個）

| | 做法 |
|--|------|
| **London Reversal** | 倫敦已反轉 → 紐約只做延續 |
| **New York Reversal** | 倫敦盤整或反向抽 → 等紐約 CISD 反轉 |
| 無效 | 倫敦已單邊擴張 → **唔做紐約** |

空頭紐約反轉常見目標：倫敦低、亞洲低、投影。

### OSOK 進場

- CISD 確認 opposing 後：下一根市價，或限價回 opposing  
- C2 closure：C3 開；SL = C2 swing  
- 種田：$247K 仍 0.25%、日停 2%

---

## 6. Fractal 流程（任意週期）

三件套：

1. HTF swing（C2 或 C3）  
2. LTF CISD + 投影（喺 HTF C2 內）  
3. 喺 **擴張燭** 入碼  
   - C2 closure → 喺 C3、C4 搵 LTF 入場  
   - C3 closure → 只喺 C4 入

檢查清單：

- [ ] HTF C2 收回 C1 或已等 C3 強收  
- [ ] LTF 已 CISD 收破 opposing open  
- [ ] 畫咗 C2 影線 EQ，價仍尊重  
- [ ] 投影 -2 / -4  
- [ ] 入場在 C3/C4 內的 opposing 或細一級 C2  
- [ ] C3 收妥後畫 C3 EQ，C4 要守

YW 實盤配對建議：

| 偏向 | HTF | CISD / 執行 |
|------|-----|-------------|
| 种田 | H1 | M5 |
| 稍慢 | H4 | M15 |
| 日內 OSOK | D1 | H1 確認 + M15 入 |

---

## 7. 同 YW 點叠

| YW | TTrades |
|----|---------|
| H-Pattern / Stair 大陰 + 上影 + 穿底 | 空頭 C2 掃高收回 + C3 離場；穿底 ≈ 細 TF CISD |
| 1H 20EMA 下只空 | 日線／H1 swing 方向 |
| FVG 未補 | 只作 POI，唔單獨進 |
| 50/20 回踩 | 只可當 C3/C4 擴張中的回抽，要有 CISD |
| 兩陽夾一陰 | 近似 opposing 系列，仍要 POI |

**唔好**：5m 無 HTF swing 就當 Fractal；Conf 分代替 CISD。

---

## 8. $247K / 种田約束

- 一主意、一方向；OSOK 精神 = 一日最多一組  
- 新聞規則優先過形態  
- 自動 EA 難完整表達週 profile + 日 profile → **人手確認**，EA 只限虧  
- 舊 C3/C4 機械回測（MCL/MBT/M6A/MYM/MNQ）作參考，BTC 近月自動單未證正期望

---

## 9. 一手清單（開盤前）

1. 今日係咪星期一／紅摺前一日？是 → 唔做  
2. 日線有無 C2/C3 + POI？無 → 唔做  
3. 週 profile 屬邊種？對唔上 → 唔做  
4. H1 有無 CISD？無 → 等  
5. 倫敦已擴？是 → 棄紐約  
6. 先投影再等 LTF opposing / C2  
7. SL = swing；TP1 = -2 或流動性；到站减倉
