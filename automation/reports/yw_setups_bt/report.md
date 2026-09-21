# YW-concept setups — Apex-constraint backtest

- Generated: 2026-09-22T01:55:44.928931+08:00 (HKT)
- Window: **2026-08-25 → 2026-09-21** (live_scan attribution; yfinance 5m ~60d max)
- Parent voices final ranking; this file is facts-only.

## Constraints (match live Apex monitor)

| Rule | Value |
|---|---|
| Grades | A/B only (skip C) |
| Size | 1 Micro |
| Point values | MNQ $2 · MES $5 · M2K $5 · MGC $10 · BTC→MBT $0.10 |
| Daily envelope | −$100 kill / +$300 TP cap (no new entries that NY day) |
| Brackets | recorded SL / T* exits; no scale/average; 1 open/strategy |
| Chase | skip if entry already past T1 |
| Sessions | tagged LDLZ 02–05 NY · NYKZ 08:30–11 NY · other |

## Verdict gates

- **keep**: net ≥ $3,000 **OR** (≥3 qual days ≥$250 **AND** n≥20)
- **tweak**: net > 0 but shy of keep
- **drop**: flat/negative, or n≈0 / overfit (n<5 & |net|<500)

## STRATEGIES dict (live_scan.py) — names + tickers

| Strategy | Configured tickers |
|---|---|
| H-Pattern | MNQ=F, MES=F, M2K=F, MGC=F, BTC-USD |
| 3-Pushes | MNQ=F, MES=F, M2K=F, MGC=F, BTC-USD |
| Two-Yang | MNQ=F, MES=F, M2K=F, MGC=F, BTC-USD |
| RSI-Div | MNQ=F, MES=F, M2K=F, MGC=F, BTC-USD |
| 50-20-Pullback | MNQ=F, MES=F, M2K=F, MGC=F, BTC-USD |
| Stair | MNQ=F, MES=F, M2K=F, MGC=F, BTC-USD |
| B1 | MNQ=F, MGC=F, BTC-USD |
| B1-3in1 | MNQ=F, MGC=F, BTC-USD |
| Kell-Cycle | MNQ=F, MES=F, M2K=F, MGC=F, BTC-USD |
| CRT | MNQ=F, MES=F, M2K=F, MGC=F, BTC-USD |
| OCS-BTC-5m | BTC-USD |

Notes: B1 / B1-3in1 restricted to MNQ+MGC+BTC in live_scan. OCS-BTC-5m is BTC-only (no rows in live_scan signals — supplemented via OCS backtest re-sim).

## Side-by-side (rank order by net P&L)

| Rank | Strategy | Net P&L | Max DD | WR | n | Qual≥$250 | LDLZ vs NYKZ | Instruments | Verdict | Data source |
|---|---|---:|---:|---:|---:|---:|---|---|---|---|
| 1 | CRT | $+1,221.86 | $379.65 | 41.3% | 121 | 6 | LDLZ n=14 $+350 | NYKZ n=12 $+39 | other n=95 $+832 | MBT≈BTC-USD, M2K=F, MES=F, MGC=F, MNQ=F | **keep** | live_scan trades.jsonl (A/B replay under Apex envelope) |
| 2 | Stair | $+405.79 | $293.32 | 40.6% | 101 | 1 | LDLZ n=7 $+219 | NYKZ n=8 $-265 | other n=86 $+452 | MBT≈BTC-USD, M2K=F, MES=F, MGC=F, MNQ=F | **tweak** | live_scan trades.jsonl (A/B replay under Apex envelope) |
| 3 | Kell-Cycle | $+292.52 | $406.42 | 40.6% | 32 | 2 | LDLZ n=1 $+32 | NYKZ n=2 $-30 | other n=29 $+290 | MBT≈BTC-USD, M2K=F, MES=F, MGC=F, MNQ=F | **tweak** | live_scan trades.jsonl (A/B replay under Apex envelope) |
| 4 | B1 | $+272.00 | $105.33 | 44.4% | 9 | 0 | LDLZ n=1 $-15 | NYKZ n=3 $+288 | other n=5 $-1 | MBT≈BTC-USD, MGC=F, MNQ=F | **tweak** | live_scan trades.jsonl (A/B replay under Apex envelope) |
| 5 | Two-Yang | $+236.07 | $409.59 | 35.4% | 48 | 2 | LDLZ n=3 $-44 | NYKZ n=10 $+243 | other n=35 $+36 | MBT≈BTC-USD, M2K=F, MES=F, MGC=F, MNQ=F | **tweak** | live_scan trades.jsonl (A/B replay under Apex envelope) |
| 6 | B1-3in1 | $+179.45 | $0.00 | 100.0% | 8 | 0 | LDLZ n=1 $+16 | NYKZ n=0 $+0 | other n=7 $+164 | MBT≈BTC-USD, MES=F, MGC=F | **tweak** | live_scan trades.jsonl (A/B replay under Apex envelope) |
| 7 | 50-20-Pullback | $+41.98 | $552.66 | 35.9% | 167 | 1 | LDLZ n=18 $+183 | NYKZ n=13 $+40 | other n=136 $-181 | MBT≈BTC-USD, M2K=F, MES=F, MGC=F, MNQ=F | **tweak** | live_scan trades.jsonl (A/B replay under Apex envelope) |
| 8 | H-Pattern | $+8.11 | $174.85 | 36.4% | 22 | 0 | BTC 24h — LDLZ n=0 $+0 | NYKZ n=5 $+79 | other n=17 $-71 | MBT≈BTC-USD | **tweak** | live_scan trades.jsonl (A/B replay under Apex envelope) |
| 9 | OCS-BTC-5m | $+2.97 | $413.25 | 48.4% | 397 | 0 | BTC 24h — LDLZ n=55 $+170 | NYKZ n=66 $+9 | other n=276 $-176 | MBT≈BTC-USD | **tweak** | re-sim:trades_60d_20260921_175536.json (OCS own gates, graded as B accept) |
| 10 | 3-Pushes | $-304.67 | $517.98 | 35.4% | 82 | 0 | LDLZ n=9 $-115 | NYKZ n=9 $+74 | other n=64 $-264 | MBT≈BTC-USD, M2K=F, MES=F, MGC=F, MNQ=F | **drop** | live_scan trades.jsonl (A/B replay under Apex envelope) |
| 11 | RSI-Div | $-392.94 | $430.30 | 25.0% | 16 | 0 | LDLZ n=1 $-21 | NYKZ n=8 $-263 | other n=7 $-109 | MBT≈BTC-USD, M2K=F, MES=F, MGC=F, MNQ=F | **drop** | live_scan trades.jsonl (A/B replay under Apex envelope) |

## Per-strategy detail

### 1. CRT — **keep**

- Data source: `live_scan trades.jsonl (A/B replay under Apex envelope)`
- Configured tickers: MNQ=F, MES=F, M2K=F, MGC=F, BTC-USD
- Instruments traded (accepted): MBT≈BTC-USD, M2K=F, MES=F, MGC=F, MNQ=F
- Net P&L: **$+1,221.86** · Max DD: $379.65 · WR: 41.3% · n=121
- Qual days ≥$250: 6
- Best day: {'date': '2026-09-02', 'pnl': 300.0} · Worst day: {'date': '2026-08-26', 'pnl': -100.0}
- Sessions: LDLZ n=14 $+350 | NYKZ n=12 $+39 | other n=95 $+832
- Skips: `{"chase_past_t1": 1, "grade_C_or_other": 12, "overlap_no_scale": 218, "daily_envelope_block": 245}`
- A/B candidates before envelope/overlap: 584

### 2. Stair — **tweak**

- Data source: `live_scan trades.jsonl (A/B replay under Apex envelope)`
- Configured tickers: MNQ=F, MES=F, M2K=F, MGC=F, BTC-USD
- Instruments traded (accepted): MBT≈BTC-USD, M2K=F, MES=F, MGC=F, MNQ=F
- Net P&L: **$+405.79** · Max DD: $293.32 · WR: 40.6% · n=101
- Qual days ≥$250: 1
- Best day: {'date': '2026-09-08', 'pnl': 300.0} · Worst day: {'date': '2026-09-02', 'pnl': -100.0}
- Sessions: LDLZ n=7 $+219 | NYKZ n=8 $-265 | other n=86 $+452
- Skips: `{"overlap_no_scale": 127, "daily_envelope_block": 27}`
- A/B candidates before envelope/overlap: 255

### 3. Kell-Cycle — **tweak**

- Data source: `live_scan trades.jsonl (A/B replay under Apex envelope)`
- Configured tickers: MNQ=F, MES=F, M2K=F, MGC=F, BTC-USD
- Instruments traded (accepted): MBT≈BTC-USD, M2K=F, MES=F, MGC=F, MNQ=F
- Net P&L: **$+292.52** · Max DD: $406.42 · WR: 40.6% · n=32
- Qual days ≥$250: 2
- Best day: {'date': '2026-09-01', 'pnl': 300.0} · Worst day: {'date': '2026-08-31', 'pnl': -100.0}
- Sessions: LDLZ n=1 $+32 | NYKZ n=2 $-30 | other n=29 $+290
- Skips: `{"grade_C_or_other": 147, "overlap_no_scale": 8, "daily_envelope_block": 2}`
- A/B candidates before envelope/overlap: 42

### 4. B1 — **tweak**

- Data source: `live_scan trades.jsonl (A/B replay under Apex envelope)`
- Configured tickers: MNQ=F, MGC=F, BTC-USD
- Instruments traded (accepted): MBT≈BTC-USD, MGC=F, MNQ=F
- Net P&L: **$+272.00** · Max DD: $105.33 · WR: 44.4% · n=9
- Qual days ≥$250: 0
- Best day: {'date': '2026-09-03', 'pnl': 164.3} · Worst day: {'date': '2026-09-16', 'pnl': -100.0}
- Sessions: LDLZ n=1 $-15 | NYKZ n=3 $+288 | other n=5 $-1
- Skips: `{}`
- A/B candidates before envelope/overlap: 9

### 5. Two-Yang — **tweak**

- Data source: `live_scan trades.jsonl (A/B replay under Apex envelope)`
- Configured tickers: MNQ=F, MES=F, M2K=F, MGC=F, BTC-USD
- Instruments traded (accepted): MBT≈BTC-USD, M2K=F, MES=F, MGC=F, MNQ=F
- Net P&L: **$+236.07** · Max DD: $409.59 · WR: 35.4% · n=48
- Qual days ≥$250: 2
- Best day: {'date': '2026-09-02', 'pnl': 300.0} · Worst day: {'date': '2026-09-01', 'pnl': -100.0}
- Sessions: LDLZ n=3 $-44 | NYKZ n=10 $+243 | other n=35 $+36
- Skips: `{"grade_C_or_other": 90, "overlap_no_scale": 27, "daily_envelope_block": 29}`
- A/B candidates before envelope/overlap: 104

### 6. B1-3in1 — **tweak**

- Data source: `live_scan trades.jsonl (A/B replay under Apex envelope)`
- Configured tickers: MNQ=F, MGC=F, BTC-USD
- Instruments traded (accepted): MBT≈BTC-USD, MES=F, MGC=F
- Net P&L: **$+179.45** · Max DD: $0.00 · WR: 100.0% · n=8
- Qual days ≥$250: 0
- Best day: {'date': '2026-09-03', 'pnl': 68.7} · Worst day: {'date': '2026-08-29', 'pnl': 11.2}
- Sessions: LDLZ n=1 $+16 | NYKZ n=0 $+0 | other n=7 $+164
- Skips: `{"grade_C_or_other": 5, "overlap_no_scale": 3}`
- A/B candidates before envelope/overlap: 11

### 7. 50-20-Pullback — **tweak**

- Data source: `live_scan trades.jsonl (A/B replay under Apex envelope)`
- Configured tickers: MNQ=F, MES=F, M2K=F, MGC=F, BTC-USD
- Instruments traded (accepted): MBT≈BTC-USD, M2K=F, MES=F, MGC=F, MNQ=F
- Net P&L: **$+41.98** · Max DD: $552.66 · WR: 35.9% · n=167
- Qual days ≥$250: 1
- Best day: {'date': '2026-08-31', 'pnl': 300.0} · Worst day: {'date': '2026-08-30', 'pnl': -100.0}
- Sessions: LDLZ n=18 $+183 | NYKZ n=13 $+40 | other n=136 $-181
- Skips: `{"grade_C_or_other": 52, "overlap_no_scale": 341, "daily_envelope_block": 273}`
- A/B candidates before envelope/overlap: 781

### 8. H-Pattern — **tweak**

- Data source: `live_scan trades.jsonl (A/B replay under Apex envelope)`
- Configured tickers: MNQ=F, MES=F, M2K=F, MGC=F, BTC-USD
- Instruments traded (accepted): MBT≈BTC-USD
- Net P&L: **$+8.11** · Max DD: $174.85 · WR: 36.4% · n=22
- Qual days ≥$250: 0
- Best day: {'date': '2026-09-21', 'pnl': 69.57} · Worst day: {'date': '2026-09-02', 'pnl': -69.29}
- Sessions: BTC 24h — LDLZ n=0 $+0 | NYKZ n=5 $+79 | other n=17 $-71
- Skips: `{"grade_C_or_other": 92, "overlap_no_scale": 6}`
- A/B candidates before envelope/overlap: 28

### 9. OCS-BTC-5m — **tweak**

- Data source: `re-sim:trades_60d_20260921_175536.json (OCS own gates, graded as B accept)`
- Configured tickers: BTC-USD
- Instruments traded (accepted): MBT≈BTC-USD
- Net P&L: **$+2.97** · Max DD: $413.25 · WR: 48.4% · n=397
- Qual days ≥$250: 0
- Best day: {'date': '2026-09-21', 'pnl': 131.89} · Worst day: {'date': '2026-09-10', 'pnl': -100.0}
- Sessions: BTC 24h — LDLZ n=55 $+170 | NYKZ n=66 $+9 | other n=276 $-176
- Skips: `{"daily_envelope_block": 11}`
- A/B candidates before envelope/overlap: 408

### 10. 3-Pushes — **drop**

- Data source: `live_scan trades.jsonl (A/B replay under Apex envelope)`
- Configured tickers: MNQ=F, MES=F, M2K=F, MGC=F, BTC-USD
- Instruments traded (accepted): MBT≈BTC-USD, M2K=F, MES=F, MGC=F, MNQ=F
- Net P&L: **$-304.67** · Max DD: $517.98 · WR: 35.4% · n=82
- Qual days ≥$250: 0
- Best day: {'date': '2026-08-25', 'pnl': 172.73} · Worst day: {'date': '2026-08-31', 'pnl': -100.0}
- Sessions: LDLZ n=9 $-115 | NYKZ n=9 $+74 | other n=64 $-264
- Skips: `{"grade_C_or_other": 24, "overlap_no_scale": 92, "daily_envelope_block": 189}`
- A/B candidates before envelope/overlap: 363

### 11. RSI-Div — **drop**

- Data source: `live_scan trades.jsonl (A/B replay under Apex envelope)`
- Configured tickers: MNQ=F, MES=F, M2K=F, MGC=F, BTC-USD
- Instruments traded (accepted): MBT≈BTC-USD, M2K=F, MES=F, MGC=F, MNQ=F
- Net P&L: **$-392.94** · Max DD: $430.30 · WR: 25.0% · n=16
- Qual days ≥$250: 0
- Best day: {'date': '2026-09-03', 'pnl': 47.4} · Worst day: {'date': '2026-09-08', 'pnl': -100.0}
- Sessions: LDLZ n=1 $-21 | NYKZ n=8 $-263 | other n=7 $-109
- Skips: `{"grade_C_or_other": 148, "overlap_no_scale": 2, "daily_envelope_block": 7}`
- A/B candidates before envelope/overlap: 25

## Method notes (facts)

1. Primary source is `automation/reports/live_scan/trades.jsonl` joined to strategy attribution already present on each row (same signals that fired live Apex/Telegram path).
2. Recorded `pnl_usd` in trades.jsonl is **price points**, not micro dollars — converted with POINT_VALUE above.
3. Grade C trades present in the log were excluded (BLOCK_GRADE_C_OPEN live policy).
4. Daily −$100 / +$300 applied per strategy independently (each strategy as sole account book).
5. OCS-BTC-5m has **zero** live_scan signal/trade attribution in-window; any OCS rows come from `ocs_backtest` re-sim only.
6. No invented trades — empty strategies stay n=0.
