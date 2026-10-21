# LLM Iteration Scientist — Deep 4D Analysis

**Date:** 2026-10-21 (HKT)  
**Source:** `automation/reports/live_scan/trades.jsonl` — 3265 closed trades (7d: 117 | 30d: 494 | all-time: 3265)  
**Window cutoff (7d):** 2026-10-14T02:46:38.882740+00:00  
**Dimensions:** aggregate · by grade · by direction · by ticker  
**Strategies covered:** 10  

> **Scope:** analysis only. No detector logic, `live_scan.py`, `strategy_overrides.json` or `weight_overrides.json` was modified. Parameter changes below are *proposals*, not applied changes.

## 1. Executive summary

| # | Finding | Severity |
|----|---------|----------|
| SF-1 | Exit model is binary — R is {-1.00, +1.618} only | 🟠 high |
| SF-2 | `min_strength` and `resample_tf` are dead config | 🔴 critical |
| SF-3 | `weight` is applied AFTER the confidence gate — it is not a strength filter | 🔴 critical |
| SF-4 | The 7d window is statistically thin | 🟠 high |
| SF-5 | Production scientist script reports all-time numbers as '7d' | 🔴 critical |
| SF-6 | The holdout-validated optimiser — the system's best levers — is completely dormant | 🔴 critical |
| SF-7 | The +1.618R monoculture is the *pre-override* regime — the new exits are untested | 🟡 medium |
| SF-8 | The scientist's LLM parser can never yield a parameter — auto-apply is structurally impossible | 🔴 critical |

**Strategy league table (7d):**

| Strategy | n(7d) | WR | PF | Total R | Avg R | MaxDD | 30d PF | 30d R | All-time R |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| **CRT** | 35 | 31.4% | 0.742 | -6.20 | -0.177 | -10.06 | 0.907 | -6.13 | +27.86 |
| **B1-3in1** | 5 | 0.0% | 0.0 | -5.00 | -1.000 | -5.0 | 0.0 | -23.00 | -39.00 |
| **RSI-Div** | 3 | 0.0% | 0.0 | -3.00 | -1.000 | -3.0 | 0.27 | -4.38 | +47.91 |
| **50-20-Pullback** | 39 | 35.9% | 0.906 | -2.35 | -0.060 | -8.53 | 0.929 | -8.21 | -69.17 |
| **Two-Yang** | 4 | 25.0% | 0.539 | -1.38 | -0.345 | -2.0 | 0.539 | -8.29 | -24.27 |
| **Kell-Cycle** | 1 | 0.0% | 0.0 | -1.00 | -1.000 | -1.0 | 1.079 | +0.24 | +9.59 |
| **Stair** | 19 | 36.8% | 0.944 | -0.67 | -0.035 | -5.0 | 0.861 | -8.61 | -19.84 |
| **H-Pattern** | 1 | 100.0% | 1.618 | +1.62 | +1.618 | 0.0 | 2.589 | +7.94 | -12.19 |
| **3-Pushes** | 8 | 50.0% | 1.618 | +2.47 | +0.309 | -2.0 | 1.375 | +7.51 | +34.82 |
| **B1** | 2 | 100.0% | 3.236 | +3.24 | +1.618 | 0.0 | 1.618 | +1.85 | +3.33 |

## 2. Cross-cutting structural findings

### SF-1 — Exit model is binary — R is {-1.00, +1.618} only

Across all 3265 trades the R-multiple takes only these values: -1R ×2021, +1.618R ×1191, +1R ×53. Every trade is either a clean +1.618R target hit or a -1.00R stop-out (there is no partial exit, no trailing, no scale-out). Consequence: the payoff ratio is structurally fixed at 1.618 for every strategy, so no strategy can be improved by tuning the exit, and **win rate is the only performance lever available**. Any recommendation about 'better risk/reward' is not implementable with the current exit model.

*Impact:* Changes the whole optimisation target: optimise hit rate, not R:R.

### SF-2 — `min_strength` and `resample_tf` are dead config

`automation/scripts/live_scan.py:206-209` copies `min_strength` and `resample_tf` out of strategy_overrides.json into the per-strategy config, but no code path ever reads them back (the detectors are called with explicit arguments; there is no `**cfg["args"]` spread). Confirmed by grep: the only other references are in param_optimizer.py, which writes them. Consequence: the last three accepted LLM param changes (RSI-Div 2026-10-17, 3-Pushes 2026-10-18, Kell-Cycle 2026-10-20) each applied `resample_tf: 15min` — all three were **no-ops**. Only the `weight` part of those changes had any effect. RSI-Div's own base arg `resample_15m: True` is dead for the same reason.

*Impact:* 3 of the last 3 'optimisations' burned confidence budget on a no-op parameter.

### SF-3 — `weight` is applied AFTER the confidence gate — it is not a strength filter

live_scan.py order is: LLM grade (1505) → BTC boost (1511) → `conf < min_conf` gate (1517) → grade gate (1520) → **weight scaling (1536)**. The code comment above line 1536 claims weight makes a down-weighted strategy 'fire less often / need more confluence', but by the time the weight is applied the signal has already passed both gates. `weight` therefore only (a) breaks stacking ties on the same ticker+direction (line 747) and (b) scales the confidence published to the AI-Trader (line 1736). It does **not** filter the strategy's own signals.

*Impact:* A weight cut is a weak instrument: it cannot fix a strategy that fires 100% of its trades.

### SF-4 — The 7d window is statistically thin

117 trades in 7d across 10 strategies (median 4.5 per strategy), versus 494 in 30d and 3265 all-time. 6 of the 10 strategies have fewer than 8 trades in 7d. Per-strategy 7d numbers are directional, not conclusive; every recommendation in this report is therefore cross-checked against the 30d and all-time windows, and confidence is capped where the windows disagree.

*Impact:* Confidence must be discounted, and per-strategy n<8 findings are labelled anecdotal.

### SF-5 — Production scientist script reports all-time numbers as '7d'

`automation/scripts/llm_iteration_scientist.py:139-183` filters signals to 7d but applies **no date filter at all to trades**. Its 'PERFORMANCE (7d window)' block therefore reports the full history — 1011 trades for 50-20-Pullback vs 39 in the real 7d window, 701 for CRT vs 35. It also computes `profit_factor` as wins/losses (line 190 — a win/loss *ratio*, not gross profit ÷ gross loss), and it pattern-matches 'B1' such that the B1 agent absorbs all 39 B1-3in1 trades (B1 shows 54 trades instead of 15). Because the 'profit factor' is really a win-rate ratio, **profitable strategies are graded D**: in the manual run of 2026-10-21 09:44 HKT CRT was graded D while showing +27.62R, and 3-Pushes was graded D while showing +34.82R. Seven of ten strategies came out as grade D.

*Impact:* The daily 00:00 HKT run has been grading strategies on wrong data, and its D grades are not evidence that a strategy loses money.

### SF-6 — The holdout-validated optimiser — the system's best levers — is completely dormant

`automation/config/agent_params.json` holds per-(strategy, ticker) cell configs for 9 strategies, each with `drop_tickers`/`keep_tickers`, `min_conf`, `grade_filter`, `direction`, `weekday_exclude`, `hours` and the exit set (`t2_r`, `breakeven_at_r`, `partial_at_r`, `stop_mult`, `max_bars_held`). These are exactly the levers the 4D analysis needs. But **every entry has `_validated` unset and `validated_on_holdout: false`**, each carrying the note *"not published: did not improve on both the live track and the independent 180-day one-hour track"* (0/9 validated). `live_scan.py:1663` gates the whole block behind `if _ap and _ap.get("_validated")`, so **not one of these levers is applied at runtime**. Matching commit: `1733faa3 feat(optimizer): second independent track — 0 of 9 configurations survive it`.

*Impact:* The system has a correct, holdout-gated optimiser and an LLM loop that pushes mostly-dead parameters. The high-value move is to make the validated path usable, not to keep tuning `weight`.

### SF-7 — The +1.618R monoculture is the *pre-override* regime — the new exits are untested

`exit_overrides.json` (written 2026-10-20T14:00:02.325747+00:00, runs=6) carries learned `t2_r` (2.0–3.0) and `breakeven_at_r` (0.5–1.5) for 6 strategies, and `resolve_exit_config` (live_scan.py:902) does read it. But every one of the 1,189 winning trades in the file is exactly +1.618R, because the last trade was recorded at 2026-10-20T13:00Z and the overrides were written at 2026-10-20T14:00Z — **after** the data. Furthermore `rl_arm.assign_arm` only applies an override during that strategy's RL half-period, and 4 strategies (3-Pushes, CRT, B1, B1-3in1) have no override at all and are therefore permanently on the default template.

*Impact:* Do not read the +1.618R monoculture as proof that exits cannot be improved. The first 14-day RL window is the real test, and it has not happened yet.

### SF-8 — The scientist's LLM parser can never yield a parameter — auto-apply is structurally impossible

`llm_iteration_scientist.py:291` parses the LLM reply with a single regex that demands **pipe-delimited** fields (`GRADE: A|B|C|D | CONFIDENCE: n | DIAGNOSIS: … | REASON: … | SUGGESTED_PARAMS: {…}`). MiniMax-M3 actually answers with **newline-delimited** fields, so the main regex never matches; the partial fallback at lines 306-312 recovers GRADE and CONFIDENCE but leaves `reason` and `suggested_params` empty. `auto_apply` (line 302) requires a non-empty `suggested_params`, so **the scientist can never auto-apply anything**, no matter how confident the model is. Measured on the manual run of 2026-10-21 09:44 HKT (`iteration_scientist_20261021_094417.json`): 10/10 agents have `suggested_params: {}` and `n_auto_applied: 0` — including `yw-two-yang`, which was graded **B with confidence 95** and whose reply explicitly carried `SUGGESTED_PARAMS: {"min_grad…` (truncated out of the diagnosis field). The sibling script `llm_iterate_all.py:91` gets this right — it scrapes `weight` with a loose regex (`r"weight['\"]?\s*[:=]\s*([0-9.]+)"`) that survives any format, which is why `strategy_overrides.json` does contain real applied changes (3 applications, last 2026-10-20) while the scientist's own proposals are always empty. The parser itself was **not** among the changes the remote made on 2026-10-21 (commits `c3ea8421`, `9a05168e`) — those only routed the call through the new shared `automation/src/llm_client.py`, which now returns `(content, error)` and lets the caller see the real cause instead of `KeyError: 'choices'`. But the scientist **discards that error** (`content, _llm_err = chat(...)`, lines 279-281), so a rate-limited call is now reported as *"[Rule-based - LLM unavailable]"* with the HTTP 429 detail thrown away, and `llm_client` itself has **no retry or backoff** for 429. Compounding everything, the script fans out to 10 workers (line 437) against a 5-hour Token Plan window: 8 of 10 calls in the 09:44 run returned HTTP 429 and were replaced by the rule-based fallback, which reuses the broken win/loss-ratio 'profit factor' from SF-5.

*Impact:* The workflow advertises 'Auto-applies high-confidence (>= 60%) parameter changes', but that path has never fired from the scientist. Every 'optimisation' in the audit log came from the other script, and half of those changes were to a dead parameter (SF-2).

## 3. Per-strategy 4D analysis

### 50-20-Pullback

*Live config:* weight=0.948 · resample_tf=(none — dead) · min_strength=(none — dead)

**D1 · Aggregate**

| Window | n | Wins | Losses | WR | PF | Total R | Avg R | Avg win | Avg loss | Payoff | MaxDD | Loss streak |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 7d | 39 | 14 | 25 | 35.9% | 0.906 | -2.35 | -0.060 | 1.618 | 1.0 | 1.618 | -8.53 | 6 |
| 30d | 181 | 66 | 115 | 36.5% | 0.929 | -8.21 | -0.045 | 1.618 | 1.0 | 1.618 | -17.35 | 6 |
| all-time | 1011 | 364 | 647 | 36.0% | 0.893 | -69.17 | -0.068 | 1.587 | 1.0 | 1.587 | -131.52 | 6 |

**D2 · By grade**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| A | 3 | 33.3% | 0.809 | -0.38 | 5 | 20.0% | 0.405 | -2.38 |
| B | 36 | 36.1% | 0.915 | -1.97 | 176 | 36.9% | 0.947 | -5.83 |

**D3 · By direction**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| LONG | 19 | 26.3% | 0.578 | -5.91 | 109 | 34.9% | 0.866 | -9.52 |
| SHORT | 20 | 45.0% | 1.324 | +3.56 | 72 | 38.9% | 1.03 | +1.30 |

**D4 · By ticker**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| BTC-USD | 34 | 32.4% | 0.774 | -5.20 | 145 | 33.8% | 0.826 | -16.72 |
| M2K=F | 1 | 100.0% | 1.618 | +1.62 | 11 | 45.5% | 1.348 | +2.09 |
| MES=F | 4 | 50.0% | 1.618 | +1.24 | 17 | 47.1% | 1.438 | +3.94 |

**Top 3 issues (deterministic, evidence-ranked):**

1. **[aggregate · medium]** 7d max drawdown -8.53R with 6-loss streak  
   Cumulative R curve in 7d drew down -8.53R (n=39, 6 consecutive losses). Total 7d R is -2.3R; the drawdown shape matters more than the final number.
2. **[confidence · medium]** Signal confidence is not calibrated — the <70 bucket beats the 70-79 bucket  
   7d: <70 n=21 PF=1.214 R=+2.6 vs 70-79 n=15 PF=0.809 R=-1.9. The confidence score the LLM assigns does not order outcomes, so raising `min_conf` would discard trades without improving the mix.
3. **[ticker · medium]** 87% of 7d trades came from BTC-USD  
   n=34 of 39 (87%) on BTC-USD, which contributed -5.2R. The 7d result is effectively a single-instrument bet.

**LLM scientist verdict:**

> **Grade D · confidence 82% · evidence moderate**  
> 策略整體呈負期望且拖累集中於 BTC 多單，但現有參數只能降低曝險，無法修復方向性優勢。  
> *Why:* 小幅降權可降低負期望曝險與回撤；因無法按方向過濾，不能聲稱提升每筆期望值。
>
> *Consensus over 3/3 samples* — confidence samples [74, 82, 82] (spread 8), param samples [0.8, 0.9, 0.9] (agreement 0.67).
>
> **Suggested params:** `{"weight": 0.9}`  
> 由0.948小幅下調至0.90（約降低5.1%），作為最小化風控變更；此數值未經候選權重回測，不代表最佳權重。
>
> LLM-listed issues:
> - 7日、30日及全時程均為負期望；全時程1011筆、PF 0.893、累計-69.17R、最大回撤-131.52R
> - LONG在7日與30日均拖累，分別為-5.91R與-9.52R，但缺少全時程方向資料驗證
> - 7日BTC佔87%並貢獻-5.20R；信心分數排序反向，提高門檻可能反而排除較佳交易

### CRT

*Live config:* weight=1.3 · resample_tf=15min · min_strength=(none — dead)

**D1 · Aggregate**

| Window | n | Wins | Losses | WR | PF | Total R | Avg R | Avg win | Avg loss | Payoff | MaxDD | Loss streak |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 7d | 35 | 11 | 24 | 31.4% | 0.742 | -6.20 | -0.177 | 1.618 | 1.0 | 1.618 | -10.06 | 0 |
| 30d | 103 | 37 | 66 | 35.9% | 0.907 | -6.13 | -0.060 | 1.618 | 1.0 | 1.618 | -10.82 | 0 |
| all-time | 701 | 281 | 420 | 40.1% | 1.066 | +27.86 | +0.040 | 1.594 | 1.0 | 1.594 | -38.56 | 0 |

**D2 · By grade**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| A | 7 | 42.9% | 1.214 | +0.85 | 21 | 33.3% | 0.809 | -2.67 |
| B | 28 | 28.6% | 0.647 | -7.06 | 82 | 36.6% | 0.933 | -3.46 |

**D3 · By direction**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| LONG | 19 | 15.8% | 0.303 | -11.15 | 53 | 28.3% | 0.639 | -13.73 |
| SHORT | 16 | 50.0% | 1.618 | +4.94 | 50 | 44.0% | 1.271 | +7.60 |

**D4 · By ticker**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| BTC-USD | 6 | 16.7% | 0.324 | -3.38 | 22 | 31.8% | 0.755 | -3.67 |
| GC=F | 3 | 33.3% | 0.809 | -0.38 | 3 | 33.3% | 0.809 | -0.38 |
| M2K=F | 6 | 16.7% | 0.324 | -3.38 | 21 | 28.6% | 0.647 | -5.29 |
| MES=F | 9 | 55.6% | 2.022 | +4.09 | 23 | 47.8% | 1.483 | +5.80 |
| MGC=F | 4 | 25.0% | 0.539 | -1.38 | 17 | 29.4% | 0.674 | -3.91 |
| MNQ=F | 7 | 28.6% | 0.647 | -1.76 | 17 | 41.2% | 1.133 | +1.33 |

**Top 3 issues (deterministic, evidence-ranked):**

1. **[direction · high]** LONG side loses while the other side wins  
   7d LONG: n=19, PF=0.303, -11.1R. 30d opposite side: n=50, PF=1.271, +7.6R. The edge is direction-specific, not setup-specific.
2. **[ticker · high]** MNQ=F is a persistent drag (PF=0.647, -1.8R)  
   7d MNQ=F: n=7, PF=0.647, -1.8R, WR 28.6%. 30d best other ticker: PF=1.483 over n=23. Concentrating on the stronger instrument should lift the blend.
3. **[ticker · high]** BTC-USD is a persistent drag (PF=0.324, -3.4R)  
   7d BTC-USD: n=6, PF=0.324, -3.4R, WR 16.7%. 30d best other ticker: PF=1.483 over n=23. Concentrating on the stronger instrument should lift the blend.

**LLM scientist verdict:**

> **Grade C · confidence 45% · evidence moderate**  
> LONG side is structurally unprofitable (7d PF=0.303 n=19, 30d PF=0.639 n=53) while SHORT works (30d PF=1.271 n=50); weight=1.3 over-amplifies during drawdown  
> *Why:* Halve weight to cap exposure to bleeding LONG signals during drawdown; cannot filter direction/ticker directly with live params
>
> *Consensus over 3/3 samples* — confidence samples [55, 58, 61] (spread 6), param samples [0.8, 0.7, 0.5] (agreement 0.33).
>
> ⚠️ proposal not stable across samples ([0.5, 0.7, 0.8]), confidence capped at 45
>
> **Suggested params:** `{"weight": 0.5}`  
> Cutting weight from 1.3 to 0.7 scales 7d loss from -6.20R to ~-3.34R and 30d from -6.13R to ~-3.30R; preserves SHORT edge while limiting LONG damage; all-time +27.86R still positive at ~+15R
>
> LLM-listed issues:
> - LONG direction bleeds -11.15R (7d) and -13.73R (30d); SHORT contributes +4.94R / +7.60R — direction-specific edge, not setup-specific
> - BTC-USD and M2K=F each lost -3.38R at PF=0.324 (7d) while MES=F gained +4.09R at PF=2.022 — ticker concentration drag
> - Dead params `min_strength`/`resample_tf` block surgical direction/ticker filtering; weight is the only runtime lever

### Stair

*Live config:* weight=1.1 · resample_tf=(none — dead) · min_strength=(none — dead)

**D1 · Aggregate**

| Window | n | Wins | Losses | WR | PF | Total R | Avg R | Avg win | Avg loss | Payoff | MaxDD | Loss streak |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 7d | 19 | 7 | 12 | 36.8% | 0.944 | -0.67 | -0.035 | 1.618 | 1.0 | 1.618 | -5.0 | 5 |
| 30d | 95 | 33 | 62 | 34.7% | 0.861 | -8.61 | -0.091 | 1.618 | 1.0 | 1.618 | -12.55 | 5 |
| all-time | 346 | 126 | 220 | 36.4% | 0.91 | -19.84 | -0.057 | 1.589 | 1.0 | 1.589 | -44.26 | 5 |

**D2 · By grade**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| A | 13 | 38.5% | 1.011 | +0.09 | 66 | 34.8% | 0.865 | -5.79 |
| B | 6 | 33.3% | 0.809 | -0.76 | 29 | 34.5% | 0.852 | -2.82 |

**D3 · By direction**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| SHORT | 19 | 36.8% | 0.944 | -0.67 | 95 | 34.7% | 0.861 | -8.61 |

**D4 · By ticker**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| GC=F | 1 | 0.0% | 0.0 | -1.00 | 1 | 0.0% | 0.0 | -1.00 |
| M2K=F | 4 | 50.0% | 1.618 | +1.24 | 25 | 32.0% | 0.761 | -4.06 |
| MGC=F | 8 | 12.5% | 0.231 | -5.38 | 31 | 25.8% | 0.563 | -10.06 |
| MNQ=F | 6 | 66.7% | 3.236 | +4.47 | 28 | 50.0% | 1.618 | +8.65 |

**Top 3 issues (deterministic, evidence-ranked):**

1. **[ticker · high]** MGC=F is a persistent drag (PF=0.231, -5.4R)  
   7d MGC=F: n=8, PF=0.231, -5.4R, WR 12.5%. 30d best other ticker: PF=1.618 over n=28. Concentrating on the stronger instrument should lift the blend.
2. **[aggregate · medium]** 7d max drawdown -5.0R with 5-loss streak  
   Cumulative R curve in 7d drew down -5.0R (n=19, 5 consecutive losses). Total 7d R is -0.7R; the drawdown shape matters more than the final number.
3. **[confidence · medium]** Signal confidence is not calibrated — the 70-79 bucket beats the 90+ bucket  
   7d: 70-79 n=4 PF=1.618 R=+1.2 vs 90+ n=10 PF=0.693 R=-2.1. The confidence score the LLM assigns does not order outcomes, so raising `min_conf` would discard trades without improving the mix.

**LLM scientist verdict:**

> **Grade C · confidence 45% · evidence moderate**  
> Stair is net-negative across all windows (7d/30d/all); the MGC=F ticker is the dominant persistent drag and weight=1.1 over-sizes a losing strategy.  
> *Why:* Cutting weight from 1.1 to 0.7 scales the MGC=F drag down while still capturing the persistent MNQ=F edge (PF 3.236 7d / 1.618 30d).
>
> *Consensus over 3/3 samples* — confidence samples [45, 55, 55] (spread 10), param samples [0.6, 0.7, 0.5] (agreement 0.33).
>
> ⚠️ proposal not stable across samples ([0.5, 0.6, 0.7]), confidence capped at 45
>
> **Suggested params:** `{"weight": 0.5}`  
> weight is the only live param. 1.1 over-sizes a -0.057R/trade avg strategy; 0.7 is the smallest decisive cut that meaningfully dampens MGC=F bleed (~-5.4R 7d, ~-10R 30d) while preserving the only sustained positive ticker cluster (MNQ=F +4.5R 7d, +8.6R 30d). Larger cut (0.5) would suppress too much of the MNQ edge; smaller (0.9) only trims ~18%.
>
> LLM-listed issues:
> - MGC=F is a persistent drag (7d PF=0.231, 30d PF=0.563) and cannot be filtered via the only live knob
> - Aggregate is negative in every window; 7d -0.67R, 30d -8.61R, all-time -19.84R — capital at risk is not earning its keep
> - Signal confidence is inverted (70-79 PF=1.618 vs 90+ PF=0.693 7d) so min_conf is unsafe; cannot be applied via weight
> - Longest losing streak 5 with maxDD -5R (7d) and -12.55R (30d) confirms edge is absent at current sizing

### 3-Pushes

*Live config:* weight=1.2 · resample_tf=15min · min_strength=(none — dead)

**D1 · Aggregate**

| Window | n | Wins | Losses | WR | PF | Total R | Avg R | Avg win | Avg loss | Payoff | MaxDD | Loss streak |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 7d | 8 | 4 | 4 | 50.0% | 1.618 | +2.47 | +0.309 | 1.618 | 1.0 | 1.618 | -2.0 | 2 |
| 30d | 37 | 17 | 20 | 45.9% | 1.375 | +7.51 | +0.203 | 1.618 | 1.0 | 1.618 | -6.0 | 2 |
| all-time | 425 | 178 | 247 | 41.9% | 1.141 | +34.82 | +0.082 | 1.583 | 1.0 | 1.583 | -24.44 | 2 |

**D2 · By grade**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| B | 8 | 50.0% | 1.618 | +2.47 | 37 | 45.9% | 1.375 | +7.51 |

**D3 · By direction**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| LONG | 1 | 100.0% | 1.618 | +1.62 | 15 | 53.3% | 1.849 | +5.94 |
| SHORT | 7 | 42.9% | 1.214 | +0.85 | 22 | 40.9% | 1.12 | +1.56 |

**D4 · By ticker**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| M2K=F | 1 | 100.0% | 1.618 | +1.62 | 5 | 40.0% | 1.079 | +0.24 |
| MES=F | 2 | 50.0% | 1.618 | +0.62 | 11 | 45.5% | 1.348 | +2.09 |
| MGC=F | 2 | 0.0% | 0.0 | -2.00 | 11 | 45.5% | 1.348 | +2.09 |
| MNQ=F | 3 | 66.7% | 3.236 | +2.24 | 9 | 55.6% | 2.022 | +4.09 |

**Top 3 issues (deterministic, evidence-ranked):**

1. **[aggregate · low]** No dominant 4D drag detected  
   7d n=8, PF=1.618, +2.5R; 30d n=37, PF=1.375. No grade/direction/ticker bucket clears the significance thresholds.
2. **[direction · low]** No actionable direction split in 7d — dimension checked, nothing to filter on  
   7d direction buckets: LONG n=1 PF=1.618 R=+1.6R; SHORT n=7 PF=1.214 R=+0.9R. No bucket clears the significance threshold (n≥5 and PF<0.8 for a drag, or PF≥1.1 elsewhere for a keeper), so no filter is proposed on this dimension. It is reported so the dimension is accounted for.
3. **[grade · low]** No actionable grade split in 7d — dimension checked, nothing to filter on  
   7d grade buckets: B n=8 PF=1.618 R=+2.5R. No bucket clears the significance threshold (n≥5 and PF<0.8 for a drag, or PF≥1.1 elsewhere for a keeper), so no filter is proposed on this dimension. It is reported so the dimension is accounted for.

**LLM scientist verdict:**

> **Grade C · confidence 38% · evidence weak**  
> Strategy posts positive expectancy but with elevated maxDD relative to total R across all windows and only marginal all-time edge (avgR=+0.082R), with no specific bucket-level drag identifiable.  
> *Why:* Trim weight from 1.2 to 1.0 to dampen the overall exposure gap that produced -24R maxDD on only +34.8R all-time.
>
> *Consensus over 3/3 samples* — confidence samples [25, 38, 48] (spread 23), param samples [1.0, 1.0] (agreement 1.0).
>
> **Suggested params:** `{"weight": 1.0}`  
> Reduces exposure ~17% to better match the strategy's modest all-time edge (avgR=0.082R) and high DD-to-gain ratio while preserving positive 7d/30d expectancy; smallest change consistent with risk-on-risk profile.
>
> LLM-listed issues:
> - no dominant bucket-level drag identified across grade/direction/ticker in 7d or 30d
> - maxDD/TotalR ratio is high in all windows (7d 0.81, 30d 0.80, all-time 0.70), indicating over-exposure
> - all-time PF=1.141 with avgR=0.082R shows only a thin long-run edge
> - 30d SHORT (n=22, PF=1.120) materially lags LONG (n=15, PF=1.849) but no live param can filter direction
> - 7d sample is small (n=8) and confidence buckets below 80 lack statistical strength
> - min_strength and resample_tf are dead config so no selection filter is actionable

### B1-3in1

*Live config:* weight=(default 1.0) · resample_tf=(none — dead) · min_strength=(none — dead)

**D1 · Aggregate**

| Window | n | Wins | Losses | WR | PF | Total R | Avg R | Avg win | Avg loss | Payoff | MaxDD | Loss streak |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 7d | 5 | 0 | 5 | 0.0% | 0.0 | -5.00 | -1.000 | 0.0 | 1.0 | 0.0 | -5.0 | 5 |
| 30d | 23 | 0 | 23 | 0.0% | 0.0 | -23.00 | -1.000 | 0.0 | 1.0 | 0.0 | -23.0 | 23 |
| all-time | 39 | 0 | 39 | 0.0% | 0.0 | -39.00 | -1.000 | 0.0 | 1.0 | 0.0 | -39.0 | 39 |

**D2 · By grade**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| A | 1 | 0.0% | 0.0 | -1.00 | 2 | 0.0% | 0.0 | -2.00 |
| B | 4 | 0.0% | 0.0 | -4.00 | 21 | 0.0% | 0.0 | -21.00 |

**D3 · By direction**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| FLAT | 5 | 0.0% | 0.0 | -5.00 | 23 | 0.0% | 0.0 | -23.00 |

**D4 · By ticker**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| M2K=F | 1 | 0.0% | 0.0 | -1.00 | 2 | 0.0% | 0.0 | -2.00 |
| MES=F | 2 | 0.0% | 0.0 | -2.00 | 6 | 0.0% | 0.0 | -6.00 |
| MGC=F | 1 | 0.0% | 0.0 | -1.00 | 8 | 0.0% | 0.0 | -8.00 |
| MNQ=F | 1 | 0.0% | 0.0 | -1.00 | 5 | 0.0% | 0.0 | -5.00 |

**Top 3 issues (deterministic, evidence-ranked):**

1. **[aggregate · high]** Degenerate: 39/39 trades are -1.0R stop-outs, 0% win rate  
   Every trade in the 7d/30d/all-time windows is a full stop-out at exactly -1.0R (total -39.0R). Every trade also carries direction='none' (FLAT) — the detector never resolves a direction, so the exit logic cannot place a target and the position is closed at the stop. This is a detector/wiring bug, not a parameter problem: no weight change can fix it. Recommended action: disable the strategy (weight 0 / remove from STRATEGIES) until the direction field is fixed — this is the single largest R leak in the pool.
2. **[sample · high]** 7d sample too thin (n=5)  
   Only 5 trades in the 7d window. 30d n=23, all-time n=39. Per-strategy 7d conclusions are statistically unreliable; base any param change on the 30d/all-time evidence instead.
3. **[grade · low]** No actionable grade split in 7d — dimension checked, nothing to filter on  
   7d grade buckets: A n=1 PF=0.0 R=-1.0R; B n=4 PF=0.0 R=-4.0R. No bucket clears the significance threshold (n≥5 and PF<0.8 for a drag, or PF≥1.1 elsewhere for a keeper), so no filter is proposed on this dimension. It is reported so the dimension is accounted for.

**LLM scientist verdict:**

> **Grade D · confidence 95% · evidence strong**  
> Detector never resolves direction (all trades FLAT/none), so exit logic can only hit the stop — every trade is an identical -1R stop-out, a wiring bug not a parameter problem.  
> *Why:* Set weight=0 to halt a pure -1R-per-trade bleed; smallest change, largest drag removed until direction wiring is repaired.
>
> *Consensus over 3/3 samples* — confidence samples [92, 95, 95] (spread 3), param samples [0.0, 0.0, 0.0] (agreement 1.0).
>
> **Suggested params:** `{"weight": 0.0}`  
> weight is the only live knob; 0 disables the strategy in live_scan.py and immediately stops the -5R/wk drain. Any non-zero weight continues to lose 1R per trade because the bug is pre-execution, not tuning-driven. Once direction emission is fixed and a non-degenerate sample (n≥30, PF>1.0) is re-validated, weight can be restored to ~1.0.
>
> LLM-listed issues:
> - Degenerate 0% WR with every trade exiting at exactly -1.0R across 39 all-time / 23 30d / 5 7d trades
> - Direction field always 'none'/'FLAT' — target side of the R-multiple formula never fires
> - Single largest R-leak in the pool (-39.0R all-time, -23.0R 30d) with no variance to extract a signal
> - No parameter change (incl. weight) can repair a missing direction field — must be disabled until fixed
> - Per-strategy 7d sample is thin (n=5), but 30d/all-time confirm the identical outcome so sign-off is justified

### Two-Yang

*Live config:* weight=(default 1.0) · resample_tf=(none — dead) · min_strength=(none — dead)

**D1 · Aggregate**

| Window | n | Wins | Losses | WR | PF | Total R | Avg R | Avg win | Avg loss | Payoff | MaxDD | Loss streak |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 7d | 4 | 1 | 3 | 25.0% | 0.539 | -1.38 | -0.345 | 1.618 | 1.0 | 1.618 | -2.0 | 1 |
| 30d | 24 | 6 | 18 | 25.0% | 0.539 | -8.29 | -0.345 | 1.618 | 1.0 | 1.618 | -10.53 | 1 |
| all-time | 222 | 76 | 146 | 34.2% | 0.834 | -24.27 | -0.109 | 1.602 | 1.0 | 1.602 | -35.4 | 1 |

**D2 · By grade**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| B | 4 | 25.0% | 0.539 | -1.38 | 24 | 25.0% | 0.539 | -8.29 |

**D3 · By direction**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| LONG | 4 | 25.0% | 0.539 | -1.38 | 24 | 25.0% | 0.539 | -8.29 |

**D4 · By ticker**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| BTC-USD | 2 | 50.0% | 1.618 | +0.62 | 9 | 22.2% | 0.462 | -3.76 |
| M2K=F | 1 | 0.0% | 0.0 | -1.00 | 3 | 33.3% | 0.809 | -0.38 |
| MES=F | 1 | 0.0% | 0.0 | -1.00 | 6 | 33.3% | 0.809 | -0.76 |

**Top 3 issues (deterministic, evidence-ranked):**

1. **[sample · high]** 7d sample too thin (n=4)  
   Only 4 trades in the 7d window. 30d n=24, all-time n=222. Per-strategy 7d conclusions are statistically unreliable; base any param change on the 30d/all-time evidence instead.
2. **[direction · low]** No actionable direction split in 7d — dimension checked, nothing to filter on  
   7d direction buckets: LONG n=4 PF=0.539 R=-1.4R. No bucket clears the significance threshold (n≥5 and PF<0.8 for a drag, or PF≥1.1 elsewhere for a keeper), so no filter is proposed on this dimension. It is reported so the dimension is accounted for.
3. **[grade · low]** No actionable grade split in 7d — dimension checked, nothing to filter on  
   7d grade buckets: B n=4 PF=0.539 R=-1.4R. No bucket clears the significance threshold (n≥5 and PF<0.8 for a drag, or PF≥1.1 elsewhere for a keeper), so no filter is proposed on this dimension. It is reported so the dimension is accounted for.

**LLM scientist verdict:**

> **Grade D · confidence 62% · evidence moderate**  
> Two-Yang is a persistent net loser across 7d, 30d, and all-time (PF<1.0 in all windows, -24.27R lifetime), warranting reduced allocation.  
> *Why:* Persistent sub-1.0 PF across all windows means current weight allocates too much capital to a losing edge; minimum weight cuts drag fastest.
>
> *Consensus over 3/3 samples* — confidence samples [58, 62, 74] (spread 16), param samples [0.5, 0.5, 0.5] (agreement 1.0).
>
> **Suggested params:** `{"weight": 0.5}`  
> 0.5 is the floor of the allowed range and proportional to the severity: all-time PF 0.834 implies ~17% expected loss per unit risk, and 30d PF 0.539 implies ~46% — halving weight is the smallest change that materially reduces capital at risk while preserving the strategy for re-evaluation once a full 30d sample accumulates with a non-trivial edge.
>
> LLM-listed issues:
> - 7d sample too thin (n=4) but directionally confirms 30d loss pattern
> - All-time n=222 with PF=0.834 and -24.27R total shows chronic underperformance, not noise
> - Only LONG signals, all grade B — no diversification in signal type to rescue edge
> - 30d PF=0.539 with -8.29R shows the drawdown is accelerating, not mean-reverting
> - MGC=F and M2K=F tickers contributing outsized losses relative to trade count

### RSI-Div

*Live config:* weight=0.6 · resample_tf=15min · min_strength=(none — dead)

**D1 · Aggregate**

| Window | n | Wins | Losses | WR | PF | Total R | Avg R | Avg win | Avg loss | Payoff | MaxDD | Loss streak |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 7d | 3 | 0 | 3 | 0.0% | 0.0 | -3.00 | -1.000 | 0.0 | 1.0 | 0.0 | -3.0 | 3 |
| 30d | 7 | 1 | 6 | 14.3% | 0.27 | -4.38 | -0.626 | 1.618 | 1.0 | 1.618 | -5.0 | 5 |
| all-time | 180 | 88 | 92 | 48.9% | 1.521 | +47.91 | +0.266 | 1.59 | 1.0 | 1.59 | -10.67 | 5 |

**D2 · By grade**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| A | 3 | 0.0% | 0.0 | -3.00 | 6 | 16.7% | 0.324 | -3.38 |

**D3 · By direction**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| LONG | 2 | 0.0% | 0.0 | -2.00 | 4 | 25.0% | 0.539 | -1.38 |
| SHORT | 1 | 0.0% | 0.0 | -1.00 | 3 | 0.0% | 0.0 | -3.00 |

**D4 · By ticker**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| MES=F | 1 | 0.0% | 0.0 | -1.00 | 4 | 25.0% | 0.539 | -1.38 |
| MGC=F | 2 | 0.0% | 0.0 | -2.00 | 3 | 0.0% | 0.0 | -3.00 |

**Top 3 issues (deterministic, evidence-ranked):**

1. **[sample · high]** 7d sample too thin (n=3)  
   Only 3 trades in the 7d window. 30d n=7, all-time n=180. Per-strategy 7d conclusions are statistically unreliable; base any param change on the 30d/all-time evidence instead.
2. **[direction · low]** No actionable direction split in 7d — dimension checked, nothing to filter on  
   7d direction buckets: LONG n=2 PF=0.0 R=-2.0R; SHORT n=1 PF=0.0 R=-1.0R. No bucket clears the significance threshold (n≥5 and PF<0.8 for a drag, or PF≥1.1 elsewhere for a keeper), so no filter is proposed on this dimension. It is reported so the dimension is accounted for.
3. **[grade · low]** No actionable grade split in 7d — dimension checked, nothing to filter on  
   7d grade buckets: A n=3 PF=0.0 R=-3.0R. No bucket clears the significance threshold (n≥5 and PF<0.8 for a drag, or PF≥1.1 elsewhere for a keeper), so no filter is proposed on this dimension. It is reported so the dimension is accounted for.

**LLM scientist verdict:**

> **Grade C · confidence 28% · evidence weak**  
> 可確認的是 7d 樣本過薄，且 7d/30d 負績與 all-time 正績衝突，資料不足以定位參數根因。  
> *Why:* 7d/30d 與 all-time 訊號相反，且無 weight 對照；目前調權缺乏證據。
>
> *Consensus over 3/3 samples* — confidence samples [28, 28, 40] (spread 12), param samples [0.5, 0.4] (agreement 0.5).
>
> **Suggested params:** `{"weight": 0.4}`  
> 維持 weight=0.6；all-time 正 expectancy 支持保留策略，但近期樣本不足，無法證明調高或調低權重會改善結果。
>
> LLM-listed issues:
> - 7d 僅 3 筆、30d 僅 7 筆；近期結果可靠度有限，7d 尤其屬 anecdote。
> - 30d 總計 -4.38R、PF 0.27，但 all-time n=180、PF 1.521、+47.91R，跨窗口訊號相反。
> - 方向、grade 與 ticker 桶均缺乏 n≥5 且有 all-time 同向驗證的可用拆分；亦無不同 weight 的對照結果。

### B1

*Live config:* weight=0.9 · resample_tf=15min · min_strength=(none — dead)

**D1 · Aggregate**

| Window | n | Wins | Losses | WR | PF | Total R | Avg R | Avg win | Avg loss | Payoff | MaxDD | Loss streak |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 7d | 2 | 2 | 0 | 100.0% | 3.236 | +3.24 | +1.618 | 1.618 | 0.0 | 0.0 | 0.0 | 0 |
| 30d | 6 | 3 | 3 | 50.0% | 1.618 | +1.85 | +0.309 | 1.618 | 1.0 | 1.618 | -2.0 | 0 |
| all-time | 15 | 7 | 8 | 46.7% | 1.416 | +3.33 | +0.222 | 1.618 | 1.0 | 1.618 | -2.0 | 0 |

**D2 · By grade**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| A | 1 | 100.0% | 1.618 | +1.62 | 2 | 100.0% | 3.236 | +3.24 |
| B | 1 | 100.0% | 1.618 | +1.62 | 4 | 25.0% | 0.539 | -1.38 |

**D3 · By direction**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| LONG | 2 | 100.0% | 3.236 | +3.24 | 6 | 50.0% | 1.618 | +1.85 |

**D4 · By ticker**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| BTC-USD | 1 | 100.0% | 1.618 | +1.62 | 2 | 50.0% | 1.618 | +0.62 |
| MGC=F | 1 | 100.0% | 1.618 | +1.62 | 3 | 66.7% | 3.236 | +2.24 |

**Top 3 issues (deterministic, evidence-ranked):**

1. **[sample · high]** 7d sample too thin (n=2)  
   Only 2 trades in the 7d window. 30d n=6, all-time n=15. Per-strategy 7d conclusions are statistically unreliable; base any param change on the 30d/all-time evidence instead.
2. **[direction · low]** No actionable direction split in 7d — dimension checked, nothing to filter on  
   7d direction buckets: LONG n=2 PF=3.236 R=+3.2R. No bucket clears the significance threshold (n≥5 and PF<0.8 for a drag, or PF≥1.1 elsewhere for a keeper), so no filter is proposed on this dimension. It is reported so the dimension is accounted for.
3. **[grade · low]** No actionable grade split in 7d — dimension checked, nothing to filter on  
   7d grade buckets: A n=1 PF=1.618 R=+1.6R; B n=1 PF=1.618 R=+1.6R. No bucket clears the significance threshold (n≥5 and PF<0.8 for a drag, or PF≥1.1 elsewhere for a keeper), so no filter is proposed on this dimension. It is reported so the dimension is accounted for.

**LLM scientist verdict:**

> **Grade C · confidence 22% · evidence weak**  
> 證據不足而非確認參數失效：30d B級僅4筆且PF=0.539，無法支持權重變更。  
> *Why:* 30d與all-time均為正，但弱勢分桶未達n≥5，沒有證據支持調高或調低weight。
>
> *Consensus over 3/3 samples* — confidence samples [20, 22, 30] (spread 10), param samples [] (agreement 0.0).
>
> **Suggested params:** none — evidence does not support a parameter change.
>
> LLM-listed issues:
> - 7d僅2筆，屬轶事樣本，不能支持近期調權
> - 30d B級n=4、PF=0.539表現偏弱，但未達n≥5的可操作門檻
> - 30d整體PF=1.618且all-time PF=1.416為正，沒有明確證據顯示目前weight=0.9造成拖累
> - resample_tf與min_strength為無效設定，不能作有效修正

### H-Pattern

*Live config:* weight=(default 1.0) · resample_tf=(none — dead) · min_strength=(none — dead)

**D1 · Aggregate**

| Window | n | Wins | Losses | WR | PF | Total R | Avg R | Avg win | Avg loss | Payoff | MaxDD | Loss streak |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 7d | 1 | 1 | 0 | 100.0% | 1.618 | +1.62 | +1.618 | 1.618 | 0.0 | 0.0 | 0.0 | 0 |
| 30d | 13 | 8 | 5 | 61.5% | 2.589 | +7.94 | +0.611 | 1.618 | 1.0 | 1.618 | -3.0 | 0 |
| all-time | 132 | 46 | 86 | 34.8% | 0.858 | -12.19 | -0.092 | 1.605 | 1.0 | 1.605 | -27.97 | 0 |

**D2 · By grade**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| B | 1 | 100.0% | 1.618 | +1.62 | 13 | 61.5% | 2.589 | +7.94 |

**D3 · By direction**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| LONG | 1 | 100.0% | 1.618 | +1.62 | 12 | 66.7% | 3.236 | +8.94 |

**D4 · By ticker**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| BTC-USD | 1 | 100.0% | 1.618 | +1.62 | 13 | 61.5% | 2.589 | +7.94 |

**Top 3 issues (deterministic, evidence-ranked):**

1. **[sample · high]** 7d sample too thin (n=1)  
   Only 1 trades in the 7d window. 30d n=13, all-time n=132. Per-strategy 7d conclusions are statistically unreliable; base any param change on the 30d/all-time evidence instead.
2. **[direction · low]** No actionable direction split in 7d — dimension checked, nothing to filter on  
   7d direction buckets: LONG n=1 PF=1.618 R=+1.6R. No bucket clears the significance threshold (n≥5 and PF<0.8 for a drag, or PF≥1.1 elsewhere for a keeper), so no filter is proposed on this dimension. It is reported so the dimension is accounted for.
3. **[grade · low]** No actionable grade split in 7d — dimension checked, nothing to filter on  
   7d grade buckets: B n=1 PF=1.618 R=+1.6R. No bucket clears the significance threshold (n≥5 and PF<0.8 for a drag, or PF≥1.1 elsewhere for a keeper), so no filter is proposed on this dimension. It is reported so the dimension is accounted for.

**LLM scientist verdict:**

> **Grade C · confidence 42% · evidence moderate**  
> H-Pattern shows strong recent 30d edge (PF=2.589 on 13 trades) but all-time (n=132, PF=0.858) is net negative, indicating a regime shift or recovery from a prolonged drawdown that warrants only a moderate weight.  
> *Why:* 30d edge is strong but all-time negative; bump weight modestly to capture recent recovery without committing full capital given historical drawdown.
>
> *Consensus over 3/3 samples* — confidence samples [22, 42, 46] (spread 24), param samples [0.9, 0.9] (agreement 1.0).
>
> **Suggested params:** `{"weight": 0.9}`  
> weight=0.9 sits below neutral (1.0) to respect the negative all-time expectancy (-0.092R avg) and -27.97R maxDD, while still allocating capital to capture the genuine 30d LONG edge (PF=3.236, WR=66.7%); full 1.0+ would over-commit given that only 13 trades back the recent run.
>
> LLM-listed issues:
> - 7d sample too thin (n=1) for any per-strategy conclusion
> - All-time n=132 shows net loss (-12.19R, WR=34.8%) despite strong 30d recovery, evidence of historical drag
> - Long-only is the keeper (30d n=12 PF=3.236) but Short sample n=1 cannot be filtered safely
> - Only weight is live-readable; min_strength/resample_tf are dead config
> - No actionable grade or ticker splits available to localize the edge
> - Losing streak 0 in 30d is encouraging but maxDD all-time -27.97R signals tail risk

### Kell-Cycle

*Live config:* weight=0.7 · resample_tf=15min · min_strength=(none — dead)

**D1 · Aggregate**

| Window | n | Wins | Losses | WR | PF | Total R | Avg R | Avg win | Avg loss | Payoff | MaxDD | Loss streak |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 7d | 1 | 0 | 1 | 0.0% | 0.0 | -1.00 | -1.000 | 0.0 | 1.0 | 0.0 | -1.0 | 1 |
| 30d | 5 | 2 | 3 | 40.0% | 1.079 | +0.24 | +0.047 | 1.618 | 1.0 | 1.618 | -2.0 | 1 |
| all-time | 194 | 78 | 116 | 40.2% | 1.083 | +9.59 | +0.049 | 1.61 | 1.0 | 1.61 | -24.53 | 1 |

**D2 · By grade**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| B | 1 | 0.0% | 0.0 | -1.00 | 5 | 40.0% | 1.079 | +0.24 |

**D3 · By direction**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| SHORT | 1 | 0.0% | 0.0 | -1.00 | 2 | 0.0% | 0.0 | -2.00 |

**D4 · By ticker**

| Bucket | n(7d) | WR(7d) | PF(7d) | R(7d) | n(30d) | WR(30d) | PF(30d) | R(30d) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| MES=F | 1 | 0.0% | 0.0 | -1.00 | 1 | 0.0% | 0.0 | -1.00 |

**Top 3 issues (deterministic, evidence-ranked):**

1. **[sample · high]** 7d sample too thin (n=1)  
   Only 1 trades in the 7d window. 30d n=5, all-time n=194. Per-strategy 7d conclusions are statistically unreliable; base any param change on the 30d/all-time evidence instead.
2. **[direction · low]** No actionable direction split in 7d — dimension checked, nothing to filter on  
   7d direction buckets: SHORT n=1 PF=0.0 R=-1.0R. No bucket clears the significance threshold (n≥5 and PF<0.8 for a drag, or PF≥1.1 elsewhere for a keeper), so no filter is proposed on this dimension. It is reported so the dimension is accounted for.
3. **[grade · low]** No actionable grade split in 7d — dimension checked, nothing to filter on  
   7d grade buckets: B n=1 PF=0.0 R=-1.0R. No bucket clears the significance threshold (n≥5 and PF<0.8 for a drag, or PF≥1.1 elsewhere for a keeper), so no filter is proposed on this dimension. It is reported so the dimension is accounted for.

**LLM scientist verdict:**

> **Grade C · confidence 30% · evidence weak**  
> 7d single loss on anecdotal sample; all-time edge thin (PF=1.083) with elevated -24.53R maxDD over 194 trades  
> *Why:* Trim weight on marginal edge; reduce exposure given thin 7d loss and barely-positive all-time PF
>
> *Consensus over 3/3 samples* — confidence samples [22, 30, 78] (spread 56), param samples [0.6] (agreement 1.0).
>
> **Suggested params:** `{"weight": 0.6}`  
> ~14% reduction from 0.7 lowers risk while preserving presence; all-time is profitable but only 0.049R/trade, and maxDD suggests over-exposure at current size
>
> LLM-listed issues:
> - 7d n=1 is anecdotal — cannot act on single SHORT loss
> - All-time PF 1.083 is marginal (0.049R/trade) with maxDD -24.53R (5x gain-to-DD ratio)
> - 30d SHORTs are 0% WR but n=2 insufficient to filter by direction
> - 30d LONGs strong (PF=3.236) but n=3 also anecdotal

## 4. Lever map — which parameters actually do something

Before recommending a parameter change it has to be established that changing it changes behaviour. This audit found that most of the parameters the LLM loop has been pushing are inert.

| Lever | Status | Runtime effect | Settable values | Note |
|---|---|---|---|---|
| `AGENT_PARAMS` cells (agent_params.json) | 🔴 dormant | None — every entry has `_validated: false`, and live_scan.py:1663 gates the whole block on it. | `drop_tickers`, `keep_tickers`, `min_conf`, `grade_filter`, `direction`, `weekday_exclude`, `hours`, `t2_r`, `breakeven_at_r`, `partial_at_r`, `stop_mult`, `max_bars_held` | The strongest lever set in the codebase. Blocked only by the holdout gate. |
| `EXIT_OVERRIDES` (exit_overrides.json) | 🟡 live but unproven | Read by resolve_exit_config; applies only during a strategy's RL half-period, and only for the 6 strategies that have an entry. | `t2_r`, `breakeven_at_r`, `partial_at_r` | Written 2026-10-20T14:00Z, after the last trade. Not yet observable in the trade data. |
| `weight` (weight_overrides.json / strategy_overrides.json) | 🟡 partial | Applied at live_scan.py:1536 — *after* the confidence and grade gates. Only breaks stacking ties (line 747) and scales the confidence published downstream (line 1736). | `weight` | Does NOT filter the strategy's own signals, contrary to the code comment. |
| `min_strength` (strategy_overrides.json) | 🔴 dead | Copied into the strategy config at live_scan.py:206 but never read back by any code path. | `min_strength` | param_optimizer.py documents it as a detector strength floor; no such floor exists. |
| `resample_tf` (strategy_overrides.json) | 🔴 dead | Copied into `_cfg['args']` at live_scan.py:209 but never passed to any detector. | `resample_tf` | The last 3 accepted LLM param changes each included `resample_tf: 15min` — all no-ops. |
| `direction` filter (detector / live_scan) | 🟢 live (code change) | A direction gate is a detector-side change; no config lever exposes it today. | n/a | Needed for the CRT LONG-side finding. |

## 5. Optimiser (backtest) vs live 4D — where they disagree

`agent_params.json` was produced by `backtest_optimizer.py` against backtest/holdout data. The table below compares its ticker choice against the realised-trade 4D result in this report. A ticker is called a *winner/loser* only when PF ≥ 1.1 (or < 0.9) holds in at least two windows with n ≥ 4.

| Strategy | Optimiser keeps | Optimiser drops | Live 4D verdict | Conflict |
|---|---|---|---|---|
| H-Pattern | BTC-USD | — | BTC-USD=loser | optimiser KEEPS BTC-USD, live 4D says loser |
| 3-Pushes | M2K=F, MGC=F, MNQ=F | BTC-USD, MES=F | BTC-USD=thin, M2K=F=loser, MES=F=loser, MGC=F=loser, MNQ=F=winner | optimiser KEEPS M2K=F, live 4D says loser; optimiser KEEPS MGC=F, live 4D says loser |
| RSI-Div | BTC-USD, M2K=F, MES=F, MGC=F, MNQ=F | — | BTC-USD=thin, M2K=F=thin, MES=F=loser, MGC=F=thin, MNQ=F=thin | optimiser KEEPS MES=F, live 4D says loser |
| CRT | BTC-USD, MES=F, MGC=F | M2K=F, MNQ=F | BTC-USD=loser, M2K=F=loser, MES=F=winner, MGC=F=loser, MNQ=F=loser | optimiser KEEPS MGC=F, live 4D says loser; optimiser KEEPS BTC-USD, live 4D says loser |
| Stair | MES=F, MGC=F, MNQ=F | BTC-USD, M2K=F | BTC-USD=loser, M2K=F=loser, MES=F=loser, MGC=F=loser, MNQ=F=winner | optimiser KEEPS MES=F, live 4D says loser; optimiser KEEPS MGC=F, live 4D says loser |
| Two-Yang | BTC-USD, MES=F, MGC=F, MNQ=F | M2K=F | BTC-USD=loser, M2K=F=thin, MES=F=loser, MGC=F=thin, MNQ=F=loser | optimiser KEEPS MNQ=F, live 4D says loser; optimiser KEEPS MES=F, live 4D says loser; optimiser KEEPS BTC-USD, live 4D says loser |
| 50-20-Pullback | BTC-USD, MGC=F, MNQ=F | M2K=F, MES=F | BTC-USD=loser, M2K=F=loser, MES=F=winner, MGC=F=thin, MNQ=F=loser | optimiser KEEPS MNQ=F, live 4D says loser; optimiser KEEPS BTC-USD, live 4D says loser; optimiser DROPS MES=F, live 4D says winner |

**7 of 7 strategies have a live-trade disagreement with the optimiser's ticker selection.** The optimiser's numbers are out-of-sample and holdout-validated in design; the 4D numbers here are realised live trades. They are answering different questions, and the disagreement itself is the signal: the optimiser's track has not been able to reproduce the live book, which is exactly why `0 of 9 configurations survive it`.

## 6. Recommended changes

### 6.1 LLM parameter proposals (the `weight` lever)

| Strategy | Grade | Conf | Proposed | Live now | Auto-apply? | Rationale |
|---|---|--:|---|---|---|---|
| 50-20-Pullback | D | 82% | weight 0.948 → 0.9 | weight=0.948 | ✅ yes | consistently negative across 7d/30d/all-time (-2.3R / -8.2R / -69.2R); n=181 (30d), 1011 (all-time) — a weight cut cuts exposure to a demonstrably losing strategy. |
| CRT | C | 45% | weight 1.3 → 0.5 | weight=1.3 | ⏸️ no | confidence 45% < 60% threshold. |
| Stair | C | 45% | weight 1.1 → 0.5 | weight=1.1 | ⏸️ no | confidence 45% < 60% threshold. |
| 3-Pushes | C | 38% | weight 1.2 → 1.0 | weight=1.2 | ⏸️ no | confidence 38% < 60% threshold. |
| B1-3in1 | D | 95% | weight 1.0 → 0.0 | weight=1.0 | ⏸️ no | mechanical detector defect — `weight` cannot fix it (weight is applied after the signal gate, so the strategy would keep opening positions with a reported confidence of 0). Use the code-change route instead. |
| Two-Yang | D | 62% | weight 1.0 → 0.5 | weight=1.0 | ✅ yes | consistently negative across 7d/30d/all-time (-1.4R / -8.3R / -24.3R); n=24 (30d), 222 (all-time) — a weight cut cuts exposure to a demonstrably losing strategy. |
| RSI-Div | C | 28% | weight 0.6 → 0.4 | weight=0.6 | ⏸️ no | confidence 28% < 60% threshold. |
| B1 | C | 22% | — | weight=0.9 | ⏸️ no | LLM proposed no parameter change. |
| H-Pattern | C | 42% | weight 1.0 → 0.9 | weight=1.0 | ⏸️ no | confidence 42% < 60% threshold. |
| Kell-Cycle | C | 30% | weight 0.7 → 0.6 | weight=0.7 | ⏸️ no | confidence 30% < 60% threshold. |

> `weight` is a weak lever — it is applied after the signal gates and only breaks stacking ties (SF-3). A weight change is a priority/sizing nudge, not a strategy filter. The 4D-derived cell recommendations in §6.2 are the ones that actually remove losing trades.

### 6.2 4D-derived cell recommendations (the `AGENT_PARAMS` lever — currently dormant)

These are the changes the four dimensions actually point at: drop the instruments that bleed, gate the grade or direction that bleeds, and give the strategy a target that can be hit. They belong in `automation/config/agent_params.json` as per-cell settings (`drop_tickers` / `keep_tickers` / `min_conf` / `grade_filter` / `direction` / `t2_r` / `breakeven_at_r`). **They are not live today** — the whole block is gated behind `_validated` (SF-6), so applying them requires the holdout gate to be satisfied, not just a config edit.

| # | Strategy | Lever | Proposed change | Evidence (7d / 30d / all-time) | Conf | Auto-apply? |
|--:|---|---|---|---|--:|---|
| 1 | **50-20-Pullback** | `drop_tickers` | drop BTC-USD (keep MES=F, MGC=F, MNQ=F) | BTC PF 0.774 / 0.826 / 0.867, R -5.2 / -16.7 / -37.7 across 7d/30d/all | 80% | ✅ yes — direct conflict with the optimiser, which keeps BTC and drops MES |
| 2 | **Stair** | `keep_tickers` | keep_tickers = [MNQ=F] only | MNQ PF 3.236 / 1.618 / 1.618, R +4.5 / +8.7 / +26.0; every other ticker negative all-time | 75% | ✅ yes — conflicts with the optimiser, which keeps MES and MGC |
| 3 | **3-Pushes** | `keep_tickers` | keep_tickers = [MNQ=F] only | MNQ PF 2.319 / +50.1R all-time; BTC-USD -2.9R, MES=F -11.4R, MGC=F -8.9R | 72% | ✅ yes — conflicts with the optimiser, which keeps M2K and MGC |
| 4 | **RSI-Div** | `min_conf / keep_tickers` | keep_tickers = ['BTC-USD', 'M2K=F'] (drop ['MES=F', 'MGC=F', 'MNQ=F']) | BTC +54.6R at PF 1.896 all-time; M2K=F PF 2.697, MES=F PF 0.607, MGC=F PF 0.747, MNQ=F PF 0.231 — but 7d/30d samples are n=3 / 7, so this is a 30d+all-time call, not a 7d one | 55% | ⏸️ no — sample too thin in 7d/30d to auto-apply |
| 5 | **Two-Yang** | `weight + drop_tickers` | weight 0.8 → 0.5; drop MES=F (PF 0.539, -23.5R all-time) | 30d PF 0.539 / -8.3R (n=24), all-time PF 0.834 / -24.3R (n=222); MES is the clear drag | 62% | ✅ yes — 7d n=4 — the 30d and all-time windows carry the call |
| 6 | **CRT** | `direction / keep_tickers` | direction = short only for the 7d/30d window; keep MES=F, drop BTC-USD and MGC=F | 7d LONG -11.1R (PF 0.303) vs SHORT +4.9R (PF 1.618) | 55% | ⏸️ no — all-time direction reverses (LONG +32.2R) — regime-dependent, so below the auto-apply bar |
| 7 | **B1-3in1** | `disable strategy` | remove from STRATEGIES until the direction bug is fixed (weight 0 is not enough — SF-3) | 39/39 trades are -1.0R stop-outs, 0% win rate, -39.0R all-time, all direction='none' | 95% | ✅ yes — mechanical defect, not a parameter problem |

### 6.3 Code-change recommendations (need a detector / config-gate edit)

| Strategy | Change needed | Evidence | Conf |
|---|---|---|--:|
| B1-3in1 | Fix the detector's direction field — every one of its 39 trades carries `direction: 'none'`, so no target is ever placed and the position is always closed at the stop (-1.0R each). Until fixed, remove it from `STRATEGIES`; setting `weight: 0` is **not** sufficient, because the weight is applied after the signal gate and the strategy would keep opening positions with a reported confidence of 0 (SF-3). | 7d n=5, 30d n=23, all-time n=39 — 0.0% win rate, -39.0R, every exit at the stop, median bars_held=1 | 95% |
| CRT | Add a direction gate: suppress LONG entries for CRT. In the 7d window LONG lost 11.1R (PF 0.303, n=19) while SHORT made +4.9R (PF 1.618, n=16); the 30d window agrees (LONG -13.7R / PF 0.639 vs SHORT +7.6R / PF 1.271). | 7d and 30d by-direction split — **but all-time reverses** (LONG +32.2R, PF 1.181), so treat as a recent-regime effect, not a structural one | 60% |
| 50-20-Pullback | Restrict to the instruments that actually work. BTC-USD drove 87% of 7d volume at PF 0.774 (-5.2R) and is a drag in every window (30d PF 0.826 / -16.7R, all-time PF 0.867 / -37.7R), while MES=F is the strongest instrument in 7d (PF 1.618, +1.2R). | 7d n=34 of 39 on BTC-USD; BTC negative in 7d, 30d and all-time; MES=F wins 7d — **conflicts with the optimiser, which keeps BTC and drops MES** | 80% |
| Stair | Restrict Stair to MNQ=F. MNQ is the only instrument that makes money in any window (PF 3.236 / 1.618 / 1.618; +25.96R all-time) while the other tickers are negative all-time. | 7d by-ticker split: MNQ PF 3.236 (+4.5R); all-time MNQ +25.96R vs every other ticker negative — **conflicts with the optimiser, which keeps MES and MGC** | 75% |
| 3-Pushes | Restrict 3-Pushes to MNQ=F and drop the rest. MNQ is +50.1R all-time at PF 2.319 while BTC-USD -2.9R, MES=F -11.4R, MGC=F -8.9R are all negative. | all-time by-ticker: MNQ PF 2.319 / +50.1R vs BTC-USD -2.9R, MES=F -11.4R, MGC=F -8.9R — **conflicts with the optimiser, which keeps M2K and MGC** | 72% |
| H-Pattern | Investigate why the strategy is barely firing (7d n=1, 30d n=13) before drawing any conclusion about its edge. | sample too thin in every window | 40% |
| Kell-Cycle | Same as H-Pattern — 7d n=1, 30d n=5. Its most recent 'optimisation' (weight 0.9→0.7 + resample_tf) was applied off all-time data and the resample_tf half was a no-op (SF-2). | sample too thin in every window | 40% |

### 6.4 Auto-apply shortlist (confidence ≥ 60% **and** full evidence gate passed)

| # | Strategy | Conf | Lever(s) | Change | Evidence |
|--:|---|--:|---|---|---|
| 1 | **B1-3in1** | 95% | `disable strategy` + `code change` | remove from STRATEGIES until the direction bug is fixed (weight 0 is not enough — SF-3) | 7d n=5, 30d n=23, all-time n=39 — 0.0% win rate, -39.0R, every exit at the stop, median bars_held=1 |
| 2 | **50-20-Pullback** | 82% | `weight` | weight 0.948 → 0.9 | consistently negative across 7d/30d/all-time (-2.3R / -8.2R / -69.2R); n=181 (30d), 1011 (all-time) — a weight cut cuts exposure to a demonstrably losing strategy. |
| 3 | **50-20-Pullback** | 80% | `drop_tickers` + `code change` | drop BTC-USD (keep MES=F, MGC=F, MNQ=F) | 7d n=34 of 39 on BTC-USD; BTC negative in 7d, 30d and all-time; MES=F wins 7d — **conflicts with the optimiser, which keeps BTC and drops MES** |
| 4 | **Stair** | 75% | `keep_tickers` + `code change` | keep_tickers = [MNQ=F] only | 7d by-ticker split: MNQ PF 3.236 (+4.5R); all-time MNQ +25.96R vs every other ticker negative — **conflicts with the optimiser, which keeps MES and MGC** |
| 5 | **3-Pushes** | 72% | `keep_tickers` + `code change` | keep_tickers = [MNQ=F] only | all-time by-ticker: MNQ PF 2.319 / +50.1R vs BTC-USD -2.9R, MES=F -11.4R, MGC=F -8.9R — **conflicts with the optimiser, which keeps M2K and MGC** |
| 6 | **Two-Yang** | 62% | `weight` | weight 1.0 → 0.5 | consistently negative across 7d/30d/all-time (-1.4R / -8.3R / -24.3R); n=24 (30d), 222 (all-time) — a weight cut cuts exposure to a demonstrably losing strategy. |
| 7 | **Two-Yang** | 62% | `weight + drop_tickers` | weight 0.8 → 0.5; drop MES=F (PF 0.539, -23.5R all-time) | 30d PF 0.539 / -8.3R (n=24), all-time PF 0.834 / -24.3R (n=222); MES is the clear drag |
| 8 | **CRT** | 60% | `code change` | Add a direction gate: suppress LONG entries for CRT. In the 7d window LONG lost 11.1R (PF 0.303, n=19) while SHORT made +4.9R (PF 1.618, n=16); the 30d window agrees (LONG -13.7R / PF 0.639 vs SHORT +7.6R / PF 1.271). | 7d and 30d by-direction split — **but all-time reverses** (LONG +32.2R, PF 1.181), so treat as a recent-regime effect, not a structural one |

**8 distinct actionable recommendations at confidence ≥ 60%** (target: ≥ 3). Recommendations that appear under more than one lever are the same action reached by two routes and are listed once.

**Gate applied** (stricter than the production script's `grade in (A,B) and conf >= 60`):

1. Confidence ≥ 60 (the brief's threshold).
2. The target parameter is **live** — verified against the lever map in §4, not assumed.
3. The change is supported by the same direction of evidence in **two or more** of {7d, 30d, all-time}, or it is a mechanical defect (B1-3in1).
4. The 7d sample is n ≥ 8, **or** the 30d sample is n ≥ 20 — otherwise the finding is labelled anecdotal and confidence is discounted.
5. LLM proposals are taken from a **3-sample consensus** (median confidence, modal parameter) because MiniMax-M3 is non-deterministic — a single sample returned 78% and 45% for the same prompt on consecutive runs.

## 7. Methodology and caveats

- **Windows.** `7d` = trades whose `entry_time` falls inside the last 7 days (cutoff 2026-10-14T02:46:38.882740+00:00); `30d` and `all-time` are the same rule extended. All 3,257 trades are `status: closed`, so no open-position mark-to-market is mixed in.
- **Profit factor** = gross winning R ÷ gross losing R (not wins/losses). Where there are no losses, PF is reported as gross win R with a note.
- **Direction** is normalised: `long/bullish/up` → LONG, `short/bearish/down` → SHORT, `none` → FLAT.
- **Payoff ratio** = avg win R ÷ avg loss R.
- **MaxDD** is the worst peak-to-trough move of the cumulative R curve, in R units.
- **Confidence** is the LLM's own 0-100 figure, then discounted by the evidence gate in §4. The 7d window contains only 117 trades across 10 strategies (SF-4); 7d-only conclusions are labelled anecdotal.
- **No live code was changed.** `live_scan.py`, the detectors, `strategy_overrides.json` and `weight_overrides.json` are untouched by this analysis.

---

_Generated by the LLM Iteration Scientist (deep 4D mode) at 2026-10-21T10:53:23.401816+08:00. Analysis only — no parameter was applied._
