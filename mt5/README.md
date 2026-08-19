# MT5 Experts（YW / Kell）

放到 `MQL5/Experts/` 後編譯。建議 5min；種田預設風險 $100、RR 1.5、日停利 $200。

| 檔案 | Setup | Magic |
|------|--------|-------|
| [YW_50_20_Pullback.mq5](YW_50_20_Pullback.mq5) | EMA20×SMA50 交叉後回踩 | 5020 |
| [Kell_ReversalExtension.mq5](Kell_ReversalExtension.mq5) | 遠離 10EMA + 反轉 K（可要求靠近 EMA50） | 1511 |
| [Kell_WedgePopDrop.mq5](Kell_WedgePopDrop.mq5) | 10/20 收窄後重奪／跌穿 | 1512 |
| [Kell_EMA_Crossback.mq5](Kell_EMA_Crossback.mq5) | 重奪 10/20 後第一次回踩 | 1513 |
| [Kell_BaseNBreak.mq5](Kell_BaseNBreak.mq5) | 沿均線築底後突破 | 1514 |
| [Kell_Exhaustion.mq5](Kell_Exhaustion.mq5) | 第 2 次延伸：平倉或反向 | 1515 |

## 使用注意
- `InpLotSize=0` 時按 `InpRiskMoney` 自動算倉。
- MNQ 可先用 `InpSL_Points=50`；MGC／MCL 要按點值改。
- Exhaustion 的 `InpManageMagic` 可填其他 Kell EA 的 Magic，用來只平趨勢單、自己再開 fade。
- 代理規則，唔等於書中人工讀圖；先 Strategy Tester 再實盤。

對應說明：[docs/15-Oliver-Kell-Cycle.md](../docs/15-Oliver-Kell-Cycle.md)
