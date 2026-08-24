# YW Concept Trading Research

本倉庫整理 **YW Trader HK** 在 Discord `#📖｜ywconcept百科全書` 頻道分享的原始概念，並延伸 TTFM、CRT、Kell Cycle、YW Indicator 等合流研究。

## 文件目錄

### 核心定義
- [01 - YW Concept 總覽](docs/01-YW-Concept-Overview.md)
- [02 - H-Pattern 官方定義](docs/02-H-Pattern.md)（3min/5min，4 大特點）
- [03 - 3 Pushes 官方定義](docs/03-Three-Pushes.md)（5min/15min）
- [04 - 兩陽夾一陰](docs/04-Two-Yang-One-Yin.md)（15min + 統計勝率分析）
- [08 - RSI Divergence](docs/08-RSI-Divergence.md)（1/3/5min）
- [09 - 輔助技巧](docs/09-Auxiliary-Tips.md)（ES 對照、慢牛快熊）
- [11 - 50/20（20EMA / 50SMA 刮均線）](docs/11-50-20.md)
- [12 - Stair Pattern](docs/12-Stair-Pattern.md)
- [13 - TTFM Fractal Model](docs/13-TTFM-Fractal-Model.md)
- [14 - CRT Candle Range Theory](docs/14-CRT-Candle-Range-Theory.md)
- [15 - Oliver Kell Cycle of Price Action](docs/15-Oliver-Kell-Cycle.md)
- [16 - YW Indicator（TradingView 摸頂底）](docs/16-YW-Indicator.md)

### 圖示與實戰
- [05 - 圖示描述與視覺參考](docs/05-Image-Descriptions.md)
- [06 - 實戰例子整理](docs/06-Practical-Examples.md)

### 種田流
- [07 - 種田流完整整理](docs/07-Zhongtian-Notes.md)
- [10 - 種田策略實務 Setup](docs/10-Zhongtian-Practical-Setup.md)

### MT5 程式
- [mt5/](mt5/) — 50/20 Pullback + Kell Cycle 五支 EA

### 報告與圖表
- `華爾街農夫_種田流交易秘笈.pdf` / `.docx`

## 來源說明

YW 核心定義來自 Discord 原始訊息。YW Indicator 說明整理自《YW指標使用手冊 v6》。其餘為公開教學摘要與代理回測。

僅供學習研究，不構成投資建議。交易有風險。

最後更新：2026-08-20

---

## 🚀 安裝與設定

**新用戶請先睇 [INSTALL.md](INSTALL.md)** — 涵蓋：
- 環境設定（Python 3.11+、GHA secrets）
- 3 個 workflows 自動跑 setup
- API key 設定（Massive/Telegram/MiniMax-M3/AI-Trader）
- Troubleshooting 常見問題
- 20 日 backtest 結果預期

## 🤖 自動化 Pipeline

呢個 repo 而家跑緊 3 個 GHA workflow（每個都需要 secrets）：

1. **`yw-daily.yml`** — 每日 21:00 HKT LLM-graded reminder（4-Chart Standard）
2. **`yw-publish-signal.yml`** — 21:30 HKT 自動 publish 頭位信號去 AI-Trader
3. **`ocs-btc-5m.yml`** — 24/7 每 5 分鐘 OCS BTC 5m 信號（基於 OCS-Style AI Trader Pine 移植）

詳情睇 [docs/OCS-SETUP.md](docs/OCS-SETUP.md)
