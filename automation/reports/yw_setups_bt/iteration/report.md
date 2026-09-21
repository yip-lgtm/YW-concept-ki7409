# YW setups — filter iteration report

- Generated: 2026-09-22T02:08:54.438889+08:00 (HKT)
- Window: **2026-08-25 → 2026-09-21** (unchanged)
- Constraints unchanged: A/B, 1 micro PV, daily −$100/+$300, no scale, skip chase past T1
- Method: re-sim candidates with concrete filters → same Apex envelope as `replay_apex_yw.py`
- Facts only — no invented P&L

## Ranked summary AFTER iteration

| Rank | Strategy | Filter | Net BEFORE | Net AFTER | MaxDD | WR | n | Qual≥$250 | Verdict BEFORE | Verdict AFTER |
|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| 1 | Stair | `skip NYKZ + skip BTC + skip MES` | $+405.79 | $+1,363.54 | $290.55 | 52.6% | 57 | 2 | tweak | **tweak** |
| 2 | CRT | `no change (baseline best)` | $+1,221.86 | $+1,221.86 | $379.65 | 41.3% | 121 | 6 | keep | **keep** |
| 3 | 50-20-Pullback | `skip MGC + keep MNQ all sessions + LDLZ/NYKZ for others` | $+41.98 | $+696.19 | $400.00 | 50.8% | 65 | 3 | tweak | **keep** |
| 4 | 3-Pushes | `MNQ+BTC up only` | $-304.67 | $+623.17 | $195.26 | 40.0% | 50 | 0 | drop | **tweak** |
| 5 | Two-Yang | `skip MNQ + skip MES + skip LDLZ` | $+236.07 | $+476.77 | $216.43 | 47.1% | 34 | 2 | tweak | **tweak** |
| 6 | Kell-Cycle | `MGC short only` | $+292.52 | $+387.50 | $132.60 | 55.6% | 9 | 1 | tweak | **tweak** |
| 7 | B1 | `no change (baseline best)` | $+272.00 | $+272.00 | $105.33 | 44.4% | 9 | 0 | tweak | **tweak** |
| 8 | OCS-BTC-5m | `LDLZ + NYKZ long` | $+2.97 | $+254.50 | $195.98 | 58.6% | 87 | 0 | tweak | **tweak** |
| 9 | B1-3in1 | `skip MES (keep MGC+BTC)` | $+179.45 | $+196.93 | $0.00 | 100.0% | 7 | 0 | tweak | **tweak** |
| 10 | H-Pattern | `NYKZ only` | $+8.11 | $+78.96 | $32.95 | 60.0% | 5 | 0 | tweak | **tweak** |
| 11 | RSI-Div | `skip MNQ+MGC+MES` | $-392.94 | $+46.94 | $101.05 | 50.0% | 12 | 0 | drop | **tweak** |

## Per-strategy one-liners

- **Stair**: tweak→tweak via `skip NYKZ + skip BTC + skip MES` ($+406→$+1364, n 101→57)
- **CRT**: keep→keep via `no change (baseline best)` ($+1222→$+1222, n 121→121)
- **50-20-Pullback**: tweak→keep via `skip MGC + keep MNQ all sessions + LDLZ/NYKZ for others` ($+42→$+696, n 167→65)
- **3-Pushes**: drop→tweak via `MNQ+BTC up only` ($-305→$+623, n 82→50)
- **Two-Yang**: tweak→tweak via `skip MNQ + skip MES + skip LDLZ` ($+236→$+477, n 48→34)
- **Kell-Cycle**: tweak→tweak via `MGC short only` ($+293→$+388, n 32→9)
- **B1**: tweak→tweak via `no change (baseline best)` ($+272→$+272, n 9→9)
- **OCS-BTC-5m**: tweak→tweak via `LDLZ + NYKZ long` ($+3→$+254, n 397→87)
- **B1-3in1**: tweak→tweak via `skip MES (keep MGC+BTC)` ($+179→$+197, n 8→7)
- **H-Pattern**: tweak→tweak via `NYKZ only` ($+8→$+79, n 22→5)
- **RSI-Div**: drop→tweak via `skip MNQ+MGC+MES` ($-393→$+47, n 16→12)

## Live arm recommendation (Tradovate MNQ / MGC MGCZ6)

Arm **CRT** (unfiltered keep, qual=6, n=121, net $+1,221.86) live on Tradovate MNQ + MGC (MGCZ6); paper **Stair** with skip-NYKZ+skip-BTC+skip-MES (AFTER $+1,363.54, qual=2) and optional second book **50-20-Pullback** with skip-MGC + MNQ-all / others-LDLZ|NYKZ only (new keep $+696.19, qual=3) — do not arm drop-to-tweak salvages (3-Pushes/RSI-Div) live.

## CRT confirm note

CRT stays **keep** with baseline (no filter). All tested filters (skip BTC, MGC+MNQ allowlist, skip NYKZ bearish) remain keep but **lower re-sim net** ($667–$910 vs $1,222) because removing losing BTC/NYKZ cells reshuffles Apex overlap/daily envelope onto weaker replacements. Post-hoc on *already-accepted* trades would drop BTC (−$79) but that is not how a live pre-entry filter behaves — re-sim is the binding test. **Confirm keep; do not tighten.**

## Verdict counts AFTER

- keep: 2 — CRT, 50-20-Pullback (filtered)
- tweak: 9
- drop: 0

## Near-miss

- **Stair** AFTER `skip NYKZ + skip BTC + skip MES`: net $+1,363.54, n=57, qual=2 — highest net but **tweak** (needs qual≥3 for keep). Paper this filter on MNQ/MGC.

See `per_strategy/*.md` for grade/session/ticker analysis and all filter experiments.
