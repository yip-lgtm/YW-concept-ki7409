//+------------------------------------------------------------------+
//|                                                CRT_BTC_EA.mq5    |
//|  Candle Range Theory — 4H range + 5m sweep/MSS                   |
//|  v1.10  修正：不重覆歷史掃、ticket、T1保本、日DD、filling          |
//+------------------------------------------------------------------+
#property copyright "YW Concept / Apex Bootcamp"
#property version   "1.10"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\DealInfo.mqh>

input group "=== Risk ==="
input double   RiskUSD         = 100.0;
input double   MaxDrawdownPct  = 5.0;     // vs day-start equity
input int      MaxOpenTrades   = 1;
input int      InpMagic        = 14101;

input group "=== CRT Range ==="
input double   MinCRTRangePct  = 0.5;
input double   MaxCRTRangePct  = 5.0;
input int      ATR_Period      = 14;
input double   ATR_StopMult    = 1.6;
input bool     UseT2Close      = true;
input double   T2_R_Mult       = 1.618;
input bool     UseT1Breakeven  = true;    // T1=1R 推保本

input group "=== Direction / Session ==="
input bool     TradeLongs      = true;
input bool     TradeShorts     = true;
input bool     TradeCrypto     = true;    // true=24/7
input int      SessionStartH   = 8;
input int      SessionEndH     = 22;
input bool     EnableAlerts    = false;
input int      InpSlippage     = 30;

CTrade         trade;
CPositionInfo  pos;

int            g_atrHandle;
datetime       g_lastBar = 0;
datetime       g_lastH4  = 0;
datetime       g_armedH4 = 0;     // which H4 range already used
int            g_armedDir = 0;
double         g_dayStartEq = 0;
int            g_dayKey = 0;

int            g_total = 0, g_wins = 0, g_losses = 0;
double         g_totalR = 0;

int OnInit()
{
   if(RiskUSD <= 0) return INIT_PARAMETERS_INCORRECT;

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippage);
   trade.SetTypeFillingBySymbol(_Symbol);

   g_atrHandle = iATR(_Symbol, PERIOD_M5, ATR_Period);
   if(g_atrHandle == INVALID_HANDLE) return INIT_FAILED;

   g_dayStartEq = AccountInfoDouble(ACCOUNT_EQUITY);
   g_dayKey = DayKey();
   Print("CRT_BTC_EA v1.10 | ", _Symbol, " Risk$", RiskUSD);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(g_atrHandle != INVALID_HANDLE) IndicatorRelease(g_atrHandle);
   Print("CRT stop | trades=", g_total, " W/L=", g_wins, "/", g_losses,
         " R=", DoubleToString(g_totalR, 2));
}

int DayKey()
{
   MqlDateTime d;
   TimeToStruct(TimeCurrent(), d);
   return d.year * 1000 + d.day_of_year;
}

void ResetDay()
{
   int k = DayKey();
   if(k != g_dayKey)
   {
      g_dayKey = k;
      g_dayStartEq = AccountInfoDouble(ACCOUNT_EQUITY);
   }
}

bool InSession()
{
   if(TradeCrypto) return true;
   MqlDateTime d;
   TimeToStruct(TimeCurrent(), d);
   if(SessionStartH < SessionEndH)
      return (d.hour >= SessionStartH && d.hour < SessionEndH);
   return (d.hour >= SessionStartH || d.hour < SessionEndH);
}

bool CheckDailyDrawdown()
{
   ResetDay();
   if(g_dayStartEq <= 0) return false;
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double dd = (g_dayStartEq - eq) / g_dayStartEq * 100.0;
   return (dd > MaxDrawdownPct);
}

int CountOurPos()
{
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
      if(pos.SelectByIndex(i) && pos.Symbol() == _Symbol && pos.Magic() == InpMagic)
         n++;
   return n;
}

bool GetCRTRange(double &hi, double &lo, double &pct, datetime &t4)
{
   t4 = iTime(_Symbol, PERIOD_H4, 1);
   if(t4 <= 0) return false;
   hi = iHigh(_Symbol, PERIOD_H4, 1);
   lo = iLow(_Symbol, PERIOD_H4, 1);
   if(lo <= 0 || hi <= lo) return false;
   pct = (hi - lo) / lo * 100.0;
   return true;
}

double CalcLot(double slDist)
{
   if(slDist <= 0) return 0;
   double tickVal  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickSize <= 0 || tickVal <= 0) return 0;
   double lot = RiskUSD / ((slDist / tickSize) * tickVal);
   double mn = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double mx = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double st = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(st <= 0) st = mn;
   lot = MathFloor(lot / st) * st;
   if(lot < mn) lot = 0;
   if(lot > mx) lot = mx;
   return lot;
}

void OpenCRT(const int dir, const double slDistHint)
{
   double atr[];
   ArraySetAsSeries(atr, true);
   if(CopyBuffer(g_atrHandle, 0, 1, 1, atr) < 1) return;
   if(atr[0] <= 0) return;

   double slDist = atr[0] * ATR_StopMult;
   if(slDistHint > slDist) slDist = slDistHint; // at least beyond raid wick a bit

   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double lot = CalcLot(slDist);
   if(lot <= 0) { Print("lot=0 slDist=", slDist); return; }

   double sl, tp, entry;
   if(dir > 0)
   {
      entry = ask;
      sl = NormalizeDouble(entry - slDist, digits);
      tp = UseT2Close ? NormalizeDouble(entry + slDist * T2_R_Mult, digits)
                      : NormalizeDouble(entry + slDist, digits);
      if(!trade.Buy(lot, _Symbol, entry, sl, tp, "CRT-L"))
      {
         Print("Buy fail ", trade.ResultRetcodeDescription());
         return;
      }
   }
   else
   {
      entry = bid;
      sl = NormalizeDouble(entry + slDist, digits);
      tp = UseT2Close ? NormalizeDouble(entry - slDist * T2_R_Mult, digits)
                      : NormalizeDouble(entry - slDist, digits);
      if(!trade.Sell(lot, _Symbol, entry, sl, tp, "CRT-S"))
      {
         Print("Sell fail ", trade.ResultRetcodeDescription());
         return;
      }
   }
   g_total++;
   Print("CRT ", (dir > 0 ? "LONG" : "SHORT"),
         " @", entry, " SL=", sl, " TP=", tp, " lot=", lot);
   if(EnableAlerts)
      Alert("CRT ", dir > 0 ? "LONG" : "SHORT", " @", DoubleToString(entry, 2));
}

void CheckSetup()
{
   double hi, lo, pct;
   datetime t4;
   if(!GetCRTRange(hi, lo, pct, t4)) return;
   if(pct < MinCRTRangePct || pct > MaxCRTRangePct) return;

   // new H4 candle → reset arm
   if(t4 != g_lastH4)
   {
      g_lastH4 = t4;
      g_armedH4 = 0;
      g_armedDir = 0;
   }
   if(g_armedH4 == t4) return; // already traded this 4H range

   // only the last closed 5m bar — no 48-bar historical re-fire
   double h1 = iHigh(_Symbol, PERIOD_M5, 1);
   double l1 = iLow(_Symbol, PERIOD_M5, 1);
   double c1 = iClose(_Symbol, PERIOD_M5, 1);
   double h2 = iHigh(_Symbol, PERIOD_M5, 2);
   double l2 = iLow(_Symbol, PERIOD_M5, 2);

   // Bull: bar2 swept CRT low, bar1 closed back above bar2 high (MSS)
   if(TradeLongs && l2 < lo && c1 > h2 && c1 > lo)
   {
      g_armedH4 = t4;
      g_armedDir = 1;
      OpenCRT(1, (hi - lo) * 0.15);
      return;
   }
   // Bear: bar2 swept CRT high, bar1 closed back below bar2 low
   if(TradeShorts && h2 > hi && c1 < l2 && c1 < hi)
   {
      g_armedH4 = t4;
      g_armedDir = -1;
      OpenCRT(-1, (hi - lo) * 0.15);
      return;
   }
}

void ManageBE()
{
   if(!UseT1Breakeven) return;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!pos.SelectByIndex(i)) continue;
      if(pos.Symbol() != _Symbol || pos.Magic() != InpMagic) continue;

      double open = pos.PriceOpen();
      double sl   = pos.StopLoss();
      double tp   = pos.TakeProfit();
      int digits  = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
      double risk = MathAbs(open - sl);
      if(risk <= 0) continue;

      if(pos.PositionType() == POSITION_TYPE_BUY)
      {
         double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         if(bid >= open + risk && sl < open)
            trade.PositionModify(pos.Ticket(), NormalizeDouble(open, digits), tp);
      }
      else
      {
         double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         if(ask <= open - risk && (sl > open || sl == 0))
            trade.PositionModify(pos.Ticket(), NormalizeDouble(open, digits), tp);
      }
   }
}

void HarvestClosedStats()
{
   // last deals for our magic on this symbol
   datetime from = TimeCurrent() - 86400;
   if(!HistorySelect(from, TimeCurrent())) return;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      if(HistoryDealGetString(d, DEAL_SYMBOL) != _Symbol) continue;
      if((int)HistoryDealGetInteger(d, DEAL_MAGIC) != InpMagic) continue;
      if((int)HistoryDealGetInteger(d, DEAL_ENTRY) != DEAL_ENTRY_OUT) continue;
      // one-shot: store last processed deal time via comment skip if needed
   }
}

void OnTick()
{
   ManageBE();
   if(CheckDailyDrawdown()) return;

   datetime t = iTime(_Symbol, PERIOD_M5, 0);
   if(t == g_lastBar) return;
   g_lastBar = t;

   if(!InSession()) return;
   if(CountOurPos() >= MaxOpenTrades) return;
   CheckSetup();
}
