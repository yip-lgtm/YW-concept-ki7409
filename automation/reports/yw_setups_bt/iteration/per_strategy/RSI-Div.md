# RSI-Div — iteration

- Window: **2026-08-25 → 2026-09-21** (HKT report gen)
- Method: re-sim Apex envelope on live_scan/OCS candidates with post-detect filters
- Filter applied: **`skip MNQ+MGC+MES`**

## BEFORE vs AFTER

| Metric | BEFORE | AFTER | Δ |
|---|---:|---:|---:|
| Net P&L | $-392.94 | $+46.94 | $+439.88 |
| Max DD | $430.30 | $101.05 | $-329.25 |
| WR | 25.0% | 50.0% | +25.0pp |
| n | 16 | 12 | -4 |
| Qual≥$250 | 0 | 0 | +0 |
| Verdict | **drop** | **tweak** | |

## Grade mix (BEFORE accepted)

| Grade | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| A | 8 | 25.0% | $-142.29 | $-17.79 |
| B | 8 | 25.0% | $-250.65 | $-31.33 |

## Best conditions (BEFORE)

- ticker M2K=F: n=3 WR 66.7% $+36.00

## Failure modes (BEFORE)

- ticker BTC-USD: n=6 WR 33.3% $-42.99
- ticker MES=F: n=2 WR 0.0% $-48.15
- ticker MGC=F: n=2 WR 0.0% $-85.90
- ticker MNQ=F: n=3 WR 0.0% $-251.90
- session LDLZ: n=1 WR 0.0% $-21.30
- session other: n=7 WR 28.6% $-108.57
- session NYKZ: n=8 WR 25.0% $-263.07
- direction bullish: n=12 WR 33.3% $-185.74
- direction bearish: n=4 WR 0.0% $-207.20
- grade A: n=8 WR 25.0% $-142.29
- grade B: n=8 WR 25.0% $-250.65

## Ticker / session / direction (BEFORE)

### Ticker
| Ticker | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| M2K=F | 3 | 66.7% | $+36.00 | $+12.00 |
| BTC-USD | 6 | 33.3% | $-42.99 | $-7.17 |
| MES=F | 2 | 0.0% | $-48.15 | $-24.08 |
| MGC=F | 2 | 0.0% | $-85.90 | $-42.95 |
| MNQ=F | 3 | 0.0% | $-251.90 | $-83.97 |

### Session
| Session | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| LDLZ | 1 | 0.0% | $-21.30 | $-21.30 |
| other | 7 | 28.6% | $-108.57 | $-15.51 |
| NYKZ | 8 | 25.0% | $-263.07 | $-32.88 |

### Direction
| Dir | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| bullish | 12 | 33.3% | $-185.74 | $-15.48 |
| bearish | 4 | 0.0% | $-207.20 | $-51.80 |

## Proposed filter tweaks (tested)

1. **`skip MNQ+MGC+MES`** → net $+46.94 (Δ $+439.88), dd $101.05, WR 50.0%, n=12, qual=0, verdict **tweak**
2. **`M2K only`** → net $+28.00 (Δ $+420.94), dd $39.60, WR 60.0%, n=5, qual=0, verdict **tweak**
3. **`skip bearish + skip MNQ`** → net $+20.11 (Δ $+413.05), dd $134.90, WR 41.7%, n=12, qual=0, verdict **tweak**

## All experiments

| Filter | Net | MaxDD | WR | n | Qual | Verdict | raw_after_filter |
|---|---:|---:|---:|---:|---:|---|---:|
| M2K only | $+28.00 | $39.60 | 60.0% | 5 | 0 | tweak | 8 |
| skip bearish + skip MNQ | $+20.11 | $134.90 | 41.7% | 12 | 0 | tweak | 94 |
| bull only | $-333.84 | $371.20 | 30.8% | 13 | 0 | drop | 101 |
| skip NYKZ | $-40.54 | $195.09 | 36.4% | 11 | 0 | drop | 140 |
| skip MNQ+MGC+MES | $+46.94 | $101.05 | 50.0% | 12 | 0 | tweak | 142 |

## AFTER session split

LDLZ n=0 $+0 | NYKZ n=6 $-51 | other n=6 $+98

- Instruments: MBT≈BTC-USD, M2K=F
- Skips: `{"grade_C_or_other": 130}`
- Best day: {'date': '2026-09-03', 'pnl': 74.25} · Worst day: {'date': '2026-09-18', 'pnl': -61.45}

Facts only — P&L from replay of recorded trades; no invented fills.