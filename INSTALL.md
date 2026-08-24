# Installation & Setup Guide

> **YW Concept Trading Automation** — Daily LLM-graded reminders + 24/7 OCS BTC 5m auto-signal pipeline.

## 📋 Prerequisites

- **Python 3.11+** (tested on 3.11.16)
- **Git** (for cloning + workflow_dispatch)
- **GitHub account** (for GHA + secrets)
- **API keys** (3 required for full pipeline):
  - **Massive.com** (formerly Polygon.io) API key — for 5m BTC data
  - **MiniMax-M3** LLM API key — for grading strategies
  - **Telegram bot token + chat ID** — for outbound alerts

---

## 🚀 Quick Start (Local Dev)

### 1. Clone the repo

```bash
git clone https://github.com/yip-lgtm/YW-concept-ki7409.git
cd YW-concept-ki7409
```

### 2. Set up Python venv

```bash
cd automation
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Note**: Sandbox environments may have pypi blocked. Symlink to an existing venv:

```bash
ln -sf /path/to/existing/venv .venv
```

### 3. Configure environment variables

Create `automation/.env` (gitignored):

```bash
# Massive.com (Polygon rebrand) — 5m crypto data
# Free tier: 5 calls/min, 15-min delayed
# Basic tier: $9/mo, real-time
POLYGON_API_KEY=your_massive_key_here

# MiniMax-M3 LLM — strategy grading
MINIMAX_API_KEY=sk-cp-your_key_here

# Telegram bot (via @BotFather)
TELEGRAM_BOT_TOKEN=1234567890:ABCDEFG_your_bot_token
TELEGRAM_CHAT_ID=1234567890

# AI-Trader (ai4trade.ai) — signal publishing
AI_TRADER_TOKEN=your_ai_trader_token

# GitHub PAT (for GHA git push)
APEX_PAT=ghp_your_pat
```

### 4. Test each component

```bash
# Set env
set -a; source automation/.env; set +a

# Test data source
.venv/bin/python -c "
import sys
sys.path.insert(0, 'automation/src')
from data_source import fetch_bars
df = fetch_bars('BTC-USD', days=2, interval_min=5)
print(f'OK: {len(df)} bars, last close: \${df[\"Close\"].iloc[-1]:,.2f}')
"

# Test OCS scan
.venv/bin/python automation/src/ocs_btc_5m.py

# Test position tracker
.venv/bin/python automation/scripts/ocs_position_tracker.py

# Test daily report
.venv/bin/python automation/scripts/ocs_daily_report.py

# Test 20d backtest
.venv/bin/python automation/scripts/ocs_backtest.py --days 20
```

Expected output:
- Data source: 1000+ bars, fresh last close
- OCS scan: vote/conf/layer_score (may be "no signal" — normal)
- Tracker: "0 open position(s)"
- Daily report: `daily/YYYY-MM-DD.md` + `.png` created
- Backtest: 271 trades, +21.00R, 53.9% WR

---

## ⚙️ GitHub Actions Setup (Production)

### 1. Push to your fork

```bash
# Fork the repo on GitHub first
git remote add origin https://github.com/YOUR_USERNAME/YW-concept-ki7409.git
git push -u origin main
```

### 2. Set GHA secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Required by | How to get |
|--------|-------------|------------|
| `TELEGRAM_BOT_TOKEN` | All alerts | Message @BotFather on Telegram |
| `TELEGRAM_CHAT_ID` | All alerts | Send /start to your bot, then `https://api.telegram.org/bot<TOKEN>/getUpdates` |
| `MINIMAX_API_KEY` | LLM grading | MiniMax-M3 dashboard |
| `POLYGON_API_KEY` | 5m data (optional) | https://massive.com/dashboard |
| `AI_TRADER_TOKEN` | Signal publishing (optional) | https://ai4trade.ai |
| `APEX_PAT` | Auto-commit + push | GitHub Settings → Tokens (fine-grained, repo scope) |

**Note**: Do NOT use `GITHUB_*` prefix — GitHub reserves that namespace. Use `APEX_PAT` instead.

### 3. Verify workflows

The repo ships with 3 GHA workflows in `.github/workflows/`:

| Workflow | Cron | Purpose |
|----------|------|---------|
| `yw-daily.yml` | `0 13 * * 1-5` UTC (21:00 HKT weekdays) | Daily LLM-graded reminder with 4-Chart Standard |
| `yw-publish-signal.yml` | `30 13 * * 1-5` UTC (21:30 HKT weekdays) | Publish top YW signal to AI-Trader |
| `ocs-btc-5m.yml` | `*/5 * * * *` (24/7 every 5 min) | OCS BTC 5m auto-signal pipeline |

**Each workflow runs automatically** — no manual triggering required.

### 4. Manual trigger (for testing)

```bash
# Trigger OCS BTC 5m workflow
gh workflow run ocs-btc-5m.yml

# Or via API
curl -X POST \
  -H "Authorization: Bearer YOUR_PAT" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/YOUR_USERNAME/YW-concept-ki7409/actions/workflows/ocs-btc-5m.yml/dispatches \
  -d '{"ref":"main"}'
```

---

## 📁 Project Structure

```
YW-concept-ki7409/
├── automation/
│   ├── src/                        # Core source
│   │   ├── data_source.py          # Polygon + yfinance abstraction
│   │   ├── ocs_btc_5m.py           # OCS signal generation (KNN + 8 features)
│   │   ├── yw_daily.py             # YW daily reminder pipeline
│   │   ├── yw_indicators.py        # Strategy detectors (H-Pattern, 3-Pushes, etc.)
│   │   ├── yw_indicators_extra.py  # CRT, Stair-Pattern, Kell Cycle
│   │   ├── yw_grader.py            # Priority scoring + ranking
│   │   ├── env_loader.py           # .env loader
│   │   └── llm_grader.py           # LLM-based grading (apex-bootcamp)
│   ├── scripts/                    # Operational scripts
│   │   ├── ocs_act.py              # TG alert + AI-Trader publish on signal
│   │   ├── ocs_position_tracker.py # Walk forward positions, R-multiple P&L
│   │   ├── ocs_daily_report.py     # Daily summary (md + chart)
│   │   ├── ocs_backtest.py         # Historical backtest mode
│   │   ├── publish_signal.py       # YW signal publisher
│   │   └── summarize_log.py        # Forward log P&L summarizer
│   ├── reports/                    # Generated reports (gitignored)
│   │   ├── daily/                  # YW daily reminders
│   │   └── ocs_btc_5m/             # OCS state + backtest results
│   └── requirements.txt
├── docs/                           # Concept documentation (Chinese)
│   ├── 01-YW-Concept-Overview.md
│   ├── 02-H-Pattern.md
│   ├── ... (16 concept docs)
│   └── OCS-SETUP.md                # OCS pipeline details
├── mt5/                            # MetaTrader 5 EAs
├── .github/workflows/              # 3 GHA workflows
├── INSTALL.md                      # ← This file
├── README.md
└── requirements.txt                # Top-level deps
```

---

## 🧪 Verification Checklist

After install, verify each component works:

| Component | Expected | Command |
|-----------|----------|---------|
| Data source | 1000+ BTC 5m bars | `python -c "from data_source import fetch_bars; print(len(fetch_bars('BTC-USD', days=5)))"` |
| OCS scan | vote/conf output | `python src/ocs_btc_5m.py` |
| Position tracker | "0 open positions" | `python scripts/ocs_position_tracker.py` |
| Daily report | `daily/YYYY-MM-DD.md` | `python scripts/ocs_daily_report.py` |
| 20d backtest | ~270 trades, PF > 1.0 | `python scripts/ocs_backtest.py --days 20` |

---

## 🐛 Common Issues

### "No data" from Polygon
- Free tier: 5 calls/min, 15-min delayed
- **Fix**: Wait 60s, or upgrade to Basic ($9/mo) for real-time
- **Fallback**: yfinance automatically used if Polygon fails

### "POLYGON_API_KEY" not set
- Check `automation/.env` exists
- Run `set -a; source automation/.env; set +a` before running scripts

### GHA workflow fails with "403 / 401"
- Secret not set: Check **Settings → Secrets**
- Wrong name: Must be `APEX_PAT` not `GITHUB_PAT` (reserved prefix)

### "ModuleNotFoundError: No module named 'requests'"
- venv not activated or packages not installed
- Run: `.venv/bin/pip install -r requirements.txt`
- Or symlink: `ln -sf /path/to/existing/venv .venv`

### "Could not find a version that satisfies the requirement" (pypi blocked)
- pypi access is restricted in some sandboxes
- Use cached packages from a working venv:
  ```bash
  ln -sf /workspace/apex-bootcamp/AUTOMATION/.venv .venv
  ```

### OCS signals never fire
- Check `in_chop` is False in logs (chop filter)
- Check `vote >= 4` and `conf >= 0.55` in logs (KNN threshold)
- Check yfinance returns fresh data (last bar < 1 hour old)
- Run backtest: `python scripts/ocs_backtest.py --days 20` to validate strategy

---

## 📊 Performance Expectations (backtest 20d)

| Metric | Value |
|--------|-------|
| Trades (20d) | ~270 (~13.5/day) |
| Win rate | 53.9% |
| Profit factor | 1.17 |
| Avg R | +0.08 |
| Total R (20d) | +21.00R |

**Live trading differs** — current volatility regime affects trigger rate. Expect 5-30 signals/day depending on market.

---

## 🔐 Security Notes

- **Never commit `.env`** — it's in `.gitignore`
- **API keys should be GitHub secrets** (encrypted with sealed box)
- **PAT should be fine-grained** with only `contents: write` scope
- **Rotate keys every 90 days** for production

---

## 📞 Support

- **GitHub Issues**: https://github.com/yip-lgtm/YW-concept-ki7409/issues
- **Discord**: YW Trader HK `#📖｜ywconcept百科全書`
- **AI-Trader platform**: https://ai4trade.ai

---

**Last updated**: 2026-08-24
**Version**: v1.4 (OCS + YW + AI-Trader)
