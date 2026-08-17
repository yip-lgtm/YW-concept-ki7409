# Candle Range Theory（CRT）— 4H Range

來源：社群 CRT 整理（衍生自 ICT Liquidity Sweep、Power of 3、Session H/L）+ 4H／5min 代理回測

> CRT **不是** ICT 官方原名概念，而是對 ICT 流動性與 PO3 的重新包裝。

## 核心定義

高時間框每一根 K，在低時間框就是一個 **Range**：

| 名稱 | 含義 |
|------|------|
| **CRT-High** | 該根 HTF K 的最高價 |
| **CRT-Low** | 該根 HTF K 的最低價 |

**假設**：價格先 **raid** 前一根 K 的 High 或 Low，再 **run** 去 range 另一邊。

- 掃 **CRT-Low** 且收返 → 預期往 **CRT-High**
- 掃 **CRT-High** 且收返 → 預期往 **CRT-Low**

本倉庫研究預設 **HTF = 4H**，執行 **5min**。

---

## Bullish CRT（做多）

1. 價格在 HTF **關鍵支撐**（高機率條件；回測代理可先省略）
2. 標定已收完 4H K 的 CRT-H / CRT-L
3. 下一 4H 時段內，5min **掃 CRT-L 並收返其上方**
4. **確認**：5min 收破掃低那根的 High（MSS 代理），或官方 MSS／CISD
5. 可選 retest 後做多
6. **SL**：掃低低點下（或 MSS-low）；**TP**：CRT-High 或下一流動性

## Bearish CRT（做空）

對稱：掃 CRT-H 收返下方 → 確認收破掃高那根 Low → SL 在掃高上 → TP 打 CRT-Low。

## 同 PO3

| PO3 | CRT |
|-----|-----|
| Accumulate | Range 內盤整 |
| Manipulate | 掃 CRT-H 或 CRT-L |
| Distribute | 跑向另一邊 |

高機率時段：ICT Killzone、Session Raid（亞／倫／紐）。

## 同 YW / TTFM

| CRT | TTFM | YW |
|-----|------|-----|
| 掃 CRT 邊 + 收返 | C2 | Sweep / H 第一段 |
| MSS 確認 | CISD / C3 | BOS |
| 跑向 CRT 對邊 | C4 | 延續目標 |
| 4H range | HTF candle | 1H／4H 定場地 |

---

## 回測代理規則（本研究）

1. 已收完 **4H** → CRT-H / CRT-L（**每根 4H 都用**，未強制 S/R）
2. 下一 4H 窗口內 5min 掃邊 + 收返
3. 其後 ≤12 根 5min 內，收破掃邊 K 的極端 → 確認入場
4. 風險上限 **$100**；TP = **CRT 對邊** 或 **固定 1.5R**
5. Session 過濾（可選）：
   - ALL：全日
   - NY：09:30–16:00 ET
   - NY AM：09:30–12:00 ET

**限制**：無關鍵 S/R 過濾；MSS 為簡化代理；未計成本；≠ 完整官方 CRT／ICT。

---

## 回測結果（約 60 日，5min 執行，Risk $100）

### 4H CRT — TP = CRT 對邊

| 標的 | Session | 筆數 | 勝率 | 總 PNL | 均每筆 | MaxDD |
|------|---------|------|------|--------|--------|-------|
| **MCL** | ALL | 158 | 39.2% | **+$939** | **+$5.94** | **-$357** |
| **MCL** | NY 9:30–16:00 | 29 | 34.5% | **+$182** | **+$6.28** | **-$229** |
| **MCL** | **NY AM 9:30–12:00** | **12** | **41.7%** | **+$154** | **+$12.83** | **-$119** |
| MYM | ALL | 168 | 35.7% | +$175 | +$1.04 | -$499 |
| MYM | NY | 44 | 36.4% | -$328 | -$7.44 | -$550 |
| MYM | NY AM | 22 | 40.9% | -$309 | -$14.05 | -$344 |
| MNQ | ALL | 168 | 28.6% | -$1,614 | -$9.60 | -$4,346 |
| MNQ | NY | 45 | 24.4% | -$1,375 | -$30.56 | -$2,122 |
| MNQ | NY AM | 25 | 28.0% | -$829 | -$33.16 | -$900 |
| MGC | ALL | 143 | 32.9% | -$2,021 | -$14.13 | -$2,268 |
| MGC | NY | 32 | 40.6% | -$519 | -$16.22 | -$619 |
| MGC | NY AM | 12 | 41.7% | -$288 | -$24.00 | -$262 |

### 簡要結論

| 標的 | 建議 |
|------|------|
| **MCL** | 4H CRT 樣本內最好；全日或 **NY AM** 均可參考；MaxDD 較細 |
| MNQ | 無 S/R 的 4H CRT 代理偏弱；需合流 TTFM Bias／YW 形態 |
| MYM / MGC | 期望偏弱或接近 0 |

原油較適合 **TP 打 CRT 對邊**；指數需更嚴過濾。

---

## 實盤 Checklist（4H CRT）

```
□ 4H 在關鍵支撐／阻力收線 → 標 CRT-H / CRT-L
□ 5min 掃一邊並收返
□ MSS / CISD / C3 確認（可選 retest）
□ SL 在掃邊外；TP = CRT 對邊或 1.5R
□ 優先 Killzone（如 NY 09:30–12:00）
□ 風險約 $100；种田日停利紀律
```

## 相關文件

- [13 - TTFM Fractal Model](13-TTFM-Fractal-Model.md)
- [12 - Stair Pattern](12-Stair-Pattern.md)
- [02 - H-Pattern](02-H-Pattern.md)
- [11 - 50/20](11-50-20.md)

**更新時間**：2026-08-17
