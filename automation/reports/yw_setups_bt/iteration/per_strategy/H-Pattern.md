# H-Pattern — iteration

- Window: **2026-08-25 → 2026-09-21** (HKT report gen)
- Method: re-sim Apex envelope on live_scan/OCS candidates with post-detect filters
- Filter applied: **`NYKZ only`**

## BEFORE vs AFTER

| Metric | BEFORE | AFTER | Δ |
|---|---:|---:|---:|
| Net P&L | $+8.11 | $+78.96 | $+70.85 |
| Max DD | $174.85 | $32.95 | $-141.90 |
| WR | 36.4% | 60.0% | +23.6pp |
| n | 22 | 5 | -17 |
| Qual≥$250 | 0 | 0 | +0 |
| Verdict | **tweak** | **tweak** | |

## Grade mix (BEFORE accepted)

| Grade | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| B | 22 | 36.4% | $+8.11 | $+0.37 |

## Best conditions (BEFORE)

- ticker BTC-USD: n=22 WR 36.4% $+8.11
- session NYKZ: n=5 WR 60.0% $+78.96 avg $+15.79

## Failure modes (BEFORE)

- session other: n=17 WR 29.4% $-70.85

## Ticker / session / direction (BEFORE)

### Ticker
| Ticker | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| BTC-USD | 22 | 36.4% | $+8.11 | $+0.37 |

### Session
| Session | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| NYKZ | 5 | 60.0% | $+78.96 | $+15.79 |
| other | 17 | 29.4% | $-70.85 | $-4.17 |

### Direction
| Dir | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| long | 20 | 35.0% | $+21.23 | $+1.06 |
| short | 2 | 50.0% | $-13.12 | $-6.56 |

## Proposed filter tweaks (tested)

1. **`NYKZ only`** → net $+78.96 (Δ $+70.85), dd $32.95, WR 60.0%, n=5, qual=0, verdict **tweak**
2. **`NYKZ long only`** → net $+78.96 (Δ $+70.85), dd $32.95, WR 60.0%, n=5, qual=0, verdict **tweak**
3. **`skip other session`** → net $+78.96 (Δ $+70.85), dd $32.95, WR 60.0%, n=5, qual=0, verdict **tweak**

## All experiments

| Filter | Net | MaxDD | WR | n | Qual | Verdict | raw_after_filter |
|---|---:|---:|---:|---:|---:|---|---:|
| NYKZ only | $+78.96 | $32.95 | 60.0% | 5 | 0 | tweak | 16 |
| NYKZ long only | $+78.96 | $32.95 | 60.0% | 5 | 0 | tweak | 16 |
| skip other session | $+78.96 | $32.95 | 60.0% | 5 | 0 | tweak | 24 |
| long only | $+21.23 | $140.20 | 35.0% | 20 | 0 | tweak | 118 |

## AFTER session split

BTC 24h — LDLZ n=0 $+0 | NYKZ n=5 $+79 | other n=0 $+0

- Instruments: MBT≈BTC-USD
- Skips: `{"grade_C_or_other": 11}`
- Best day: {'date': '2026-09-21', 'pnl': 69.57} · Worst day: {'date': '2026-09-01', 'pnl': -32.95}

Facts only — P&L from replay of recorded trades; no invented fills.