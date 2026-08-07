//+------------------------------------------------------------------+
//|                                          YW_50_20_Pullback.mq5   |
//|  YW Concept 50/20 (EMA20 + SMA50) + Pullback Entry               |
//|  RR 1:1.5 | 種田流兼容                                            |
//+------------------------------------------------------------------+
#property copyright "YW Concept Research"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

//--- Input parameters
input group "=== 均線設定 ==="
input int      InpEMAPeriod     = 20;      // EMA 週期
input int      InpSMAPeriod     = 50;      // SMA 週期

input group "=== 進場設定 ==="
input int      InpMaxWaitBars   = 24;      // 交叉後最多等幾根K線出現回踩
input double   InpPullbackTol   = 0.0008;  // 回踩容差 (相對EMA，0.0008≈0.08%)
input bool     InpOnlyOnePos    = true;    // 同時只允許一單

input group "=== 風控 (RR 1:1.5) ==="
input double   InpSL_Points     = 50;      // 止損點數 (MNQ建議50; 黃金依點值調整)
input double   InpRR            = 1.5;     // 盈虫比 (TP = SL × RR)
input double   InpLotSize       = 0.1;     // 固定手數 (0=依風險金額計算)
input double   InpRiskMoney     = 100.0;   // 單筆風險金額 (InpLotSize=0時使用)

input group "=== 種田流 ==="
input double   InpDailyTP       = 200.0;   // 當日盈利達此金額停手
input double   InpDailySL       = 600.0;   // 當日虫損達此金額停手
input bool     InpUseDailyLimit = true;    // 啟用每日停利/停損

input group "=== 其他 ==="
input int      InpMagic         = 5020;    // Magic Number
input string   InpComment       = "YW50/20"; // 註解

//--- Globals
CTrade         trade;
CPositionInfo  pos;
int            hEMA, hSMA;
datetime       lastBarTime = 0;
int            crossBar = -1;
int            crossDir = 0;
bool           waitingPullback = false;
double         dayStartBalance = 0;
int            dayStamp = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(20);
   trade.SetTypeFillingBySymbol(_Symbol);

   hEMA = iMA(_Symbol, PERIOD_CURRENT, InpEMAPeriod, 0, MODE_EMA, PRICE_CLOSE);
   hSMA = iMA(_Symbol, PERIOD_CURRENT, InpSMAPeriod, 0, MODE_SMA, PRICE_CLOSE);
   if(hEMA == INVALID_HANDLE || hSMA == INVALID_HANDLE)
   {
      Print("均線指標建立失敗");
      return INIT_FAILED;
   }

   dayStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   dayStamp = DayOfYear();
   Print("YW 50/20 Pullback EA 啟動 | SL=", InpSL_Points, " pts | RR=", InpRR);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(hEMA != INVALID_HANDLE) IndicatorRelease(hEMA);
   if(hSMA != INVALID_HANDLE) IndicatorRelease(hSMA);
}

//+------------------------------------------------------------------+
int DayOfYear()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   return dt.day_of_year + dt.year * 1000;
}

//+------------------------------------------------------------------+
void ResetDayIfNeeded()
{
   int d = DayOfYear();
   if(d != dayStamp)
   {
      dayStamp = d;
      dayStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
      Print("新交易日，重置日結基準 Balance=", dayStartBalance);
   }
}

//+------------------------------------------------------------------+
bool DailyLimitHit()
{
   if(!InpUseDailyLimit) return false;
   ResetDayIfNeeded();
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double pnl = equity - dayStartBalance;
   if(pnl >= InpDailyTP)
   {
      Print("日停利觸發 +", pnl);
      return true;
   }
   if(pnl <= -InpDailySL)
   {
      Print("日停損觸發 ", pnl);
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
bool HasOurPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(pos.SelectByIndex(i) && pos.Symbol() == _Symbol && pos.Magic() == InpMagic)
         return true;
   }
   return false;
}

//+------------------------------------------------------------------+
double CalcLot(double slPoints)
{
   if(InpLotSize > 0) return InpLotSize;

   double tickVal = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(tickSize <= 0 || point <= 0) return SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);

   double moneyPerPoint = tickVal * (point / tickSize);
   if(moneyPerPoint <= 0) return SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);

   double lot = InpRiskMoney / (slPoints * moneyPerPoint);

   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   lot = MathFloor(lot / step) * step;
   if(lot < minLot) lot = minLot;
   if(lot > maxLot) lot = maxLot;
   return lot;
}

//+------------------------------------------------------------------+
void OnTick()
{
   datetime t = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(t == lastBarTime) return;
   lastBarTime = t;

   if(DailyLimitHit()) return;
   if(InpOnlyOnePos && HasOurPosition()) return;

   double ema[], sma[], close[], high[], low[];
   ArraySetAsSeries(ema, true);
   ArraySetAsSeries(sma, true);
   ArraySetAsSeries(close, true);
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);

   if(CopyBuffer(hEMA, 0, 0, InpMaxWaitBars + 5, ema) < InpMaxWaitBars + 5) return;
   if(CopyBuffer(hSMA, 0, 0, InpMaxWaitBars + 5, sma) < InpMaxWaitBars + 5) return;
   if(CopyClose(_Symbol, PERIOD_CURRENT, 0, InpMaxWaitBars + 5, close) < InpMaxWaitBars + 5) return;
   if(CopyHigh(_Symbol, PERIOD_CURRENT, 0, InpMaxWaitBars + 5, high) < InpMaxWaitBars + 5) return;
   if(CopyLow(_Symbol, PERIOD_CURRENT, 0, InpMaxWaitBars + 5, low) < InpMaxWaitBars + 5) return;

   if(ema[2] <= sma[2] && ema[1] > sma[1])
   {
      crossBar = 1;
      crossDir = 1;
      waitingPullback = true;
      Print("金叉 @ ", TimeToString(iTime(_Symbol, PERIOD_CURRENT, 1)));
   }
   else if(ema[2] >= sma[2] && ema[1] < sma[1])
   {
      crossBar = 1;
      crossDir = -1;
      waitingPullback = true;
      Print("死叉 @ ", TimeToString(iTime(_Symbol, PERIOD_CURRENT, 1)));
   }

   if(!waitingPullback || crossDir == 0) return;

   bool found = false;
   double entryPrice = 0;

   for(int i = 1; i <= InpMaxWaitBars; i++)
   {
      if(crossDir == 1 && ema[i] < sma[i]) { waitingPullback = false; break; }
      if(crossDir == -1 && ema[i] > sma[i]) { waitingPullback = false; break; }

      if(crossDir == 1)
      {
         if(low[i] <= ema[i] * (1.0 + InpPullbackTol) && close[i] >= ema[i])
         {
            if(i == 1)
            {
               found = true;
               entryPrice = close[i];
            }
            break;
         }
      }
      else
      {
         if(high[i] >= ema[i] * (1.0 - InpPullbackTol) && close[i] <= ema[i])
         {
            if(i == 1)
            {
               found = true;
               entryPrice = close[i];
            }
            break;
         }
      }
   }

   static int waitCount = 0;
   if(waitingPullback && !found)
   {
      waitCount++;
      if(waitCount > InpMaxWaitBars)
      {
         waitingPullback = false;
         waitCount = 0;
         crossDir = 0;
      }
      return;
   }
   waitCount = 0;

   if(!found) return;

   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double slDist = InpSL_Points * point;
   double tpDist = slDist * InpRR;
   double lot = CalcLot(InpSL_Points);

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   if(crossDir == 1)
   {
      double sl = NormalizeDouble(ask - slDist, digits);
      double tp = NormalizeDouble(ask + tpDist, digits);
      if(trade.Buy(lot, _Symbol, ask, sl, tp, InpComment))
         Print("多單進場 Lot=", lot, " SL=", sl, " TP=", tp);
      else
         Print("多單失敗: ", trade.ResultRetcodeDescription());
   }
   else if(crossDir == -1)
   {
      double sl = NormalizeDouble(bid + slDist, digits);
      double tp = NormalizeDouble(bid - tpDist, digits);
      if(trade.Sell(lot, _Symbol, bid, sl, tp, InpComment))
         Print("空單進場 Lot=", lot, " SL=", sl, " TP=", tp);
      else
         Print("空單失敗: ", trade.ResultRetcodeDescription());
   }

   waitingPullback = false;
   crossDir = 0;
}

//+------------------------------------------------------------------+
