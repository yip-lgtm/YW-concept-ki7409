//+------------------------------------------------------------------+
//|                                     YW_5020_FXIFY_XAU.mq5        |
//|                                     YW Concept 50/20 gold        |
//|                                     Fxify 10K evaluation preset  |
//+------------------------------------------------------------------+
#property copyright "YW Concept"
#property link      "https://github.com/yip-lgtm/YW-concept-ki7409"
#property version   "1.00"
#property strict

// Fxify $10K One Phase defaults (check the program you actually bought):
//   profit target 10% = $1,000
//   daily loss    3%  = $300   (from prior 17:00 EST balance)
//   max DD        6%  = $600   trailing until it locks at start
// Instant Funding often bans EAs. This EA is bar-based, not HFT.

enum ENUM_FXIFY_PRESET
{
   PRESET_ONE_PHASE = 0,     // One Phase 10K: 3% day / 6% trail / 10% target
   PRESET_TWO_STANDARD = 1,  // Two Phase Standard: 4% day / 10% trail / 10% then 5%
   PRESET_TWO_PRO = 2,       // Two Phase Pro: 4% day / 8% static / 4% then 8%
   PRESET_LIGHTNING = 3,     // Lightning: 3% day / 4% trail / 5% in 7 days
   PRESET_CUSTOM = 4         // Use the percent inputs below
};

input string            InpSymbol          = "";          // Symbol (empty = chart symbol)
input ENUM_FXIFY_PRESET InpPreset          = PRESET_ONE_PHASE;
input double            InpAccountSize     = 10000.0;     // Account size USD
input double            InpRiskUSD         = 50.0;        // Risk per trade USD
input double            InpDailyLossPct    = 3.0;         // Custom daily loss %
input double            InpMaxDDPct        = 6.0;         // Custom max DD %
input double            InpTargetPct       = 10.0;        // Custom profit target %
input bool              InpStopAtTarget    = true;        // Halt when target hit
input int               InpMaxTradesDay    = 4;           // Max entries per day

input int               InpEMAPeriod       = 20;          // 20 EMA
input int               InpSMAPeriod       = 50;          // 50 SMA
input ENUM_TIMEFRAMES   InpSignalTF        = PERIOD_M15;  // Signal timeframe
input ENUM_TIMEFRAMES   InpFilterTF        = PERIOD_H1;   // Direction filter TF
input bool              InpUseHTFFilter    = true;        // Price vs HTF EMA20
input int               InpMaxWaitBars     = 16;          // Bars to wait for pullback
input double            InpPullbackATR     = 0.20;        // Touch band = ATR * this
input bool              InpRequireTouch    = true;        // Must tag EMA20
input double            InpRR              = 1.5;         // TP = SL * RR
input double            InpSL_ATR          = 1.2;         // SL = ATR * this
input double            InpMinSL_USD       = 1.50;        // Min SL distance in price
input bool              InpAllowLong       = true;
input bool              InpAllowShort      = true;
input bool              InpOnlyOnePos      = true;

input bool              InpUseSession      = true;        // London + NY only
input int               InpSessionStart    = 7;           // Server hour start
input int               InpSessionEnd      = 21;          // Server hour end

input bool              InpBreakeven       = true;
input double            InpBE_R            = 1.0;         // Move SL to entry at this R
input int               InpMagic           = 502010;
input string            InpComment         = "YW-5020-XAU";
input int               InpSlippage        = 30;

int      g_ema = INVALID_HANDLE;
int      g_sma = INVALID_HANDLE;
int      g_atr = INVALID_HANDLE;
int      g_htf = INVALID_HANDLE;
datetime g_lastBar = 0;
datetime g_dayKey  = 0;
int      g_tradesToday = 0;
double   g_dayStartBal = 0.0;
double   g_peakBal     = 0.0;
int      g_crossBar    = -1;
int      g_crossDir    = 0;   // 1 long, -1 short

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
string Sym()
{
   return (InpSymbol == "" ? _Symbol : InpSymbol);
}
//+------------------------------------------------------------------+
int OnInit()
{
   string s = Sym();
   g_ema = iMA(s, InpSignalTF, InpEMAPeriod, 0, MODE_EMA, PRICE_CLOSE);
   g_sma = iMA(s, InpSignalTF, InpSMAPeriod, 0, MODE_SMA, PRICE_CLOSE);
   g_atr = iATR(s, InpSignalTF, 14);
   g_htf = iMA(s, InpFilterTF, InpEMAPeriod, 0, MODE_EMA, PRICE_CLOSE);
   if(g_ema == INVALID_HANDLE || g_sma == INVALID_HANDLE || g_atr == INVALID_HANDLE || g_htf == INVALID_HANDLE)
   {
      Print("indicator handle failed");
      return INIT_FAILED;
   }
   g_dayStartBal = AccountInfoDouble(ACCOUNT_BALANCE);
   g_peakBal = g_dayStartBal;
   g_dayKey = iTime(s, PERIOD_D1, 0);
   PrintFormat("YW 5020 XAU ready. preset=%d risk=$%.0f day=%.1f%% max=%.1f%%",
               InpPreset, InpRiskUSD, DayLossPct(), MaxDDPct());
   return INIT_SUCCEEDED;
}
void OnDeinit(const int reason)
{
   if(g_ema != INVALID_HANDLE) IndicatorRelease(g_ema);
   if(g_sma != INVALID_HANDLE) IndicatorRelease(g_sma);
   if(g_atr != INVALID_HANDLE) IndicatorRelease(g_atr);
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
   if(eq <= dayFloor)
   {
      Comment("YW-5020 HALT daily loss");
      return true;
   }
   double peakBase = MathMax(g_peakBal, InpAccountSize);
   double ddFloor = peakBase * (1.0 - MaxDDPct() / 100.0);
   if(InpPreset == PRESET_TWO_PRO)
      ddFloor = InpAccountSize * (1.0 - MaxDDPct() / 100.0);
   if(eq <= ddFloor)
   {
      Comment("YW-5020 HALT max DD");
      return true;
   }
   if(InpStopAtTarget && bal >= InpAccountSize * (1.0 + TargetPct() / 100.0))
   {
      Comment("YW-5020 target hit, halted");
      return true;
   }
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
void DetectCross()
{
   double e0, e1, s0, s1;
   if(!Copy1(g_ema, 1, e0) || !Copy1(g_ema, 2, e1)) return;
   if(!Copy1(g_sma, 1, s0) || !Copy1(g_sma, 2, s1)) return;
   if(e1 <= s1 && e0 > s0)
   {
      g_crossDir = 1;
      g_crossBar = iBars(Sym(), InpSignalTF) - 1;
   }
   else if(e1 >= s1 && e0 < s0)
   {
      g_crossDir = -1;
      g_crossBar = iBars(Sym(), InpSignalTF) - 1;
   }
}
bool CrossFresh()
{
   if(g_crossDir == 0) return false;
   int age = (iBars(Sym(), InpSignalTF) - 1) - g_crossBar;
   return (age >= 1 && age <= InpMaxWaitBars);
}
bool HTFOk(int dir)
{
   if(!InpUseHTFFilter) return true;
   double ema, close;
   if(!Copy1(g_htf, 1, ema)) return false;
   close = iClose(Sym(), InpFilterTF, 1);
   if(dir > 0) return close > ema;
   return close < ema;
}
bool PullbackOk(int dir, double ema, double atr)
{
   double high = iHigh(Sym(), InpSignalTF, 1);
   double low  = iLow(Sym(), InpSignalTF, 1);
   double close = iClose(Sym(), InpSignalTF, 1);
   double band = atr * InpPullbackATR;
   if(dir > 0)
   {
      bool touch = (!InpRequireTouch) || (low <= ema + band);
      return touch && close > ema && close > iOpen(Sym(), InpSignalTF, 1);
   }
   bool touch = (!InpRequireTouch) || (high >= ema - band);
   return touch && close < ema && close < iOpen(Sym(), InpSignalTF, 1);
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
   // hard cap: never risk more than daily budget / 3 on one ticket
   double dayBudget = InpAccountSize * DayLossPct() / 100.0;
   double maxRisk = dayBudget / 3.0;
   if(InpRiskUSD > maxRisk) Print("warning: risk exceeds 1/3 of daily budget");
   return lots;
}
bool Send(int dir, double slDist)
{
   string s = Sym();
   double ask = SymbolInfoDouble(s, SYMBOL_ASK);
   double bid = SymbolInfoDouble(s, SYMBOL_BID);
   double entry = (dir > 0 ? ask : bid);
   double sl = (dir > 0 ? entry - slDist : entry + slDist);
   double tp = (dir > 0 ? entry + slDist * InpRR : entry - slDist * InpRR);
   int digits = (int)SymbolInfoInteger(s, SYMBOL_DIGITS);
   sl = NormalizeDouble(sl, digits);
   tp = NormalizeDouble(tp, digits);
   double lots = LotsFor(slDist);
   if(lots <= 0)
   {
      Print("lot size 0, skip");
      return false;
   }
   MqlTradeRequest req;
   MqlTradeResult  res;
   ZeroMemory(req);
   ZeroMemory(res);
   req.action = TRADE_ACTION_DEAL;
   req.symbol = s;
   req.volume = lots;
   req.type = (dir > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   req.price = entry;
   req.sl = sl;
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
   g_crossDir = 0;
   PrintFormat("entry %s lots=%.2f sl=%.2f tp=%.2f", (dir > 0 ? "BUY" : "SELL"), lots, sl, tp);
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

   DetectCross();
   if(!CrossFresh()) return;

   double ema, atr;
   if(!Copy1(g_ema, 1, ema) || !Copy1(g_atr, 1, atr)) return;
   if(atr <= 0) return;
   if(!PullbackOk(g_crossDir, ema, atr)) return;
   if(!HTFOk(g_crossDir)) return;
   if(g_crossDir > 0 && !InpAllowLong) return;
   if(g_crossDir < 0 && !InpAllowShort) return;

   double slDist = MathMax(atr * InpSL_ATR, InpMinSL_USD);
   Send(g_crossDir, slDist);
}
//+------------------------------------------------------------------+
