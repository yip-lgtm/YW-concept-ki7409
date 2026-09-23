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
| `9-strategy-live-scan.yml` | 15min | Power 3 — **11 路 detector + LLM grading + open-position gates** |
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
| 2.10 | Stair ticker+session ban | **P1** | ticker ∈ {BTC,MES} OR session ∈ {RTH_Close,AsiaLate,Lunch} → SKIP | `f805506b` (v5) |
| 2.11 | 3-Pushes ticker+session ban | **P1** | ticker == BTC OR session ∈ {RTH_Close,AsiaLate} → SKIP | `f805506b` (v5) |
| 2.12 | 50-20 ticker ban | **P1** | ticker == MGC → SKIP | `f805506b` (v5) |
| 2.13 | RSI-Div paper-only | **P1** | grade ≠ A OR ticker == BTC → SKIP | `f805506b` (v5) |
| 5 | Stair 4h re-entry cooldown | **P0.5** | prior Stair same-ticker-same-dir closed <4h ago → SKIP | `f805506b` (v5) |
| 3 | Direction conflict | **P0** | same ticker `long + short` 兩個 direction → 兩個都 SKIP | `9698d36` |
| 4 | Stacking | **P0.5** | same ticker + same direction ≥ 2 strategies → 留最強 grade (A>B)，ties conf desc | `9698d36` |
| 1× | Circuit breaker | **P1** | Tech Analyst >50% fail rate (TTL 2h, recover after 3 OK scans) → BLOCK all | `8fd2140` (v3) |

### Critical fixes per patch

| Patch | Commit | What it fixed | Why it mattered |
|-------|--------|--------------|----------------|
| **v3** | `8fd2140` | CRT chase gate + Analyst circuit breaker | Chase 0.43×range 直接 SL −$197 |
| **v4** | `599c7bf8` | Signal dict 入 detector raw fields (`mss_confirm`, `crt_high`, ...) | **v3 patch 之前 0% trigger 因為 gate 讀唔到 detector fields** |
| **v4.1** | `70750671` | Gate 2.7 — 50-20 Pullback EMA drift > 0.1% skip | 9/21 「唔追 81.5 之上嘅 50-20 多」 |
| **v5** | `f805506b` | 6 gates (Stair/3-Pushes/50-20/RSI-Div/cooldown) + 3-Pushes direction fix + TTrades size cap | 9/21-22 trade review: BTC 單筆決定全日、Stair 同 ticker 同方向 4h 內重開、3-Pushes `Dir:up` 文案寫衰竭但開多 |

### Live evidence (sha=`f805506b` 9/23 06:57 UTC cycle)

```
[live_scan] LLM-confirmed signals: 2
⏰ SKIP 50-20-Pullback MNQ=F: outside RTH
⏰ SKIP 50-20-Pullback MGC=F: outside RTH
[live_scan] ✓ Heartbeat saved (15.7s)
```

**Real-trade avoidance (9/21-22 retrospective)**:

| Time | Trade | v4.1 outcome | v5 outcome |
|------|-------|--------------|------------|
| 9/21 17:51 Stair BTC short A | −$224 SL | opened | **SKIP** (BTC ticker) |
| 9/21 21:00 Stair MES A | −$5 SL | opened | **SKIP** (MES ticker) |
| 9/21 21:26 Stair BTC short B | **−$323 / 87 bars** | opened | **SKIP** (BTC ticker) |
| 9/22 01:00 Stair MNQ+MGC A | −$11/+11 | opened | MGC SKIP (AsiaLate) ; MNQ keep |
| 9/22 10:50 3-Pushes MGC `Dir:up` | −$4 SL | **opened LONG** | **now SHORT** (direction fix) + skip if AsiaLate |
| 9/21 13:52 RSI-Div BTC A | −$374 SL | opened | **SKIP** (paper-only) |
| 9/22 TTrades 0.75 BTC / $64k | — | fired | **CAP at 0.5 BTC / $43k** |
| 9/21 18:42 50-20 MGC A | −$5 SL | opened | **SKIP** (MGC ticker) |
| 9/21 17:30 3-Pushes BTC down | −$119 SL | opened | **SKIP** (BTC ticker) |

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

## 📊 Strategy Setup & Iteration

11 路 detector (10 unique + B1 3合1 multi-asset split)，全部已經 iterate 過。Apex envelope
replay 喺 [docs/STRATEGY-SETUP.md](docs/STRATEGY-SETUP.md)，detail per-strategy LLM analysis
喺 `automation/reports/yw_setups_bt/iteration/per_strategy/` (11 份 .md)。

### 11 Strategies (current config)

| # | Strategy | Ticker | Weight | LLM Iter |
|---|----------|--------|--------|----------|
| 1 | OCS BTC 5m | BTC-USD | 1.0 | — |
| 2 | H-Pattern | MNQ=F | 1.2 | — |
| 3 | 3-Pushes | MNQ=F | 1.0 | — |
| 4 | 兩陽夾一陰 (Two-Yang) | MNQ=F | 0.8 | v2 2026-08-25 |
| 5 | RSI Divergence | MNQ=F | 0.7 | v1 2026-08-25 |
| 6 | 50/20 Pullback | MNQ=F | 1.0 | — |
| 7 | Stair Pattern | MNQ=F | 0.9 | v3 2026-08-25 |
| 8 | CRT | MNQ=F | 1.1 | v5 2026-08-26 |
| 9 | Kell Cycle | MNQ=F | 0.9 | v4 2026-08-26 |
| 10 | B1 战法 (MNQ/MGC/BTC) | multi | 1.0 | v6 2026-08-27 |
| 11 | B1 3合1 (multi-asset) | multi | 1.0 | v6 2026-08-27 |

### Latest Iteration (2026-09-22 02:08 HKT) — Apex envelope re-sim

11 strategies 全 iterate。Verdict 統計：**keep 2 / tweak 9 / drop 0**。

| Rank | Strategy | Filter | Net AFTER | MaxDD | WR | n | Verdict |
|------|----------|--------|----------:|------:|---:|---:|---------|
| 🥇 | **Stair** | skip NYKZ + skip BTC + skip MES | **$+1,363.54** | $290.55 | 52.6% | 57 | tweak |
| 🥈 | **CRT** | no change (baseline best) | **$+1,221.86** | $379.65 | 41.3% | 121 | **keep** |
| 🥉 | **50-20-Pullback** | skip MGC + keep MNQ all sessions | **$+696.19** | $400.00 | 50.8% | 65 | **keep** ↑ |
| 4 | 3-Pushes | MNQ+BTC up only | $+623.17 | $195.26 | 40.0% | 50 | tweak ↑ from drop |
| 5 | Two-Yang | skip MNQ + skip MES + skip LDLZ | $+476.77 | $216.43 | 47.1% | 34 | tweak |
| 6 | Kell-Cycle | MGC short only | $+387.50 | $132.60 | 55.6% | 9 | tweak |
| 7 | B1 | no change (baseline best) | $+272.00 | $105.33 | 44.4% | 9 | tweak |
| 8 | OCS-BTC-5m | LDLZ + NYKZ long | $+254.50 | $195.98 | 58.6% | 87 | tweak |
| 9 | B1-3in1 | skip MES (keep MGC+BTC) | $+196.93 | $0.00 | 100.0% | 7 | tweak |
| 10 | H-Pattern | NYKZ only | $+78.96 | $32.95 | 60.0% | 5 | tweak |
| 11 | RSI-Div | skip MNQ+MGC+MES | $+46.94 | $101.05 | 50.0% | 12 | tweak ↑ from drop |

### Live arm recommendation (Tradovate MNQ + MGCZ6)
- **Arm CRT live** (unfiltered, qual=6, n=121, net $+1,221.86)
- **Paper Stair** with skip-NYKZ+skip-BTC+skip-MES (AFTER $+1,363.54, qual=2)
- **Optional 2nd book 50-20-Pullback** with skip-MGC + MNQ-all / others-LDLZ|NYKZ only (keep $+696.19, qual=3)
- ❌ Do NOT arm 3-Pushes/RSI-Div (drop-to-tweak salvages) live

### CRT deep analysis (LLM-validated)
- 121 accepted Apex trades, **net +$1,221.86**（WR 41.3%, 50W/71L）
- **B grade carried the book** (92 trades, $+1,131.82, WR 43.5%) — A underperformed (29 trades, $+90.04, WR 34.5%)
- **MGC=F best ticker** (n=13, WR 61.5%, $+736.14); MNQ=F (n=31, WR 45.2%, $+486.41)
- **BTC-USD worst** (n=40, WR 30.0%, **−$79.49**) — drives v4 chase gate
- **LDLZ session best expectancy** (02-05 NY: n=14, WR 57.1%, +$25.02/trade)
- LLM verdict: **do NOT tighten** — all tested filters (skip BTC, MGC+MNQ allowlist, skip NYKZ bearish)
  remain keep but **lower re-sim net** ($667–$910 vs $1,222) because removing losing BTC/NYKZ cells
  reshuffles Apex overlap/daily envelope onto weaker replacements
- 詳見 `automation/reports/yw_setups_bt/crt_llm_analysis.md`

### Files (artifacts)
| File | 用途 |
|------|------|
| [docs/STRATEGY-SETUP.md](docs/STRATEGY-SETUP.md) | Auto-regenerated, top-level 11 strategies config table |
| `automation/reports/yw_setups_bt/report.md` | Master Apex-envelope re-sim constraints + verdict gates |
| `automation/reports/yw_setups_bt/iteration/report.md` | Latest per-strategy filter iteration (BEFORE/AFTER) |
| `automation/reports/yw_setups_bt/iteration/per_strategy/*.md` | 11 份 strategy-specific LLM analysis |
| `automation/reports/yw_setups_bt/crt_llm_analysis.md` | CRT deep-dive (ticker / session / grade mix) |
| `automation/reports/yw_setups_bt/replay_apex_yw.py` | Apex-envelope replay engine (553 lines) |
| `automation/reports/yw_setups_bt/ranking.json` | Raw ranking data (post-iter) |

---

## 📈 7-Day Rolling Ranking (live closed trades)

> 來源：`automation/reports/live_scan/trades.jsonl`，filter `exit_time ∈ [now-7d, now]` + `status=closed`。
> Window: **2026-09-15 16:17 UTC → 2026-09-22 16:17 UTC** (135 closed trades, +3.8R, +$993 net)。

| Rank | Strategy | n | W/L | WR | Total R | Avg R | Total $ | PF | Avg Bars |
|------|----------|--:|----:|----:|--------:|------:|--------:|---:|---------:|
| 🥇 | **CRT** | **49** | 21/28 | 42.9% | +6.0 | +0.122 | +$234.66 | 1.13 | 11.7 |
| 🥈 | **50-20-Pullback** | 28 | 12/16 | 42.9% | +3.4 | +0.122 | **+$1,066.01** | **1.84** | 11.8 |
| 🥉 | H-Pattern | 2 | 2/0 | 100.0% | +3.2 | +1.618 | +$1,137.10 | ∞ | 9.5 |
| 4 | Kell-Cycle | 4 | 2/2 | 50.0% | +1.2 | +0.309 | +$148.67 | 1.92 | 12.2 |
| 5 | B1 | 2 | 1/1 | 50.0% | +0.6 | +0.309 | −$3.10 | 0.75 | 4.5 |
| 6 | Two-Yang | 5 | 2/3 | 40.0% | +0.2 | +0.047 | +$37.22 | **2.80** | 9.0 |
| 7 | B1-3in1 | 1 | 0/1 | 0.0% | −1.0 | −1.000 | +$3.11 | ∞ | 1.0 |
| 8 | Stair | 21 | 7/14 | 33.3% | −2.7 | −0.127 | +$19.38 | 1.04 | 11.5 |
| 9 | RSI-Div | 6 | 1/5 | 16.7% | −3.4 | −0.564 | **−$1,000.33** | 0.23 | 13.2 |
| 10 | 3-Pushes | 17 | 5/12 | 29.4% | −3.9 | −0.230 | −$649.59 | 0.48 | **34.6** |
| | **Σ Total** | **135** | **54/81** | **40.0%** | **+3.8** | **+0.028** | **+$993.13** | — | — |

### Reliability split
- **Robust (n ≥ 30)**: CRT only (n=49) — only statistical signal we can trust for the week
- **Small sample (n < 30)**: 50-20-Pullback n=28, Stair n=21, 3-Pushes n=17, RSI-Div n=6, Two-Yang n=5, Kell-Cycle n=4, H-Pattern n=2, B1 n=2, B1-3in1 n=1

### 🎯 Robust PF ranking (n ≥ 30 only)
| Rank | Strategy | PF | Total R | WR | n |
|------|----------|---:|--------:|----:|--:|
| 🥇 | CRT | 1.13 | +6.0 | 42.9% | 49 |

### 對比 9/22 LLM iteration (Apex re-sim)

| Strategy | LLM iter verdict | LLM iter filter | Live 7d | 一致? |
|----------|-----------------|-----------------|---------|------|
| CRT | **keep** | baseline | +6.0R, n=49, PF 1.13 | ✅ aligned |
| 50-20-Pullback | **keep ↑** | skip MGC | +3.4R, n=28, PF 1.84 | ✅ aligned |
| Stair | tweak | skip NYKZ+MES+BTC | **−2.7R, n=21, PF 1.04** | ⚠️ filter NOT applied live |
| 3-Pushes | tweak ↑ from drop | MNQ+BTC up only | **−3.9R, n=17, PF 0.48** | ⚠️ filter NOT applied live |
| RSI-Div | tweak ↑ from drop | skip MNQ+MGC+MES | **−3.4R, n=6, PF 0.23** | ⚠️ filter NOT applied live |
| Two-Yang | tweak | skip MNQ+MES+LDLZ | +0.2R, n=5, PF 2.80 | ⚠️ n too small |
| Kell-Cycle | tweak | MGC short only | +1.2R, n=4, PF 1.92 | ⚠️ n too small |
| H-Pattern | tweak | NYKZ only | +3.2R, n=2, PF ∞ | ⚠️ n too small |
| B1 | tweak | baseline | +0.6R, n=2 | ⚠️ n too small |
| B1-3in1 | tweak | skip MES | −1.0R, n=1 | ⚠️ n too small |

### Critical gap — LLM iter filter 仍未 deploy 到 live_scan.py

9/22 嘅 LLM iteration paper 結果 (Apex envelope re-sim) 同 live closed trades **4 個 strategy 唔對齊**:

- **Stair**: LLM paper #1 ($+1,363) but live −2.7R → 必須 apply `skip NYKZ+MES+BTC` filter 去 live_scan.py
- **3-Pushes**: LLM saved from drop ($+623 paper) but live −3.9R → 必須 apply `MNQ+BTC up only` filter
- **RSI-Div**: LLM saved from drop ($+47 paper) but live −$1k → 必須 apply `skip MNQ+MGC+MES` filter
- 3 個策略加埋 live 虧損 −$2,017 / −10.0R，**filter 套用後預計可避免絕大部分**

### Action items

| Priority | Action | Expected saving |
|----------|--------|-----------------|
| **P0** | Apply Stair filter `skip NYKZ+MES+BTC` to live_scan.py | ~$400/wk |
| **P0** | Apply 3-Pushes filter `MNQ+BTC up only` to live_scan.py | ~$650/wk |
| **P0** | Apply RSI-Div filter `skip MNQ+MGC+MES` to live_scan.py | ~$1,000/wk |
| **P1** | Wait for more samples on H-Pattern / Kell-Cycle / B1-3in1 (n < 5) | n/a |
| **P2** | Track CRT PF 1.13 (modest) — LLM iter suggests baseline OK, monitor WR | n/a |

**Total expected savings**: ~$2,000/wk if all 3 filters applied.

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
n_fired=1 n_pre_gate=3 n_gated=2 n_signals=10 n_detections=55
Circuit breaker: open=False
```

> Last update: auto-regenerated every cycle. 4 signals gated today = Grade C × 2 +
> per-ticker dedup × 1 + (CRT/50-20 drift pending fresh cross).

---

## 🔑 Workflows + Secrets Quick Ref

### 21 Active Workflows

| File | Cron (UTC) | HKT equivalent | 職責 |
|------|------------|----------------|------|
| `9-strategy-live-scan.yml` | `workflow_dispatch` only | manual | Power 3 — 11 路 detector + LLM grade |
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

最後更新：**2026-09-23** (v4.5 doc refresh — v5 patch deployed: 6 gates + 3-Pushes direction fix + TTrades 0.5 BTC cap + Stair 4h cooldown, per 9/21-22 user review)
