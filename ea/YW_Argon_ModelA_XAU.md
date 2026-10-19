# YW Argon Model A — Fxify / Gold EA

`YW_Argon_ModelA_XAU.mq5`

對齊 `docs/21-Argon-Gold-SOP.md` 模型 A：

**流動性掃蕩 + Pin Bar / 吞沒**

## 預設

| 項目 | 數值 |
|------|------|
| 單筆風險 | $50 |
| 止損上限 | ≤ $5.0（過寬自動放棄） |
| RR | 1.5 |
| 保本 | 1R 後移 SL 到進場價 |
| 訊號 | M5 收盤確認 |
| 掃蕩參考 | M15 近 20 根最低/最高 |
| 過濾 | H1 EMA20 方向 |
| 每日最多 | 4 單 |

可在 `InpPreset` 切換 Fxify One Phase / Two Phase 等風控。

## 進場邏輯

1. H1 收盤在 EMA20 上只多、下只空
2. M5 收盤 K 線低點刺穿 M15 近期低點（流動性掃蕩）
3. 同一根 K 線是 Pin Bar（下影 ≥ 66% 全長且收陽）或 Bullish Engulfing
4. 收盤收回掃蕩水平之上
5. 止損 = 掃蕩最低點 − buffer；若距離 > $5 則跳過
6. 口數按 tick value 計算，風險固定 $50

空頭反向。

## 注意

- 只在新 K 收盤後判斷，非 HFT。
- Instant Funding 多數禁 EA，用考核帳戶。
- 先用 Strategy Tester 跑 XAUUSD M5，本金 $10,000。
- 黃金合約規格因券商而異，掛之前確認點值。

**更新**：2026-10-19
