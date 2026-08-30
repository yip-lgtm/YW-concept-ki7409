//+------------------------------------------------------------------+
//|                                          CRT_BTC_EA.mq5          |
//|                                          Apex Bootcamp EA       |
//|                                          v1.01 - 2026-08-30     |
//+------------------------------------------------------------------+
#property copyright "Apex Bootcamp"
#property link      "https://github.com/yip-lgtm/apex-bootcamp"
#property version   "1.01"
#property strict

// Required includes
#include <Trade\Trade.mqh>

//+------------------------------------------------------------------+
//| Input Parameters                                                  |
//+------------------------------------------------------------------+
input group "=== Risk Management ==="
input double RiskUSD        = 100.0;    // Risk per trade (USD)
input double MaxDrawdownPct  = 5.0;     // Max daily drawdown %
input int    MaxOpenTrades   = 1;       // Max concurrent trades

input group "=== CRT Strategy ==="
input ENUM_TIMEFRAMES CRT_TF   = PERIOD_H4;   // CRT range timeframe
input ENUM_TIMEFRAMES ENTRY_TF = PERIOD_M5;   // Entry timeframe
input double MinCRTRangePct    = 0.5;          // Min CRT range (%)
input double MaxCRTRangePct    = 5.0;          // Max CRT range (%)
input int    ATR_Period         = 14;            // ATR period
input double ATR_StopMult       = 1.6;           // SL = ATR * this

input group "=== T2 Close Mode (1.618R) ==="
input bool   UseT2Close         = true;          // Use T2 close instead of T1
input double T2_R_Mult          = 1.618;          // T2 multiplier
input bool   TrackRunners       = true;          // Track T3-T5 runners

input group "=== Trade Filters ==="
input bool   TradeLongs         = true;           // Allow long trades
input bool   TradeShorts        = true;           // Allow short trades
input bool   TradeCrypto        = true;           // 24/7 (BTC always)

input group "=== Notifications ==="
input bool   EnableAlerts       = true;           // Pop-up alerts
input string TelegramToken      = "";             // Telegram bot token
input string TelegramChat       = "";             // Telegram chat ID

//+------------------------------------------------------------------+
//| Global Variables                                                  |
//+------------------------------------------------------------------+
CTrade trade;
int atrHandle;
datetime lastBarTime = 0;
int totalTrades = 0;
int wins = 0;
int losses = 0;
double totalR = 0;

// Track open positions
struct TradeTracker
{
    ulong  ticket;
    double entry;
    double sl;
    double t1;
    double t2;
    double size;
    int    direction;    // +1 long, -1 short
    bool   t1Hit;
    bool   closed;
};

TradeTracker trackers[];

//+------------------------------------------------------------------+
//| Expert initialization function                                    |
//+------------------------------------------------------------------+
int OnInit()
{
    if(RiskUSD <= 0)
    {
        Print("ERROR: RiskUSD must be > 0");
        return(INIT_PARAMETERS_INCORRECT);
    }

    atrHandle = iATR(_Symbol, ENTRY_TF, ATR_Period);
    if(atrHandle == INVALID_HANDLE)
    {
        Print("ERROR: Failed to create ATR handle");
        return(INIT_FAILED);
    }

    Print("=== CRT BTC EA v1.01 Initialized ===");
    Print("Symbol: ", _Symbol);
    Print("Risk per trade: $", DoubleToString(RiskUSD, 2));
    Print("Use T2 close: ", UseT2Close ? "YES (1.618R)" : "NO (T1 1R)");

    if(EnableAlerts) Alert("CRT BTC EA v1.01 started on ", _Symbol);

    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                  |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    if(atrHandle != INVALID_HANDLE) IndicatorRelease(atrHandle);
    Print("=== CRT BTC EA stopped ===");
    Print("Stats: ", totalTrades, " trades, ", wins, "W-", losses, "L, Total R: ", DoubleToString(totalR, 2));
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick()
{
    datetime currentBarTime = iTime(_Symbol, ENTRY_TF, 0);
    bool isNewBar = (currentBarTime != lastBarTime);
    if(isNewBar) lastBarTime = currentBarTime;

    if(CheckDailyDrawdown()) return;

    // Manage existing positions
    ManageOpenPositions();

    // Look for new signals
    if(isNewBar && !IsTradingTime()) return;
    if(isNewBar && CountOpenPositions() < MaxOpenTrades)
    {
        CheckForCRTSetup();
    }
}

//+------------------------------------------------------------------+
//| Check if current time is in allowed trading session              |
//+------------------------------------------------------------------+
bool IsTradingTime()
{
    MqlDateTime dt;
    TimeCurrent(dt);
    int hour = dt.hour;

    // Crypto: 24/7 if enabled
    if(TradeCrypto && (StringFind(_Symbol, "BTC") >= 0 || StringFind(_Symbol, "ETH") >= 0))
        return true;

    return true;  // Default: trade anytime
}

//+------------------------------------------------------------------+
//| Get CRT range from 4H candle                                     |
//+------------------------------------------------------------------+
bool GetCRTRange(double &crtHigh, double &crtLow, double &rangePct)
{
    double h4_high[];
    double h4_low[];
    if(CopyHigh(_Symbol, CRT_TF, 1, 1, h4_high) <= 0) return false;
    if(CopyLow(_Symbol, CRT_TF, 1, 1, h4_low) <= 0) return false;

    crtHigh = h4_high[0];
    crtLow = h4_low[0];
    rangePct = (crtHigh - crtLow) / crtLow * 100.0;
    return true;
}

//+------------------------------------------------------------------+
//| Check for CRT setup                                               |
//+------------------------------------------------------------------+
void CheckForCRTSetup()
{
    double crtHigh, crtLow, crtRangePct;
    if(!GetCRTRange(crtHigh, crtLow, crtRangePct)) return;
    if(crtRangePct < MinCRTRangePct || crtRangePct > MaxCRTRangePct) return;

    // Look at last 48 5min bars (covers 4H session)
    int lookback = 48;
    double m5_high[];
    double m5_low[];
    double m5_close[];
    double m5_open[];
    datetime m5_time[];

    if(CopyHigh(_Symbol, ENTRY_TF, 1, lookback, m5_high) < lookback) return;
    if(CopyLow(_Symbol, ENTRY_TF, 1, lookback, m5_low) < lookback) return;
    if(CopyClose(_Symbol, ENTRY_TF, 1, lookback, m5_close) < lookback) return;
    if(CopyOpen(_Symbol, ENTRY_TF, 1, lookback, m5_open) < lookback) return;

    // Bullish CRT: 5m dipped below CRT-L, then closed back above
    if(TradeLongs)
    {
        for(int i = lookback - 2; i >= 0; i--)
        {
            if(m5_low[i] < crtLow && m5_close[i+1] > m5_high[i])
            {
                OpenCRTTrade(1, m5_close[i+1], crtHigh, crtLow);
                return;
            }
        }
    }

    // Bearish CRT: 5m broke above CRT-H, then closed back below
    if(TradeShorts)
    {
        for(int i = lookback - 2; i >= 0; i--)
        {
            if(m5_high[i] > crtHigh && m5_close[i+1] < m5_low[i])
            {
                OpenCRTTrade(-1, m5_close[i+1], crtHigh, crtLow);
                return;
            }
        }
    }
}

//+------------------------------------------------------------------+
//| Open CRT trade                                                    |
//+------------------------------------------------------------------+
void OpenCRTTrade(int direction, double entryPrice, double crtHigh, double crtLow)
{
    // Get ATR for stop loss
    double atr[];
    if(CopyBuffer(atrHandle, 0, 0, 1, atr) <= 0) return;
    double atrVal = atr[0];

    // Calculate SL = entry - ATR * mult (long) or entry + ATR * mult (short)
    double slDistance = atrVal * ATR_StopMult;
    double sl;
    if(direction > 0) sl = entryPrice - slDistance;
    else sl = entryPrice + slDistance;

    // Calculate lot size
    double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
    double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
    double riskPerUnit = (slDistance / tickSize) * tickValue;

    if(riskPerUnit <= 0) return;

    double lots = RiskUSD / riskPerUnit;
    lots = NormalizeDouble(lots, 2);

    double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
    lots = MathMax(minLot, MathMin(maxLot, lots));

    // Calculate T1-T2
    double risk = MathAbs(entryPrice - sl);
    double t1, t2;
    if(direction > 0)
    {
        t1 = entryPrice + risk * 1.0;
        t2 = entryPrice + risk * T2_R_Mult;
    }
    else
    {
        t1 = entryPrice - risk * 1.0;
        t2 = entryPrice - risk * T2_R_Mult;
    }

    // Place order
    string comment = StringFormat("CRT %s T2=%.2f", direction > 0 ? "LONG" : "SHORT", t2);
    bool result;
    if(direction > 0) result = trade.Buy(lots, _Symbol, entryPrice, sl, t2, comment);
    else result = trade.Sell(lots, _Symbol, entryPrice, sl, t2, comment);

    if(result)
    {
        ulong ticket = trade.ResultOrder();
        TradeTracker tr;
        tr.ticket = ticket;
        tr.entry = entryPrice;
        tr.sl = sl;
        tr.t1 = t1;
        tr.t2 = t2;
        tr.size = lots;
        tr.direction = direction;
        tr.t1Hit = false;
        tr.closed = false;

        int size = ArraySize(trackers);
        ArrayResize(trackers, size + 1);
        trackers[size] = tr;

        totalTrades++;
        Print("CRT ", direction > 0 ? "LONG" : "SHORT", " @ ", DoubleToString(entryPrice, 2),
              " SL=", DoubleToString(sl, 2), " T2=", DoubleToString(t2, 2),
              " lots=", DoubleToString(lots, 2));

        if(EnableAlerts)
        {
            Alert(StringFormat("CRT %s @ %s | T2=%s | SL=%s | %s lots",
                  direction > 0 ? "LONG" : "SHORT",
                  DoubleToString(entryPrice, 2),
                  DoubleToString(t2, 2),
                  DoubleToString(sl, 2),
                  DoubleToString(lots, 2)));
        }
    }
    else
    {
        Print("ERROR: Failed to open trade: ", trade.ResultRetcodeDescription());
    }
}

//+------------------------------------------------------------------+
//| Manage open positions                                              |
//+------------------------------------------------------------------+
void ManageOpenPositions()
{
    for(int i = ArraySize(trackers) - 1; i >= 0; i--)
    {
        if(trackers[i].closed)
        {
            RemoveTracker(i);
            continue;
        }

        if(!PositionSelectByTicket(trackers[i].ticket))
        {
            // Position closed by SL/TP
            UpdateStats(i);
            trackers[i].closed = true;
            continue;
        }

        double currentPrice = PositionGetDouble(POS_PRICE_CURRENT);

        if(trackers[i].direction > 0)
        {
            // Long
            if(!trackers[i].t1Hit && currentPrice >= trackers[i].t1)
            {
                trackers[i].t1Hit = true;
                Print("T1 hit @ ", DoubleToString(currentPrice, 2));
            }
        }
        else
        {
            // Short
            if(!trackers[i].t1Hit && currentPrice <= trackers[i].t1)
            {
                trackers[i].t1Hit = true;
                Print("T1 hit @ ", DoubleToString(currentPrice, 2));
            }
        }
    }
}

//+------------------------------------------------------------------+
//| Update stats when position closes                                 |
//+------------------------------------------------------------------+
void UpdateStats(int idx)
{
    if(PositionSelectByTicket(trackers[idx].ticket))
    {
        double profit = PositionGetDouble(POS_PROFIT);
        double slDistance = MathAbs(trackers[idx].entry - trackers[idx].sl);
        double rMultiple = profit / (slDistance * trackers[idx].size);
        if(rMultiple > 0) wins++;
        else losses++;
        totalR += rMultiple;
        Print("Trade closed R: ", DoubleToString(rMultiple, 2), " Total R: ", DoubleToString(totalR, 2));
    }
}

//+------------------------------------------------------------------+
//| Remove tracker from array                                         |
//+------------------------------------------------------------------+
void RemoveTracker(int idx)
{
    int size = ArraySize(trackers);
    if(size <= 0) return;
    for(int i = idx; i < size - 1; i++)
    {
        trackers[i] = trackers[i + 1];
    }
    ArrayResize(trackers, size - 1);
}

//+------------------------------------------------------------------+
//| Count current open positions                                      |
//+------------------------------------------------------------------+
int CountOpenPositions()
{
    int count = 0;
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(ticket > 0 && PositionGetString(POS_SYMBOL) == _Symbol) count++;
    }
    return count;
}

//+------------------------------------------------------------------+
//| Check daily drawdown                                              |
//+------------------------------------------------------------------+
bool CheckDailyDrawdown()
{
    double balance = AccountInfoDouble(ACCOUNT_BALANCE);
    double equity = AccountInfoDouble(ACCOUNT_EQUITY);
    if(balance <= 0) return false;
    double dd = (balance - equity) / balance * 100.0;
    if(dd > MaxDrawdownPct)
    {
        if(EnableAlerts) Alert("Daily DD ", DoubleToString(dd, 1), "% - PAUSED");
        return true;
    }
    return false;
}
//+------------------------------------------------------------------+
