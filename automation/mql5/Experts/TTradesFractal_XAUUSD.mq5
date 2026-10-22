//+------------------------------------------------------------------+
//|                                            TTradesFractal_XAUUSD.mq5 |
//|  TTrades ICT Fractal Model (H4 closure + M15 CISD) on XAUUSD      |
//|  Ported 1:1 from automation/scripts/ttrades_btc.py (repo: repo-yw)|
//|                                                                   |
//|  Rules:                                                          |
//|   1. H4 C2 closure (fallback C3 closure) -> swing + EQ           |
//|   2. M15 CISD: close breaks the opposing series' extreme open    |
//|   3. EQ respect: price on the correct side of the C2 wick EQ     |
//|   4. D1 trend filter: only take with EMA50/EMA20 alignment       |
//|   5. SL = swing +/- buffer x ATR ; TP1/TP2/TP3 = 1.0R/1.6R/2.6R   |
//|                                                                   |
//|  Risk: lot clamped 0.01-0.05, daily loss limit $100 (auto flat)  |
//|  NO repaint: every decision uses CLOSED bars only (shift>=1)      |
//+------------------------------------------------------------------+
#property copyright "TTrades Fractal - arena-fractal"
#property link      ""
#property version   "1.00"
#property description "TTrades ICT Fractal (H4 closure + M15 CISD) for XAUUSD. Daily SL $100, lot 0.01-0.05."

#include <Trade\Trade.mqh>

//--- ============================ 交易參數 ============================
input group "===== 交易 / 風控 ====="
input string   InpSymbol             = "XAUUSD";   // 交易品種（XAUUSD / GOLD / XAUUSD.m 均可）
input double   InpMinLot             = 0.01;       // 最小手數
input double   InpMaxLot             = 0.05;       // 最大手數
input double   InpRiskPerTradeUSD    = 50.0;       // 單筆風險上限 (USD)
input double   InpDailySLUSD         = 100.0;      // 每日虧損上限 (USD)，觸及即全平並鎖死當日
input int      InpMaxTradesPerDay    = 1;          // 每日最多開倉次數
input ulong    InpMagic              = 20261022;   // Magic number
input int      InpMaxSpreadPoints    = 60;         // 最高點差（gold 0.01 tick = $0.60）
input int      InpSlippagePoints     = 30;         // 允許滑點
input int      InpDayStartHour       = 0;          // 交易日開始（小時，server time）
input bool     InpCloseAtDayEnd      = false;      // 收市前自動全平
input bool     InpDailySLAllSymbols  = true;       // 每日 SL 計算是否包括其它品種
input bool     InpVerbose            = true;       // 打印每根 M15 嘅決策原因

//--- ============================ 模型參數 ============================
input group "===== 模型 (Fractal) ====="
input double   InpSlBufferATR        = 0.15;       // SL buffer = swing +/- buffer x ATR
input int      InpAtrPeriod          = 14;         // ATR 週期 (H1)
input bool     InpUseTrueATR         = false;      // false = range-ATR（同 Python backtest 一致）
input int      InpCisdLookback       = 8;          // M15 連續序列視窗
input double   InpTp1R               = 1.0;        // TP1 = x R
input double   InpTp2R               = 1.6;        // TP2 = x R
input double   InpTp3R               = 2.6;        // TP3 = x R（掛單 TP）
input double   InpTp1ClosePct        = 50.0;       // TP1 平倉比例 %
input double   InpTp2ClosePct        = 50.0;       // TP2 平倉比例 %（相對剩餘）
input bool     InpBreakevenAtTp1     = true;       // TP1 後移 SL 到保本
input double   InpBeBufferPrice      = 0.05;       // 保本緩衝（price 單位）
input int      InpMinD1Bars          = 60;         // D1 最少 bar 數（EMA50 預熱）

//--- ============================== 全域 ==============================
CTrade         trade;
string         g_sym        = "";
int            g_hEma50     = INVALID_HANDLE;
int            g_hEma20     = INVALID_HANDLE;
datetime       g_lastM15Bar = 0;
datetime       g_dayStamp   = 0;
bool           g_dayLocked  = false;
double         g_dayStartBalance = 0.0;

#define GV_PREFIX "TF_FX_"
#define GV_DAY   GV_PREFIX "daystamp"
#define GV_LOCK  GV_PREFIX "daylock"
#define GV_LASTBAR GV_PREFIX "lastm15"
#define GV_SWING GV_PREFIX "swing"

//--- ============================= 工具 ===============================
string GV(string name) { return(GV_PREFIX + name); }

void Log(string msg)
{
   if(InpVerbose) Print("[TF-Fractal] ", msg);
}

datetime DayStartTime()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   dt.hour = InpDayStartHour;
   dt.min  = 0;
   dt.sec  = 0;
   datetime d = StructToTime(dt);
   if(TimeCurrent() < d) d -= 86400;
   return(d);
}

//+--- 今日已實現盈虧（已平倉 deal 的 profit+swap+commission）
double DayRealized(string sym)
{
   double sum = 0.0;
   datetime d0 = DayStartTime();
   if(!HistorySelect(d0, TimeCurrent())) return(0.0);
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong t = HistoryDealGetTicket(i);
      if(t == 0) continue;
      if(!InpDailySLAllSymbols && HistoryDealGetString(t, DEAL_SYMBOL) != sym) continue;
      long entry = HistoryDealGetInteger(t, DEAL_ENTRY);
      if(entry == DEAL_ENTRY_IN) continue;           // 只算平倉
      sum += HistoryDealGetDouble(t, DEAL_PROFIT)
           + HistoryDealGetDouble(t, DEAL_SWAP)
           + HistoryDealGetDouble(t, DEAL_COMMISSION);
   }
   return(sum);
}

//+--- 今日已平倉次數（本 EA / 本品種）
int ClosedTradesToday(string sym)
{
   int n = 0;
   datetime d0 = DayStartTime();
   if(!HistorySelect(d0, TimeCurrent())) return(0);
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong t = HistoryDealGetTicket(i);
      if(t == 0) continue;
      if(HistoryDealGetString(t, DEAL_SYMBOL) != sym) continue;
      if(HistoryDealGetInteger(t, DEAL_MAGIC) != (long)InpMagic) continue;
      if(HistoryDealGetInteger(t, DEAL_ENTRY) == DEAL_ENTRY_IN) continue;
      n++;
   }
   return(n);
}

//+--- 今日總盈虧 = equity - 當日開始時的 balance
double DayPnL()
{
   return(AccountInfoDouble(ACCOUNT_EQUITY) - g_dayStartBalance);
}

//+--- 每 $1 價格變動、每 1 手值多少錢（XAUUSD: tick 0.01 / tickValue $1 -> $100 per $1 per lot）
double MoneyPerPointPerLot(string sym)
{
   double tv = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
   double ts = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   if(ts <= 0.0) return(0.0);
   return(tv / ts);
}

//+--- 手數正規化：落在 [InpMinLot, InpMaxLot] 同 broker 限制內
double NormVol(string sym, double lots)
{
   double step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   if(step <= 0.0) step = 0.01;
   if(vmin <= 0.0) vmin = 0.01;
   if(vmax <= 0.0) vmax = 100.0;
   double v = lots;
   v = MathMax(v, MathMax(vmin, InpMinLot));
   v = MathMin(v, MathMin(vmax, InpMaxLot));
   v = MathFloor(v / step) * step;
   v = MathMax(v, MathMax(vmin, InpMinLot));
   v = MathMin(v, MathMin(vmax, InpMaxLot));
   return(NormalizeDouble(v, 2));
}

//+--- range-ATR（Python 版口徑：H1 (High-Low) 平均）
double CalcRangeATR(string sym)
{
   double sum = 0.0;
   int n = 0;
   for(int s = 1; s <= InpAtrPeriod; s++)
   {
      double h = iHigh(sym, PERIOD_H1, s);
      double l = iLow(sym, PERIOD_H1, s);
      if(h > 0.0 && l > 0.0) { sum += (h - l); n++; }
   }
   return(n > 0 ? sum / n : 0.0);
}

//+--- 標準 ATR(14) on H1
double CalcTrueATR(string sym)
{
   double tr = 0.0, pc = 0.0;
   for(int s = 1; s <= InpAtrPeriod; s++)
   {
      double h = iHigh(sym, PERIOD_H1, s);
      double l = iLow(sym, PERIOD_H1, s);
      double c = iClose(sym, PERIOD_H1, s);
      double t;
      if(s == 1) t = h - l;
      else       t = MathMax(h - l, MathMax(MathAbs(h - pc), MathAbs(l - pc)));
      tr += t;
      pc = c;
   }
   return(InpAtrPeriod > 0 ? tr / InpAtrPeriod : 0.0);
}

double CalcATR(string sym)
{
   return(InpUseTrueATR ? CalcTrueATR(sym) : CalcRangeATR(sym));
}

//--- =========================== H4 Swing ============================
struct SwingInfo
{
   bool     valid;
   int      type;        // 1 = C2 closure, 2 = C3 closure
   int      dir;         // +1 long, -1 short
   double   swingLevel;
   double   eq;
   double   refClose;    // 入場參考價（H4 收盤）
   datetime id;          // swing 身份（c2 bar 時間），用嚟 dedupe
};

//+--- C1..C4 全部用「已收線」H4 bar（shift 1 = 最新已收線）
bool DetectSwing(string sym, SwingInfo &s)
{
   s.valid = false;
   s.type  = 0; s.dir = 0; s.swingLevel = 0; s.eq = 0; s.refClose = 0; s.id = 0;

   double h1 = iHigh(sym, PERIOD_H4, 3), l1 = iLow(sym, PERIOD_H4, 3), c1 = iClose(sym, PERIOD_H4, 3);
   double h2 = iHigh(sym, PERIOD_H4, 2), l2 = iLow(sym, PERIOD_H4, 2), c2 = iClose(sym, PERIOD_H4, 2);
   double h3 = iHigh(sym, PERIOD_H4, 1), l3 = iLow(sym, PERIOD_H4, 1), c3 = iClose(sym, PERIOD_H4, 1);

   //--- C2 closure: C2 掃過 C1 極值之後收回 C1 範圍內
   if(h2 > h1 && c2 < h1)                                   // bearish
   {
      s.valid = true; s.type = 1; s.dir = -1;
      s.swingLevel = h2;
      s.eq = (h2 + l2) / 2.0;
      s.refClose = c3;
      s.id = iTime(sym, PERIOD_H4, 2);
      return(true);
   }
   if(l2 < l1 && c2 > l1)                                   // bullish
   {
      s.valid = true; s.type = 1; s.dir = +1;
      s.swingLevel = l2;
      s.eq = (h2 + l2) / 2.0;
      s.refClose = c3;
      s.id = iTime(sym, PERIOD_H4, 2);
      return(true);
   }

   //--- C3 closure fallback: C2 冇返，C3 實體確認
   double h4 = iHigh(sym, PERIOD_H4, 4), l4 = iLow(sym, PERIOD_H4, 4), c4 = iClose(sym, PERIOD_H4, 4);
   double o3 = iOpen(sym, PERIOD_H4, 2), c3b = iClose(sym, PERIOD_H4, 2);
   double h3b = iHigh(sym, PERIOD_H4, 2), l3b = iLow(sym, PERIOD_H4, 2);
   double body = MathAbs(c3b - o3);
   double rng  = h3b - l3b;
   if(rng <= 0.0 || body / rng < 0.55) return(false);

   if(h3 > h4 && c3b >= h4 && c3b < o3)                      // bearish
   {
      s.valid = true; s.type = 2; s.dir = -1;
      s.swingLevel = h3;
      s.eq = (h3 + l3) / 2.0;
      s.refClose = c4;
      s.id = iTime(sym, PERIOD_H4, 3);
      return(true);
   }
   if(l3 < l4 && c3b <= l4 && c3b > o3)                      // bullish
   {
      s.valid = true; s.type = 2; s.dir = +1;
      s.swingLevel = l3;
      s.eq = (h3 + l3) / 2.0;
      s.refClose = c4;
      s.id = iTime(sym, PERIOD_H4, 3);
      return(true);
   }
   return(false);
}

//--- ========================== M15 CISD ============================
struct Series { int dir; int start; int end; };   // dir: +1 bull, -1 bear

//+--- 由舊到新掃 M15，砌連續同向序列（doji 不切斷序列，同 Python 版）
int BuildSeries(string sym, int count, Series &out[])
{
   ArrayResize(out, 0);
   int cur = 0, start = 0;
   for(int k = 0; k < count; k++)
   {
      int    shift = count - k;                  // k=0 最舊, k=count-1 最新已收線
      double o = iOpen(sym, PERIOD_M15, shift);
      double c = iClose(sym, PERIOD_M15, shift);
      int d = 0;
      if(c > o) d = +1;
      else if(c < o) d = -1;
      if(d == 0) continue;
      if(d != cur)
      {
         if(cur != 0)
         {
            Series s; s.dir = cur; s.start = start; s.end = k - 1;
            int n = ArraySize(out);
            ArrayResize(out, n + 1);
            out[n] = s;
         }
         cur = d;
         start = k;
      }
   }
   if(cur != 0)
   {
      Series s; s.dir = cur; s.start = start; s.end = count - 1;
      int n = ArraySize(out);
      ArrayResize(out, n + 1);
      out[n] = s;
   }
   return(ArraySize(out));
}

//+--- CISD: 收盤價突破對向序列嘅極值開盤價
//    tradeDir: +1 long (要突破 bear 序列), -1 short (要突破 bull 序列)
bool CheckCISD(string sym, int tradeDir, double &extreme, int &seriesLen)
{
   extreme = 0.0; seriesLen = 0;
   Series s[];
   int n = BuildSeries(sym, InpCisdLookback, s);
   if(n == 0) return(false);

   int target = (tradeDir == -1) ? +1 : -1;      // short 要搵 bull 序列, long 要搵 bear 序列
   int idx = -1;
   for(int i = n - 1; i >= 0; i--)
      if(s[i].dir == target) { idx = i; break; }
   if(idx < 0) return(false);

   double e = (target == +1) ? 1.0e100 : -1.0e100;
   for(int k = s[idx].start; k <= s[idx].end; k++)
   {
      double o = iOpen(sym, PERIOD_M15, InpCisdLookback - k);
      if(target == +1) e = MathMin(e, o);
      else             e = MathMax(e, o);
   }
   extreme   = e;
   seriesLen = s[idx].end - s[idx].start + 1;

   double lastClose = iClose(sym, PERIOD_M15, 1);
   if(tradeDir == -1) return(lastClose < e);
   return(lastClose > e);
}

//+--- EQ 守規：最新已收線 M15 收盤價要喺 EQ 嘅正確一邊
bool EQRespected(string sym, SwingInfo &s)
{
   double last = iClose(sym, PERIOD_M15, 1);
   if(s.dir == -1) return(last <= s.eq);
   return(last >= s.eq);
}

//+--- D1 趨勢：close vs EMA50 / EMA20（用已收線 D1 bar）
bool D1Aligned(string sym, int tradeDir, string &trendName)
{
   trendName = "unknown";
   if(iBars(sym, PERIOD_D1) < InpMinD1Bars) return(false);
   double e50[1], e20[1];
   if(CopyBuffer(g_hEma50, 0, 1, 1, e50) <= 0) return(false);
   if(CopyBuffer(g_hEma20, 0, 1, 1, e20) <= 0) return(false);
   double c = iClose(sym, PERIOD_D1, 1);
   if(c > e50[0] && e20[0] > e50[0])      trendName = "uptrend";
   else if(c < e50[0] && e20[0] < e50[0]) trendName = "downtrend";
   else                                   trendName = "ranging";
   if(tradeDir == +1) return(trendName == "uptrend");
   return(trendName == "downtrend");
}

//--- ========================= 倉位狀態 =============================
void SaveState(ulong ticket, double entry, double risk, double t1, double t2, double t3, double vol)
{
   string k = GV_PREFIX + "p" + IntegerToString((long)ticket) + "_";
   GlobalVariableSet(k + "entry", entry);
   GlobalVariableSet(k + "risk",  risk);
   GlobalVariableSet(k + "t1",    t1);
   GlobalVariableSet(k + "t2",    t2);
   GlobalVariableSet(k + "t3",    t3);
   GlobalVariableSet(k + "vol",   vol);
   GlobalVariableSet(k + "tp1",   0);
   GlobalVariableSet(k + "tp2",   0);
}

void LoadState(ulong ticket, double &entry, double &risk, double &t1, double &t2, double &t3, double &vol, bool &tp1, bool &tp2)
{
   string k = GV_PREFIX + "p" + IntegerToString((long)ticket) + "_";
   entry = GlobalVariableGet(k + "entry");
   risk  = GlobalVariableGet(k + "risk");
   t1    = GlobalVariableGet(k + "t1");
   t2    = GlobalVariableGet(k + "t2");
   t3    = GlobalVariableGet(k + "t3");
   vol   = GlobalVariableGet(k + "vol");
   tp1   = (GlobalVariableGet(k + "tp1") > 0.5);
   tp2   = (GlobalVariableGet(k + "tp2") > 0.5);
}

void DropState(ulong ticket)
{
   string k = GV_PREFIX + "p" + IntegerToString((long)ticket) + "_";
   GlobalVariableDel(k + "entry");
   GlobalVariableDel(k + "risk");
   GlobalVariableDel(k + "t1");
   GlobalVariableDel(k + "t2");
   GlobalVariableDel(k + "t3");
   GlobalVariableDel(k + "vol");
   GlobalVariableDel(k + "tp1");
   GlobalVariableDel(k + "tp2");
}

//--- ========================== 交易動作 ============================
bool HasOurPosition(string sym)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != sym) continue;
      if(PositionGetInteger(POSITION_MAGIC) != (long)InpMagic) continue;
      return(true);
   }
   return(false);
}

//+--- 攞返我哋喺呢個品種嘅持倉 ticket（netting 帳戶下 order ticket ≠ position ticket）
ulong OurTicket(string sym)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != sym) continue;
      if(PositionGetInteger(POSITION_MAGIC) != (long)InpMagic) continue;
      return(t);
   }
   return(0);
}

void CloseOurPositions(string sym)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(!InpDailySLAllSymbols && PositionGetString(POSITION_SYMBOL) != sym) continue;
      if(PositionGetInteger(POSITION_MAGIC) != (long)InpMagic) continue;
      trade.PositionClose(t);
   }
}

void TryEntry(string sym)
{
   //--- 每日上限
   if(g_dayLocked) { Log("daily lock on - no new trades today"); return; }
   if(ClosedTradesToday(sym) >= InpMaxTradesPerDay) { Log("max trades/day reached"); return; }
   if(HasOurPosition(sym)) return;

   //--- 點差
   double spread = (double)SymbolInfoInteger(sym, SYMBOL_SPREAD);
   if(InpMaxSpreadPoints > 0 && spread > InpMaxSpreadPoints)
   {
      Log(StringFormat("spread too wide: %d > %d", (int)spread, InpMaxSpreadPoints));
      return;
   }

   //--- 1. H4 closure
   SwingInfo s;
   if(!DetectSwing(sym, s)) { Log("Fractal quiet: no H4 C2/C3 closure"); return; }

   //--- swing dedupe：同一個 swing 只做一次
   datetime lastSwing = (datetime)GlobalVariableGet(GV_SWING);
   if(s.id > 0 && s.id == lastSwing) { Log("this H4 swing already traded"); return; }

   //--- 2. M15 CISD
   double extreme; int slen;
   if(!CheckCISD(sym, s.dir, extreme, slen))
   {
      Log(StringFormat("no M15 CISD (%s)", s.dir == -1 ? "need break bull open" : "need break bear open"));
      return;
   }

   //--- 3. EQ 守規
   if(!EQRespected(sym, s))
   {
      Log(StringFormat("EQ not respected (close %.2f vs EQ %.2f)", iClose(sym, PERIOD_M15, 1), s.eq));
      return;
   }

   //--- 4. D1 趨勢
   string trend;
   if(!D1Aligned(sym, s.dir, trend))
   {
      Log(StringFormat("D1 %s not aligned with %s", trend, s.dir == 1 ? "long" : "short"));
      return;
   }

   //--- ATR + 價位
   double atr = CalcATR(sym);
   if(atr <= 0.0) { Log("no ATR"); return; }
   double buffer = atr * InpSlBufferATR;
   double sl = (s.dir == -1) ? s.swingLevel + buffer : s.swingLevel - buffer;

   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   if(ask <= 0.0 || bid <= 0.0) return;
   double entry = (s.dir == +1) ? ask : bid;

   double riskDist = MathAbs(entry - sl);
   if(riskDist <= 0.0) return;

   //--- 最低停車距離
   double stopsLevel = (double)SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL) * SymbolInfoDouble(sym, SYMBOL_POINT);
   if(riskDist < stopsLevel) { Log("stop too close to market (stops level)"); return; }

   //--- 手數：風險 sizing，之後夾落 0.01-0.05
   double mpp = MoneyPerPointPerLot(sym);
   if(mpp <= 0.0) { Log("bad tick spec"); return; }
   double riskPerLot = riskDist * mpp;
   double lots = InpRiskPerTradeUSD / riskPerLot;
   lots = NormVol(sym, lots);

   //--- 每日剩餘額度
   double dayPnl = DayPnL();
   double remaining = InpDailySLUSD + dayPnl;          // dayPnl 為負
   if(remaining <= 0.0) { LockDay(sym); return; }
   double riskAtLot = lots * riskPerLot;
   if(riskAtLot > remaining)
   {
      // 收細手數都仲超額 -> 今日唔做
      Log(StringFormat("skip: risk $%.2f exceeds remaining daily budget $%.2f", riskAtLot, remaining));
      return;
   }

   //--- TP
   double t1 = entry + s.dir * riskDist * InpTp1R;
   double t2 = entry + s.dir * riskDist * InpTp2R;
   double t3 = entry + s.dir * riskDist * InpTp3R;
   int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   sl  = NormalizeDouble(sl,  digits);
   t1  = NormalizeDouble(t1,  digits);
   t2  = NormalizeDouble(t2,  digits);
   t3  = NormalizeDouble(t3,  digits);

   //--- 下單
   bool ok = false;
   if(s.dir == +1) ok = trade.Buy(lots, sym, 0.0, sl, t3, "TF-Fractal long H4 C2/C3");
   else            ok = trade.Sell(lots, sym, 0.0, sl, t3, "TF-Fractal short H4 C2/C3");

   if(!ok)
   {
      Log(StringFormat("order failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      return;
   }

   ulong ticket = OurTicket(sym);
   if(ticket == 0) ticket = trade.ResultOrder();
   double fill = trade.ResultPrice();
   if(fill <= 0.0) fill = entry;
   double fillVol = trade.ResultVolume();
   if(fillVol <= 0.0) fillVol = lots;
   SaveState(ticket, fill, MathAbs(fill - sl), t1, t2, t3, fillVol);
   GlobalVariableSet(GV_SWING, (double)s.id);

   Log(StringFormat("ENTRY %s %.2f lots @ %.2f  SL %.2f  TP1 %.2f TP2 %.2f TP3 %.2f  risk $%.2f (1R=%.2f)  [H4 %s, CISD %d-bar, D1 %s]",
                    s.dir == +1 ? "LONG" : "SHORT", lots, fill, sl, t1, t2, t3,
                    lots * riskDist * mpp, riskDist,
                    s.type == 1 ? "C2" : "C3", slen, trend));
}

//--- 每日 SL 觸及：全平 + 鎖死當日
void LockDay(string sym)
{
   if(g_dayLocked) return;
   g_dayLocked = true;
   GlobalVariableSet(GV_LOCK, 1);
   Log(StringFormat("DAILY SL BREACH: day P&L $%.2f -> close all & lock for today", DayPnL()));
   CloseOurPositions(sym);
}

//--- TP1 / TP2 部份平倉 + 保本
void ManagePositions(string sym)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != sym) continue;
      if(PositionGetInteger(POSITION_MAGIC) != (long)InpMagic) continue;

      double entry, risk, t1, t2, t3, vol0;
      bool tp1done, tp2done;
      LoadState(ticket, entry, risk, t1, t2, t3, vol0, tp1done, tp2done);
      if(entry <= 0.0 || risk <= 0.0) continue;

      long   ptype = PositionGetInteger(POSITION_TYPE);
      double vol   = PositionGetDouble(POSITION_VOLUME);
      if(vol <= 0.0) continue;
      double bid   = SymbolInfoDouble(sym, SYMBOL_BID);
      double ask   = SymbolInfoDouble(sym, SYMBOL_ASK);
      int    digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
      double vmin   = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
      double curSL  = PositionGetDouble(POSITION_SL);
      double curTP  = PositionGetDouble(POSITION_TP);

      if(!tp1done && t1 > 0.0)
      {
         bool hit = (ptype == POSITION_TYPE_BUY) ? (bid >= t1) : (ask <= t1);
         if(hit)
         {
            double closeVol = NormalizeDouble(vol * InpTp1ClosePct / 100.0, 2);
            if(vol - closeVol < vmin) closeVol = vol;          // 剩太少就全平
            if(trade.PositionClosePartial(ticket, closeVol))
            {
               tp1done = true;
               GlobalVariableSet(GV_PREFIX + "p" + IntegerToString((long)ticket) + "_tp1", 1);
               if(InpBreakevenAtTp1)
               {
                  double be = (ptype == POSITION_TYPE_BUY) ? entry + InpBeBufferPrice : entry - InpBeBufferPrice;
                  be = NormalizeDouble(be, digits);
                  bool better = (ptype == POSITION_TYPE_BUY) ? (be > curSL) : (be < curSL);
                  if(better) trade.PositionModify(ticket, be, curTP);
               }
               Log(StringFormat("TP1 hit @ %.2f - closed %.2f lot(s), SL -> BE", t1, closeVol));
            }
            else Log(StringFormat("TP1 partial close failed: %d", trade.ResultRetcode()));
         }
      }
      else if(tp1done && !tp2done && t2 > 0.0)
      {
         bool hit = (ptype == POSITION_TYPE_BUY) ? (bid >= t2) : (ask <= t2);
         if(hit)
         {
            double closeVol = NormalizeDouble(vol * InpTp2ClosePct / 100.0, 2);
            if(vol - closeVol < vmin) closeVol = vol;
            if(trade.PositionClosePartial(ticket, closeVol))
            {
               tp2done = true;
               GlobalVariableSet(GV_PREFIX + "p" + IntegerToString((long)ticket) + "_tp2", 1);
               Log(StringFormat("TP2 hit @ %.2f - closed %.2f lot(s)", t2, closeVol));
            }
         }
      }
   }
}

//--- 每日狀態更新（跨日重置 + 計算當日 P&L）
void UpdateDayState(string sym)
{
   datetime d0 = DayStartTime();
   if(g_dayStamp != d0)
   {
      g_dayStamp = d0;
      g_dayLocked = false;
      GlobalVariableSet(GV_DAY, (double)d0);
      GlobalVariableDel(GV_LOCK);
      g_dayStartBalance = AccountInfoDouble(ACCOUNT_BALANCE) - DayRealized(sym);
      Log(StringFormat("new trading day %s - start balance $%.2f", TimeToString(d0, TIME_DATE | TIME_MINUTES), g_dayStartBalance));
   }
   else if(g_dayStartBalance == 0.0)
   {
      g_dayStartBalance = AccountInfoDouble(ACCOUNT_BALANCE) - DayRealized(sym);
   }

   if(g_dayLocked) return;

   double pnl = DayPnL();
   if(pnl <= -InpDailySLUSD)
   {
      LockDay(sym);
   }
}

//--- 收市前全平
void CheckDayEndFlat(string sym)
{
   if(!InpCloseAtDayEnd) return;
   datetime d0 = DayStartTime();
   datetime nxt = d0 + 86400;
   if(nxt - TimeCurrent() <= 300) CloseOurPositions(sym);
}

//--- ============================== 事件 =============================
int OnInit()
{
   g_sym = InpSymbol;
   if(!SymbolSelect(g_sym, true))
   {
      // 自動搵 XAU / GOLD
      int total = SymbolsTotal(true);
      for(int i = 0; i < total; i++)
      {
         string nm = SymbolName(i, true);
         if(StringFind(nm, "XAU") >= 0 || StringFind(nm, "GOLD") >= 0)
         {
            g_sym = nm;
            break;
         }
      }
      if(!SymbolSelect(g_sym, true))
      {
         Print("[TF-Fractal] symbol not found: ", InpSymbol);
         return(INIT_FAILED);
      }
      Print("[TF-Fractal] using symbol: ", g_sym);
   }

   g_hEma50 = iMA(g_sym, PERIOD_D1, 50, 0, MODE_EMA, PRICE_CLOSE);
   g_hEma20 = iMA(g_sym, PERIOD_D1, 20, 0, MODE_EMA, PRICE_CLOSE);
   if(g_hEma50 == INVALID_HANDLE || g_hEma20 == INVALID_HANDLE)
   {
      Print("[TF-Fractal] failed to create EMA handles");
      return(INIT_FAILED);
   }

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetTypeFillingBySymbol(g_sym);

   g_dayStamp = (datetime)GlobalVariableGet(GV_DAY);
   g_dayLocked = (GlobalVariableCheck(GV_LOCK) && GlobalVariableGet(GV_LOCK) > 0.5
                  && (datetime)GlobalVariableGet(GV_DAY) == DayStartTime());
   g_lastM15Bar = (datetime)GlobalVariableGet(GV_LASTBAR);
   g_dayStartBalance = AccountInfoDouble(ACCOUNT_BALANCE) - DayRealized(g_sym);

   EventSetTimer(15);
   Print("[TF-Fractal] init OK. symbol=", g_sym, " tick_value=", SymbolInfoDouble(g_sym, SYMBOL_TRADE_TICK_VALUE),
         " tick_size=", SymbolInfoDouble(g_sym, SYMBOL_TRADE_TICK_SIZE),
         " minlot=", SymbolInfoDouble(g_sym, SYMBOL_VOLUME_MIN),
         " step=", SymbolInfoDouble(g_sym, SYMBOL_VOLUME_STEP));
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   if(g_hEma50 != INVALID_HANDLE) IndicatorRelease(g_hEma50);
   if(g_hEma20 != INVALID_HANDLE) IndicatorRelease(g_hEma20);
}

void OnTick()
{
   UpdateDayState(g_sym);
   ManagePositions(g_sym);
   CheckDayEndFlat(g_sym);
}

void OnTimer()
{
   UpdateDayState(g_sym);
   ManagePositions(g_sym);
   CheckDayEndFlat(g_sym);

   //--- 新 M15 bar 先做決策（唔喺 bar 內反覆入場）
   datetime bar = iTime(g_sym, PERIOD_M15, 0);
   if(bar == 0 || bar == g_lastM15Bar) return;
   g_lastM15Bar = bar;
   GlobalVariableSet(GV_LASTBAR, (double)bar);

   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED)
      || !AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
   {
      Log("trading disabled for this account/terminal");
      return;
   }

   TryEntry(g_sym);
}
//+------------------------------------------------------------------+
