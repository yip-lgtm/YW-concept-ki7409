# CRT deep analysis (YW Apex replay)

- Generated: 2026-09-22 (HKT)
- Window: **2026-08-25 → 2026-09-21** (~28 calendar days)
- Sources: `/workspace/yw_setups_bt/{report.md,ranking.json,trades_replay.json}`; live_scan `signals.jsonl` / `trades.jsonl` filtered to strategy CRT
- Facts only — counts from files; no invented trades

---

## 1) CRT mechanic recap

**Candle Range Theory (4H range → 5m raid → MSS)** — from `detect_crt` / grader:

1. **4H range**: last closed 4H candle High = CRT-H, Low = CRT-L.
2. **5m raid**: within the next 4H window (~48×5m bars), price sweeps CRT-L (bull) or CRT-H (bear) — liquidity grab.
3. **MSS confirm**: next 5m after the raid closes back through the raid candle (bull: close > raid High; bear: close < raid Low).
4. **Targets**: run toward the opposite side of the 4H range (CRT-H for bull / CRT-L for bear).
5. **Live chase gate (v3)**: if `last_close` is already > **0.3× range** past MSS, treat as chase — `gate_blocked` (not a fresh confirmation entry).

---

## 2) Grade quality mix (accepted Apex replay A/B)

Accepted CRT trades under Apex envelope: **n=121**, net **$+1,221.86**, WR **41.3%** (50W / 71L).

| Grade | n | Wins | Losses | WR | Net P&L | Avg $/trade |
|---|---:|---:|---:|---:|---:|---:|
| **A** | 29 | 10 | 19 | 34.5% | $+90.04 | $+3.10 |
| **B** | 92 | 40 | 52 | 43.5% | $+1,131.82 | $+12.30 |

Notes:
- Live_scan CRT **signals** in-window grade mix (pre-envelope): A=145, B=579, C=17 (C skipped by policy).
- Replay skips include `grade_C_or_other: 12`.
- **B carried the book**; A underperformed on WR and contribution in this window (esp. A×BTC-USD n=9 WR 11.1% −$105).

---

## 3) Best market conditions

### By ticker (accepted trades)

| Ticker | n | WR | Net P&L | Note |
|---|---:|---:|---:|---|
| **MGC=F** | 13 | 61.5% | **$+736.14** | Best edge; B-grade heavy |
| **MNQ=F** | 31 | 45.2% | **$+486.41** | Strong; LDLZ MNQ n=4 $+307 |
| MES=F | 14 | 50.0% | $+60.70 | Modest |
| M2K=F | 23 | 39.1% | $+18.10 | Near flat; other-session drag |
| **BTC-USD** | 40 | 30.0% | **−$79.49** | Worst; high volume, low WR |

### By session

| Session | n | WR | Net | Avg $/trade |
|---|---:|---:|---:|---:|
| **LDLZ** (02–05 NY) | 14 | **57.1%** | **$+350.34** | **$+25.02** |
| NYKZ (08:30–11 NY) | 12 | 41.7% | $+39.17 | $+3.26 |
| other | 95 | 38.9% | $+832.35 | $+8.76 |

- Absolute dollars: **other** still largest book (volume).
- Quality: **LDLZ best expectancy**; NYKZ nearly flat overall — **NYKZ bearish** n=10 WR 40% **−$100**; NYKZ bullish n=2 $+139.

### By direction

| Direction | n | WR | Net |
|---|---:|---:|---:|
| **bullish** | 57 | 40.4% | **$+874.40** |
| bearish | 64 | 42.2% | $+347.46 |

Bullish CRT made ~2.5× bearish dollars despite fewer trades.

### Cross highlights
- Best cells: MGC×other $+554; MNQ×LDLZ $+307; MGC×NYKZ $+153 (n=1).
- Weak cells: MNQ×NYKZ −$164; BTC×NYKZ −$96; M2K×other −$79.

---

## 4) Chase failures

| Gate / skip | Count | Source |
|---|---:|---|
| **`gate_blocked` CRT chasing** (`distance_from_mss` > 0.3×range) | **17** | live_scan `signals.jsonl` CRT in window |
| **`chase_past_t1`** (entry already past T1) | **1** | Apex replay skip_counts |

**Failure mode:** detector can still mark raid+MSS “present,” but price has already run away from MSS. Entry then has broken R:R (stop far / target close) — same “partial CRT ≠ open / B-grade chase leak” issue noted in live_scan v3 comments. Distances blocked: **0.31–0.87×range** (median ~0.71). Mix: B=13 / A=4; mostly **bullish** (14/17); tickers M2K 5, MNQ 4, MGC 3, MES 3, BTC 2.

Other CRT `gate_blocked` in-window (context, not chase): direction_conflict 32, stacking 9, grade 5 → **63** total gated CRT signals.

---

## 5) CRT vs peers (Apex A/B replay)

| Strategy | Net P&L | WR | n | Qual days ≥$250 | Max DD | Verdict |
|---|---:|---:|---:|---:|---:|---|
| **CRT** | **$+1,221.86** | 41.3% | 121 | **6** | $379.65 | **keep** |
| Stair | $+405.79 | 40.6% | 101 | 1 | $293.32 | tweak |
| Kell-Cycle | $+292.52 | 40.6% | 32 | 2 | $406.42 | tweak |
| B1 | $+272.00 | 44.4% | 9 | 0 | $105.33 | tweak |
| 50-20-Pullback | $+41.98 | 35.9% | 167 | 1 | $552.66 | tweak |
| H-Pattern | $+8.11 | 36.4% | 22 | 0 | $174.85 | tweak |

Keep gate: `net≥$3000` **OR** (`qual≥3` **AND** `n≥20`). CRT clears via **6 qual days + n=121** (net shy of $3k alone). CRT is **#1 by net**, only strategy with keep, and only one with ≥3 qual days in this set.

Exit mix (CRT accepted): SL 71 / T2 46 / T1 4 — winners largely T2; losses clustered at SL. Expectancy **~$10.10/trade**; avg win $66.72 vs avg loss −$29.78.

---

## 6) Verdict — **KEEP as primary**

### Strengths
- Clear #1 net and only **keep** under Apex gates; **6** days hit ≥$250 (capped at $300 several times).
- Robust sample (n=121) across MNQ/MES/M2K/MGC/BTC.
- Asymmetric payoff (avg win ≈ 2.2× avg loss) despite ~41% WR.
- **LDLZ** and **MGC / MNQ** show clean positive expectancy; bullish skew helpful.
- Chase gates already catching late entries (17 MSS-distance blocks).

### Weaknesses
- Grade **A did not beat B** this window; A×BTC notably poor.
- **BTC-USD** drag (−$79, WR 30%); volume without edge.
- **NYKZ bearish** weak; MNQ NYKZ negative.
- High skip friction: overlap 218 + daily envelope 245 — many candidates never fill under sole-book envelope.
- Max DD $380 with daily −$100 kills (worst day 2026-08-26 −$100).

### Actionable live rules
1. **Keep CRT primary** under current Apex envelope (A/B, 1 micro, brackets).
2. **Prefer entries near MSS** — honor `distance_from_mss ≤ 0.3×range`; do not override chase blocks.
3. **Prefer LDLZ** when choosing among simultaneous CRT alerts; treat NYKZ (esp. bearish / MNQ) as optional/lower size.
4. **Prefer MGC & MNQ**; demote or skip **BTC** CRT unless exceptional structure.
5. **Skip chase**: never enter if past T1 or >0.3×range past MSS — failure mode is R:R collapse, not missed runners.
6. Do not overweight grade A vs B from this window; B paid; still skip C.
7. Bullish CRT historically paid more dollars here — not a ban on shorts, but raise bar on NYKZ shorts.

---

*Parent voices final ranking; this file is analysis-only from recorded replay + live_scan.*
