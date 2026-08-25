# 自動迭代說明手冊 (Auto-Iteration Manual)

> **版本**: 2026-08-26 v4  
> **Repo**: https://github.com/yip-lgtm/YW-concept-ki7409  
> **對象**: 9 個 strategy sub-agents (含 OCS BTC 5m)

## 一句話總結

**每個 strategy sub-agent 自己 review 自己嘅 live/backtest 表現，問 MiniMax-M3 LLM 點優化自己嘅參數。Confidence ≥ 60% 自動 apply。**

---

## 系統架構

```
┌─────────────────────────────────────────────────────────────┐
│  9 Strategy Sub-Agents                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ yw-h-pattern│  │ yw-3-pushes │  │ yw-two-yang │  ...   │
│  │ weight 1.2  │  │ weight 1.0  │  │ weight 0.3  │         │
│  │ ticker MNQ=F│  │ ticker MNQ=F│  │ ticker MNQ=F│         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
└─────────┼─────────────────┼─────────────────┼───────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
   ┌──────────────────────────────────────────────────┐
   │  Per-Agent LLM Iteration (parallel)              │
   │  → load_live_trades(strategy)                    │
   │  → call_minimax(prompt_with_context)             │
   │  → parse {grade, confidence, weight, tf, ...}   │
   │  → if confidence ≥ 60% → auto-apply              │
   └──────────────────────────────────────────────────┘
          │
          ▼
   ┌──────────────────────────────────────────────────┐
   │  Output                                          │
   │  • automation/reports/strategy_ranking/          │
   │    iterations/iteration_all_<TS>.{json,md}       │
   │  • strategy_ranking.py STRATEGIES weight update  │
   │  • yw_grader.py STRATEGIES dict update           │
   │  • Telegram: applied/skipped summary            │
   └──────────────────────────────────────────────────┘
```

---

## 觸發方式 (3 個)

| 觸發 | 頻率 | 指令 |
|------|------|------|
| **GHA 自動** (主) | 21:30 HKT 週一至五 | `.github/workflows/strategy-ranking.yml` |
| **手動 GHA** | on-demand | `gh workflow run strategy-ranking.yml` |
| **本地手動** | 即時 | `cd automation && .venv/bin/python scripts/llm_iterate_all.py [--tg]` |

---

## 9 個 Agent 列表

| ID | Agent | Ticker | Detector 函數 | 源碼 |
|----|-------|--------|---------------|------|
| `h-pattern` | yw-h-pattern | MNQ=F | `detect_h_pattern()` | [yw_indicators.py](../automation/src/yw_indicators.py) |
| `3-pushes` | yw-3-pushes | MNQ=F | `detect_3_pushes()` | [yw_indicators.py](../automation/src/yw_indicators.py) |
| `two-yang` | yw-two-yang | MNQ=F | `detect_two_yang_one_yin()` | [yw_indicators.py](../automation/src/yw_indicators.py) |
| `rsi-div` | yw-rsi-div | MNQ=F | `detect_rsi_divergence()` | [yw_indicators.py](../automation/src/yw_indicators.py) |
| `50-20-pullback` | yw-50-20-pullback | MNQ=F | `detect_5020_pullback()` | [yw_indicators.py](../automation/src/yw_indicators.py) |
| `stair-pattern` | yw-stair-pattern | MNQ=F | `detect_stair_pattern()` | [yw_indicators_extra.py](../automation/src/yw_indicators_extra.py) |
| `crt` | yw-crt | MNQ=F | `detect_crt()` (4H + 5m) | [yw_indicators_extra.py](../automation/src/yw_indicators_extra.py) |
| `kell-cycle` | yw-kell-cycle | MNQ=F | `detect_kell_setups()` (5 sub) | [yw_indicators_extra.py](../automation/src/yw_indicators_extra.py) |
| `ocs-btc` | ocs-btc-5m | BTC-USD | `compute_signal()` (KNN) | [ocs_btc_5m.py](../automation/src/ocs_btc_5m.py) |

---

## Iteration 流程 (每個 agent 1 round)

### 1. Load live trades

```python
def load_live_trades_for(strategy_id):
    """從 live_scan/trades.jsonl filter 呢個 strategy 嘅 trades"""
    fp = REPO / "automation/reports/live_scan/trades.jsonl"
    return [t for t in load(fp) if strategy_id.replace("-", " ").lower() in t.strategy.lower()]
```

### 2. Build per-strategy context

| 字段 | 來源 |
|------|------|
| `Live n trades, W-L, WR, PF, R` | `live_scan/trades.jsonl` |
| `Per-ticker breakdown` | 同上，按 ticker 分組 |
| `Current config (weight, tf, indicators)` | `strategy_ranking.py` STRATEGIES |
| `Backtest fallback` | `ranking_YYYY-MM-DD.json` (20d backtest) |

### 3. Query LLM (parallel, 9 workers)

```python
prompt = f"""你是 {agent} sub-agent。Review 自己嘅 live performance:
- Live: {n} trades, WR {wr}%, PF {pf}, R {total_r}
- Per ticker: {ticker_breakdown}
- Current config: weight={w}, tf={tf}, indicators={inds}

請用 EXACT format 回答:
GRADE: <A/B/C/D> | CONFIDENCE: <0-100> | REASON: <50字>

suggested_params = {{
  "weight": <0.1-2.0>,
  "timeframe": "<例: 5min 或 15min 或 5min/15min>",
  "indicators": ["<list", "of", "indicators>"],
  "r_multiples": [<T1>, <T2>, <T3>, <T4>, <T5>],
  "rationale": "<具體原因 50字>"
}}

禁止 <think> 標籤。"""
```

### 4. Parse + Auto-apply

```python
if conf >= 60:
    # Apply to strategy_ranking.py + yw_grader.py
    apply_to_config(strategy_id, suggested_params)
else:
    # Log only, no apply
    log_skipped(strategy_id, conf, reason)
```

---

## Auto-Apply 規則

| Confidence | Action |
|------------|--------|
| **≥ 60%** | **Auto-apply** — update `strategy_ranking.py` STRATEGIES + `yw_grader.py` STRATEGIES dict + commit + push |
| 30-59% | Log only — 唔 apply，俾下次多啲 data 再 iter |
| < 30% | Log only — LLM 唔 confident，唔好亂改 |

**為何 60% 係 threshold**: 
- 太低 (e.g. 30%) 容易將 noise 當 signal
- 太高 (e.g. 80%) 幾乎永遠都唔會 apply
- 60% 平衡咗 conservative (唔亂改) 同 reactive (有 edge 即時 capture)

---

## 影響嘅檔案

| File | 修改 |
|------|------|
| `automation/scripts/strategy_ranking.py` | STRATEGIES list (weight) |
| `automation/src/yw_grader.py` | STRATEGIES dict (timeframe, r_multiples, indicators) |
| `automation/reports/strategy_ranking/iterations/iteration_all_<TS>.json` | Full LLM response log |
| `automation/reports/strategy_ranking/iterations/iteration_all_<TS>.md` | Human-readable summary |

---

## Iteration 歷史 (cumulative)

| Iter | Date HKT | Auto-Applied | Conf | LLM Reason |
|------|----------|--------------|------|------------|
| v1 | 2026-08-25 17:00 | RSI-Div → w=0.7, tf=15min | high | Live PF 0.92 < 1, need wider targets |
| v2 | 2026-08-25 20:22 | Two-Yang → w=0.3, tf=5/15min, R=[1.5,2.5,4,6,8] | 72% | PF 0.67 = no edge, lower exposure + wider R |
| v2 | 2026-08-25 20:22 | Kell-Cycle → w=0.5, tf=5min | 72% | 5min + 5 sub-detectors noisy, lower |
| v3 | 2026-08-25 20:36 | Stair-Pattern → w=1.2, tf=15min | **85%** | 20d 383 trades PF 1.08 = solid edge, raise |
| v4 | 2026-08-26 00:35 | Kell-Cycle → w=0.6, tf=15min | 72% | 4d 16 trades WR 56% R +2.36 = raise |

---

## Quick Reference

### Local 觸發

```bash
cd /workspace/YW-concept-ki7409/automation
set -a; source /workspace/apex-bootcamp/AUTOMATION/.env; set +a
.venv/bin/python scripts/llm_iterate_all.py --tg    # 完整 run + TG
.venv/bin/python scripts/llm_iterate_all.py         # 完整 run
.venv/bin/python scripts/llm_iterate.py             # 舊版 (只 iter worst 1 個)
```

### 手動 trigger GHA

```bash
# GitHub UI → Actions → "Strategy Ranking & LLM Iteration" → Run workflow
# 或 CLI:
gh workflow run strategy-ranking.yml
```

### 看 iteration 結果

```bash
# 最新 iteration log
ls -lt automation/reports/strategy_ranking/iterations/iteration_all_*.json | head -3
cat automation/reports/strategy_ranking/iterations/iteration_all_<TS>.md

# 或開 dashboard:
# https://r1j8xqlpbghjd.space.minimax.io  (Public)
# 或本地: python3 -m http.server 8000 --directory docs/
```

---

## 監控 + 異常處理

| 場景 | 自動處理 |
|------|----------|
| LLM 返 GRADE 但 confidence < 60% | Log only, 唔 apply |
| LLM response 有 <think> 標籤 | Strip 後再 parse |
| LLM 完全冇 response | Skip 嗰 agent，其他繼續 |
| 9 個 agent 全部 < 60% | 全部 log 為 skipped，照常 commit log file |
| Push 時 GHA 已 push 新 commit | `force-with-lease` 自動處理（rebase + 推）|
| Apply 之後效果差 | 下次 iter 會 reflect 新 live data，自動 re-iterate |

---

## 何時需要人手介入

- ⚠️ 同一 strategy 連續 3+ iter 都 > 80% confidence 但 live 持續 -R → 可能係 detector 根本有問題，要睇 source code
- ⚠️ 全部 9 個 agent 長期 conf < 30% → 可能 LLM prompt 要 tune，或者 live 數據太少
- ⚠️ 4d backtest vs live 落差大 (e.g. 4d +5R 但 live -5R) → 過擬合 backtest，要檢查 detector 條件
- ⚠️ 個別 strategy weight < 0.1 → 可能要考慮停用 (paper trade only)

---

## 對應 source files

- 入口: [`automation/scripts/llm_iterate_all.py`](../automation/scripts/llm_iterate_all.py) (1KB, parallel 9 workers)
- 觸發: [`.github/workflows/strategy-ranking.yml`](../.github/workflows/strategy-ranking.yml) (cron `30 13 * * 1-5`)
- 應用: [`automation/scripts/strategy_ranking.py`](../automation/scripts/strategy_ranking.py) line 41-51 (STRATEGIES)
- 應用: [`automation/src/yw_grader.py`](../automation/src/yw_grader.py) (STRATEGIES dict, per-strategy params)
- Logs: `automation/reports/strategy_ranking/iterations/`
- Dashboard: [docs/strategy-dashboard.html](strategy-dashboard.html) (live public URL above)
