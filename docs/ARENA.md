# 22 - Arena：15 個策略 agent 交易競賽

## 這是什麼

書入面每一個策略都有一個 agent，各有各的虛擬帳戶、各有的倉、各有的 level。
15 個 agent 喺同一塊板上面對打：**全標的、可以同時持多過一個倉、日目標 +1 level**。
贏嗰個唔係因為策略好，而係因為嗰一日嘅帳面靚。

15 個名單（同一個係 live 治理階梯 `strategy_levels.json` 入面嗰批，minus B1-3in1）：

OCS-BTC-5m · H-Pattern · 3-Pushes · Two-Yang · RSI-Div · 50-20-Pullback ·
Stair · CRT · Kell-Cycle · B1 · TTrades-Fractal · TTrades-L12 · TTrades-L13 ·
TTrades-L14 · Argon-Gold

## 紙上競賽，唔會郁真錢

Repo 入面嘅 Longbridge client **只係讀行情**（quote / candlesticks /
balance / positions），全個 tree 冇 `submit_order` 或者 `place_order`。
Arena 只係喺自己嘅 account 檔案入面郁數字，冇落過任何單。
live 嘅治理階梯 `strategy_levels.json` 亦都冇畀 arena 郁過 —— arena 有自己嘅
level counter，所以正式嘅升級規則（n ≥ 10、14 日窗、連續兩日）原封不動。

## 同 live 書分別喺邊

live 書好小心：每個策略一個倉、每個策略固定標的、有交易時段閘、每個訊號要
LLM 評級、升級要十四日內十單。**Arena 全部照抄 detector，但刻意唔抄嗰啲閘**，
因為競賽要成交量：

- 每個 agent 最多同時 5 個倉，跨全部 6 個標的（MNQ/MES/M2K/MGC/GC/BTC）
- 每單風險 $100（用 `contract_specs.size_position`，所以 GC 會自動變 0.17 張）
- 冇 LLM 喺 loop 入面：detector 自己嘅 strength 就係 grade（同一個
  `detector_proxy` 近似，historical backtest 都係咁標）
- live 嘅標的封殺（Stair 唔做 BTC、3-Pushes 唔做 BTC、50-20 唔做 MGC、CRT 唔做 GC）
  **唔適用**。老闆話咗要全標的，arena 就照做，而且會記低每個標的嘅成績，
  令封殺可以靠證據決定，唔係靠 inheritance

## Engine 點行

`automation/scripts/arena.py` 係一個 **rolling simulator**，唔係 snapshot：

1. 每個 instrument 攞一次 frame（5m 十五日、1h 六十日、resample 出 4h）
2. 每個 agent 由上次行完之後嘅新 bar 開始逐支行：
   - 先用嗰支 bar 嘅 high/low 結算現有倉（食 SL 或者食到 T2 就平倉）
   - 然後喺嗰支 bar 跑自己個 detector，fire 就開倉（entry = 該 bar 收盤）
3. 第一個 run 由 `BOOTSTRAP_BARS`（288 支 = 24 個鐘）開始，令 arena 一開波
   已經有帳戶有倉，唔係一張白紙
4. 每 15 分鐘行一次（`arena.yml`，同 live-scan 一齊嘅節奏）

TTrades 家族用自己嘅 frame（H4 / M15 / D1），所以佢哋每 15 分鐘先評估一次
（`minute % 15 == 0`），同佢哋自己條 live pipeline 一致。**重播時 frame 會
cut 到被重播嗰支 bar 為止**，唔會有未來資料漏入。

## Level 規則

`automation/config/arena_rules.json`：

- **升級**：今日 n ≥ 1、PF > 1.0、WR ≥ 50%、RR > 1、pnl > 0 → **+1**
- **降級**：今日 n ≥ 5、PF < 0.5、pnl < −$300（超過三倍風險預算）→ **−1**
- 目標係「日 +1 level」。升級門檻故意平，因為競賽要有人贏；降級門檻故意高，
  level 係分數唔係懲罰 —— 第一版用咗 n≥3 / PF<0.7，一日就把三個 agent 打到 lv0，
  樓梯即刻冇意思

## 輸出

```
automation/reports/arena/leaderboard.json            板
automation/reports/arena/arena_YYYY-MM-DD.md         當日報告
automation/reports/arena/agents/<slug>/account.json   每 agent 狀態
automation/reports/arena/agents/<slug>/trades.jsonl   每 agent 交易
automation/reports/arena/taunts/<day>_<slug>.md       互噴存檔
```

## 每日流程

1. `arena.yml` 每 15 分鐘行 engine，state  commit 落 repo
2. 每日（紐約日完咗）host session 拉最新 board，逐個 ping 15 個 agent session
3. 每個 agent 讀自己個帳戶 + 板，寫 3-5 句垃圾話落 `taunts/`
4. `arena_report.py` 砌成 digest，發 Telegram，同埋 commit 落 repo

```bash
# 行一次 engine
python automation/scripts/arena.py

# 砌報告（加 --taunts 就會包埋互噴）
python automation/scripts/arena_report.py --taunts automation/reports/arena/taunts
```

## 重現

工具：`automation/scripts/arena.py`（engine）、`arena_report.py`（報告 + Telegram）。
66 MB 級嘅 raw bar 唔入 repo；board、帳戶、交易、互噴全部入 repo。
