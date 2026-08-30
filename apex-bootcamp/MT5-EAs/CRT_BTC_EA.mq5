//+------------------------------------------------------------------+
//|                                          CRT_BTC_EA.mq5          |
//|                                          Apex Bootcamp EA       |
//|                                          2026-08-30              |
//+------------------------------------------------------------------+
#property copyright "Apex Bootcamp"
#property version   "1.00"
#property strict

//+------------------------------------------------------------------+
//| Input Parameters                                                  |
//+------------------------------------------------------------------+
input group "=== Risk Management ==="
input double RiskUSD        = 100.0;    // Risk per trade (USD)
input double AccountRiskPct  = 1.0;     // % account risk per trade
input double MaxDrawdownPct  = 5.0;     // Max daily drawdown %
input int    MaxOpenTrades   = 1;       // Max concurrent trades

input group "=== CRT Strategy ==="
input ENUM_TIMEFRAMES CRT_TF  = PERIOD_H4;   // CRT range timeframe
input ENUM_TIMEFRAMES ENTRY_TF = PERIOD_M5;  // Entry timeframe
input double MinCRTRangePct = 0.5;           // Min CRT range (%)
input double MaxCRTRangePct = 5.0;           // Max CRT range (%)
input int    ATR_Period      = 14;            // ATR period
input double ATR_StopMult    = 1.6;           // SL = ATR * this
input int    MSS_BarsAhead   = 5;             // Bars ahead for MSS confirm

input group "=== T2 Close Mode (1.618R) ==="
input bool   UseT2Close      = true;          // Use T2 close instead of T1
input double T2_R_Mult       = 1.618;          // T2 multiplier (Golden Ratio)
input bool   TrackRunners    = true;          // Track T3-T5 runners

input group "=== Trade Filters ==="
input int    MinConfluence   = 1;              // Min confluence (1-3)
input double MinRR           = 2.0;            // Min risk:reward
input bool   TradeLongs      = true;           // Allow long trades
input bool   TradeShorts     = true;           // Allow short trades

input group "=== Session Filters ==="
input bool   TradeAsian      = false;          // 00:00-08:00 UTC
input bool   TradeLondon     = true;           // 08:00-13:00 UTC
input bool   TradeNY         = true;           // 13:00-22:00 UTC
input bool   TradeCrypto     = true;           // 24/7 (BTC always)

input group "=== Notifications ==="
input bool   EnableAlerts    = true;           // Pop-up alerts
input bool   EnablePush      = false;          // Push notifications
input string TelegramToken   = "";             // Telegram bot token
input string TelegramChat    = "";             // Telegram chat ID

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
struct TradeTracker {
    ulong  ticket;
    double entry;
    double sl;
    double t1, t2, t3, t4, t5;
    double riskPerUnit;  // $ risk per 1 unit move
    int    direction;    // +1 long, -1 short
    double size;         // position size in lots
    bool   t1Hit;
    bool   t2Hit;
};

TradeTracker trackers[];

//+------------------------------------------------------------------+
//| Expert initialization function                                    |
//+------------------------------------------------------------------+
int OnInit()
{
    // Validate inputs
    if(RiskUSD <= 0) {
        Print("ERROR: RiskUSD must be > 0");
        return(INIT_PARAMETERS_INCORRECT);
    }
    
    // Create ATR indicator handle
    atrHandle = iATR(_Symbol, ENTRY_TF, ATR_Period);
    if(atrHandle == INVALID_HANDLE) {
        Print("ERROR: Failed to create ATR handle");
        return(INIT_FAILED);
    }
    
    Print("=== CRT BTC EA Initialized ===");
    Print("Symbol: ", _Symbol);
    Print("Risk per trade: $", DoubleToString(RiskUSD, 2));
    Print("Use T2 close: ", UseT2Close ? "YES (1.618R)" : "NO (T1 1R)");
    
    // Send startup alert
    if(EnableAlerts) {
        Alert("CRT BTC EA started on ", _Symbol);
    }
    
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                  |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    if(atrHandle != INVALID_HANDLE) {
        IndicatorRelease(atrHandle);
    }
    Print("=== CRT BTC EA stopped ===");
    Print("Stats: ", totalTrades, " trades, ", wins, "W-", losses, "L, Total R: ", DoubleToString(totalR, 2));
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick()
{
    // Run on each new bar only (avoid spam)
    datetime currentBarTime = iTime(_Symbol, ENTRY_TF, 0);
    bool isNewBar = (currentBarTime != lastBarTime);
    if(isNewBar) lastBarTime = currentBarTime;
    
    // Check daily drawdown
    if(CheckDailyDrawdown()) return;
    
    // Manage existing positions (every tick)
    ManageOpenPositions();
    
    // Look for new signals (on new bar only)
    if(isNewBar && !IsTradingTime()) return;
    if(isNewBar && CountOpenPositions() < MaxOpenTrades) {
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
    if(TradeCrypto && _Symbol == "BTCUSD" || StringFind(_Symbol, "BTC") >= 0) {
        return true;
    }
    
    // Asian session: 00:00-08:00 UTC
    if(hour >= 0 && hour < 8) return TradeAsian;
    
    // London: 08:00-13:00 UTC
    if(hour >= 8 && hour < 13) return TradeLondon;
    
    // New York: 13:00-22:00 UTC
    if(hour >= 13 && hour < 22) return TradeNY;
    
    // Off hours: 22:00-00:00 UTC
    return false;
}

//+------------------------------------------------------------------+
//| Get CRT range from 4H candle                                     |
//+------------------------------------------------------------------+
bool GetCRTRange(double &crtHigh, double &crtLow, double &rangePct)
{
    double h4_high[], h4_low[];
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
    
    // Filter by range size
    if(crtRangePct < MinCRTRangePct || crtRangePct > MaxCRTRangePct) return;
    
    // Look at last 48 5min bars (covers 4H session)
    double m5_high[], m5_low[], m5_close[];
    if(CopyHigh(_Symbol, ENTRY_TF, 1, 48, m5_high) < 48) return;
    if(CopyLow(_Symbol, ENTRY_TF, 1, 48, m5_low) < 48) return;
    if(CopyClose(_Symbol, ENTRY_TF, 1, 48, m5_close) < 48) return;
    
    // Copy times to check raid sequence
    datetime m5_time[];
    if(CopyTime(_Symbol, ENTRY_TF, 1, 48, m5_time) < 48) return;
    
    // Copy open prices
    double m5_open[];
    if(CopyOpen(_Symbol, ENTRY_TF, 1, 48, m5_open) < 48) return;
    
    // Search for bullish CRT: 5m dipped below CRT-L, then closed back above
    for(int i = 0; i < ArraySize(m5_low) - 1; i++) {
        if(m5_low[i] < crtLow && m5_close[i+1] > m5_high[i] && TradeLongs) {
            // BULLISH CRT confirmed
            OpenCRTTrade(1, m5_close[i+1], crtHigh, crtLow);
            return;
        }
    }
    
    // Search for bearish CRT: 5m broke above CRT-H, then closed back below
    for(int i = 0; i < ArraySize(m5_high) - 1; i++) {
        if(m5_high[i] > crtHigh && m5_close[i+1] < m5_low[i] && TradeShorts) {
            // BEARISH CRT confirmed
            OpenCRTTrade(-1, m5_close[i+1], crtHigh, crtLow);
            return;
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
    
    // Calculate risk per unit (1 lot)
    double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
    double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
    double riskPerUnit = (slDistance / tickSize) * tickValue;
    
    // Calculate lot size
    double lots = RiskUSD / riskPerUnit;
    lots = NormalizeDouble(lots, 2);
    
    // Min lot check
    double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
    lots = MathMax(minLot, MathMin(maxLot, lots));
    
    // Calculate T1-T5
    double risk = MathAbs(entryPrice - sl);
    double t1, t2, t3, t4, t5;
    if(direction > 0) {
        t1 = entryPrice + risk * 1.0;
        t2 = entryPrice + risk * T2_R_Mult;  // 1.618R
        t3 = entryPrice + risk * 2.618;
        t4 = entryPrice + risk * 3.618;
        t5 = entryPrice + risk * 5.0;
    } else {
        t1 = entryPrice - risk * 1.0;
        t2 = entryPrice - risk * T2_R_Mult;
        t3 = entryPrice - risk * 2.618;
        t4 = entryPrice - risk * 3.618;
        t5 = entryPrice - risk * 5.0;
    }
    
    // Place order
    string comment = StringFormat("CRT %s T2=%.2f", direction > 0 ? "LONG" : "SHORT", t2);
    bool result;
    if(direction > 0) {
        result = trade.Buy(lots, _Symbol, entryPrice, sl, t2, comment);
    } else {
        result = trade.Sell(lots, _Symbol, entryPrice, sl, t2, comment);
    }
    
    if(result) {
        ulong ticket = trade.ResultOrder();
        TradeTracker tr;
        tr.ticket = ticket;
        tr.entry = entryPrice;
        tr.sl = sl;
        tr.t1 = t1; tr.t2 = t2; tr.t3 = t3; tr.t4 = t4; tr.t5 = t5;
        tr.riskPerUnit = riskPerUnit;
        tr.direction = direction;
        tr.size = lots;
        tr.t1Hit = false;
        tr.t2Hit = false;
        int size = ArraySize(trackers);
        ArrayResize(trackers, size + 1);
        trackers[size] = tr;
        
        totalTrades++;
        Print("✓ CRT ", direction > 0 ? "LONG" : "SHORT", " opened @ ", DoubleToString(entryPrice, 2),
              " SL=", DoubleToString(sl, 2), " T2=", DoubleToString(t2, 2),
              " lots=", DoubleToString(lots, 2));
        
        if(EnableAlerts) {
            Alert(StringFormat("CRT %s @ %s | T2=%s | SL=%s | %s lots",
                  direction > 0 ? "LONG" : "SHORT",
                  DoubleToString(entryPrice, 2),
                  DoubleToString(t2, 2),
                  DoubleToString(sl, 2),
                  DoubleToString(lots, 2)));
        }
    } else {
        Print("ERROR: Failed to open CRT trade: ", trade.ResultRetcodeDescription());
    }
}

//+------------------------------------------------------------------+
//| Manage open positions (T1-T5 partial close tracking)            |
//+------------------------------------------------------------------+
void ManageOpenPositions()
{
    for(int i = ArraySize(trackers) - 1; i >= 0; i--) {
        if(!PositionSelectByTicket(trackers[i].ticket)) {
            // Position closed
            UpdateStats(i);
            RemoveTracker(i);
            continue;
        }
        
        double currentPrice = PositionGetDouble(POS_PRICE_CURRENT);
        double entry = trackers[i].entry;
        int dir = trackers[i].direction;
        
        // Check if SL or T1/T2 hit
        if(dir > 0) {
            // Long: check high targets
            if(!trackers[i].t1Hit && currentPrice >= trackers[i].t1) {
                trackers[i].t1Hit = true;
                Print("T1 hit @ ", DoubleToString(currentPrice, 2));
            }
            if(trackers[i].t1Hit && currentPrice < trackers[i].entry) {
                // Price returned below entry after T1 - close at breakeven
                trade.PositionClose(trackers[i].ticket);
                Print("Closed at breakeven after T1");
            }
        } else {
            // Short: check low targets
            if(!trackers[i].t1Hit && currentPrice <= trackers[i].t1) {
                trackers[i].t1Hit = true;
                Print("T1 hit @ ", DoubleToString(currentPrice, 2));
            }
            if(trackers[i].t1Hit && currentPrice > trackers[i].entry) {
                trade.PositionClose(trackers[i].ticket);
                Print("Closed at breakeven after T1");
            }
        }
    }
}

//+------------------------------------------------------------------+
//| Update stats when position closes                                 |
//+------------------------------------------------------------------+
void UpdateStats(int idx)
{
    if(PositionSelectByTicket(trackers[idx].ticket)) {
        double profit = PositionGetDouble(POS_PROFIT);
        double slDistance = MathAbs(trackers[idx].entry - trackers[idx].sl);
        double rMultiple = profit / (slDistance * trackers[idx].size);
        totalR += rMultiple;
        if(rMultiple > 0) wins++;
        else losses++;
        Print("Trade closed R: ", DoubleToString(rMultiple, 2), " Total R: ", DoubleToString(totalR, 2));
    }
}

//+------------------------------------------------------------------+
//| Remove tracker from array                                         |
//+------------------------------------------------------------------+
void RemoveTracker(int idx)
{
    int size = ArraySize(trackers);
    for(int i = idx; i < size - 1; i++) {
        trackers[i] = trackers[i+1];
    }
    ArrayResize(trackers, size - 1);
}

//+------------------------------------------------------------------+
//| Count current open positions                                      |
//+------------------------------------------------------------------+
int CountOpenPositions()
{
    int count = 0;
    for(int i = PositionsTotal() - 1; i >= 0; i--) {
        if(PositionGetTicket(i) > 0) {
            if(PositionGetString(POS_SYMBOL) == _Symbol) count++;
        }
    }
    return count;
}

//+------------------------------------------------------------------+
//| Check daily drawdown                                              |
//+------------------------------------------------------------------+
bool CheckDailyDrawdown()
{
    double startBalance = 0;
    if(!HistorySelect(TimeCurrent() - PeriodSeconds(PERIOD_D1), TimeCurrent())) return false;
    
    double dailyPnL = 0;
    for(int i = HistoryDealsTotal() - 1; i >= 0; i--) {
        ulong ticket = HistoryDealGetTicket(i);
        if(ticket > 0) {
            dailyPnL += HistoryDealGetDouble(ticket, DEAL_PROFIT);
        }
    }
    
    double balance = AccountInfoDouble(ACCOUNT_BALANCE);
    double equity = AccountInfoDouble(ACCOUNT_EQUITY);
    double dd = (balance - equity) / balance * 100.0;
    
    if(dd > MaxDrawdownPct) {
        if(EnableAlerts) Alert("Daily drawdown ", DoubleToString(dd, 1), "% - PAUSED");
        return true;
    }
    return false;
}
//+------------------------------------------------------------------+
