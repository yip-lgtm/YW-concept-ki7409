//+------------------------------------------------------------------+
//|                                    Kell_ReversalExtension.mq5    |
//|  Oliver Kell: Reversal Extension (HTF support + LTF 遠離10EMA)   |
//+------------------------------------------------------------------+
#property copyright "YW Concept Research"
#property version   "1.00"
#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

input int    InpEMA10=10;
input int    InpEMA20=20;
input int    InpEMA50=50;
input double InpExtATR=1.2;     // 遠離10EMA最少 ATR 倍數
input bool   InpNeedHTF=true;   // 要求靠近 EMA50（HTF支撐代理）
input double InpHTFTolATR=1.5;  // 距EMA50 容差（ATR倍）
input bool   InpAllowLong=true;
input bool   InpAllowShort=true;
input bool   InpOnlyOnePos=true;
input double InpSL_Points=50;
input double InpRR=1.5;
input bool   InpTP_EMA20=false; // true=TP用20EMA，false=固定RR
input double InpLotSize=0.1;
input double InpRiskMoney=100;
input double InpDailyTP=200;
input double InpDailySL=600;
input bool   InpUseDailyLimit=true;
input int    InpMagic=1511;
input string InpComment="Kell-RE";

CTrade trade; CPositionInfo pos;
int h10,h20,h50,hATR; datetime lastBar=0;
double dayBal=0; int dayStamp=0;

int OnInit(){
  trade.SetExpertMagicNumber(InpMagic);
  trade.SetDeviationInPoints(20);
  trade.SetTypeFillingBySymbol(_Symbol);
  h10=iMA(_Symbol,PERIOD_CURRENT,InpEMA10,0,MODE_EMA,PRICE_CLOSE);
  h20=iMA(_Symbol,PERIOD_CURRENT,InpEMA20,0,MODE_EMA,PRICE_CLOSE);
  h50=iMA(_Symbol,PERIOD_CURRENT,InpEMA50,0,MODE_EMA,PRICE_CLOSE);
  hATR=iATR(_Symbol,PERIOD_CURRENT,14);
  if(h10==INVALID_HANDLE||h20==INVALID_HANDLE||h50==INVALID_HANDLE||hATR==INVALID_HANDLE) return INIT_FAILED;
  dayBal=AccountInfoDouble(ACCOUNT_BALANCE); dayStamp=DayOfYear();
  return INIT_SUCCEEDED;
}
void OnDeinit(const int r){
  IndicatorRelease(h10); IndicatorRelease(h20); IndicatorRelease(h50); IndicatorRelease(hATR);
}
int DayOfYear(){ MqlDateTime d; TimeToStruct(TimeCurrent(),d); return d.day_of_year+d.year*1000; }
void ResetDay(){ int d=DayOfYear(); if(d!=dayStamp){ dayStamp=d; dayBal=AccountInfoDouble(ACCOUNT_BALANCE);} }
bool DailyHit(){
  if(!InpUseDailyLimit) return false; ResetDay();
  double pnl=AccountInfoDouble(ACCOUNT_EQUITY)-dayBal;
  return (pnl>=InpDailyTP || pnl<=-InpDailySL);
}
bool HasPos(){
  for(int i=PositionsTotal()-1;i>=0;i--) if(pos.SelectByIndex(i)&&pos.Symbol()==_Symbol&&pos.Magic()==InpMagic) return true;
  return false;
}
double CalcLot(double slPts){
  if(InpLotSize>0) return InpLotSize;
  double tv=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE);
  double ts=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
  double pt=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
  if(ts<=0||pt<=0) return SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
  double mpp=tv*(pt/ts); if(mpp<=0) return SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
  double lot=InpRiskMoney/(slPts*mpp);
  double mn=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN), mx=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX), st=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
  lot=MathFloor(lot/st)*st; if(lot<mn) lot=mn; if(lot>mx) lot=mx; return lot;
}
void Send(int dir,double slPrice,double tpPrice){
  int dg=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
  double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK), bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
  double slDist=(dir==1? ask-slPrice : slPrice-bid);
  double pt=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
  double slPts=slDist/pt; if(slPts<1) slPts=InpSL_Points;
  double lot=CalcLot(slPts);
  slPrice=NormalizeDouble(slPrice,dg); tpPrice=NormalizeDouble(tpPrice,dg);
  if(dir==1) trade.Buy(lot,_Symbol,ask,slPrice,tpPrice,InpComment);
  else trade.Sell(lot,_Symbol,bid,slPrice,tpPrice,InpComment);
}
void OnTick(){
  datetime t=iTime(_Symbol,PERIOD_CURRENT,0); if(t==lastBar) return; lastBar=t;
  if(DailyHit()) return; if(InpOnlyOnePos&&HasPos()) return;
  double e10[],e20[],e50[],atr[],c[],h[],l[],o[];
  ArraySetAsSeries(e10,true); ArraySetAsSeries(e20,true); ArraySetAsSeries(e50,true);
  ArraySetAsSeries(atr,true); ArraySetAsSeries(c,true); ArraySetAsSeries(h,true);
  ArraySetAsSeries(l,true); ArraySetAsSeries(o,true);
  if(CopyBuffer(h10,0,0,6,e10)<6) return;
  if(CopyBuffer(h20,0,0,6,e20)<6) return;
  if(CopyBuffer(h50,0,0,6,e50)<6) return;
  if(CopyBuffer(hATR,0,0,6,atr)<6) return;
  if(CopyClose(_Symbol,PERIOD_CURRENT,0,6,c)<6) return;
  if(CopyHigh(_Symbol,PERIOD_CURRENT,0,6,h)<6) return;
  if(CopyLow(_Symbol,PERIOD_CURRENT,0,6,l)<6) return;
  if(CopyOpen(_Symbol,PERIOD_CURRENT,0,6,o)<6) return;
  double ext=atr[1]*InpExtATR;
  bool revUp=(c[1]>o[1] && c[1]>=(h[1]+l[1])/2.0);
  bool revDn=(c[1]<o[1] && c[1]<=(h[1]+l[1])/2.0);
  bool near50=MathAbs(c[1]-e50[1])<=atr[1]*InpHTFTolATR;
  int dg=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
  double pt=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
  if(InpAllowLong && revUp && (e10[1]-l[1])>=ext){
    if(InpNeedHTF && !near50 && c[1]>e50[1]+atr[1]) { /* too far above 50, skip */ }
    else{
      double sl=l[1]-pt*2;
      if((c[1]-sl)/pt < InpSL_Points*0.3) sl=c[1]-InpSL_Points*pt;
      double tp=InpTP_EMA20? e20[1] : c[1]+(c[1]-sl)*InpRR;
      if(tp>c[1]) Send(1,sl,tp);
    }
  }
  if(InpAllowShort && revDn && (h[1]-e10[1])>=ext){
    if(InpNeedHTF && !near50 && c[1]<e50[1]-atr[1]) {}
    else{
      double sl=h[1]+pt*2;
      if((sl-c[1])/pt < InpSL_Points*0.3) sl=c[1]+InpSL_Points*pt;
      double tp=InpTP_EMA20? e20[1] : c[1]-(sl-c[1])*InpRR;
      if(tp<c[1]) Send(-1,sl,tp);
    }
  }
}
