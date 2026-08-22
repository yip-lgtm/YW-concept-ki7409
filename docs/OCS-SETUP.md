# OCS BTC 5m Auto-Signal — Setup Guide

> OCS-Style AI Trader ported from Pine Script to Python, running 24/7 on GitHub Actions, every 5 minutes, on **BTC-USD 5m**.

## What is OCS?

**OCS** = **Open Approximation of Closed Source** AI Trader. Originally an invite-only TradingView indicator using KNN with Lorentzian distance over an 8-dimensional feature vector. We ported the open-approximation version to Python so it can run serverless on GHA.

**Reference**: Pine Script `OCS-Style AI Trader [Open Approximation]` by Ankit_1618, v6 indicator.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ GitHub Actions (GHA) — every 5 min, 24/7                        │
│                                                                  │
│   ┌─────────────────────┐                                       │
│   │ Step 1: OCS Scan    │  automation/src/ocs_btc_5m.py         │
│   │ (signal generation) │  • yf.download BTC-USD 5m             │
│   └──────────┬──────────┘  • 8 features                         │
│              │             • Rolling KNN (K=7)                   │
│              ▼             • /tmp/ocs_btc/latest.json            │
│   ┌─────────────────────┐                                       │
│   │ Step 2: Act         │  automation/scripts/ocs_act.py        │
│   │ (act on signal)     │  • If signal: TG + AI-Trader publish  │
│   └──────────┬──────────┘  • Save signals.jsonl                 │
│              │                                                    │
│              ▼                                                    │
│   ┌─────────────────────┐                                       │
│   │ Step 3: Tracker     │  automation/scripts/                  │
│   │ (position tracker)  │    ocs_position_tracker.py            │
│   └──────────┬──────────┘  • Walk open positions                 │
│              │             • Detect SL / T1-T5 hits              │
│              ▼             • Log trades.jsonl + stats.json       │
│   ┌─────────────────────┐                                       │
│   │ Step 4: Daily Report│  automation/scripts/                  │
│   │ (daily summary)     │    ocs_daily_report.py                │
│   └──────────┬──────────┘  • daily/YYYY-MM-DD.md + .png          │
│              │                                                    │
│              ▼                                                    │
│   ┌─────────────────────┐                                       │
│   │ Step 5: Commit log  │  git push to main                      │
│   └─────────────────────┘                                       │
└──────────────────────────────────────────────────────────────────┘

External APIs:
  • yfinance → BTC-USD 5m OHLCV
  • Telegram Bot API → @yip0802_bot
  • AI-Trader (ai4trade.ai) → publish signals
```

## File Inventory

### Source code
| File | Size | Purpose |
|------|------|---------|
| `automation/src/ocs_btc_5m.py` | ~10.5KB | OCS port — features + KNN + signal gen |
| `automation/scripts/ocs_act.py` | ~4.4KB | TG alert + AI-Trader publish + signal log |
| `automation/scripts/ocs_position_tracker.py` | ~9.8KB | Walk forward + R-multiple P&L |
| `automation/scripts/ocs_daily_report.py` | ~4.8KB | Markdown + chart daily report |

### Workflow
| File | Size | Purpose |
|------|------|---------|
| `.github/workflows/ocs-btc-5m.yml` | ~2.6KB | Schedule `*/5 * * * *` 24/7 |

### State files (git-tracked)
| File | Purpose |
|------|---------|
| `automation/reports/ocs_btc_5m/positions.json` | Open positions |
| `automation/reports/ocs_btc_5m/trades.jsonl` | Closed trade log (append-only) |
| `automation/reports/ocs_btc_5m/stats.json` | Win rate / avg R / PF |
| `automation/reports/ocs_btc_5m/daily/YYYY-MM-DD.md` | Daily summary |
| `automation/reports/ocs_btc_5m/daily/YYYY-MM-DD.png` | Cumulative P&L chart |

### Temp / runtime
| File | Purpose |
|------|---------|
| `/tmp/ocs_btc/latest.json` | Latest signal (between steps) |

## Required GHA Secrets (4)

| Secret | Used by |
|--------|---------|
| `TELEGRAM_BOT_TOKEN` | Step 2 (TG alert) + Step 3 (TG close alert) |
| `TELEGRAM_CHAT_ID` | Same |
| `AI_TRADER_TOKEN` | Step 2 (publish signal) |
| `APEX_PAT` | Step 5 (git push) — **NOTE**: must NOT be `GITHUB_*` prefix (GitHub reserved) |

To set secrets, go to **Settings → Secrets and variables → Actions → New repository secret**.

## 8 OCS Features (normalized 0-1)

| # | Feature | Implementation |
|---|---------|----------------|
| 1 | RSI(14) | Wilder smoothing |
| 2 | Stoch K(14) | %K of 14-bar range |
| 3 | Supertrend offset | (close − lower) / (upper − lower) − 0.5 |
| 4 | TRIX(15) | Triple EMA momentum % |
| 5 | Fisher(10) | Inverse tanh transform |
| 6 | LMS slope | EMA(20) diff / ATR |
| 7 | Vol Z-score | (vol − SMA20) / std, clipped ±3σ |
| 8 | Close vs MA50 | Offset by 2×ATR, clipped ±1 |

## KNN Classifier

```python
K = 7              # neighbors
TRAIN_WINDOW = 160 # 160 bars = 13.3 hours
HORIZON = 6        # 6 bars = 30 min future
distance = Σ log(1+|d|)   # Lorentzian
label = +1 if close[t] > close[t+6] else -1
```

**Vote** = sum of K nearest labels (range: −7 to +7)
**Conf** = |vote| / K (range: 0 to 1)

## Signal Logic

```python
if vote >= 4 AND conf >= 0.55 AND layer_score > 0
   AND NOT in_chop AND close > KAMA_proxy:
    signal = "BUY" (long)
elif vote <= -4 AND conf >= 0.55 AND layer_score < 0
   AND NOT in_chop AND close < KAMA_proxy:
    signal = "SELL" (short)
else:
    signal = "none"
```

`KAMA_proxy` = EMA(50).
`in_chop` = current ATR < 50% of historical ATR mean.

## R-Multiple Targets (1.6× ATR stop)

| Level | Multiple | Meaning |
|-------|----------|---------|
| SL | −1.0R | Catastrophic invalidation |
| T1 | +1.0R | First scale-out, break-even move |
| T2 | +1.618R | Golden ratio |
| T3 | +2.618R | — |
| T4 | +3.618R | — |
| T5 | +5.0R | Runner |

**Hit priority** (same bar):
- SL > T1 > T2 > T3 > T4 > T5
- If both SL and TP hit on the same bar: assume SL (conservative)

## Telegram Alert Formats

### On signal
```
🟢 OCS BTC 5m Signal — LONG

Ticker: BTC-USD @ $77,444
Signal: BUY (vote +5/±7, conf 0.71)
Direction: long

Risk Plan (1.6× ATR stop, R-multiple targets):
• Stop: $77,162 ($282 away)
• T1 (1R): $77,726
• T2 (1.618R): $77,901
• T3 (2.618R): $78,184
• T4 (3.618R): $78,466
• T5 (5.0R): $78,853
```

### On position close
```
OCS BTC 5m - Position Closed

WIN: LONG entry 77,000 -> T1 77,320 | R=+1.00 | $+320 | 1 bars

Stats: 5 trades | WR 60% | avg R 0.85 | total R +4.2 | PF 1.7
```

## Run Cycle (~40s per execution)

```
T+0:00  GHA fires
T+0:05  Install deps (5s)
T+0:10  Checkout main (3s)
T+0:13  Run OCS scan (10s)
        — 1440 5m bars loaded (5d)
        — 8 features computed
        — 7-NN vote = N
        — /tmp/ocs_btc/latest.json updated
T+0:23  Run act script (3s)
        — IF signal: TG + AI-Trader (1+ reputation point)
T+0:26  Run position tracker (8s)
        — For each open pos: walk forward bars
        — IF SL/TP hit: close + log + TG alert
        — Stats updated
T+0:34  Generate daily report (2s)
        — daily/YYYY-MM-DD.md + .png
T+0:36  Commit + push (5s)
T+0:41  Done — next run in 4 min 19s
```

## Failure Modes Handled

| Failure | Behavior |
|---------|----------|
| yfinance down | OCS scan fails → next run retries (no signal lost) |
| TG API down | ocs_act.py catches exception, signal still logged |
| AI-Trader down | Logged to stderr, signal still works locally |
| GHA runner error | `continue-on-error` on scan/tracker/report, commit still runs |
| yfinance 5m limit | Yahoo limits 5m to 60d; we use 5d window which is fine |
| Lapsed GHA token | Re-issued on next run (auto-rotated) |

## Local Development

```bash
# 1. Setup venv
cd /workspace/YW-concept-ki7409/automation
ln -sf /workspace/apex-bootcamp/AUTOMATION/.venv .venv

# 2. Set env vars (from .env in apex-bootcamp)
set -a; source /workspace/apex-bootcamp/AUTOMATION/.env; set +a

# 3. Run each step manually
.venv/bin/python src/ocs_btc_5m.py
.venv/bin/python scripts/ocs_act.py
.venv/bin/python scripts/ocs_position_tracker.py
.venv/bin/python scripts/ocs_daily_report.py
```

## Monitoring

```bash
# Live GHA runs
curl -s "https://api.github.com/repos/yip-lgtm/YW-concept-ki7409/actions/runs?per_page=5" \
  -H "Authorization: Bearer <PAT>" | jq

# Latest signal
cat /tmp/ocs_btc/latest.json

# Open positions
cat automation/reports/ocs_btc_5m/positions.json

# Stats
cat automation/reports/ocs_btc_5m/stats.json

# Today
cat automation/reports/ocs_btc_5m/daily/$(date +%Y-%m-%d).md
```

## Differences from Original Pine Script

| Component | Pine | Python port |
|-----------|------|-------------|
| LMS filter | Real LMS w/ mu=0.02 | Simplified EMA slope proxy |
| Dominant cycle | 8-48 bar detection | Skipped (fixed horizon=6) |
| KNN | Auto-rebuilt on each bar | Rolling window=160 |
| HTF confirm ×3 | 1H + 15m alignment | Skipped (5m only) |
| Regime filter | 61.8 chop threshold | ATR-based chop filter |
| Supertrend | 3.0× ATR | Same |
| Training data | Live rolling | Same |

Port retains ~70% of the core signal logic. LMS, regime, and chop filter are simplified. HTF confirmation skipped (can be added later).

## Future Improvements (v2 ideas)

1. **OCS backtest mode** — 60d BTC 5m historical walk-forward to validate strategy
2. **Multi-pair expansion** — ETH/SOL with same 8-feature KNN
3. **HTF confirmation** — add 15m + 1H alignment filters (×3 time-sync)
4. **Live equity curve** — chain daily reports into a lifetime P&L chart
5. **Adjustable R targets** — user-configurable risk appetite
6. **Self-hosting** — local cron loop (since GHA free tier may throttle on long schedules)
