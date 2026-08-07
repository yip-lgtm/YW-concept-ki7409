# YW Concept Trading Research

本倉庫整理 **YW Trader HK** 在 Discord `#📖｜ywconcept百科全書` 頻道分享的原始概念、圖示與實戰心得。

## 文件目錄

### 核心定義
- [01 - YW Concept 總覽](docs/01-YW-Concept-Overview.md)
- [02 - H-Pattern 官方定義](docs/02-H-Pattern.md)（3min/5min，4 大特點）
- [03 - 3 Pushes 官方定義](docs/03-Three-Pushes.md)（5min/15min）
- [04 - 兩陽夾一陰](docs/04-Two-Yang-One-Yin.md)（15min + 統計勝率分析）
- [08 - RSI Divergence](docs/08-RSI-Divergence.md)（1/3/5min）
- [09 - 輔助技巧](docs/09-Auxiliary-Tips.md)（ES 對照、慢牛快熊）
- [11 - 50/20（20EMA / 50SMA 刮均線）](docs/11-50-20.md) ← 含 60 日回測

### 圖示與實戰
- [05 - 圖示描述與視覺參考](docs/05-Image-Descriptions.md)
- [06 - 實戰例子整理](docs/06-Practical-Examples.md)

### 種田流
- [07 - 種田流完整整理](docs/07-Zhongtian-Notes.md)
- [10 - 種田策略實務 Setup](docs/10-Zhongtian-Practical-Setup.md)

### MT5 程式
- [mt5/YW_50_20_Pullback.mq5](mt5/YW_50_20_Pullback.mq5) — 50/20 + 回踩 + RR 1:1.5 Expert Advisor

### 報告與圖表
- `華爾街農夫_種田流交易秘笈.pdf` / `.docx`
- 本地 PNL 圖：`PNL_MGC_50_20_pullback.png`、`PNL_MNQ_50_20_pullback.png`

## 50/20 回測摘要（近 60 日 5min）

| 標的 | 勝率 | 總 PNL | 均每筆 |
|------|------|--------|--------|
| MGC（SL $10 / TP $15） | 43.0% | +$2,004 | +$6.7 |
| MNQ（SL 50點 / TP 75點） | 42.7% | +$1,850 | +$6.6 |

詳見 [docs/11-50-20.md](docs/11-50-20.md)

## 來源說明

全部核心定義直接來自 YW 於 2026 年 4 月起在 Discord 的原始訊息與圖示，種田部分整理自「种田.pdf」。

僅供學習研究，不構成任何投資建議。交易有風險。

最後更新：2026-08-07
