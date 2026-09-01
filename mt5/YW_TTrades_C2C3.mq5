//+------------------------------------------------------------------+
//|                                          YW_TTrades_C2C3.mq5     |
//|  TTrades swing: C2 closure → enter C3 open                      |
//|                 C3 closure → enter C4 open                      |
//|  SL = C2 swing. Optional EMA50 + session + $247K risk.          |
//|  CISD on same TF: close through C1 extreme (simplified).        |
//+------------------------------------------------------------------+
#property copyright "YW Concept"
#property version   "1.00"
#property description "TTrades C2/C3 entry. Hang on H1 or M15."

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

input group "=== Swing ==="
input bool     InpAllowC2Entry   = true;   // C2 close inside C1 → buy/sell C3 open
input bool     InpAllowC3Entry   = true;   // C2 failed → wait strong C3 → C4 open
input bool     InpAllowLong      = true;
input bool     InpAllowShort     = true;
input double   InpC3BodyMin      = 0.50;   // C3 |body|/range minimum (conditional)
input bool     InpC3MustCloseBeyondC2 = true; // C3 close beyond C2 extreme

input group "=== Filter ==="
input bool     InpUseEMA50       = true;
input int      InpEMA50Period    = 50;
input bool     InpEMASoft        = false;  // true = mid EMA still trade
input bool     InpOnlyOnePos     = true;

input group "=== Session ==="
input bool     InpUseSession     = true;
input int      InpSessionStartH  = 8;
input int      InpSessionEndH    = 21;
input bool     InpSkipMonday     = true;

input group "=== Risk $247K ==="
input double   InpRiskPercent    = 0.25;
input double   InpFixedRiskUSD   = 0;      // >0 overrides %
input double   InpRR             = 1.5;
input double   InpSLBufferATR    = 0.15;   // extra beyond swing
input double   InpMinSL_Price    = 0;      // 0 = off; XAU try 3.0
input double   InpDailyLossPct   = 2.0;
input double   InpDailyProfitPct = 2.0;
input bool     InpUseDailyProfit = true;
input double   InpMaxDDPct       = 8.0;
input int      InpMaxTradesDay   = 3;
input bool     InpBreakeven      = true;
input double   InpBE_R           = 1.0;

input group "=== Misc ==="
input int      InpMagic          = 17301;
input string   InpComment        = "YW-TT-C2C3";
input int      InpSlippage       = 30;

CTrade         trade;
CPositionInfo  pos;

int            hEMA = INVALID_HANDLE;
int            hATR = INVALID_HANDLE;
datetime       lastBar = 0;
double         dayStartEquity = 0, initialEquity = 0;
int            dayStamp = 0, tradesToday = 0;

int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippage);
   trade.SetTypeFillingBySymbol(_Symbol);

   hEMA = iMA(_Symbol, PERIOD_CURRENT, InpEMA50Period, 0, MODE_EMA, PRICE_CLOSE);
   hATR = iATR(_Symbol, PERIOD_CURRENT, 14);
   if(hEMA==INVALID_HANDLE || hATR==INVALID_HANDLE)
      return INIT_FAILED;

   initialEquity  = AccountInfoDouble(ACCOUNT_EQUITY);
   dayStartEquity = initialEquity;
   dayStamp       = DayKey();

   Print("YW TTrades C2/C3 v1.00 | ", _Symbol, " ", EnumToString(Period()),
         " C2=", InpAllowC2Entry, " C3=", InpAllowC3Entry, " RR=", InpRR);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(hEMA!=INVALID_HANDLE) IndicatorRelease(hEMA);
   if(hATR!=INVALID_HANDLE) IndicatorRelease(hATR);
}

int DayKey()
{
   MqlDateTime d; TimeToStruct(TimeCurrent(), d);
   return d.year*10000 + d.mon*100 + d.day;
}

void ResetDay()
{
   int k = DayKey();
   if(k != dayStamp)
   {
      dayStamp = k;
      dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      tradesToday = 0;
   }
}

bool IsMonday()
{
   MqlDateTime d; TimeToStruct(TimeCurrent(), d);
   return (d.day_of_week == 1);
}

bool InSession()
{
   if(!InpUseSession) return true;
   MqlDateTime d; TimeToStruct(TimeCurrent(), d);
   if(InpSessionStartH < InpSessionEndH)
      return (d.hour >= InpSessionStartH && d.hour < InpSessionEndH);
   return (d.hour >= InpSessionStartH || d.hour < InpSessionEndH);
}

bool HasOurPos()
{
   for(int i=PositionsTotal()-1;i>=0;i--)
      if(pos.SelectByIndex(i) && pos.Symbol()==_Symbol && pos.Magic()==InpMagic)
         return true;
   return false;
}

bool RiskBlocks()
{
   ResetDay();
   if(InpSkipMonday && IsMonday()) return true;
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(initialEquity>0 && (initialEquity-eq)/initialEquity*100.0 >= InpMaxDDPct) return true;
   if(dayStartEquity>0)
   {
      double p = (eq-dayStartEquity)/dayStartEquity*100.0;
      if(p <= -InpDailyLossPct) return true;
      if(InpUseDailyProfit && p >= InpDailyProfitPct) return true;
   }
   if(tradesToday >= InpMaxTradesDay) return true;
   if(InpOnlyOnePos && HasOurPos()) return true;
   return false;
}

int EMABias()
{
   if(!InpUseEMA50) return 0;
   double e[]; ArraySetAsSeries(e,true);
   if(CopyBuffer(hEMA,0,1,2,e)<2) return 0;
   double cl = iClose(_Symbol, PERIOD_CURRENT, 1);
   if(cl > e[0]) return 1;
   if(cl < e[0]) return -1;
   return 0;
}

bool EMAAllows(const int dir)
{
   if(!InpUseEMA50) return true;
   int b = EMABias();
   if(b==dir) return true;
   if(b==0 && InpEMASoft) return true;
   return false;
}

double CalcLot(double slDist)
{
   if(slDist<=0) return 0;
   double risk = InpFixedRiskUSD;
   if(risk<=0) risk = AccountInfoDouble(ACCOUNT_EQUITY)*InpRiskPercent/100.0;
   double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(ts<=0 || tv<=0) return 0;
   double lot = risk / ((slDist/ts)*tv);
   double mn = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double mx = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double st = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(st<=0) st = mn;
   lot = MathFloor(lot/st)*st;
   if(lot<mn) return 0;
   if(lot>mx) lot = mx;
   return lot;
}

void ManageBE()
{
   if(!InpBreakeven) return;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      if(!pos.SelectByIndex(i)) continue;
      if(pos.Symbol()!=_Symbol || pos.Magic()!=InpMagic) continue;
      double o=pos.PriceOpen(), sl=pos.StopLoss(), tp=pos.TakeProfit();
      double risk=MathAbs(o-sl); if(risk<=0) continue;
      int dg=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
      if(pos.PositionType()==POSITION_TYPE_BUY)
      {
         if(SymbolInfoDouble(_Symbol,SYMBOL_BID)>=o+risk*InpBE_R && sl<o)
            trade.PositionModify(pos.Ticket(), NormalizeDouble(o,dg), tp);
      }
      else
      {
         if(SymbolInfoDouble(_Symbol,SYMBOL_ASK)<=o-risk*InpBE_R && (sl>o || sl==0))
            trade.PositionModify(pos.Ticket(), NormalizeDouble(o,dg), tp);
      }
   }
}

void OpenDir(const int dir, const double slPrice)
{
   int digits=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
   double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   double sl = NormalizeDouble(slPrice, digits);
   double slDist = (dir>0) ? (ask-sl) : (sl-bid);
   if(slDist<=0)
   {
      Print("SL on wrong side sl=", sl, " ask=", ask, " bid=", bid);
      return;
   }
   if(InpMinSL_Price>0 && slDist<InpMinSL_Price)
   {
      slDist = InpMinSL_Price;
      sl = (dir>0) ? NormalizeDouble(ask-slDist,digits) : NormalizeDouble(bid+slDist,digits);
   }
   double lot=CalcLot(slDist);
   if(lot<=0){ Print("lot=0 slDist=", slDist); return; }
   double tp;
   if(dir>0)
   {
      tp=NormalizeDouble(ask+slDist*InpRR,digits);
      if(!trade.Buy(lot,_Symbol,ask,sl,tp,InpComment))
         Print("Buy fail ", GetLastError(), " ", trade.ResultRetcodeDescription());
      else { tradesToday++; Print("C2C3 LONG lot=",lot," SL=",sl," TP=",tp); }
   }
   else
   {
      tp=NormalizeDouble(bid-slDist*InpRR,digits);
      if(!trade.Sell(lot,_Symbol,bid,sl,tp,InpComment))
         Print("Sell fail ", GetLastError(), " ", trade.ResultRetcodeDescription());
      else { tradesToday++; Print("C2C3 SHORT lot=",lot," SL=",sl," TP=",tp); }
   }
}

bool StrongBody(const double o, const double c, const double h, const double l)
{
   double rng = h-l;
   if(rng<=0) return false;
   return (MathAbs(c-o)/rng) >= InpC3BodyMin;
}

// C2 just closed = shift 1; C1 = shift 2
// Bear C2: took C1 high, closed back below C1 high (inside C1 range from above)
bool IsC2Bear(const double &h[], const double &l[], const double &c[], const int c2)
{
   int c1 = c2+1;
   if(h[c2] <= h[c1]) return false;
   if(c[c2] >= h[c1]) return false;          // must close back below C1 high
   return true;
}

bool IsC2Bull(const double &h[], const double &l[], const double &c[], const int c2)
{
   int c1 = c2+1;
   if(l[c2] >= l[c1]) return false;
   if(c[c2] <= l[c1]) return false;
   return true;
}

// C2 failed to close inside C1, then C3 (shift 1) is strong continuation
bool IsC3Bear(const double &o[], const double &h[], const double &l[], const double &c[])
{
   // C1=3 C2=2 C3=1
   if(h[2] <= h[3]) return false;            // C2 must make the high
   if(c[2] < h[3])  return false;            // C2 DID close back — that is C2 setup, not C3
   if(c[1] >= o[1]) return false;            // C3 must be down-close
   if(!StrongBody(o[1],c[1],h[1],l[1])) return false;
   if(InpC3MustCloseBeyondC2 && c[1] >= l[2]) return false;
   return true;
}

bool IsC3Bull(const double &o[], const double &h[], const double &l[], const double &c[])
{
   if(l[2] >= l[3]) return false;
   if(c[2] > l[3])  return false;
   if(c[1] <= o[1]) return false;
   if(!StrongBody(o[1],c[1],h[1],l[1])) return false;
   if(InpC3MustCloseBeyondC2 && c[1] <= h[2]) return false;
   return true;
}

void OnTick()
{
   ManageBE();
   datetime t = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(t==lastBar) return;
   lastBar = t;                              // new bar: previous candle just closed

   if(RiskBlocks()) return;
   if(!InSession()) return;

   double o[],h[],l[],c[],atr[];
   ArraySetAsSeries(o,true); ArraySetAsSeries(h,true);
   ArraySetAsSeries(l,true); ArraySetAsSeries(c,true); ArraySetAsSeries(atr,true);
   if(CopyOpen(_Symbol,PERIOD_CURRENT,0,6,o)<6) return;
   if(CopyHigh(_Symbol,PERIOD_CURRENT,0,6,h)<6) return;
   if(CopyLow(_Symbol,PERIOD_CURRENT,0,6,l)<6) return;
   if(CopyClose(_Symbol,PERIOD_CURRENT,0,6,c)<6) return;
   if(CopyBuffer(hATR,0,0,4,atr)<4) return;

   double buf = atr[1]*InpSLBufferATR;

   // --- C2 closure just printed on shift 1 → enter now (C3 open) ---
   if(InpAllowC2Entry)
   {
      if(InpAllowShort && IsC2Bear(h,l,c,1) && EMAAllows(-1))
      {
         double sl = h[1] + buf;
         Print("C2 BEAR close @ ", c[1], " C1.high=", h[2]);
         OpenDir(-1, sl);
         return;
      }
      if(InpAllowLong && IsC2Bull(h,l,c,1) && EMAAllows(1))
      {
         double sl = l[1] - buf;
         Print("C2 BULL close @ ", c[1], " C1.low=", l[2]);
         OpenDir(1, sl);
         return;
      }
   }

   // --- C3 closure just printed on shift 1 → enter now (C4 open) ---
   if(InpAllowC3Entry)
   {
      if(InpAllowShort && IsC3Bear(o,h,l,c) && EMAAllows(-1))
      {
         double sl = MathMax(h[2], h[1]) + buf;
         Print("C3 BEAR close @ ", c[1], " swing=", sl);
         OpenDir(-1, sl);
         return;
      }
      if(InpAllowLong && IsC3Bull(o,h,l,c) && EMAAllows(1))
      {
         double sl = MathMin(l[2], l[1]) - buf;
         Print("C3 BULL close @ ", c[1], " swing=", sl);
         OpenDir(1, sl);
         return;
      }
   }
}
