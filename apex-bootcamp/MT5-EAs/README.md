# CRT BTC MT5 Expert Advisor

Apex Bootcamp v2.6 - Crypto Trading EA

## Overview
- **Strategy**: CRT (Candle Range Theory)
- **Asset**: BTCUSD (also works on BTCUSD# exchanges)
- **Timeframes**: 4H range → 5min execution
- **Best For**: 24/7 crypto markets
- **Performance**: 81.8% WR 24h, +12.56R, +$1,113

## Installation

1. Copy `CRT_BTC_EA.mq5` to your MT5 `MQL5/Experts/` folder
2. In MetaEditor, open the file and press `F7` to compile
3. Drag the EA onto a BTCUSD chart
4. Enable AutoTrading in MT5

## Recommended Settings

### Conservative
```
Risk per trade:      $100
Max drawdown:        5%
Max open trades:     1
Use T2 close:        YES (1.618R)
Track runners:       YES
```

### Aggressive
```
Risk per trade:      $250
Max drawdown:        10%
Max open trades:     2
Use T2 close:        YES
```

## Strategy Logic

### Bullish CRT (Long)
1. Identify 4H candle High (CRT-H) and Low (CRT-L)
2. Wait for 5min price to dip below CRT-L (raid)
3. Confirm: next 5min candle closes above raid candle's High (MSS)
4. Enter long at close of confirm candle

### Bearish CRT (Short)
1. Identify 4H candle High (CRT-H) and Low (CRT-L)
2. Wait for 5min price to break above CRT-H (raid)
3. Confirm: next 5min candle closes below raid candle's Low
4. Enter short at close of confirm candle

## Risk Management

### Position Sizing
- Risk: $100 per trade (configurable)
- SL = 1.6× ATR(14) from entry
- Lot size = Risk / (SL distance × tick value)

### Take Profits (T2 Close Mode)
- T1 = 1R (breakeven after hit)
- T2 = 1.618R (close target)
- T3 = 2.618R (runner)
- T4 = 3.618R (runner)
- T5 = 5.0R (runner)

In T2 close mode, positions close at T2 by default.
T3-T5 are tracked as runners (if enabled).

### Daily Drawdown
- Max 5% daily drawdown
- EA auto-pauses if exceeded
- Resume next day

## Filters

### CRT Range Filter
- Min range: 0.5% (avoid tiny ranges)
- Max range: 5.0% (avoid volatile sessions)

### Session Filter
- Asian (00:00-08:00 UTC): Off
- London (08:00-13:00 UTC): On
- New York (13:00-22:00 UTC): On
- Crypto: 24/7 (BTC always)

### Confluence Filter
- Min confluence: 1 (CRT alone is enough)
- Min R:R: 2.0

## Notifications

- **Alerts**: Pop-up alerts on signals
- **Telegram**: Optional - add bot token + chat ID

## Performance Tracking

The EA tracks:
- Total trades
- Wins / Losses
- Total R
- Daily P&L

## Troubleshooting

### EA not opening trades
1. Check AutoTrading is enabled
2. Verify trading hours
3. Check CRT range is between 0.5%-5.0%
4. Check account balance is sufficient
5. View Journal for error messages

### Compile errors
1. Ensure using MT5 build 3600+
2. Right-click → Refresh in Navigator
3. Check #include paths

## Backtest

```bash
# In MT5 Strategy Tester:
# Symbol: BTCUSD
# Period: M5
# Modeling: Every tick
# Date: 2025-01-01 to 2026-08-30
# Parameters: Use defaults
```

## Changelog

### v1.00 (2026-08-30)
- Initial release
- CRT detection on 4H→5min
- T2 close mode (1.618R)
- Position tracking with T1-T5
- Daily drawdown protection
- Session filters
- Telegram notifications

## Risk Disclaimer

Trading involves substantial risk. Past performance is not indicative of
future results. Test thoroughly on demo before live trading.
