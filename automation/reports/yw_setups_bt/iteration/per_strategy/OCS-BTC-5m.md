# OCS-BTC-5m — iteration

- Window: **2026-08-25 → 2026-09-21** (HKT report gen)
- Method: re-sim Apex envelope on live_scan/OCS candidates with post-detect filters
- Filter applied: **`LDLZ + NYKZ long`**

## BEFORE vs AFTER

| Metric | BEFORE | AFTER | Δ |
|---|---:|---:|---:|
| Net P&L | $+2.97 | $+254.50 | $+251.53 |
| Max DD | $413.25 | $195.98 | $-217.27 |
| WR | 48.4% | 58.6% | +10.2pp |
| n | 397 | 87 | -310 |
| Qual≥$250 | 0 | 0 | +0 |
| Verdict | **tweak** | **tweak** | |

## Grade mix (BEFORE accepted)

| Grade | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| B | 397 | 48.4% | $+2.97 | $+0.01 |

## Best conditions (BEFORE)

- ticker BTC-USD: n=397 WR 48.4% $+2.97
- session LDLZ: n=55 WR 60.0% $+169.98 avg $+3.09
- direction long: n=194 WR 49.0% $+87.01

## Failure modes (BEFORE)

- session other: n=276 WR 46.0% $-176.26
- direction short: n=203 WR 47.8% $-84.04

## Ticker / session / direction (BEFORE)

### Ticker
| Ticker | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| BTC-USD | 397 | 48.4% | $+2.97 | $+0.01 |

### Session
| Session | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| LDLZ | 55 | 60.0% | $+169.98 | $+3.09 |
| NYKZ | 66 | 48.5% | $+9.25 | $+0.14 |
| other | 276 | 46.0% | $-176.26 | $-0.64 |

### Direction
| Dir | n | WR | Net | Avg |
|---|---:|---:|---:|---:|
| long | 194 | 49.0% | $+87.01 | $+0.45 |
| short | 203 | 47.8% | $-84.04 | $-0.41 |

## Proposed filter tweaks (tested)

1. **`LDLZ + NYKZ long`** → net $+254.50 (Δ $+251.53), dd $195.98, WR 58.6%, n=87, qual=0, verdict **tweak**
2. **`LDLZ+NYKZ only`** → net $+179.23 (Δ $+176.26), dd $197.63, WR 53.7%, n=121, qual=0, verdict **tweak**
3. **`skip other`** → net $+179.23 (Δ $+176.26), dd $197.63, WR 53.7%, n=121, qual=0, verdict **tweak**

## All experiments

| Filter | Net | MaxDD | WR | n | Qual | Verdict | raw_after_filter |
|---|---:|---:|---:|---:|---:|---|---:|
| LDLZ only | $+169.98 | $105.35 | 60.0% | 55 | 0 | tweak | 55 |
| LDLZ + NYKZ long | $+254.50 | $195.98 | 58.6% | 87 | 0 | tweak | 87 |
| LDLZ+NYKZ only | $+179.23 | $197.63 | 53.7% | 121 | 0 | tweak | 121 |
| long only | $+100.91 | $280.20 | 49.0% | 194 | 0 | tweak | 200 |
| skip other | $+179.23 | $197.63 | 53.7% | 121 | 0 | tweak | 121 |

## AFTER session split

BTC 24h — LDLZ n=55 $+170 | NYKZ n=32 $+85 | other n=0 $+0

- Instruments: MBT≈BTC-USD
- Skips: `{}`
- Best day: {'date': '2026-09-21', 'pnl': 146.89} · Worst day: {'date': '2026-09-11', 'pnl': -55.93}

Facts only — P&L from replay of recorded trades; no invented fills.