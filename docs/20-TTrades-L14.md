# 20. TTrades L14 — Candle 3 Closure

來源：第三方筆記整理 TTrades 免費課程 L14，非原文複製、非官網  
https://notes.powerofdeal.com/courses/ttrades-fractal-model/lesson-14/  
原片：https://www.youtube.com/watch?v=MsuEQQl7L6s  
關聯：[17-TTrades-Model.md](17-TTrades-Model.md)、[18-TTrades-L12.md](18-TTrades-L12.md)、[19-TTrades-L13.md](19-TTrades-L13.md)  
更新：2026-10-09

L14 是第二條路徑：到了 POI 但沒有掃流動性，不准當反轉。等 Candle 3 收破 C2 實體，再做 Candle 4。

## 1. 兩種收盤，兩種 closure

| 類型 | 規則 | 之後做邊根 |
|------|------|------------|
| 延續收盤 | 掃過前極值，收在極值外面 | 不是反轉，不入這套 |
| C2 closure | C2 掃出 C1 極值，收回 C1 區間內 | 反轉已在 C2 完成，期待 C3、C4 |
| C3 closure | 沒有掃極值，但 C3 收破 C2 實體 | 確認延後一根，只期待 C4 |

- 看漲 C3 closure：沒有掃 C1 低，C3 收在 C2 實體上方。
- 看跌 C3 closure：沒有掃 C1 高，C3 收在 C2 實體下方。

兩者都沒有，這個 swing point 不在 model 內，不做。POI 上沒有 C2 closure 時，不准硬接。等下一根表態：要麼 C3 closure，要麼繼續延續。

## 2. EQ

C3 closure 之後，用 Candle 3 整根區間的 0.5 判斷 C4 回調。回調守住 EQ（多頭在上半）先容易擴張。用整根區間，不用影線的一半。

## 3. 例子

EURUSD 日線：回測 FVG 時掃低收回，是 C2 closure。另一處回測同類 POI，沒有掃低。兩個等法是再掃出前低成 C2，或等 C3 closure。次日收破 C2 實體，成 C3 closure，之後上漲。

NQ 4 小時：掃過 swing low，但沒有收回前一根之內，所以不是 C2。下一根 4 小時收破 C2 實體，才確認 C3 closure。標出 C3 整段，等價格在 EQ 之上回調再上。其後尊重 EQ，並收破前高。

進場降到 15 分鐘：等 CISD 同 protected swing。進場區是新蠟燭開盤，或 4 小時 C3 區間上半。停損在 protected swing 外，目標 2R。之後整固如果兩種 closure 都沒有，即使主觀看漲，model 也不給訊號。

## 4. 過濾

批量標 swing 之後逐個刪：

- 沒有收破實體，也沒有收回極值內：刪。
- 機械上成立，但沒碰到 POI（差一點未到 FVG）：刪。
- 成立，但前高太近，或已到 equal lows／failure swing 目標：不做。

第三條屬盤感。先只用 closure 定義加 POI 統計，再加情境過濾。

## 5. 同現有 pipeline 的缺口

無掃流動性就開，L14 否決。無 C2 closure 只能等 C3 收破 C2 實體，而且只做 C4，不能在 C3 收盤當下當 C2 延續單。C4 還要守 C3 整段 EQ，再加低周期 CISD。兩種 closure 都沒有就 skip，不准用主觀偏向補。
