# Two-Yang — iteration

- Window: **2026-08-25 → 2026-09-21** (HKT report gen)
- Method: re-sim Apex envelope on live_scan/OCS candidates with post-detect filters
- Filter applied: **`skip MNQ + skip MES + skip LDLZ`**

## BEFORE vs AFTER

| Metric | BEFORE | AFTER | Δ |
|---|---:|---:|---:|
| Net P&L | $+236.07 | $+476.77 | $+240.70 |
| Max DD | $409.59 | $216.43 | $-193.16 |
| WR | 35.4% | 47.1% | +11.7pp |
| n | 48 | 34 | -14 |
| Qual≥$250 | 2 | 2 | +0 |
| Verdict | **tweak** | **tweak** | |

## Grade mix (BEFORE accepted)

| Grade | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| B | 48 | 35.4% | $+236.07 | $+4.92 |

## Best conditions (BEFORE)

- ticker MGC=F: n=11 WR 45.5% $+299.00
- ticker BTC-USD: n=9 WR 33.3% $+34.07
- ticker M2K=F: n=8 WR 37.5% $+18.90
- session NYKZ: n=10 WR 50.0% $+243.49 avg $+24.35
- direction long: n=48 WR 35.4% $+236.07

## Failure modes (BEFORE)

- ticker MES=F: n=13 WR 30.8% $-45.06
- ticker MNQ=F: n=7 WR 28.6% $-70.84
- session LDLZ: n=3 WR 33.3% $-43.72

## Ticker / session / direction (BEFORE)

### Ticker
| Ticker | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| MGC=F | 11 | 45.5% | $+299.00 | $+27.18 |
| BTC-USD | 9 | 33.3% | $+34.07 | $+3.79 |
| M2K=F | 8 | 37.5% | $+18.90 | $+2.36 |
| MES=F | 13 | 30.8% | $-45.06 | $-3.47 |
| MNQ=F | 7 | 28.6% | $-70.84 | $-10.12 |

### Session
| Session | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| NYKZ | 10 | 50.0% | $+243.49 | $+24.35 |
| other | 35 | 31.4% | $+36.30 | $+1.04 |
| LDLZ | 3 | 33.3% | $-43.72 | $-14.57 |

### Direction
| Dir | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| long | 48 | 35.4% | $+236.07 | $+4.92 |

## Proposed filter tweaks (tested)

1. **`skip MNQ + skip MES + skip LDLZ`** → net $+476.77 (Δ $+240.70), dd $216.43, WR 47.1%, n=34, qual=2, verdict **tweak**
2. **`allowlist MGC+BTC+M2K + skip LDLZ`** → net $+476.77 (Δ $+240.70), dd $216.43, WR 47.1%, n=34, qual=2, verdict **tweak**
3. **`skip LDLZ`** → net $+279.79 (Δ $+43.72), dd $392.44, WR 35.6%, n=45, qual=2, verdict **tweak**

## All experiments

| Filter | Net | MaxDD | WR | n | Qual | Verdict | raw_after_filter |
|---|---:|---:|---:|---:|---:|---|---:|
| skip MNQ + skip MES + skip LDLZ | $+476.77 | $216.43 | 47.1% | 34 | 2 | tweak | 97 |
| MGC only (NYKZ+other) | $+261.00 | $252.30 | 42.9% | 14 | 1 | tweak | 29 |
| skip LDLZ | $+279.79 | $392.44 | 35.6% | 45 | 2 | tweak | 187 |
| NYKZ only | $+214.67 | $200.16 | 45.5% | 11 | 0 | tweak | 18 |
| allowlist MGC+BTC+M2K + skip LDLZ | $+476.77 | $216.43 | 47.1% | 34 | 2 | tweak | 97 |

## AFTER session split

LDLZ n=0 $+0 | NYKZ n=6 $+334 | other n=28 $+143

- Instruments: MBT≈BTC-USD, M2K=F, MGC=F
- Skips: `{"grade_C_or_other": 43, "overlap_no_scale": 8, "daily_envelope_block": 12}`
- Best day: {'date': '2026-09-02', 'pnl': 300.0} · Worst day: {'date': '2026-09-01', 'pnl': -100.0}

Facts only — P&L from replay of recorded trades; no invented fills.