# TTrades Fractal — XAUUSD EA (MQL5)

`automation/mql5/Experts/TTradesFractal_XAUUSD.mq5` — TTrades ICT Fractal Model ported 1:1 from
`automation/scripts/ttrades_btc.py` (repo `repo-yw`). MetaTrader 5, build 2000+.

## 規則鏈（全部用「已收線」bar，冇 repaint）

| # | 條件 | 來源 |
|---|---|---|
| 1 | H4 **C2 closure**（C2 掃過 C1 極值後收回 C1 範圍內）→ swing level + C2 wick EQ | `detect_c2_closure()` |
| 1b | 失敗時用 H4 **C3 closure** fallback（C3 實體 ≥ 55% range） | `detect_c3_closure()` |
| 2 | M15 **CISD**：收盤價突破對向連續序列嘅極值開盤價（8 bar 視窗） | `check_cisd()` |
| 3 | **EQ 守規**：M15 收盤價要喺 EQ 正確一邊 | `check_eq_respect()` |
| 4 | **D1 趨勢**：只做順 D1（close vs EMA50/EMA20 都要同向） | `check_d1_trend()` |
| 5 | SL = swing ± 0.15×ATR(H1)；TP1/TP2/TP3 = 1.0R / 1.6R / 2.6R | `calculate_trade_levels()` |

**同 Python 版嘅唯一分別（刻意）**：Python 用緊 forming bar（會 repaint），
EA 一律用 shift ≥ 1 嘅已收線 bar —— 即係「等收線」。

## 風控（按你要求）

- 手數：**0.01 – 0.05**，先按風險 sizing（單筆 $50），再夾落呢個區間
- **每日 SL $100**：當日 equity 對比日初 balance 蝕到 −$100 → 自動全平 + 鎖死當日唔再入場
- 每日最多 1 單（`InpMaxTradesPerDay`）
- TP1 平 50% + SL 移保本，TP2 再平 50%，TP3 掛單全平

## 安裝

1. MT5 → `File → Open Data Folder → MQL5/Experts/`，把 `.mq5` 放落去
2. MetaEditor 按 F7 編譯（0 errors 先好）
3. Navigator → Expert Advisors → 拖落 XAUUSD chart，開 `Allow Algo Trading`
4. 工具 → 選項 → Expert Advisors → 勾 **Allow live trading**（有 VPS 先好）

## 必查：broker 嘅 XAUUSD 合約規格

EA 靠 `SYMBOL_TRADE_TICK_VALUE` / `SYMBOL_TRADE_TICK_SIZE` 計「每 $1 價位 = 幾多錢」，
唔 hardcode。啟動時個 Experts log 會印：

```
[TF-Fractal] init OK. symbol=XAUUSD tick_value=1.0 tick_size=0.01 minlot=0.01 step=0.01
```

一般 broker：tick_value=1.0 / tick_size=0.01 → 1 手 = 100 oz → **0.01 手 = 1 oz，$1 價位 = $1**。
如果你見到 `tick_value=100`（即 1 手 = 10000 盎司，罕見）→ 每 $1 價位 = $100，風險 sizing 會自動縮手，
唔會錯落。**唔好信網上抄落嚟嘅「XAUUSD 1 手 = 100 盎司」，一定以你 broker 為準。**

## 重要參數

| 參數 | 預設 | 說明 |
|---|---|---|
| `InpSymbol` | XAUUSD | 唔存在會自動搵含 XAU / GOLD 嘅品種 |
| `InpMinLot` / `InpMaxLot` | 0.01 / 0.05 | 手數區間 |
| `InpRiskPerTradeUSD` | 50 | 單筆風險上限（sizing 用，實際受手數區間夾住） |
| `InpDailySLUSD` | 100 | 每日虧損上限 → 全平 + 鎖日 |
| `InpMaxTradesPerDay` | 1 | 每日最多開倉 |
| `InpMaxSpreadPoints` | 60 | gold 0.01 tick = $0.60 點差上限 |
| `InpDayStartHour` | 0 | 交易日開始（server time） |
| `InpCloseAtDayEnd` | false | 收市前 5 分鐘自動全平 |
| `InpUseTrueATR` | false | false = range-ATR（同 Python backtest 口徑一致） |
| `InpTp1R/Tp2R/Tp3R` | 1.0/1.6/2.6 | TP 倍數 |

## 上真錢之前 —— 實測結果（唔係我估，係 repo 真實資料跑出嚟）

用 repo 嘅真實黃金資料 `automation/data/deep_history/MGCF/`（15m 4,526 根、2026-08-13 → 2026-10-22），
**完全照 EA 嘅邏輯**（只用已收線 H4 bar、correct CISD、EQ 守規、D1 趨勢、TP1 50% + 移保本、TP2、TP3）
逐 bar 模擬：

| 變體 | n | 交易頻率 | WR | avgR | totalR | PF(R) | 最大回撤 |
|---|--:|--:|--:|--:|--:|--:|--:|
| **EA 版（correct CISD）** | 55 | ~23.6 / 30日 | 45.5% | **−0.083** | **−4.56R** | **0.85** | −15.5R |
| REPO 版（buggy CISD） | 45 | ~19.3 / 30日 | 53.3% | +0.123 | +5.53R | 1.26 | −7.9R |

**結論：呢個模型喺黃金上面未證明有 edge。** n=45-55、PF 1.26 喺統計上唔顯著
（PF 1.26 嘅 95% CI 大概 0.9–1.8），correct CISD 版本甚至係負數。

所以正確做法：
1. 先用 MT5 Strategy Tester（"Every tick based on real ticks"、XAUUSD、2024-01 → 2026-10）再跑多次
2. 再上 demo 跑夠 3 個月
3. 先上實盤，而且用返你要求嘅 **0.01–0.05 手 + 每日 SL $100** —— 就算模型廢咗，
   爆倉金額都細過一餐飯

## ⚠️ 發現 repo `ttrades_btc.py` 有 CISD 窗口 bug（影響 arena 成績）

`check_cisd()` 砌連續序列用 `ltf_df.tail(8)`（最新 8 根），但攞 "opposing open" 時寫咗
`ltf_df['Open'].iloc[i]` —— `i` 係 tail 視窗內嘅索引，`.iloc[]` 落到 **frame 最舊嗰幾根**。
即係話：CISD 攞嚟比較嘅「對向序列開盤價」，係**成個資料窗最舊嘅 8 根 bar**，唔係當前序列。

實測（真實 MGC 15m，8,932 次評估）：

- **48.2% 嘅情況，buggy 版同 correct 版結論相反**
- "confirmed" 率：buggy 49.1% vs correct 24.2% —— repo 個閘門闊咗一倍，而且量錯咗嘢
- live 環境 M15 係 `period="7d"`（約 672 根），即係拿 **7 日前** 嘅開盤價嚟比現價
- `automation/scripts/arena.py:377` 直接用 `base.check_cisd(m15, direction)`，
  所以 **arena 入面 TTrades-Fractal 嘅交易（包括我嗰單 MGC 空）都係用咗呢個壞閘門**

**我冇改 repo 個檔**（會影響 live + arena，唔係我可以自己決定）。
本 EA 用**正確**版本（tail 窗口）。如果你想修 repo，建議加個 const switch：
`CISD_USE_TAIL_WINDOW = True`，先喺 Strategy Tester 對過數再上。

## 已知限制

- 冇 news filter（新聞時段會出現假 CISD）→ 建議用 `InpMaxSpreadPoints` 擋大部分
- H4 closure + M15 CISD 係慢模型，實際可能幾日先有一單 —— 唔好因為冇單就手改規則
- 淨係 `InpDailySLAllSymbols=true` 時，先會連其它品種嘅盈虧一齊計入每日 SL
