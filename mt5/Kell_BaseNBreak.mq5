//+------------------------------------------------------------------+
//|                                           Kell_BaseNBreak.mq5    |
//|  Oliver Kell: Base n' Break（沿10/20築底後突破）                  |
//+------------------------------------------------------------------+
#property copyright "YW Concept Research"
#property version   "1.00"
#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

input int    InpEMA10=10;
input int    InpEMA20=20;
input int    InpMinBase=6;      // 最少盤整根數
input int    InpMaxBase=30;
input double InpBaseATR=1.8;    // 盤整高低 ≤ ATR×此值
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
input int    InpMagic=1514;
input string InpComment="Kell-BB";

CTrade trade; CPositionInfo pos;
int h10,h20,hATR; datetime lastBar=0; double dayBal=0; int dayStamp=0;

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
  int n=InpMaxBase+5;
  double e10[],e20[],atr[],c[],h[],l[];
  ArraySetAsSeries(e10,true); ArraySetAsSeries(e20,true); ArraySetAsSeries(atr,true);
  ArraySetAsSeries(c,true); ArraySetAsSeries(h,true); ArraySetAsSeries(l,true);
  if(CopyBuffer(h10,0,0,n,e10)<n) return;
  if(CopyBuffer(h20,0,0,n,e20)<n) return;
  if(CopyBuffer(hATR,0,0,n,atr)<n) return;
  if(CopyClose(_Symbol,PERIOD_CURRENT,0,n,c)<n) return;
  if(CopyHigh(_Symbol,PERIOD_CURRENT,0,n,h)<n) return;
  if(CopyLow(_Symbol,PERIOD_CURRENT,0,n,l)<n) return;
  // 從 bar2 往回量盤整（bar1 用來確認突破）
  int base=0; double bh=h[2], bl=l[2];
  for(int i=2;i<InpMaxBase+2 && i<n;i++){
    double mid=(e10[i]+e20[i])/2.0;
    if(MathAbs(c[i]-mid)>atr[i]*InpBaseATR) break;
    if(h[i]>bh) bh=h[i]; if(l[i]<bl) bl=l[i];
    if((bh-bl)>atr[2]*InpBaseATR*1.4) break;
    base++;
  }
  if(base<InpMinBase) return;
  double pt=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
  if(InpAllowLong && c[1]>bh && c[1]>e10[1] && c[1]>e20[1]){
    double sl=bl-2*pt; if((c[1]-sl)/pt<InpSL_Points*0.3) sl=c[1]-InpSL_Points*pt;
    Send(1,sl,c[1]+(c[1]-sl)*InpRR);
  }
  if(InpAllowShort && c[1]<bl && c[1]<e10[1] && c[1]<e20[1]){
    double sl=bh+2*pt; if((sl-c[1])/pt<InpSL_Points*0.3) sl=c[1]+InpSL_Points*pt;
    Send(-1,sl,c[1]-(sl-c[1])*InpRR);
  }
}
