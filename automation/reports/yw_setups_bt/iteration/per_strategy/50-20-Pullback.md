# 50-20-Pullback — iteration

- Window: **2026-08-25 → 2026-09-21** (HKT report gen)
- Method: re-sim Apex envelope on live_scan/OCS candidates with post-detect filters
- Filter applied: **`skip MGC + keep MNQ all sessions + LDLZ/NYKZ for others`**

## BEFORE vs AFTER

| Metric | BEFORE | AFTER | Δ |
|---|---:|---:|---:|
| Net P&L | $+41.98 | $+696.19 | $+654.21 |
| Max DD | $552.66 | $400.00 | $-152.66 |
| WR | 35.9% | 50.8% | +14.9pp |
| n | 167 | 65 | -102 |
| Qual≥$250 | 1 | 3 | +2 |
| Verdict | **tweak** | **keep** | |

## Grade mix (BEFORE accepted)

| Grade | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| A | 6 | 50.0% | $+177.47 | $+29.58 |
| B | 161 | 35.4% | $-135.49 | $-0.84 |

## Best conditions (BEFORE)

- ticker MNQ=F: n=23 WR 47.8% $+393.78
- ticker BTC-USD: n=82 WR 35.4% $+5.79
- session LDLZ: n=18 WR 50.0% $+182.57 avg $+10.14
- direction short: n=79 WR 32.9% $+122.53

## Failure modes (BEFORE)

- ticker MGC=F: n=8 WR 25.0% $-353.02
- session other: n=136 WR 33.8% $-181.07
- direction long: n=88 WR 38.6% $-80.55
- grade B: n=161 WR 35.4% $-135.49

## Ticker / session / direction (BEFORE)

### Ticker
| Ticker | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| MNQ=F | 23 | 47.8% | $+393.78 | $+17.12 |
| BTC-USD | 82 | 35.4% | $+5.79 | $+0.07 |
| MES=F | 34 | 35.3% | $-2.13 | $-0.06 |
| M2K=F | 20 | 30.0% | $-2.44 | $-0.12 |
| MGC=F | 8 | 25.0% | $-353.02 | $-44.13 |

### Session
| Session | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| LDLZ | 18 | 50.0% | $+182.57 | $+10.14 |
| NYKZ | 13 | 38.5% | $+40.48 | $+3.11 |
| other | 136 | 33.8% | $-181.07 | $-1.33 |

### Direction
| Dir | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| short | 79 | 32.9% | $+122.53 | $+1.55 |
| long | 88 | 38.6% | $-80.55 | $-0.92 |

## Proposed filter tweaks (tested)

1. **`skip MGC + keep MNQ all sessions + LDLZ/NYKZ for others`** → net $+696.19 (Δ $+654.21), dd $400.00, WR 50.8%, n=65, qual=3, verdict **keep**
2. **`A-grade only`** → net $+608.84 (Δ $+566.86), dd $136.20, WR 54.8%, n=31, qual=0, verdict **tweak**
3. **`skip MGC`** → net $+146.14 (Δ $+104.16), dd $500.36, WR 36.1%, n=166, qual=1, verdict **tweak**

## All experiments

| Filter | Net | MaxDD | WR | n | Qual | Verdict | raw_after_filter |
|---|---:|---:|---:|---:|---:|---|---:|
| skip MGC | $+146.14 | $500.36 | 36.1% | 166 | 1 | tweak | 741 |
| LDLZ+NYKZ only | $+59.27 | $348.40 | 41.0% | 39 | 1 | tweak | 71 |
| skip MGC + LDLZ+NYKZ only | $+59.27 | $348.40 | 43.6% | 39 | 1 | tweak | 66 |
| MNQ only | $+133.30 | $497.98 | 44.7% | 38 | 1 | tweak | 130 |
| A-grade only | $+608.84 | $136.20 | 54.8% | 31 | 0 | tweak | 40 |
| skip MGC + keep MNQ all sessions + LDLZ/NYKZ for others | $+696.19 | $400.00 | 50.8% | 65 | 3 | keep | 182 |

## AFTER session split

LDLZ n=17 $+256 | NYKZ n=14 $+62 | other n=34 $+378

- Instruments: MBT≈BTC-USD, M2K=F, MES=F, MNQ=F
- Skips: `{"grade_C_or_other": 3, "overlap_no_scale": 41, "daily_envelope_block": 73}`
- Best day: {'date': '2026-09-10', 'pnl': 300.0} · Worst day: {'date': '2026-08-30', 'pnl': -100.0}

Facts only — P&L from replay of recorded trades; no invented fills.