# Kell-Cycle — iteration

- Window: **2026-08-25 → 2026-09-21** (HKT report gen)
- Method: re-sim Apex envelope on live_scan/OCS candidates with post-detect filters
- Filter applied: **`MGC short only`**

## BEFORE vs AFTER

| Metric | BEFORE | AFTER | Δ |
|---|---:|---:|---:|
| Net P&L | $+292.52 | $+387.50 | $+94.98 |
| Max DD | $406.42 | $132.60 | $-273.82 |
| WR | 40.6% | 55.6% | +15.0pp |
| n | 32 | 9 | -23 |
| Qual≥$250 | 2 | 1 | -1 |
| Verdict | **tweak** | **tweak** | |

## Grade mix (BEFORE accepted)

| Grade | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| B | 31 | 38.7% | $+215.42 | $+6.95 |
| A | 1 | 100.0% | $+77.10 | $+77.10 |

## Best conditions (BEFORE)

- ticker MGC=F: n=13 WR 46.2% $+331.42
- ticker M2K=F: n=3 WR 66.7% $+26.50
- ticker MES=F: n=5 WR 40.0% $+6.55
- session other: n=29 WR 37.9% $+290.40 avg $+10.01
- direction short: n=16 WR 43.8% $+451.96

## Failure modes (BEFORE)

- ticker MNQ=F: n=4 WR 25.0% $-61.46
- session NYKZ: n=2 WR 50.0% $-30.03
- direction long: n=16 WR 37.5% $-159.44

## Ticker / session / direction (BEFORE)

### Ticker
| Ticker | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| MGC=F | 13 | 46.2% | $+331.42 | $+25.49 |
| M2K=F | 3 | 66.7% | $+26.50 | $+8.83 |
| MES=F | 5 | 40.0% | $+6.55 | $+1.31 |
| BTC-USD | 7 | 28.6% | $-10.49 | $-1.50 |
| MNQ=F | 4 | 25.0% | $-61.46 | $-15.37 |

### Session
| Session | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| other | 29 | 37.9% | $+290.40 | $+10.01 |
| LDLZ | 1 | 100.0% | $+32.15 | $+32.15 |
| NYKZ | 2 | 50.0% | $-30.03 | $-15.02 |

### Direction
| Dir | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| short | 16 | 43.8% | $+451.96 | $+28.25 |
| long | 16 | 37.5% | $-159.44 | $-9.96 |

## Proposed filter tweaks (tested)

1. **`MGC short only`** → net $+387.50 (Δ $+94.98), dd $132.60, WR 55.6%, n=9, qual=1, verdict **tweak**
2. **`short only`** → net $+385.35 (Δ $+92.83), dd $262.87, WR 41.2%, n=17, qual=2, verdict **tweak**
3. **`short only + skip BTC + skip MNQ`** → net $+373.10 (Δ $+80.58), dd $144.20, WR 50.0%, n=12, qual=2, verdict **tweak**

## All experiments

| Filter | Net | MaxDD | WR | n | Qual | Verdict | raw_after_filter |
|---|---:|---:|---:|---:|---:|---|---:|
| short only | $+385.35 | $262.87 | 41.2% | 17 | 2 | tweak | 89 |
| short only + skip BTC + skip MNQ | $+373.10 | $144.20 | 50.0% | 12 | 2 | tweak | 33 |
| MGC short only | $+387.50 | $132.60 | 55.6% | 9 | 1 | tweak | 12 |
| skip long + skip MNQ | $+358.03 | $159.27 | 42.9% | 14 | 2 | tweak | 79 |

## AFTER session split

LDLZ n=0 $+0 | NYKZ n=1 $-100 | other n=8 $+488

- Instruments: MGC=F
- Skips: `{"grade_C_or_other": 2, "daily_envelope_block": 1}`
- Best day: {'date': '2026-09-01', 'pnl': 300.0} · Worst day: {'date': '2026-08-31', 'pnl': -100.0}

Facts only — P&L from replay of recorded trades; no invented fills.