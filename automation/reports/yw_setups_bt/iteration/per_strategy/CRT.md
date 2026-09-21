# CRT — iteration

- Window: **2026-08-25 → 2026-09-21** (HKT report gen)
- Method: re-sim Apex envelope on live_scan/OCS candidates with post-detect filters
- Filter applied: **`no change (baseline best)`**

## BEFORE vs AFTER

| Metric | BEFORE | AFTER | Δ |
|---|---:|---:|---:|
| Net P&L | $+1,221.86 | $+1,221.86 | $+0.00 |
| Max DD | $379.65 | $379.65 | $+0.00 |
| WR | 41.3% | 41.3% | +0.0pp |
| n | 121 | 121 | +0 |
| Qual≥$250 | 6 | 6 | +0 |
| Verdict | **keep** | **keep** | |

## Grade mix (BEFORE accepted)

| Grade | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| B | 92 | 43.5% | $+1,131.82 | $+12.30 |
| A | 29 | 34.5% | $+90.04 | $+3.10 |

## Best conditions (BEFORE)

- ticker MGC=F: n=13 WR 61.5% $+736.14
- ticker MNQ=F: n=31 WR 45.2% $+486.41
- ticker MES=F: n=14 WR 50.0% $+60.70
- session other: n=95 WR 38.9% $+832.35 avg $+8.76
- session LDLZ: n=14 WR 57.1% $+350.34 avg $+25.02
- direction bullish: n=57 WR 40.4% $+874.40
- direction bearish: n=64 WR 42.2% $+347.46

## Failure modes (BEFORE)

- ticker BTC-USD: n=40 WR 30.0% $-79.49

## Ticker / session / direction (BEFORE)

### Ticker
| Ticker | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| MGC=F | 13 | 61.5% | $+736.14 | $+56.63 |
| MNQ=F | 31 | 45.2% | $+486.41 | $+15.69 |
| MES=F | 14 | 50.0% | $+60.70 | $+4.34 |
| M2K=F | 23 | 39.1% | $+18.10 | $+0.79 |
| BTC-USD | 40 | 30.0% | $-79.49 | $-1.99 |

### Session
| Session | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| other | 95 | 38.9% | $+832.35 | $+8.76 |
| LDLZ | 14 | 57.1% | $+350.34 | $+25.02 |
| NYKZ | 12 | 41.7% | $+39.17 | $+3.26 |

### Direction
| Dir | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| bullish | 57 | 40.4% | $+874.40 | $+15.34 |
| bearish | 64 | 42.2% | $+347.46 | $+5.43 |

## Proposed filter tweaks (tested)

1. **`skip BTC-USD (tested, no material improvement)`** → net $+903.15 (Δ $-318.71), dd $515.12, WR 44.6%, n=92, qual=4, verdict **keep**
2. **`skip BTC + skip NYKZ bearish (tested, no material improvement)`** → net $+797.36 (Δ $-424.50), dd $451.54, WR 44.2%, n=86, qual=4, verdict **keep**
3. **`skip BTC + skip MNQ×NYKZ (tested, no material improvement)`** → net $+909.88 (Δ $-311.98), dd $440.06, WR 44.9%, n=89, qual=4, verdict **keep**

## All experiments

| Filter | Net | MaxDD | WR | n | Qual | Verdict | raw_after_filter |
|---|---:|---:|---:|---:|---:|---|---:|
| skip BTC-USD | $+903.15 | $515.12 | 44.6% | 92 | 4 | keep | 432 |
| skip BTC + skip NYKZ bearish | $+797.36 | $451.54 | 44.2% | 86 | 4 | keep | 416 |
| skip BTC + skip MNQ×NYKZ | $+909.88 | $440.06 | 44.9% | 89 | 4 | keep | 424 |
| allowlist MGC+MNQ only | $+742.36 | $464.08 | 44.8% | 67 | 4 | keep | 221 |
| allowlist MGC+MNQ + skip NYKZ bearish | $+667.44 | $412.98 | 45.3% | 64 | 4 | keep | 214 |

## AFTER session split

LDLZ n=14 $+350 | NYKZ n=12 $+39 | other n=95 $+832

- Instruments: MBT≈BTC-USD, M2K=F, MES=F, MGC=F, MNQ=F
- Skips: `{"chase_past_t1": 1, "grade_C_or_other": 12, "overlap_no_scale": 218, "daily_envelope_block": 245}`
- Best day: {'date': '2026-09-02', 'pnl': 300.0} · Worst day: {'date': '2026-08-26', 'pnl': -100.0}

Facts only — P&L from replay of recorded trades; no invented fills.
## CRT confirm note

All skip-BTC / MGC+MNQ allowlist experiments stay **keep** but cut re-sim net vs baseline ($667–$910 vs $1,222) due to Apex envelope reshuffle. Confirm unfiltered keep; no tighten.
