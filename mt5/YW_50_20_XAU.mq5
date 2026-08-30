//+------------------------------------------------------------------+
//|                                              YW_50_20_XAU.mq5    |
//|  YW 50/20 EMA20 x SMA50 pullback — XAUUSD / GOLD                 |
//|  Defaults from MGC 60d study (RR 1.5, pullback, ~43% WR)         |
//|  Tradeify $247K: 0.25% risk, 2% day stop, 8% max DD              |
//+------------------------------------------------------------------+
#property copyright "YW Concept"
#property version   "1.00"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

input group "=== MA ==="
input int      InpEMAPeriod     = 20;
input int      InpSMAPeriod     = 50;

input group "=== Entry ==="
input int      InpMaxWaitBars   = 16;
input double   InpPullbackATR   = 0.25;
input bool     InpRequireTouch  = true;
input bool     InpOnlyOnePos    = true;
input bool     InpAllowLong     = true;
input bool     InpAllowShort    = true;

input group "=== HTF filter ==="
input bool     InpUseHTFFilter  = true;
input ENUM_TIMEFRAMES InpHTF    = PERIOD_H1;
input int      InpHTF_EMA       = 20;
input bool     InpHTF_Soft      = true;

input group "=== Session (server) ==="
input bool     InpUseSession    = true;
input int      InpSessionStartH = 8;     // London
input int      InpSessionEndH   = 21;    // NY mid

input group "=== Risk $247K ==="
input double   InpRiskPercent   = 0.25;
input double   InpFixedRiskUSD  = 600;   // ~0.25% of 247k; set 0 to use %
input double   InpRR            = 1.5;   // MGC best
input double   InpSL_ATR        = 1.4;
input double   InpMinSL_Price   = 3.0;   // min SL distance in PRICE (XAU $)
input double   InpDailyLossPct  = 2.0;
input double   InpDailyProfitPct= 2.0;
input bool     InpUseDailyProfit= true;
input double   InpMaxDDPct      = 8.0;
input int      InpMaxTradesDay  = 4;
input bool     InpBreakeven     = true;
input double   InpBE_R          = 1.0;

input group "=== Misc ==="
input int      InpMagic         = 50248;
input string   InpComment       = "YW50/20-XAU";
input int      InpSlippage      = 30;

CTrade         trade;
CPositionInfo  pos;

int            hEMA, hSMA, hATR, hHTF;
datetime       lastBar = 0;
double         dayStartEquity = 0, initialEquity = 0;
int            dayStamp = 0, tradesToday = 0;
int            crossDir = 0, waitBars = 0;
bool           waiting = false;

int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippage);
   trade.SetTypeFillingBySymbol(_Symbol);

   hEMA = iMA(_Symbol, PERIOD_CURRENT, InpEMAPeriod, 0, MODE_EMA, PRICE_CLOSE);
   hSMA = iMA(_Symbol, PERIOD_CURRENT, InpSMAPeriod, 0, MODE_SMA, PRICE_CLOSE);
   hATR = iATR(_Symbol, PERIOD_CURRENT, 14);
   hHTF = iMA(_Symbol, InpHTF, InpHTF_EMA, 0, MODE_EMA, PRICE_CLOSE);
   if(hEMA==INVALID_HANDLE || hSMA==INVALID_HANDLE ||
      hATR==INVALID_HANDLE || hHTF==INVALID_HANDLE)
      return INIT_FAILED;

   initialEquity  = AccountInfoDouble(ACCOUNT_EQUITY);
   dayStartEquity = initialEquity;
   dayStamp       = DayKey();

   string s = _Symbol;
   StringToUpper(s);
   if(StringFind(s,"XAU")<0 && StringFind(s,"GOLD")<0 && StringFind(s,"PAXG")<0)
      Print("WARNING: symbol looks not gold: ", _Symbol);

   Print("YW 50/20 XAU v1.00 | ", _Symbol, " TF=", EnumToString(Period()),
         " FixedRisk=", InpFixedRiskUSD, " RR=", InpRR);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(hEMA!=INVALID_HANDLE) IndicatorRelease(hEMA);
   if(hSMA!=INVALID_HANDLE) IndicatorRelease(hSMA);
   if(hATR!=INVALID_HANDLE) IndicatorRelease(hATR);
   if(hHTF!=INVALID_HANDLE) IndicatorRelease(hHTF);
}

int DayKey()
{
   MqlDateTime d; TimeToStruct(TimeCurrent(), d);
   return d.year*1000 + d.day_of_year;
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

int HTFBias()
{
   if(!InpUseHTFFilter) return 0;
   double ema[]; ArraySetAsSeries(ema,true);
   if(CopyBuffer(hHTF,0,1,2,ema)<2) return 0;
   double cl = iClose(_Symbol, InpHTF, 1);
   double band = ema[0]*0.0004; // ~0.04% gold
   if(cl > ema[0]+band) return 1;
   if(cl < ema[0]-band) return -1;
   return 0;
}

bool HTFAllows(const int dir)
{
   if(!InpUseHTFFilter) return true;
   int b = HTFBias();
   if(b==dir) return true;
   if(b==0 && InpHTF_Soft) return true;
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
   if(st<=0) st=mn;
   lot = MathFloor(lot/st)*st;
   if(lot<mn) return 0;
   if(lot>mx) lot=mx;
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

void OpenDir(const int dir, const double atr)
{
   int digits=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
   double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   double slDist=atr*InpSL_ATR;
   if(slDist < InpMinSL_Price) slDist = InpMinSL_Price;
   double lot=CalcLot(slDist);
   if(lot<=0){ Print("lot=0 slDist=", slDist); return; }
   double sl,tp;
   if(dir>0)
   {
      sl=NormalizeDouble(ask-slDist,digits);
      tp=NormalizeDouble(ask+slDist*InpRR,digits);
      if(!trade.Buy(lot,_Symbol,ask,sl,tp,InpComment))
         Print("Buy fail ", trade.ResultRetcodeDescription());
      else { tradesToday++; Print("XAU LONG lot=",lot," SL=",sl," TP=",tp); }
   }
   else
   {
      sl=NormalizeDouble(bid+slDist,digits);
      tp=NormalizeDouble(bid-slDist*InpRR,digits);
      if(!trade.Sell(lot,_Symbol,bid,sl,tp,InpComment))
         Print("Sell fail ", trade.ResultRetcodeDescription());
      else { tradesToday++; Print("XAU SHORT lot=",lot," SL=",sl," TP=",tp); }
   }
}

void OnTick()
{
   ManageBE();
   datetime t=iTime(_Symbol,PERIOD_CURRENT,0);
   if(t==lastBar) return;
   lastBar=t;
   if(RiskBlocks()) return;
   if(!InSession()) return;

   int need=InpMaxWaitBars+5;
   double ema[],sma[],atr[],cl[],hi[],lo[];
   ArraySetAsSeries(ema,true); ArraySetAsSeries(sma,true); ArraySetAsSeries(atr,true);
   ArraySetAsSeries(cl,true); ArraySetAsSeries(hi,true); ArraySetAsSeries(lo,true);
   if(CopyBuffer(hEMA,0,0,need,ema)<need) return;
   if(CopyBuffer(hSMA,0,0,need,sma)<need) return;
   if(CopyBuffer(hATR,0,0,need,atr)<need) return;
   if(CopyClose(_Symbol,PERIOD_CURRENT,0,need,cl)<need) return;
   if(CopyHigh(_Symbol,PERIOD_CURRENT,0,need,hi)<need) return;
   if(CopyLow(_Symbol,PERIOD_CURRENT,0,need,lo)<need) return;
   if(atr[1]<=0) return;

   if(ema[2]<=sma[2] && ema[1]>sma[1] && InpAllowLong && HTFAllows(1))
   { crossDir=1; waitBars=0; waiting=true; Print("XAU golden"); }
   else if(ema[2]>=sma[2] && ema[1]<sma[1] && InpAllowShort && HTFAllows(-1))
   { crossDir=-1; waitBars=0; waiting=true; Print("XAU death"); }

   if(!waiting || crossDir==0) return;
   waitBars++;
   if(waitBars>InpMaxWaitBars){ waiting=false; crossDir=0; return; }
   if(crossDir==1 && ema[1]<sma[1]){ waiting=false; crossDir=0; return; }
   if(crossDir==-1 && ema[1]>sma[1]){ waiting=false; crossDir=0; return; }
   if(!HTFAllows(crossDir)){ waiting=false; crossDir=0; return; }

   double band=atr[1]*InpPullbackATR;
   bool hit=false;
   if(crossDir==1 && lo[1]<=ema[1]+band && cl[1]>sma[1]) hit=true;
   if(crossDir==-1 && hi[1]>=ema[1]-band && cl[1]<sma[1]) hit=true;
   if(!hit) return;
   OpenDir(crossDir, atr[1]);
   waiting=false; crossDir=0;
}
