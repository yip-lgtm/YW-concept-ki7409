# YW 50/20 — Fxify $10K Gold EA

`YW_5020_FXIFY_XAU.mq5`

## 預設（Fxify One Phase $10,000）

| 規則 | 數值 |
|------|------|
| 目標 | 10% = $1,000，達標停手 |
| 日損 | 3% = $300，權益觸及即停 |
| 最大回撤 | 6% trailing（Two Phase Pro 改用 static） |
| 單筆風險 | $50 |
| 每日最多 | 4 單 |
| 圖 | M15 訊號，H1 EMA20 方向過濾 |
| RR | 1.5，1R 推保本 |

Two Phase Standard / Pro、Lightning 可在 `InpPreset` 切換。

## 進場（對齊 docs/11-50-20.md）

1. 20 EMA 穿 50 SMA（金叉多、死叉空）
2. 之後最多 16 根內回踩 20 EMA（ATR 帶內觸及）
3. 收盤仍在均線正確一側，且是順向燭
4. H1 收盤在 EMA20 上只多、下只空
5. 口數 = 風險金額 ÷ 停損距離，用合約 tick value，唔係固定手數

## 注意

- Instant Funding 多數禁 EA。用考核帳戶。
- 禁 HFT。這支是收盤後新 K 才判斷。
- 掛之前打開 XAUUSD 規格：合約大小、最小手、點值。常見 1.00 lot = 100 oz，$1 波動約 $100。
- One Phase 的 trailing 對黃金急回不利。想地板固定，用 Two Phase Pro（static 8%）。
- 先用 Strategy Tester 跑 M15，本金設 $10,000。
