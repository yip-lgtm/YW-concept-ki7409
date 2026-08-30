//+------------------------------------------------------------------+
//|                                          CRT_BTC_EA.mq5          |
//|                                          Apex Bootcamp v1.02     |
//|                                          Simplified, no classes  |
//+------------------------------------------------------------------+
#property copyright "Apex Bootcamp"
#property link      "https://github.com/yip-lgtm/apex-bootcamp"
#property version   "1.02"
#property strict

//+------------------------------------------------------------------+
//| Input Parameters                                                  |
//+------------------------------------------------------------------+
input double RiskUSD         = 100.0;    // Risk per trade (USD)
input double MaxDrawdownPct  = 5.0;      // Max daily drawdown %
input int    MaxOpenTrades    = 1;        // Max concurrent trades

input double MinCRTRangePct   = 0.5;      // Min CRT range (%)
input double MaxCRTRangePct   = 5.0;      // Max CRT range (%)
input int    ATR_Period       = 14;       // ATR period
input double ATR_StopMult     = 1.6;      // SL distance = ATR * this

input bool   UseT2Close      = true;     // Close at T2 (1.618R)
input double T2_R_Mult       = 1.618;    // T2 multiplier

input bool   TradeLongs      = true;     // Allow long trades
input bool   TradeShorts     = true;     // Allow short trades
input bool   TradeCrypto     = true;     // 24/7 BTC mode

input bool   EnableAlerts    = true;     // Pop-up alerts

//+------------------------------------------------------------------+
//| Global Variables                                                  |
//+------------------------------------------------------------------+
datetime g_lastBarTime = 0;
int      g_atrHandle;
int      g_totalTrades = 0;
int      g_wins = 0;
int      g_losses = 0;
double   g_totalR = 0;

// Per-position tracking (parallel arrays - no struct)
ulong   g_tickets[];
double  g_entries[];
double  g_sls[];
double  g_t1s[];
double  g_t2s[];
double  g_sizes[];
int     g_directions[];
bool    g_t1Hit[];
bool    g_closed[];

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
   
   g_atrHandle = iATR(_Symbol, PERIOD_M5, ATR_Period);
   if(g_atrHandle == INVALID_HANDLE)
   {
      Print("ERROR: Failed to create ATR handle");
      return(INIT_FAILED);
   }
   
   Print("CRT BTC EA v1.02 started on ", _Symbol);
   Print("Risk/trade: $", DoubleToString(RiskUSD, 2));
   Print("T2 close: ", UseT2Close ? "YES (1.618R)" : "NO");
   
   if(EnableAlerts) Alert("CRT BTC EA v1.02 started on ", _Symbol);
   
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                  |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(g_atrHandle != INVALID_HANDLE) IndicatorRelease(g_atrHandle);
   Print("CRT BTC EA stopped. Total: ", g_totalTrades, " trades, ", 
         g_wins, "W-", g_losses, "L, Total R: ", DoubleToString(g_totalR, 2));
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick()
{
   // New bar detection
   datetime currentBarTime = iTime(_Symbol, PERIOD_M5, 1);
   bool isNewBar = (currentBarTime != g_lastBarTime);
   if(isNewBar) g_lastBarTime = currentBarTime;
   
   // Drawdown check
   if(CheckDailyDrawdown()) return;
   
   // Manage open positions
   ManageOpenPositions();
   
   // Look for new setups
   if(isNewBar && IsTradingTime())
   {
      if(CountOpenPositions() < MaxOpenTrades) CheckForCRTSetup();
   }
}

//+------------------------------------------------------------------+
//| Check trading time                                                |
//+------------------------------------------------------------------+
bool IsTradingTime()
{
   if(TradeCrypto) return true;  // BTC 24/7
   MqlDateTime dt;
   TimeCurrent(dt);
   int hour = dt.hour;
   return (hour >= 8 && hour < 22);  // London + NY
}

//+------------------------------------------------------------------+
//| Get CRT range from 4H candle                                     |
//+------------------------------------------------------------------+
bool GetCRTRange(double &crtHigh, double &crtLow, double &rangePct)
{
   double h4high[];
   double h4low[];
   ArraySetAsSeries(h4high, true);
   ArraySetAsSeries(h4low, true);
   if(CopyHigh(_Symbol, PERIOD_H4, 1, 1, h4high) <= 0) return false;
   if(CopyLow(_Symbol, PERIOD_H4, 1, 1, h4low) <= 0) return false;
   crtHigh = h4high[0];
   crtLow = h4low[0];
   if(crtLow <= 0) return false;
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
   double m5high[], m5low[], m5close[];
   ArraySetAsSeries(m5high, true);
   ArraySetAsSeries(m5low, true);
   ArraySetAsSeries(m5close, true);
   if(CopyHigh(_Symbol, PERIOD_M5, 1, lookback, m5high) < lookback) return;
   if(CopyLow(_Symbol, PERIOD_M5, 1, lookback, m5low) < lookback) return;
   if(CopyClose(_Symbol, PERIOD_M5, 1, lookback, m5close) < lookback) return;
   
   // Bullish CRT: 5m dipped below CRT-L, next bar closed back above raid candle high
   if(TradeLongs)
   {
      for(int i = lookback - 2; i >= 0; i--)
      {
         if(m5low[i] < crtLow && m5close[i + 1] > m5high[i])
         {
            OpenCRTTrade(1, m5close[i + 1], crtHigh, crtLow);
            return;
         }
      }
   }
   
   // Bearish CRT: 5m broke above CRT-H, next bar closed back below raid candle low
   if(TradeShorts)
   {
      for(int i = lookback - 2; i >= 0; i--)
      {
         if(m5high[i] > crtHigh && m5close[i + 1] < m5low[i])
         {
            OpenCRTTrade(-1, m5close[i + 1], crtHigh, crtLow);
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
   // Get ATR
   double atr[];
   ArraySetAsSeries(atr, true);
   if(CopyBuffer(g_atrHandle, 0, 0, 1, atr) <= 0) return;
   double atrVal = atr[0];
   if(atrVal <= 0) return;
   
   // SL = entry ± ATR * mult
   double slDistance = atrVal * ATR_StopMult;
   double sl;
   if(direction > 0) sl = entryPrice - slDistance;
   else sl = entryPrice + slDistance;
   
   // Position sizing
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickSize <= 0) return;
   double riskPerUnit = (slDistance / tickSize) * tickValue;
   if(riskPerUnit <= 0) return;
   
   double lots = RiskUSD / riskPerUnit;
   lots = NormalizeDouble(lots, 2);
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(lotStep > 0) lots = MathFloor(lots / lotStep) * lotStep;
   lots = MathMax(minLot, MathMin(maxLot, lots));
   if(lots < minLot) return;
   
   // T1/T2
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
   
   // Send order
   int slippage = 30;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double price = (direction > 0) ? ask : bid;
   int cmd = (direction > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   string comment = StringFormat("CRT%s T2=%.2f", direction > 0 ? "L" : "S", t2);
   
   ulong ticket = OrderSend(_Symbol, cmd, lots, price, slippage, sl, t2, comment, 0, 0, clrNONE);
   if(ticket > 0)
   {
      int idx = ArraySize(g_tickets);
      ArrayResize(g_tickets, idx + 1);
      ArrayResize(g_entries, idx + 1);
      ArrayResize(g_sls, idx + 1);
      ArrayResize(g_t1s, idx + 1);
      ArrayResize(g_t2s, idx + 1);
      ArrayResize(g_sizes, idx + 1);
      ArrayResize(g_directions, idx + 1);
      ArrayResize(g_t1Hit, idx + 1);
      ArrayResize(g_closed, idx + 1);
      
      g_tickets[idx] = ticket;
      g_entries[idx] = entryPrice;
      g_sls[idx] = sl;
      g_t1s[idx] = t1;
      g_t2s[idx] = t2;
      g_sizes[idx] = lots;
      g_directions[idx] = direction;
      g_t1Hit[idx] = false;
      g_closed[idx] = false;
      
      g_totalTrades++;
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
      int err = GetLastError();
      Print("OrderSend FAILED err=", err);
   }
}

//+------------------------------------------------------------------+
//| Manage open positions                                              |
//+------------------------------------------------------------------+
void ManageOpenPositions()
{
   for(int i = ArraySize(g_tickets) - 1; i >= 0; i--)
   {
      if(g_closed[i])
      {
         RemoveTracker(i);
         continue;
      }
      
      // Check if still open
      if(!PositionSelectByTicket(g_tickets[i]))
      {
         // Position closed
         UpdateStats(i);
         g_closed[i] = true;
         continue;
      }
      
      double currentPrice = PositionGetDouble(POS_PRICE_CURRENT);
      
      if(g_directions[i] > 0)
      {
         if(!g_t1Hit[i] && currentPrice >= g_t1s[i])
         {
            g_t1Hit[i] = true;
            Print("T1 hit @ ", DoubleToString(currentPrice, 2));
         }
      }
      else
      {
         if(!g_t1Hit[i] && currentPrice <= g_t1s[i])
         {
            g_t1Hit[i] = true;
            Print("T1 hit @ ", DoubleToString(currentPrice, 2));
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Update stats                                                      |
//+------------------------------------------------------------------+
void UpdateStats(int idx)
{
   if(PositionSelectByTicket(g_tickets[idx]))
   {
      double profit = PositionGetDouble(POS_PROFIT) + PositionGetDouble(POS_SWAP);
      double slDistance = MathAbs(g_entries[idx] - g_sls[idx]);
      double rMult = 0;
      if(slDistance > 0 && g_sizes[idx] > 0)
         rMult = profit / (slDistance * g_sizes[idx]);
      if(rMult > 0) g_wins++;
      else g_losses++;
      g_totalR += rMult;
      Print("Trade closed R=", DoubleToString(rMult, 2), " Total R=", DoubleToString(g_totalR, 2));
   }
}

//+------------------------------------------------------------------+
//| Remove tracker                                                    |
//+------------------------------------------------------------------+
void RemoveTracker(int idx)
{
   int size = ArraySize(g_tickets);
   if(size <= 0) return;
   for(int i = idx; i < size - 1; i++)
   {
      g_tickets[i] = g_tickets[i + 1];
      g_entries[i] = g_entries[i + 1];
      g_sls[i] = g_sls[i + 1];
      g_t1s[i] = g_t1s[i + 1];
      g_t2s[i] = g_t2s[i + 1];
      g_sizes[i] = g_sizes[i + 1];
      g_directions[i] = g_directions[i + 1];
      g_t1Hit[i] = g_t1Hit[i + 1];
      g_closed[i] = g_closed[i + 1];
   }
   ArrayResize(g_tickets, size - 1);
   ArrayResize(g_entries, size - 1);
   ArrayResize(g_sls, size - 1);
   ArrayResize(g_t1s, size - 1);
   ArrayResize(g_t2s, size - 1);
   ArrayResize(g_sizes, size - 1);
   ArrayResize(g_directions, size - 1);
   ArrayResize(g_t1Hit, size - 1);
   ArrayResize(g_closed, size - 1);
}

//+------------------------------------------------------------------+
//| Count open positions                                              |
//+------------------------------------------------------------------+
int CountOpenPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0 && PositionSelectByTicket(ticket))
      {
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
