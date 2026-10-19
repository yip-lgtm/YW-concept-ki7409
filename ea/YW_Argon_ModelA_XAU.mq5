//+------------------------------------------------------------------+
//|                              YW_Argon_ModelA_XAU.mq5             |
//|                              Argon Model A: Liquidity Sweep      |
//|                              + Pin Bar / Engulfing for Gold      |
//+------------------------------------------------------------------+
#property copyright "YW Concept"
#property link      "https://github.com/yip-lgtm/YW-concept-ki7409"
#property version   "1.00"
#property strict

// Argon Model A — Liquidity Sweep + Pin Bar / Engulfing
// Gold short-term. Bar-based, not HFT.
// Default risk $50, SL max $5, 1R BE, 1.5R TP.
// Aligns with docs/21-Argon-Gold-SOP.md

enum ENUM_FXIFY_PRESET
{
   PRESET_ONE_PHASE = 0,     // One Phase 10K: 3% day / 6% trail / 10% target
   PRESET_TWO_STANDARD = 1,
   PRESET_TWO_PRO = 2,
   PRESET_LIGHTNING = 3,
   PRESET_CUSTOM = 4
};

input string            InpSymbol          = "";          // Symbol (empty = chart symbol)
input ENUM_FXIFY_PRESET InpPreset          = PRESET_ONE_PHASE;
input double            InpAccountSize     = 10000.0;
input double            InpRiskUSD         = 50.0;        // Risk per trade
input double            InpDailyLossPct    = 3.0;
input double            InpMaxDDPct        = 6.0;
input double            InpTargetPct       = 10.0;
input bool              InpStopAtTarget    = true;
input int               InpMaxTradesDay    = 4;

input ENUM_TIMEFRAMES   InpSignalTF        = PERIOD_M5;   // Signal TF (M5 recommended)
input ENUM_TIMEFRAMES   InpSwingTF         = PERIOD_M15;  // Swing / value area TF
input ENUM_TIMEFRAMES   InpFilterTF        = PERIOD_H1;   // HTF trend filter
input int               InpSwingLookback   = 20;          // Bars to find recent swing low/high
input int               InpEMAPeriod       = 20;          // HTF EMA for direction
input bool              InpUseHTFFilter    = true;
input double            InpPinWickRatio    = 0.66;        // Lower wick >= this of total range
input double            InpSLBuffer        = 0.30;        // Extra buffer below sweep low (price)
input double            InpMaxSL_USD       = 5.0;         // Abandon if SL distance > this
input double            InpRR              = 1.5;
input bool              InpAllowLong       = true;
input bool              InpAllowShort      = true;
input bool              InpOnlyOnePos      = true;

input bool              InpUseSession      = true;
input int               InpSessionStart    = 7;
input int               InpSessionEnd      = 21;

input bool              InpBreakeven       = true;
input double            InpBE_R            = 1.0;
input int               InpMagic           = 502021;
input string            InpComment         = "YW-Argon-A-XAU";
input int               InpSlippage        = 30;

int      g_htf = INVALID_HANDLE;
datetime g_lastBar = 0;
datetime g_dayKey  = 0;
int      g_tradesToday = 0;
double   g_dayStartBal = 0.0;
double   g_peakBal     = 0.0;

//+------------------------------------------------------------------+
double DayLossPct()
{
   if(InpPreset == PRESET_ONE_PHASE || InpPreset == PRESET_LIGHTNING) return 3.0;
   if(InpPreset == PRESET_TWO_STANDARD || InpPreset == PRESET_TWO_PRO) return 4.0;
   return InpDailyLossPct;
}
double MaxDDPct()
{
   if(InpPreset == PRESET_ONE_PHASE) return 6.0;
   if(InpPreset == PRESET_TWO_STANDARD) return 10.0;
   if(InpPreset == PRESET_TWO_PRO) return 8.0;
   if(InpPreset == PRESET_LIGHTNING) return 4.0;
   return InpMaxDDPct;
}
double TargetPct()
{
   if(InpPreset == PRESET_ONE_PHASE || InpPreset == PRESET_TWO_STANDARD) return 10.0;
   if(InpPreset == PRESET_TWO_PRO) return 4.0;
   if(InpPreset == PRESET_LIGHTNING) return 5.0;
   return InpTargetPct;
}
string Sym() { return (InpSymbol == "" ? _Symbol : InpSymbol); }

//+------------------------------------------------------------------+
int OnInit()
{
   string s = Sym();
   g_htf = iMA(s, InpFilterTF, InpEMAPeriod, 0, MODE_EMA, PRICE_CLOSE);
   if(g_htf == INVALID_HANDLE)
   {
      Print("HTF EMA handle failed");
      return INIT_FAILED;
   }
   g_dayStartBal = AccountInfoDouble(ACCOUNT_BALANCE);
   g_peakBal = g_dayStartBal;
   g_dayKey = iTime(s, PERIOD_D1, 0);
   PrintFormat("Argon Model A XAU ready. risk=$%.0f maxSL=$%.1f RR=%.1f",
               InpRiskUSD, InpMaxSL_USD, InpRR);
   return INIT_SUCCEEDED;
}
void OnDeinit(const int reason)
{
   if(g_htf != INVALID_HANDLE) IndicatorRelease(g_htf);
}

//+------------------------------------------------------------------+
bool NewBar()
{
   datetime t = iTime(Sym(), InpSignalTF, 0);
   if(t == 0 || t == g_lastBar) return false;
   g_lastBar = t;
   return true;
}
void RollDay()
{
   datetime d = iTime(Sym(), PERIOD_D1, 0);
   if(d != g_dayKey)
   {
      g_dayKey = d;
      g_tradesToday = 0;
      g_dayStartBal = AccountInfoDouble(ACCOUNT_BALANCE);
   }
   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   if(bal > g_peakBal) g_peakBal = bal;
}
bool InSession()
{
   if(!InpUseSession) return true;
   MqlDateTime tm;
   TimeToStruct(TimeCurrent(), tm);
   if(InpSessionStart <= InpSessionEnd)
      return (tm.hour >= InpSessionStart && tm.hour < InpSessionEnd);
   return (tm.hour >= InpSessionStart || tm.hour < InpSessionEnd);
}
bool RiskHalt()
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double dayFloor = g_dayStartBal * (1.0 - DayLossPct() / 100.0);
   if(eq <= dayFloor) { Comment("Argon-A HALT daily"); return true; }
   double peakBase = MathMax(g_peakBal, InpAccountSize);
   double ddFloor = peakBase * (1.0 - MaxDDPct() / 100.0);
   if(InpPreset == PRESET_TWO_PRO)
      ddFloor = InpAccountSize * (1.0 - MaxDDPct() / 100.0);
   if(eq <= ddFloor) { Comment("Argon-A HALT DD"); return true; }
   if(InpStopAtTarget && bal >= InpAccountSize * (1.0 + TargetPct() / 100.0))
   { Comment("Argon-A target hit"); return true; }
   if(g_tradesToday >= InpMaxTradesDay) return true;
   return false;
}
int CountPositions()
{
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0 || !PositionSelectByTicket(tk)) continue;
      if(PositionGetString(POSITION_SYMBOL) == Sym() &&
         (int)PositionGetInteger(POSITION_MAGIC) == InpMagic) n++;
   }
   return n;
}
bool Copy1(int handle, int shift, double &out)
{
   double buf[];
   ArraySetAsSeries(buf, true);
   if(CopyBuffer(handle, 0, shift, 1, buf) != 1) return false;
   out = buf[0];
   return true;
}

//+------------------------------------------------------------------+
bool HTFOk(int dir)
{
   if(!InpUseHTFFilter) return true;
   double ema, close;
   if(!Copy1(g_htf, 1, ema)) return false;
   close = iClose(Sym(), InpFilterTF, 1);
   if(dir > 0) return close > ema;
   return close < ema;
}
double RecentSwingLow()
{
   string s = Sym();
   double low = iLow(s, InpSwingTF, 1);
   for(int i = 2; i <= InpSwingLookback; i++)
   {
      double l = iLow(s, InpSwingTF, i);
      if(l < low) low = l;
   }
   return low;
}
double RecentSwingHigh()
{
   string s = Sym();
   double high = iHigh(s, InpSwingTF, 1);
   for(int i = 2; i <= InpSwingLookback; i++)
   {
      double h = iHigh(s, InpSwingTF, i);
      if(h > high) high = h;
   }
   return high;
}
bool IsPinBar(int shift, int dir)
{
   string s = Sym();
   double o = iOpen(s, InpSignalTF, shift);
   double h = iHigh(s, InpSignalTF, shift);
   double l = iLow(s, InpSignalTF, shift);
   double c = iClose(s, InpSignalTF, shift);
   double range = h - l;
   if(range <= 0) return false;
   if(dir > 0)
   {
      double lowerWick = MathMin(o, c) - l;
      return (lowerWick / range >= InpPinWickRatio) && (c > o);
   }
   else
   {
      double upperWick = h - MathMax(o, c);
      return (upperWick / range >= InpPinWickRatio) && (c < o);
   }
}
bool IsEngulfing(int shift, int dir)
{
   string s = Sym();
   double o1 = iOpen(s, InpSignalTF, shift);
   double c1 = iClose(s, InpSignalTF, shift);
   double o2 = iOpen(s, InpSignalTF, shift + 1);
   double c2 = iClose(s, InpSignalTF, shift + 1);
   if(dir > 0)
      return (c1 > o1) && (c2 < o2) && (c1 > o2) && (o1 < c2);
   else
      return (c1 < o1) && (c2 > o2) && (c1 < o2) && (o1 > c2);
}
bool ModelASignal(int dir, double &slPrice)
{
   string s = Sym();
   double sweepRef = (dir > 0 ? RecentSwingLow() : RecentSwingHigh());
   double barLow  = iLow(s, InpSignalTF, 1);
   double barHigh = iHigh(s, InpSignalTF, 1);
   double barClose = iClose(s, InpSignalTF, 1);

   bool swept = false;
   if(dir > 0) swept = (barLow < sweepRef);
   else        swept = (barHigh > sweepRef);
   if(!swept) return false;

   bool rejection = IsPinBar(1, dir) || IsEngulfing(1, dir);
   if(!rejection) return false;

   if(dir > 0 && barClose <= sweepRef) return false;
   if(dir < 0 && barClose >= sweepRef) return false;

   if(dir > 0)
      slPrice = barLow - InpSLBuffer;
   else
      slPrice = barHigh + InpSLBuffer;
   return true;
}
double LotsFor(double slDist)
{
   if(slDist <= 0) return 0;
   string s = Sym();
   double tickVal = SymbolInfoDouble(s, SYMBOL_TRADE_TICK_VALUE);
   double tickSz  = SymbolInfoDouble(s, SYMBOL_TRADE_TICK_SIZE);
   if(tickVal <= 0 || tickSz <= 0) return 0;
   double lossPerLot = (slDist / tickSz) * tickVal;
   if(lossPerLot <= 0) return 0;
   double lots = InpRiskUSD / lossPerLot;
   double minL = SymbolInfoDouble(s, SYMBOL_VOLUME_MIN);
   double maxL = SymbolInfoDouble(s, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(s, SYMBOL_VOLUME_STEP);
   if(step <= 0) step = 0.01;
   lots = MathFloor(lots / step) * step;
   if(lots < minL) return 0;
   if(lots > maxL) lots = maxL;
   return lots;
}
bool Send(int dir, double slPrice)
{
   string s = Sym();
   double ask = SymbolInfoDouble(s, SYMBOL_ASK);
   double bid = SymbolInfoDouble(s, SYMBOL_BID);
   double entry = (dir > 0 ? ask : bid);
   double slDist = MathAbs(entry - slPrice);
   if(slDist > InpMaxSL_USD)
   {
      PrintFormat("SL too wide %.2f > %.1f, skip", slDist, InpMaxSL_USD);
      return false;
   }
   double tp = (dir > 0 ? entry + slDist * InpRR : entry - slDist * InpRR);
   int digits = (int)SymbolInfoInteger(s, SYMBOL_DIGITS);
   slPrice = NormalizeDouble(slPrice, digits);
   tp = NormalizeDouble(tp, digits);
   double lots = LotsFor(slDist);
   if(lots <= 0) { Print("lot 0, skip"); return false; }

   MqlTradeRequest req;
   MqlTradeResult  res;
   ZeroMemory(req);
   ZeroMemory(res);
   req.action = TRADE_ACTION_DEAL;
   req.symbol = s;
   req.volume = lots;
   req.type = (dir > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   req.price = entry;
   req.sl = slPrice;
   req.tp = tp;
   req.deviation = InpSlippage;
   req.magic = InpMagic;
   req.comment = InpComment;
   req.type_filling = ORDER_FILLING_IOC;
   if(!OrderSend(req, res) || (res.retcode != TRADE_RETCODE_DONE && res.retcode != TRADE_RETCODE_PLACED))
   {
      req.type_filling = ORDER_FILLING_FOK;
      if(!OrderSend(req, res))
      {
         Print("OrderSend failed ", res.retcode);
         return false;
      }
   }
   g_tradesToday++;
   PrintFormat("ModelA %s lots=%.2f sl=%.2f tp=%.2f dist=%.2f",
               (dir > 0 ? "BUY" : "SELL"), lots, slPrice, tp, slDist);
   return true;
}
void ManageBE()
{
   if(!InpBreakeven) return;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0 || !PositionSelectByTicket(tk)) continue;
      if(PositionGetString(POSITION_SYMBOL) != Sym()) continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      long type = PositionGetInteger(POSITION_TYPE);
      double bid = SymbolInfoDouble(Sym(), SYMBOL_BID);
      double ask = SymbolInfoDouble(Sym(), SYMBOL_ASK);
      double r = MathAbs(open - sl);
      if(r <= 0) continue;
      bool hit = false;
      if(type == POSITION_TYPE_BUY && bid >= open + r * InpBE_R) hit = true;
      if(type == POSITION_TYPE_SELL && ask <= open - r * InpBE_R) hit = true;
      if(!hit) continue;
      if(type == POSITION_TYPE_BUY && sl >= open) continue;
      if(type == POSITION_TYPE_SELL && sl <= open && sl > 0) continue;
      MqlTradeRequest req;
      MqlTradeResult res;
      ZeroMemory(req);
      ZeroMemory(res);
      req.action = TRADE_ACTION_SLTP;
      req.position = tk;
      req.symbol = Sym();
      req.sl = NormalizeDouble(open, (int)SymbolInfoInteger(Sym(), SYMBOL_DIGITS));
      req.tp = tp;
      OrderSend(req, res);
   }
}
//+------------------------------------------------------------------+
void OnTick()
{
   ManageBE();
   if(!NewBar()) return;
   RollDay();
   if(!InSession()) return;
   if(RiskHalt()) return;
   if(InpOnlyOnePos && CountPositions() > 0) return;

   if(InpAllowLong && HTFOk(1))
   {
      double sl;
      if(ModelASignal(1, sl))
         Send(1, sl);
   }
   if(InpAllowShort && HTFOk(-1))
   {
      double sl;
      if(ModelASignal(-1, sl))
         Send(-1, sl);
   }
}
//+------------------------------------------------------------------+
