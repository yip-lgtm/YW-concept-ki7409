# Stair — iteration

- Window: **2026-08-25 → 2026-09-21** (HKT report gen)
- Method: re-sim Apex envelope on live_scan/OCS candidates with post-detect filters
- Filter applied: **`skip NYKZ + skip BTC + skip MES`**

## BEFORE vs AFTER

| Metric | BEFORE | AFTER | Δ |
|---|---:|---:|---:|
| Net P&L | $+405.79 | $+1,363.54 | $+957.75 |
| Max DD | $293.32 | $290.55 | $-2.77 |
| WR | 40.6% | 52.6% | +12.0pp |
| n | 101 | 57 | -44 |
| Qual≥$250 | 1 | 2 | +1 |
| Verdict | **tweak** | **tweak** | |

## Grade mix (BEFORE accepted)

| Grade | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| A | 66 | 40.9% | $+321.25 | $+4.87 |
| B | 35 | 40.0% | $+84.54 | $+2.42 |

## Best conditions (BEFORE)

- ticker MGC=F: n=14 WR 57.1% $+416.05
- ticker MNQ=F: n=22 WR 40.9% $+88.67
- ticker M2K=F: n=18 WR 38.9% $+31.36
- session other: n=86 WR 40.7% $+452.21 avg $+5.26
- session LDLZ: n=7 WR 85.7% $+218.51 avg $+31.22
- direction short: n=101 WR 40.6% $+405.79

## Failure modes (BEFORE)

- ticker MES=F: n=19 WR 36.8% $-58.95
- ticker BTC-USD: n=28 WR 35.7% $-71.34
- session NYKZ: n=8 WR 0.0% $-264.93

## Ticker / session / direction (BEFORE)

### Ticker
| Ticker | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| MGC=F | 14 | 57.1% | $+416.05 | $+29.72 |
| MNQ=F | 22 | 40.9% | $+88.67 | $+4.03 |
| M2K=F | 18 | 38.9% | $+31.36 | $+1.74 |
| MES=F | 19 | 36.8% | $-58.95 | $-3.10 |
| BTC-USD | 28 | 35.7% | $-71.34 | $-2.55 |

### Session
| Session | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| other | 86 | 40.7% | $+452.21 | $+5.26 |
| LDLZ | 7 | 85.7% | $+218.51 | $+31.22 |
| NYKZ | 8 | 0.0% | $-264.93 | $-33.12 |

### Direction
| Dir | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| short | 101 | 40.6% | $+405.79 | $+4.02 |

## Proposed filter tweaks (tested)

1. **`skip NYKZ + skip BTC + skip MES`** → net $+1,363.54 (Δ $+957.75), dd $290.55, WR 52.6%, n=57, qual=2, verdict **tweak**
2. **`allowlist MGC+MNQ+M2K + skip NYKZ`** → net $+1,363.54 (Δ $+957.75), dd $290.55, WR 52.6%, n=57, qual=2, verdict **tweak**
3. **`skip NYKZ`** → net $+631.14 (Δ $+225.35), dd $292.40, WR 43.6%, n=94, qual=1, verdict **tweak**

## All experiments

| Filter | Net | MaxDD | WR | n | Qual | Verdict | raw_after_filter |
|---|---:|---:|---:|---:|---:|---|---:|
| skip NYKZ | $+631.14 | $292.40 | 43.6% | 94 | 1 | tweak | 229 |
| skip NYKZ + skip BTC + skip MES | $+1,363.54 | $290.55 | 52.6% | 57 | 2 | tweak | 126 |
| allowlist MGC+MNQ+M2K + skip NYKZ | $+1,363.54 | $290.55 | 52.6% | 57 | 2 | tweak | 126 |
| LDLZ + other only, allowlist MGC | $+566.60 | $500.00 | 52.0% | 25 | 2 | tweak | 42 |

## AFTER session split

LDLZ n=5 $+172 | NYKZ n=0 $+0 | other n=52 $+1191

- Instruments: M2K=F, MGC=F, MNQ=F
- Skips: `{"overlap_no_scale": 39, "daily_envelope_block": 30}`
- Best day: {'date': '2026-09-09', 'pnl': 300.0} · Worst day: {'date': '2026-08-31', 'pnl': -100.0}

Facts only — P&L from replay of recorded trades; no invented fills.