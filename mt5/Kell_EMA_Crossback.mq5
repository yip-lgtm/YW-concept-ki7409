//+------------------------------------------------------------------+
//|                                        Kell_EMA_Crossback.mq5    |
//|  Oliver Kell: EMA Crossback（重奪10/20後第一次回踩）              |
//+------------------------------------------------------------------+
#property copyright "YW Concept Research"
#property version   "1.00"
#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

input int    InpEMA10=10;
input int    InpEMA20=20;
input int    InpMaxWait=16;     // 重奪後最多等幾根回踩
input double InpTolATR=0.35;    // 回踩碰到均線的 ATR 容差
input bool   InpAllowLong=true;
input bool   InpAllowShort=true;
input bool   InpOnlyOnePos=true;
input double InpSL_Points=50;
input double InpRR=1.5;
input double InpLotSize=0.1;
input double InpRiskMoney=100;
input double InpDailyTP=200;
input double InpDailySL=600;
input bool   InpUseDailyLimit=true;
input int    InpMagic=1513;
input string InpComment="Kell-CB";

CTrade trade; CPositionInfo pos;
int h10,h20,hATR; datetime lastBar=0;
int waitDir=0, waitBars=0; bool armed=false;
double dayBal=0; int dayStamp=0;

int OnInit(){
  trade.SetExpertMagicNumber(InpMagic); trade.SetDeviationInPoints(20);
  trade.SetTypeFillingBySymbol(_Symbol);
  h10=iMA(_Symbol,PERIOD_CURRENT,InpEMA10,0,MODE_EMA,PRICE_CLOSE);
  h20=iMA(_Symbol,PERIOD_CURRENT,InpEMA20,0,MODE_EMA,PRICE_CLOSE);
  hATR=iATR(_Symbol,PERIOD_CURRENT,14);
  if(h10==INVALID_HANDLE||h20==INVALID_HANDLE||hATR==INVALID_HANDLE) return INIT_FAILED;
  dayBal=AccountInfoDouble(ACCOUNT_BALANCE); dayStamp=DayOfYear(); return INIT_SUCCEEDED;
}
void OnDeinit(const int r){ IndicatorRelease(h10); IndicatorRelease(h20); IndicatorRelease(hATR); }
int DayOfYear(){ MqlDateTime d; TimeToStruct(TimeCurrent(),d); return d.day_of_year+d.year*1000; }
void ResetDay(){ int d=DayOfYear(); if(d!=dayStamp){ dayStamp=d; dayBal=AccountInfoDouble(ACCOUNT_BALANCE);} }
bool DailyHit(){ if(!InpUseDailyLimit) return false; ResetDay(); double pnl=AccountInfoDouble(ACCOUNT_EQUITY)-dayBal; return (pnl>=InpDailyTP||pnl<=-InpDailySL); }
bool HasPos(){ for(int i=PositionsTotal()-1;i>=0;i--) if(pos.SelectByIndex(i)&&pos.Symbol()==_Symbol&&pos.Magic()==InpMagic) return true; return false; }
double CalcLot(double slPts){
  if(InpLotSize>0) return InpLotSize;
  double tv=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE), ts=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE), pt=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
  if(ts<=0||pt<=0) return SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
  double mpp=tv*(pt/ts); if(mpp<=0) return SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
  double lot=InpRiskMoney/(slPts*mpp);
  double mn=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN), mx=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX), st=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
  lot=MathFloor(lot/st)*st; if(lot<mn)lot=mn; if(lot>mx)lot=mx; return lot;
}
void Send(int dir,double sl,double tp){
  int dg=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
  double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK), bid=SymbolInfoDouble(_Symbol,SYMBOL_BID), pt=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
  double slPts=(dir==1?ask-sl:sl-bid)/pt; if(slPts<1) slPts=InpSL_Points;
  double lot=CalcLot(slPts);
  sl=NormalizeDouble(sl,dg); tp=NormalizeDouble(tp,dg);
  if(dir==1) trade.Buy(lot,_Symbol,ask,sl,tp,InpComment); else trade.Sell(lot,_Symbol,bid,sl,tp,InpComment);
}
void OnTick(){
  datetime t=iTime(_Symbol,PERIOD_CURRENT,0); if(t==lastBar) return; lastBar=t;
  if(DailyHit()) return; if(InpOnlyOnePos&&HasPos()) return;
  double e10[],e20[],atr[],c[],h[],l[];
  ArraySetAsSeries(e10,true); ArraySetAsSeries(e20,true); ArraySetAsSeries(atr,true);
  ArraySetAsSeries(c,true); ArraySetAsSeries(h,true); ArraySetAsSeries(l,true);
  if(CopyBuffer(h10,0,0,6,e10)<6) return;
  if(CopyBuffer(h20,0,0,6,e20)<6) return;
  if(CopyBuffer(hATR,0,0,6,atr)<6) return;
  if(CopyClose(_Symbol,PERIOD_CURRENT,0,6,c)<6) return;
  if(CopyHigh(_Symbol,PERIOD_CURRENT,0,6,h)<6) return;
  if(CopyLow(_Symbol,PERIOD_CURRENT,0,6,l)<6) return;
  bool above1=c[1]>e10[1]&&c[1]>e20[1];
  bool below1=c[1]<e10[1]&&c[1]<e20[1];
  bool above2=c[2]>e10[2]&&c[2]>e20[2];
  bool below2=c[2]<e10[2]&&c[2]<e20[2];
  if(InpAllowLong && !above2 && above1){ armed=true; waitDir=1; waitBars=0; }
  if(InpAllowShort && !below2 && below1){ armed=true; waitDir=-1; waitBars=0; }
  if(!armed) return;
  waitBars++;
  if(waitBars>InpMaxWait){ armed=false; waitDir=0; return; }
  if(waitDir==1 && (c[1]<e10[1] && c[1]<e20[1])){ armed=false; waitDir=0; return; }
  if(waitDir==-1 && (c[1]>e10[1] && c[1]>e20[1])){ armed=false; waitDir=0; return; }
  double band=atr[1]*InpTolATR;
  double ma=MathMin(e10[1],e20[1]);
  double mx=MathMax(e10[1],e20[1]);
  double pt=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
  if(waitDir==1 && l[1]<=mx+band && c[1]>=ma){
    double sl=MathMin(l[1],ma)-2*pt;
    if((c[1]-sl)/pt<InpSL_Points*0.3) sl=c[1]-InpSL_Points*pt;
    Send(1,sl,c[1]+(c[1]-sl)*InpRR);
    armed=false; waitDir=0;
  }
  if(waitDir==-1 && h[1]>=ma-band && c[1]<=mx){
    double sl=MathMax(h[1],mx)+2*pt;
    if((sl-c[1])/pt<InpSL_Points*0.3) sl=c[1]+InpSL_Points*pt;
    Send(-1,sl,c[1]-(sl-c[1])*InpRR);
    armed=false; waitDir=0;
  }
}
