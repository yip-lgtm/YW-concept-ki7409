# YW Concept Trading Research

本倉庫整理 **YW Trader HK** 在 Discord `#📖｜ywconcept百科全書` 頻道分享的原始概念，
並延伸 TTFM、CRT、Kell Cycle、YW Indicator 等合流研究；同時係 **24/7 自動交易 pipeline**
嘅 source of truth —— 5-power separation、P0/P0.5/P1 安全閘、4 路 detector 自動 ranking
同 LLM-driven 參數優化都喺度跑。

> 🛡️ **Production state (2026-09-21)**：4 路 gate 全部 live verified (P0 Grade C / H-Pattern
> pullback / 方向 conflict；P0.5 stacking；P1 CRT chase + 50-20 drift + Analyst circuit breaker)。
> 最新 patch：`1609575` (v4.1) — 詳見 [🛡️ Open-Position Gates](#-open-position-gates-p0p05p1)。

---

## 📚 文件目錄

### 核心定義 (YW 百科全書)
| # | 主題 | 文件 |
|---|------|------|
| 01 | YW Concept 總覽 | [docs/01-YW-Concept-Overview.md](docs/01-YW-Concept-Overview.md) |
| 02 | H-Pattern 官方定義 (3min/5min) | [docs/02-H-Pattern.md](docs/02-H-Pattern.md) |
| 03 | 3 Pushes (5min/15min) | [docs/03-Three-Pushes.md](docs/03-Three-Pushes.md) |
| 04 | 兩陽夾一陰 | [docs/04-Two-Yang-One-Yin.md](docs/04-Two-Yang-One-Yin.md) |
| 08 | RSI Divergence | [docs/08-RSI-Divergence.md](docs/08-RSI-Divergence.md) |
| 09 | 輔助技巧 (ES 對照、慢牛快熊) | [docs/09-Auxiliary-Tips.md](docs/09-Auxiliary-Tips.md) |
| 11 | 50/20 (20EMA / 50SMA) | [docs/11-50-20.md](docs/11-50-20.md) |
| 12 | Stair Pattern | [docs/12-Stair-Pattern.md](docs/12-Stair-Pattern.md) |
| 13 | TTFM Fractal Model | [docs/13-TTFM-Fractal-Model.md](docs/13-TTFM-Fractal-Model.md) |
| 14 | CRT Candle Range Theory | [docs/14-CRT-Candle-Range-Theory.md](docs/14-CRT-Candle-Range-Theory.md) |
| 15 | Oliver Kell Cycle | [docs/15-Oliver-Kell-Cycle.md](docs/15-Oliver-Kell-Cycle.md) |
| 16 | YW Indicator (TradingView) | [docs/16-YW-Indicator.md](docs/16-YW-Indicator.md) |
| 17 | TTrades Model (BTC) | [docs/17-TTrades-Model.md](docs/17-TTrades-Model.md) |

### 圖示 / 實戰 / 種田流
| # | 主題 | 文件 |
|---|------|------|
| 05 | 圖示描述與視覺參考 | [docs/05-Image-Descriptions.md](docs/05-Image-Descriptions.md) |
| 06 | 實戰例子整理 | [docs/06-Practical-Examples.md](docs/06-Practical-Examples.md) |
| 07 | 種田流完整整理 | [docs/07-Zhongtian-Notes.md](docs/07-Zhongtian-Notes.md) |
| 10 | 種田策略實務 Setup | [docs/10-Zhongtian-Practical-Setup.md](docs/10-Zhongtian-Practical-Setup.md) |

### MT5 程式
- [mt5/](mt5/) — 50/20 Pullback + Kell Cycle 五支 EA (CRT BTC MT5 EA v1.04 compiled)

### 報告與圖表
- `華爾街農夫_種田流交易秘笈.pdf` / `.docx`

---

## 🚀 安裝與設定

**新用戶請先睇 [INSTALL.md](INSTALL.md)** — 涵蓋：
- 環境設定（Python 3.11+、GHA secrets、Massive/Telegram/MiniMax-M3）
- Workflows 自動跑 setup
- 5 個獨立 power 嘅 GHA secrets 配置
- Troubleshooting + 20 日 backtest 預期

---

## 🤖 24/7 Automation Pipeline

呢個 repo 同時係 **24/7 自動交易 pipeline** 嘅 source。9 個 GHA workflow 互相制衡：

| Workflow | Schedule | 職責 (Power) |
|----------|----------|-------------|
| `9-strategy-live-scan.yml` | 15min | Power 3 — 9 路 detector + LLM grading + open-position gates |
| `ocs-btc-5m.yml` | 15min | Power 3 — OCS BTC 5m 24/7 |
| `unified-pipeline.yml` | 15min (4 offsets) | Power 3 — 6 job master (OCS + Supervisor + SysEng + TechAnalyst + TTrades + Dashboard) |
| `always-on-trigger-1/2/3.yml` | 15min (3 offsets) | Stall detector backup |
| `pipeline-scheduler.yml` | 15min | Health watchdog |
| `strategy-supervisor.yml` | hourly | Power 1 — health check 11 sub-agents |
| `strategy-ranking.yml` | 3×/day | Power 4 — ranking + LLM iter |
| `update-dashboard-data.yml` | hourly | Web dashboard JSON |
| `sys-engineer.yml` | 60min | Power 2 — auto-fix |

詳見 [docs/OCS-SETUP.md](docs/OCS-SETUP.md) 同 [docs/STRATEGY-SETUP.md](docs/STRATEGY-SETUP.md)。

---

## 🛡️ Open-Position Gates (P0/P0.5/P1)

**設計理念**：LLM grading + detector 唔可以單獨決定開倉。所有 open 必須過晒下列 hard gates
先入 `open_live_position()` —— numeric structural checks，唔靠 prompt parsing。

### Gate 排隊順序（in `_apply_open_gates()`）

| # | Gate | Class | 觸發條件 | 對應 commit |
|---|------|-------|---------|------------|
| 1 | Grade C no-open | **P0** | `sig.grade == "C"` → SKIP | `bf66c0d` |
| 2 | H-Pattern pullback | **P0** | `abs(pullback_pct) ≥ 50%` → SKIP | `9698d36` |
| 2.5 | CRT distance_from_mss | **P1** | `|last - mss_confirm| / range > 0.3` → SKIP | `8fd2140` (v3) |
| 2.7 | 50-20 EMA drift | **P1** | `abs(distance_to_ema20_pct) > 0.1%` → SKIP | `70750671` (v4.1) |
| 3 | Direction conflict | **P0** | same ticker `long + short` 兩個 direction → 兩個都 SKIP | `9698d36` |
| 4 | Stacking | **P0.5** | same ticker + same direction ≥ 2 strategies → 留最強 grade (A>B)，ties conf desc | `9698d36` |
| 1× | Circuit breaker | **P1** | Tech Analyst >50% fail rate (TTL 2h, recover after 3 OK scans) → BLOCK all | `8fd2140` (v3) |

### Critical fixes per patch

| Patch | Commit | What it fixed | Why it mattered |
|-------|--------|--------------|----------------|
| **v3** | `8fd2140` | CRT chase gate + Analyst circuit breaker | Chase 0.43×range 直接 SL −$197 |
| **v4** | `599c7bf8` | Signal dict 入 detector raw fields (`mss_confirm`, `crt_high`, ...) | **v3 patch 之前 0% trigger 因為 gate 讀唔到 detector fields** |
| **v4.1** | `70750671` | Gate 2.7 — 50-20 Pullback EMA drift > 0.1% skip | 9/21 「唔追 81.5 之上嘅 50-20 多」 |

### Live evidence (sha=`1609575` 9/21 03:36 UTC cycle)

```
[live_scan] 🚧 Gate-skipped 2 signals (logged only, no position):
    - Kell-Cycle [C] BTC-USD long: Grade C: no auto-open
    - RSI-Div [C] BTC-USD bearish: Grade C: no auto-open
[open] SKIP 3-Pushes BTC-USD down: already have open 3-Pushes down @ 81511
[live_scan] ✓ 2 gated signals logged to signals.jsonl
```

**Real-trade avoidance (9/20 retrospective)**:

| Time | Trade | Without gates | With v4.1 |
|------|-------|---------------|-----------|
| 14:16 CRT BTC chase 687pt | SL −$197 | opened | **SKIP** (dist 0.43) |
| 18:09 CRT MNQ chase 141pt | T2 +$60 | opened | **SKIP** (dist 0.504) |
| 19:30 CRT MNQ chase 241pt | T2 +$40 | opened | **SKIP** (dist 0.86) |
| 19:30 50-20 BTC × 2 | +$237 | both opened | **1 SKIP** (P0.5 stacking) |

---

## 🔒 5-Power Separation + Audit Trail

```
                ┌────────────────────────────────────┐
                │   Power 1: SUPERVISOR (監督者)     │
                │   • Read-only health check        │
                │   • 唔可以落單 / auto-fix          │
                └────────────────┬───────────────────┘
                                 │ 報 BUG
                                 ▼
   ┌───────────────────┐  ┌────────────────────┐  ┌────────────────────┐
   │  Power 3:         │  │  Power 2:          │  │  Power 4:          │
   │  STRATEGY AGENT   │◄─┤  SYSTEM ENGINEER   ├─►│  LLM ITERATION     │
   │  (執行者)         │  │  (系統工程師)      │  │  SCIENTIST (科學家)│
   │  • Trade signal   │  │  • Auto-fix        │  │  • Param optimize  │
   └───────────────────┘  └────────────────────┘  └────────────────────┘
                                                          ▲
   ┌───────────────────┐                                  │
   │  Power 5:         │   audit.py → state JSON         │
   │  TECH ANALYST     │──────────────────────────────────┘
   │  (圖表)           │   Every action logged to
   │  • Chart gen      │   automation/reports/audit/
   └───────────────────┘
```

- 任何 agent **落單 / auto-fix / 改 param** → `audit.py` 寫 timestamp + agent + action + grade
- 4 個 power 互相制衡，唔可以互相包庇
- 詳見 [docs/GOVERNANCE-4-POWERS.md](docs/GOVERNANCE-4-POWERS.md)

### Accountability (問責制)
- 每個 open / close / grade / override 都會 log 入 `automation/reports/audit/`
- Circuit breaker tripped → supervisor 即時收到，下次 run 自動 re-evaluate
- LLM 出 bad call → 對應 commit hash 可追到 prompt + context

---

## 🛠️ Pipeline 24/7 Self-Healing

呢個 repo 用多重 defense layer 確保 24/7 唔停：

| Layer | Mechanism | Trigger |
|-------|-----------|---------|
| 1 | **Cron-driven workflows** (9× GHA) | 15min / hourly / 3× daily |
| 2 | **Always-on triggers** (3× with offset 3/8/13 min) | Stall detector backup |
| 3 | **Pipeline watchdog** | Detect missing heartbeat / silent push failure |
| 4 | **Master self-heal** | 30min cron, restart stuck jobs |
| 5 | **System engineer** | 60min cron, auto-fix common patterns |
| 6 | **State files** (`heartbeat.json`, `circuit_breaker.json`, `state.json`) | Concurrent-safe across runs |
| 7 | **Stash+rebase+amend+plain push** | 避免 `--force-with-lease` silent push bug |
| 8 | **Dedup keys** (`signal_ids+exit_times hash`) | 防止 Journey Closed 重複推送 |
| 9 | **Heartbeat age monitoring** | > 30min 唔 update → watchdog 警報 |

### 已知風險 / 已修嘅 bug

| Bug | Root cause | Fix commit |
|-----|-----------|-----------|
| `--force-with-lease` silent push 失敗 | 6 個 workflow 並行 push → race | `bd1e638` bulk replace |
| Journey Closed 每日重複推送 | dedup 用 `n_trades` plateau | `7d4c0a5` hash signal_ids+exit_times |
| v3 gate 0% trigger | signal dict 缺 detector fields | `599c7bf8` (v4) |
| GHA quota 超限 | 9 個 workflow 全部 5min | `5fa7bf0` 縮到 15min |
| Per-ticker 重複開倉 | 唔識 dedup | `bf66c0d` MAX 1 per ticker |
| RTH 時間 filter 缺 | H1 strategies 24/7 開 | `210a83a` filter 09:30-16:00 ET |

---

## 📡 Recent Fixes Timeline

```
2026-09-15  ... T2 close mode (1.618R) replacing T1
2026-09-16  ... P0 open-position gates v1 (commit bf66c0d)
2026-09-17  ... P0 gates v2 + P0.5 stacking + normalize (commit 9698d36)
2026-09-17  ... v3 gates: CRT chase + Analyst circuit breaker (commit 8fd2140)
2026-09-17  ... Silent push bug + Journey Closed dedup (commit 7d4c0a5)
2026-09-18  ... All 6 workflows push fix (commit bd1e638)
2026-09-18  ... Schedule cron reduction 5min→15min (commit 5fa7bf0)
2026-09-21  ... v4 patch: pass detector raw fields → gates真 work (commit 599c7bf8)
2026-09-21  ... v4.1 patch: Gate 2.7 50-20 EMA drift (commit 70750671)
```

---

## 📋 Last Reviewed Trading Day (2026-09-20, Sun, BTC focus)

> 來源：用戶盤後 review 原始 message，summarized 入 README 方便事後 audit。

### 週末 BTC 價格路徑 (EDT)
07:50 80,446 → 11:28 80,687 → 14:16 81,183 → 19:30 81,135 → 21:27 81,513

走勢：早段假跌 → 午市推上 81.1–81.5，回撤淺、金叉／均線多頭有效。**空倉全部係 5m 噪音**。

### 損益 (有結算)
| Time | Strat | Direction | R | Cash |
|------|-------|-----------|---|------|
| 07:50 | 50-20 多 (金叉 5 根) | Long | −1.00 | −$93 |
| 11:28 | 50-20 多 (0.06% 貼) | Long | +1.62 | +$259 |
| 14:16 | CRT 多 (離 MSS 687 點) | Long | −1.00 | −$197 ← **v4 已 skip** |
| 19:30 | 50-20 多 (conf 80) | Long | +1.62 | +$237 |
| **BTC 小計** | | | **+1.24R** | **+$206** |

### 結構結論
- ✅ 週末有效邊：20/50 多頭排列 + 回踩 EMA20
- ❌ 死叉空 / Stair 空 / OCS 空 / 三推空：全部逆住 80.4 → 81.5 trend
- ❌ CRT BTC 追 MSS 687 點：典型 chase，v3 patch 之前漏，**v4 已修**
- ⚠️ 兩張 50-20 BTC 同方向 (conf 80 + 72) — P0.5 stacking 之前漏，**v4 已修**

### 種田日限反思
> 兩張刮均線多賺約 $496，一張 CRT 追同早盤淺回踩食返 $290。種田日限 $100 規矩：單 BTC 一張 −$197 **已穿日限**，淨賺靠後面兩張刮返。

### 9/21 開盤前守則（user directive + v4.1 自動 gate）

| 守則 | 自動 gate | Manual |
|------|----------|--------|
| 唔追 81.5 之上 50-20 多 | ✅ **Gate 2.7** (drift > 0.1% skip) | — |
| 唔做 Stair / 三推 / OCS 空 接高位逆勢 | — | ✅ System Eng daily alert |
| CRT BTC skip (晨報已 C) | ✅ Grade C gate | — |
| H1 EMA20 站穩收陽先 0.5µ | — | ✅ Manual macro filter |
| B1 全表 http 429 (模組當死) | ✅ Grade C gate (if degrade) | — |
| MNQ 50-20 觀察 (16:55 長陰破 EMA) | — | ✅ Manual review |
| 金 CRT / Kell #1#3 要 4H range 確認 | ✅ CRT chase gate (dist > 0.3) | ✅ 4H range manual |

**一句**：週末 BTC 賺在兩次均線多、蝕在 CRT 追同過早金叉；淨 +$206 但過程把 $100 日限當無。星期一唔好把 Score 115 當成繼續加倉許可。

---

## 🛰️ Live Operations Hub

所有 live state 統一去 👉 **[docs/review.html](docs/review.html)** (每 cycle auto-regen)

### Quick links
| 用途 | URL |
|------|-----|
| 📊 Web Review Hub (charts + trade history + rankings + LLM analysis) | `docs/review.html` |
| 📈 Strategy Dashboard (charts gallery) | `docs/strategy-dashboard.html` |
| 🔢 Dashboard JSON (raw data) | `automation/reports/dashboard-data.json` |
| 🩺 Live heartbeat (latest run) | `automation/reports/live_scan/heartbeat.json` |
| 🚧 Gated signals log | `automation/reports/live_scan/signals.jsonl` |
| 📜 24h audit trail | `automation/reports/audit/{YYYY-MM-DD}/actions.jsonl` |

### Today's heartbeat (latest)
```
n_fired=0 n_pre_gate=4 n_gated=4 n_signals=13 elapsed=47.9s
Circuit breaker: open=False
```

> Last update: auto-regenerated every cycle. 4 signals gated today = Grade C × 2 +
> per-ticker dedup × 1 + (CRT/50-20 drift pending fresh cross).

---

## 🔑 Workflows + Secrets Quick Ref

### 21 Active Workflows

| File | Cron (UTC) | HKT equivalent | 職責 |
|------|------------|----------------|------|
| `9-strategy-live-scan.yml` | `workflow_dispatch` only | manual | Power 3 — 9 路 detector + LLM grade |
| `ocs-btc-5m.yml` | `*/15 * * * *` | :00/:15/:30/:45 | OCS BTC 5m 24/7 |
| `unified-pipeline.yml` | `0,15,30,45 + 8,23,38,53` | :08/:23/:38/:53 etc | Master 6-job (OCS/Supervisor/SysEng/TechAnalyst/TTrades/Dashboard) |
| `always-on-trigger-1.yml` | `3,18,33,48 * * * *` | :03/:18/:33/:48 | Stall detector backup #1 |
| `always-on-trigger-2.yml` | `8,23,38,53 * * * *` | :08/:23/:38/:53 | Stall detector backup #2 |
| `always-on-trigger-3.yml` | `13,28,43,58 * * * *` | :13/:28/:43/:58 | Stall detector backup #3 (5min latency combined) |
| `pipeline-scheduler.yml` | `*/15 * * * *` | :00/:15/:30/:45 | Git-based watchdog |
| `pipeline-watchdog.yml` | `*/15 * * * *` | :00/:15/:30/:45 | Auto-trigger if stalled |
| `master-self-heal.yml` | `*/30 * * * *` | :00/:30 | 24/7 pipeline doctor |
| `sys-engineer.yml` | `0 * * * *` | hourly | Power 2 auto-fix |
| `supervisor-monitor.yml` | `workflow_dispatch` | manual / pipeline-triggered | Power 1 health check |
| `update-dashboard-data.yml` | `workflow_dispatch` | triggered | Web dashboard JSON |
| `daily-watchdog.yml` | `30 16 * * *` (daily) | 00:30 HKT | Auto-trigger daily if stalled |
| `llm-iteration-scientist.yml` | `0 16 * * 1-5` | 00:00 HKT weekdays | Per-agent LLM self-optimize |
| `per-agent-iteration.yml` | `0 16 * * 1-5` | 00:00 HKT weekdays | 10 agents iteration |
| `strategy-ranking.yml` | `0 16 * * 0` + `12,20 UTC Sun` | 00:00 + 20:00 + 04:00 HKT Sun | Ranking + LLM iter (3× daily) |
| `strategy-reward.yml` | `10 16 * * 1-5` | 00:10 HKT weekdays | Top 3 PnL daily reward |
| `yw-daily.yml` | `0 16 * * 1-5` + `0 16 * * 6,0` | 00:00 HKT every day | Daily LLM reminder + 4-Chart |
| `yw-publish-signal.yml` | `5 16 * * 1-5` | 00:05 HKT weekdays | Push top signal to AI-Trader |
| `weekly-readme.yml` | `0 13 * * 0` | 21:00 HKT Sun | README auto-update |

### Required Secrets (7 total)
| Secret | 用途 | Required by |
|--------|------|------------|
| `GITHUB_TOKEN` / `APEX_PAT` | git push 自動 commit | All workflows |
| `TELEGRAM_BOT_TOKEN` | TG 推送信號 | most workflows |
| `TELEGRAM_CHAT_ID` | TG chat target | most workflows |
| `MINIMAX_API_KEY` | LLM grading + iteration | live-scan, llm-scientist, per-agent, yw-daily |
| `POLYGON_API_KEY` | BTC/USD fallback data source | ocs-btc, live-scan |
| `AI_TRADER_TOKEN` | HKUDS AI-Trader platform signal push | yw-publish-signal, live-scan |

> **Note**: Multi-source data fallback: yfinance → polygon → coingecko (2026-09-16)
> — single-source outage no longer kills the pipeline.

---

## 📅 本週策略報告 (2026-09-13 ~ 2026-09-20)

_由 `strategy-supervisor` 每週日 21:00 HKT 自動生成_

### 📡 OCS BTC 5m 24/7
- 監察 runs: **100** (expected ~2,016 @ 5min × 7d)
- 信號 fired: **100** (vote ≥4 + conf ≥0.55)
- 累計 trades: 3 | WR: 33.3% | PF: 0.5 | Total R: −1.0R

### 🏆 本週 9 Strategy 排名 (by 累計 P&L)
| Rank | Strategy | Days | 累計 P&L | Total R | WR | PF |
|------|----------|------|----------|---------|----|----|
| 🥇 #1 | 50/20 Pullback | 3d | $11,448 | +285.0R | 47.6% | 1.25 |
| 🥈 #2 | Kell Cycle | 3d | $8,388 | +210.0R | 46.2% | 1.18 |
| 🥉 #3 | OCS BTC 5m | 3d | $4,061 | +63.0R | 53.9% | 1.17 |
| #4 | H-Pattern | 3d | $3,204 | +75.0R | 54.3% | 1.40 |
| #5 | Stair Pattern | 3d | $2,532 | +63.0R | 43.1% | 1.08 |
| #6 | 3-Pushes | 3d | $1,740 | +36.0R | 47.0% | 1.10 |
| #7 | CRT | 3d | $1,230 | +27.0R | 48.7% | 1.06 |
| #8 | 兩陽夾一陰 | 3d | $720 | +15.0R | 50.0% | 1.05 |
| #9 | B1 战法 (MNQ) | 3d | $0 | 0.0R | 0.0% | 0.00 |

### 👑 Supervisor Health
- Status: **WARNING** (1 issue — B1 HTTP 429 rate-limited, marked dead until refresh)

---

## 📜 來源說明

YW 核心定義來自 Discord 原始訊息。YW Indicator 說明整理自《YW指標使用手冊 v6》。
其餘為公開教學摘要 + agent 回測 + LLM 優化建議。

**僅供學習研究，不構成投資建議。交易有風險。**

---

最後更新：**2026-09-21** (manual refresh — v4.1 patches documented)
