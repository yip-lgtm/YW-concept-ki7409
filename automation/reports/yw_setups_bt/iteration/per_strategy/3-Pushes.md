# 3-Pushes — iteration

- Window: **2026-08-25 → 2026-09-21** (HKT report gen)
- Method: re-sim Apex envelope on live_scan/OCS candidates with post-detect filters
- Filter applied: **`MNQ+BTC up only`**

## BEFORE vs AFTER

| Metric | BEFORE | AFTER | Δ |
|---|---:|---:|---:|
| Net P&L | $-304.67 | $+623.17 | $+927.84 |
| Max DD | $517.98 | $195.26 | $-322.72 |
| WR | 35.4% | 40.0% | +4.6pp |
| n | 82 | 50 | -32 |
| Qual≥$250 | 0 | 0 | +0 |
| Verdict | **drop** | **tweak** | |

## Grade mix (BEFORE accepted)

| Grade | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| B | 82 | 35.4% | $-304.67 | $-3.72 |

## Best conditions (BEFORE)

- ticker MNQ=F: n=12 WR 41.7% $+186.26
- ticker BTC-USD: n=40 WR 42.5% $+76.18
- session NYKZ: n=9 WR 22.2% $+74.47 avg $+8.27
- direction up: n=42 WR 38.1% $+232.71

## Failure modes (BEFORE)

- ticker MES=F: n=11 WR 18.2% $-207.40
- ticker MGC=F: n=9 WR 11.1% $-356.06
- session LDLZ: n=9 WR 44.4% $-114.83
- session other: n=64 WR 35.9% $-264.31
- direction down: n=40 WR 32.5% $-537.38
- grade B: n=82 WR 35.4% $-304.67

## Ticker / session / direction (BEFORE)

### Ticker
| Ticker | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| MNQ=F | 12 | 41.7% | $+186.26 | $+15.52 |
| BTC-USD | 40 | 42.5% | $+76.18 | $+1.90 |
| M2K=F | 10 | 40.0% | $-3.65 | $-0.37 |
| MES=F | 11 | 18.2% | $-207.40 | $-18.85 |
| MGC=F | 9 | 11.1% | $-356.06 | $-39.56 |

### Session
| Session | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| NYKZ | 9 | 22.2% | $+74.47 | $+8.27 |
| LDLZ | 9 | 44.4% | $-114.83 | $-12.76 |
| other | 64 | 35.9% | $-264.31 | $-4.13 |

### Direction
| Dir | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| up | 42 | 38.1% | $+232.71 | $+5.54 |
| down | 40 | 32.5% | $-537.38 | $-13.43 |

## Proposed filter tweaks (tested)

1. **`MNQ+BTC up only`** → net $+623.17 (Δ $+927.84), dd $195.26, WR 40.0%, n=50, qual=0, verdict **tweak**
2. **`skip MGC + skip MES`** → net $+586.57 (Δ $+891.24), dd $239.31, WR 40.7%, n=91, qual=2, verdict **tweak**
3. **`skip MGC/MES + up only`** → net $+585.96 (Δ $+890.63), dd $187.85, WR 41.7%, n=60, qual=0, verdict **tweak**

## All experiments

| Filter | Net | MaxDD | WR | n | Qual | Verdict | raw_after_filter |
|---|---:|---:|---:|---:|---:|---|---:|
| skip MGC + skip MES | $+586.57 | $239.31 | 40.7% | 91 | 2 | tweak | 261 |
| bull/up only | $+282.77 | $339.59 | 42.4% | 59 | 0 | tweak | 182 |
| MNQ+BTC up only | $+623.17 | $195.26 | 40.0% | 50 | 0 | tweak | 110 |
| skip MGC/MES + up only | $+585.96 | $187.85 | 41.7% | 60 | 0 | tweak | 137 |
| MNQ only | $+270.06 | $378.50 | 40.7% | 27 | 2 | tweak | 85 |

## AFTER session split

LDLZ n=3 $-46 | NYKZ n=8 $+373 | other n=39 $+296

- Instruments: MBT≈BTC-USD, MNQ=F
- Skips: `{"grade_C_or_other": 4, "overlap_no_scale": 54, "daily_envelope_block": 2}`
- Best day: {'date': '2026-09-02', 'pnl': 244.34} · Worst day: {'date': '2026-09-01', 'pnl': -100.0}

Facts only — P&L from replay of recorded trades; no invented fills.