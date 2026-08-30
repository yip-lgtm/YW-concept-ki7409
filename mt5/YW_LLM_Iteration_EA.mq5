//+------------------------------------------------------------------+
//|                                      YW_LLM_Iteration_EA.mq5     |
//|  LLM iteration after 50/20 + CRT BTC backtests                   |
//|  v1.00                                                            |
//|                                                                  |
//|  學到的：                                                          |
//|  • 50/20 5m/15m 否決；1H 可存活但期望近 0                     |
//|  • CRT 掃歷史會亂開；修正後 H4/M5 仍慢跌                     |
//|  • 過嚴過濾 = 0 單；過鬆 = 磨損                                  |
//|  本版：CRT 主信號 + 1H EMA 順勢，每倍 4H 最多 1 單，T1 保本   |
//|         可選 H-Pattern；默認關 5m 50/20                        |
//+------------------------------------------------------------------+
#property copyright "YW Concept LLM Iteration"
#property version   "1.00"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

input group "=== Risk $247K ==="
input double   InpRiskPercent   = 0.25;    // % equity / trade
input double   InpFixedRiskUSD  = 0;       // >0 overrides %
input double   InpDailyLossPct  = 2.0;
input double   InpDailyProfitPct= 2.0;
input bool     InpUseDailyProfit= true;
input double   InpMaxDDPct      = 8.0;
input int      InpMaxTradesDay  = 3;
input int      InpMaxOpen       = 1;
input int      InpCooldownBars  = 12;      // 5m bars after a trade
input int      InpMagic         = 16001;

input group "=== Setups ==="
input bool     InpUseCRT        = true;
input bool     InpUseHPattern   = true;
input bool     InpUse5020       = false;   // only meaningful on H1 chart

input group "=== CRT ==="
input double   InpMinRangePct   = 0.6;
input double   InpMaxRangePct   = 3.5;
input double   InpSL_ATR        = 1.6;
input double   InpRR            = 1.5;
input bool     InpT1_BE         = true;

input group "=== Filters ==="
input bool     InpUseH1EMA      = true;
input int      InpH1EMA         = 20;
input bool     InpAllowLong     = true;
input bool     InpAllowShort    = true;
input bool     InpSessionFilter = false;
input int      InpSessStart     = 8;
input int      InpSessEnd       = 21;

input group "=== H-Pattern ==="
input double   InpH_Body        = 0.60;
input double   InpH_MaxPB       = 0.50;
input double   InpH_Wick        = 0.30;
input int      InpH_MaxPBBars   = 10;
input bool     InpH_Conservative= true;

input group "=== 50/20 (H1) ==="
input int      InpEMA20         = 20;
input int      InpSMA50         = 50;
input int      InpPBWait        = 16;
input double   InpPB_ATR        = 0.30;

input group "=== Misc ==="
input string   InpComment       = "YW-LLM";
input int      InpSlippage      = 30;

CTrade         trade;
CPositionInfo  pos;

int            hATR5, hEMA1H, hEMA5, hSMA5;
datetime       lastBar5 = 0;
datetime       lastH4   = 0;
datetime       crtUsedH4 = 0;
datetime       lastTradeBar = 0;

double         dayEq = 0, initEq = 0;
int            dayKey = 0, tradesDay = 0;

// H-pattern state
int            hSt = 0; // 0 idle 1 pullback 2 ready
double         hHi = 0, hLo = 0, hPull = 0;
int            hBars = 0;
bool           hWick = false;
int            hDir = 0; // -1 short +1 long

// 50/20 state
int            xDir = 0, xWait = 0;
bool           xArm = false;

int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippage);
   trade.SetTypeFillingBySymbol(_Symbol);

   hATR5  = iATR(_Symbol, PERIOD_M5, 14);
   hEMA1H = iMA(_Symbol, PERIOD_H1, InpH1EMA, 0, MODE_EMA, PRICE_CLOSE);
   hEMA5  = iMA(_Symbol, PERIOD_M5, InpEMA20, 0, MODE_EMA, PRICE_CLOSE);
   hSMA5  = iMA(_Symbol, PERIOD_M5, InpSMA50, 0, MODE_SMA, PRICE_CLOSE);
   if(hATR5 == INVALID_HANDLE || hEMA1H == INVALID_HANDLE ||
      hEMA5 == INVALID_HANDLE || hSMA5 == INVALID_HANDLE)
      return INIT_FAILED;

   initEq = AccountInfoDouble(ACCOUNT_EQUITY);
   dayEq  = initEq;
   dayKey = DayKey();
   Print("YW LLM Iteration v1.00 | CRT=", InpUseCRT,
         " HP=", InpUseHPattern, " 5020=", InpUse5020,
         " Risk%=", InpRiskPercent, " Eq=", initEq);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(hATR5  != INVALID_HANDLE) IndicatorRelease(hATR5);
   if(hEMA1H != INVALID_HANDLE) IndicatorRelease(hEMA1H);
   if(hEMA5  != INVALID_HANDLE) IndicatorRelease(hEMA5);
   if(hSMA5  != INVALID_HANDLE) IndicatorRelease(hSMA5);
}

int DayKey()
{
   MqlDateTime d; TimeToStruct(TimeCurrent(), d);
   return d.year * 1000 + d.day_of_year;
}

void RollDay()
{
   int k = DayKey();
   if(k != dayKey) { dayKey = k; dayEq = AccountInfoDouble(ACCOUNT_EQUITY); tradesDay = 0; }
}

bool SessionOK()
{
   if(!InpSessionFilter) return true;
   MqlDateTime d; TimeToStruct(TimeCurrent(), d);
   if(InpSessStart < InpSessEnd) return (d.hour >= InpSessStart && d.hour < InpSessEnd);
   return (d.hour >= InpSessStart || d.hour < InpSessEnd);
}

bool HasPos()
{
   for(int i = PositionsTotal()-1; i >= 0; i--)
      if(pos.SelectByIndex(i) && pos.Symbol()==_Symbol && pos.Magic()==InpMagic)
         return true;
   return false;
}

bool Blocked()
{
   RollDay();
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(initEq > 0 && (initEq-eq)/initEq*100.0 >= InpMaxDDPct) return true;
   if(dayEq > 0)
   {
      double p = (eq-dayEq)/dayEq*100.0;
      if(p <= -InpDailyLossPct) return true;
      if(InpUseDailyProfit && p >= InpDailyProfitPct) return true;
   }
   if(tradesDay >= InpMaxTradesDay) return true;
   if(InpMaxOpen<=1 && HasPos()) return true;
   if(lastTradeBar > 0)
   {
      int shift = iBarShift(_Symbol, PERIOD_M5, lastTradeBar, true);
      if(shift >= 0 && shift < InpCooldownBars) return true;
   }
   return false;
}

int H1Bias()
{
   if(!InpUseH1EMA) return 0;
   double e[]; ArraySetAsSeries(e,true);
   if(CopyBuffer(hEMA1H, 0, 1, 2, e) < 2) return 0;
   double c = iClose(_Symbol, PERIOD_H1, 1);
   if(c > e[0]) return 1;
   if(c < e[0]) return -1;
   return 0;
}

bool DirOK(const int dir)
{
   if(dir > 0 && !InpAllowLong) return false;
   if(dir < 0 && !InpAllowShort) return false;
   int b = H1Bias();
   if(!InpUseH1EMA) return true;
   return (b == dir);
}

double LotBySL(const double slDist)
{
   if(slDist <= 0) return 0;
   double risk = InpFixedRiskUSD;
   if(risk <= 0) risk = AccountInfoDouble(ACCOUNT_EQUITY) * InpRiskPercent / 100.0;
   double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(ts<=0 || tv<=0) return 0;
   double lot = risk / (slDist / ts * tv);
   double mn = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double mx = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double st = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(st<=0) st = mn;
   lot = MathFloor(lot/st)*st;
   if(lot < mn) return 0;
   if(lot > mx) lot = mx;
   return lot;
}

void OpenDir(const int dir, const double slDist, const string tag)
{
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double lot = LotBySL(slDist);
   if(lot <= 0) { Print(tag, " lot=0"); return; }
   double sl, tp;
   if(dir > 0)
   {
      sl = NormalizeDouble(ask - slDist, digits);
      tp = NormalizeDouble(ask + slDist * InpRR, digits);
      if(!trade.Buy(lot, _Symbol, ask, sl, tp, tag)) { Print("Buy fail ", trade.ResultRetcodeDescription()); return; }
   }
   else
   {
      sl = NormalizeDouble(bid + slDist, digits);
      tp = NormalizeDouble(bid - slDist * InpRR, digits);
      if(!trade.Sell(lot, _Symbol, bid, sl, tp, tag)) { Print("Sell fail ", trade.ResultRetcodeDescription()); return; }
   }
   tradesDay++;
   lastTradeBar = iTime(_Symbol, PERIOD_M5, 0);
   Print(tag, " dir=", dir, " lot=", lot, " SL=", sl, " TP=", tp);
}

void ManageBE()
{
   if(!InpT1_BE) return;
   for(int i = PositionsTotal()-1; i>=0; i--)
   {
      if(!pos.SelectByIndex(i)) continue;
      if(pos.Symbol()!=_Symbol || pos.Magic()!=InpMagic) continue;
      double o = pos.PriceOpen(), sl = pos.StopLoss(), tp = pos.TakeProfit();
      double risk = MathAbs(o - sl);
      if(risk <= 0) continue;
      int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
      if(pos.PositionType()==POSITION_TYPE_BUY)
      {
         if(SymbolInfoDouble(_Symbol,SYMBOL_BID) >= o+risk && sl < o)
            trade.PositionModify(pos.Ticket(), NormalizeDouble(o,dg), tp);
      }
      else
      {
         if(SymbolInfoDouble(_Symbol,SYMBOL_ASK) <= o-risk && (sl>o || sl==0))
            trade.PositionModify(pos.Ticket(), NormalizeDouble(o,dg), tp);
      }
   }
}

void TryCRT()
{
   if(!InpUseCRT) return;
   datetime t4 = iTime(_Symbol, PERIOD_H4, 1);
   if(t4 <= 0) return;
   if(t4 != lastH4) { lastH4 = t4; }
   if(crtUsedH4 == t4) return;

   double hi = iHigh(_Symbol, PERIOD_H4, 1);
   double lo = iLow(_Symbol, PERIOD_H4, 1);
   if(lo <= 0 || hi <= lo) return;
   double pct = (hi-lo)/lo*100.0;
   if(pct < InpMinRangePct || pct > InpMaxRangePct) return;

   double h1 = iHigh(_Symbol,PERIOD_M5,1), l1 = iLow(_Symbol,PERIOD_M5,1), c1 = iClose(_Symbol,PERIOD_M5,1);
   double h2 = iHigh(_Symbol,PERIOD_M5,2), l2 = iLow(_Symbol,PERIOD_M5,2);

   double atr[]; ArraySetAsSeries(atr,true);
   if(CopyBuffer(hATR5,0,1,1,atr)<1 || atr[0]<=0) return;
   double sl = atr[0]*InpSL_ATR;

   if(l2 < lo && c1 > h2 && c1 > lo && DirOK(1))
   {
      crtUsedH4 = t4;
      OpenDir(1, sl, InpComment+"-CRT-L");
      return;
   }
   if(h2 > hi && c1 < l2 && c1 < hi && DirOK(-1))
   {
      crtUsedH4 = t4;
      OpenDir(-1, sl, InpComment+"-CRT-S");
   }
}

bool StrongBear(const double o,const double h,const double l,const double c,const double atr)
{
   double rng=h-l; if(rng<=0||atr<=0) return false;
   double body=o-c; if(body<=0) return false;
   return (body/rng>=InpH_Body && body>=atr*0.45);
}
bool StrongBull(const double o,const double h,const double l,const double c,const double atr)
{
   double rng=h-l; if(rng<=0||atr<=0) return false;
   double body=c-o; if(body<=0) return false;
   return (body/rng>=InpH_Body && body>=atr*0.45);
}
bool UpWick(const double o,const double h,const double l,const double c)
{
   double rng=h-l; if(rng<=0) return false;
   return ((h-MathMax(o,c))/rng >= InpH_Wick);
}
bool DnWick(const double o,const double h,const double l,const double c)
{
   double rng=h-l; if(rng<=0) return false;
   return ((MathMin(o,c)-l)/rng >= InpH_Wick);
}

void TryH()
{
   if(!InpUseHPattern) return;
   double o=iOpen(_Symbol,PERIOD_M5,1), h=iHigh(_Symbol,PERIOD_M5,1);
   double l=iLow(_Symbol,PERIOD_M5,1),  c=iClose(_Symbol,PERIOD_M5,1);
   double atr[]; ArraySetAsSeries(atr,true);
   if(CopyBuffer(hATR5,0,1,1,atr)<1) return;

   if(hSt==0)
   {
      if(StrongBear(o,h,l,c,atr[0]) && DirOK(-1))
      {
         hHi=h; hLo=l; hPull=c; hBars=0; hWick=false; hDir=-1; hSt=1;
         if(iHigh(_Symbol,PERIOD_M5,2)>hHi) hHi=iHigh(_Symbol,PERIOD_M5,2);
      }
      else if(StrongBull(o,h,l,c,atr[0]) && DirOK(1))
      {
         hLo=l; hHi=h; hPull=c; hBars=0; hWick=false; hDir=1; hSt=1;
         if(iLow(_Symbol,PERIOD_M5,2)<hLo) hLo=iLow(_Symbol,PERIOD_M5,2);
      }
      return;
   }

   hBars++;
   if(hDir<0)
   {
      if(h>hPull) hPull=h;
      double ret=(hPull-hLo)/(hHi-hLo+1e-12);
      if(ret>InpH_MaxPB+0.02 || hBars>InpH_MaxPBBars) { hSt=0; return; }
      if(UpWick(o,h,l,c)) hWick=true;
      if(hWick && ret<=InpH_MaxPB)
      {
         if(!InpH_Conservative) { OpenDir(-1, MathMax(hPull-c, atr[0]*InpSL_ATR), InpComment+"-H-S"); hSt=0; return; }
         hSt=2;
      }
      if(hSt==2 && c<hLo)
      {
         OpenDir(-1, MathMax(hPull-c, atr[0]*InpSL_ATR), InpComment+"-H-S");
         hSt=0;
      }
   }
   else
   {
      if(l<hPull) hPull=l;
      double ret=(hHi-hPull)/(hHi-hLo+1e-12);
      if(ret>InpH_MaxPB+0.02 || hBars>InpH_MaxPBBars) { hSt=0; return; }
      if(DnWick(o,h,l,c)) hWick=true;
      if(hWick && ret<=InpH_MaxPB)
      {
         if(!InpH_Conservative) { OpenDir(1, MathMax(c-hPull, atr[0]*InpSL_ATR), InpComment+"-H-L"); hSt=0; return; }
         hSt=2;
      }
      if(hSt==2 && c>hHi)
      {
         OpenDir(1, MathMax(c-hPull, atr[0]*InpSL_ATR), InpComment+"-H-L");
         hSt=0;
      }
   }
}

void Try5020()
{
   if(!InpUse5020) return;
   // intended when tester/chart is H1; still reads M5 MA as fallback — skip if not H1
   if(Period() != PERIOD_H1) return;

   double e[], s[], a[], cl[], hi[], lo[];
   ArraySetAsSeries(e,true); ArraySetAsSeries(s,true); ArraySetAsSeries(a,true);
   ArraySetAsSeries(cl,true); ArraySetAsSeries(hi,true); ArraySetAsSeries(lo,true);
   int n = InpPBWait+4;
   int he = iMA(_Symbol, PERIOD_H1, InpEMA20, 0, MODE_EMA, PRICE_CLOSE);
   int hs = iMA(_Symbol, PERIOD_H1, InpSMA50, 0, MODE_SMA, PRICE_CLOSE);
   int ha = iATR(_Symbol, PERIOD_H1, 14);
   if(he==INVALID_HANDLE || hs==INVALID_HANDLE || ha==INVALID_HANDLE) return;
   if(CopyBuffer(he,0,0,n,e)<n) { IndicatorRelease(he); IndicatorRelease(hs); IndicatorRelease(ha); return; }
   if(CopyBuffer(hs,0,0,n,s)<n) { IndicatorRelease(he); IndicatorRelease(hs); IndicatorRelease(ha); return; }
   if(CopyBuffer(ha,0,0,n,a)<n) { IndicatorRelease(he); IndicatorRelease(hs); IndicatorRelease(ha); return; }
   CopyClose(_Symbol,PERIOD_H1,0,n,cl); CopyHigh(_Symbol,PERIOD_H1,0,n,hi); CopyLow(_Symbol,PERIOD_H1,0,n,lo);
   IndicatorRelease(he); IndicatorRelease(hs); IndicatorRelease(ha);

   if(e[2]<=s[2] && e[1]>s[1] && DirOK(1)) { xDir=1; xWait=0; xArm=true; }
   if(e[2]>=s[2] && e[1]<s[1] && DirOK(-1)) { xDir=-1; xWait=0; xArm=true; }
   if(!xArm) return;
   xWait++;
   if(xWait>InpPBWait) { xArm=false; xDir=0; return; }
   double band=a[1]*InpPB_ATR;
   bool hit=false;
   if(xDir==1 && lo[1]<=e[1]+band && cl[1]>s[1]) hit=true;
   if(xDir==-1 && hi[1]>=e[1]-band && cl[1]<s[1]) hit=true;
   if(hit) { OpenDir(xDir, a[1]*InpSL_ATR, InpComment+"-5020"); xArm=false; xDir=0; }
}

void OnTick()
{
   ManageBE();
   datetime t = iTime(_Symbol, PERIOD_M5, 0);
   if(t == lastBar5) return;
   lastBar5 = t;

   if(Blocked()) return;
   if(!SessionOK()) return;

   TryCRT();
   if(Blocked()) return;
   TryH();
   if(Blocked()) return;
   Try5020();
}
