# LLM Iteration Scientist Sub-Agent

> **Date**: 2026-08-28 v1  
> **Sub-agent**: `llm-iteration-scientist`  
> **Schedule**: 00:00 HKT weekdays (cron `0 16 * * 1-5`)

## 1 句话总结

**LLM 深度分析 10 个 strategy agents 嘅 7d performance data，自動 diagnose + suggest concrete code changes。**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  llm_iteration_scientist.py (17.5KB)                        │
│  ├─ load_strategy_data()  — 載入 7d signals + trades        │
│  ├─ call_llm_scientist()  — LLM diagnose + suggest         │
│  ├─ iterate_agent()       — 每個 agent 完整 iteration       │
│  └─ send_tg_summary()     — TG 報告                         │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  MiniMax-M3 LLM (via api.minimax.io)                       │
│  Prompt: 7d stats + by_grade + by_direction + by_ticker    │
│  Output: GRADE | CONFIDENCE | DIAGNOSIS | SUGGESTED_PARAMS  │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Auto-Apply (conf >= 60%):                                  │
│  • Update yw_indicators.py / yw_grader.py / strategy_ranking│
│  • Commit + push to main                                    │
│  • Save iteration_scientist_<ts>.json + .md                │
└─────────────────────────────────────────────────────────────┘
```

---

## Per-Agent Analysis

Each agent 嘅 performance 會被分為 4 個維度:

| Dimension | Data Loaded |
|-----------|-------------|
| **Aggregate** | n_signals_7d, n_trades, win_rate, total_R, PF |
| **By Grade** | A / B / C 各自 win rate + total R |
| **By Direction** | long / short 各自 win rate + total R |
| **By Ticker** | MNQ / MES / M2K / MGC / BTC 各自 win rate + total R |

LLM 用呢啲 data 嚟：
1. **Diagnose** — 邊個維度 drag 低 performance
2. **Suggest** — ONE focused change (parameter / condition)
3. **Auto-apply** — if confidence >= 60%

---

## Example LLM Prompt

```
Strategy: yw-50-20-pullback (50-20-pullback)
Ticker: MNQ=F
Source: yw_indicators.py::detect_5020_pullback

PERFORMANCE (7d window):
  Signals: 16 (24h: 2)
  Trades: 16 | Wins: 5 | Losses: 11
  Win Rate: 31.2%
  Total R: -3.49 | Avg R: -0.218
  PF: 0.45

BY GRADE:
  {"B": {"n": 12, "wins": 4, "R": -2.5}, "A": {"n": 4, "wins": 1, "R": -0.99}}

BY DIRECTION:
  {"short": {"n": 13, "wins": 3, "R": -4.0}, "long": {"n": 3, "wins": 2, "R": +0.51}}

BY TICKER:
  {"MNQ=F": {"n": 12, "wins": 3, "R": -4.0}, "MES=F": {"n": 4, "wins": 2, "R": +0.51}}
```

LLM Response:
```
GRADE: C
CONFIDENCE: 65
DIAGNOSIS: Direction bias: short signals underperforming (R=-4.0)
REASON: Filter out short signals when above_50sma is true (trending market)
SUGGESTED_PARAMS: {"allow_short_in_uptrend": false}
```

→ Auto-applied to yw_indicators.py

---

## Schedule

| Time HKT | Action |
|----------|--------|
| **00:00** | LLM Iteration Scientist runs (10 agents in parallel) |
| 00:00-00:10 | Each agent: load data → LLM diagnose → suggest fix |
| Auto-apply | High-conf (>=60%) changes pushed to main |
| TG | Summary sent to @yip0802_bot chat |

---

## Output Files

- `automation/reports/strategy_ranking/iterations/iteration_scientist_<ts>.json` — Full iteration log
- `automation/reports/strategy_ranking/iterations/iteration_scientist_<ts>.md` — Markdown summary
- Code changes — auto-committed to main

---

## Comparison with `llm_iterate_all.py`

| | llm_iterate_all | llm_iteration_scientist |
|--|--|--|
| **Depth** | Simple param tuning | Deep performance analysis |
| **Data** | Recent live trades | 7d signals + by grade/direction/ticker |
| **LLM Usage** | Single prompt | Per-agent structured prompt |
| **Auto-Apply** | weight/timeframe | Parameters + code changes |
| **Schedule** | (legacy) | 00:00 HKT |
| **Output** | iteration_all_*.json | iteration_scientist_*.json + .md |

---

## Status

- ✅ Implemented (commit 1b498e8)
- ✅ GHA workflow at 00:00 HKT weekdays
- ✅ Tested locally
- ✅ Sends TG summary

## Co-authored-by

- Mavis <mavis@MiniMax>
