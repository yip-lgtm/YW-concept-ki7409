//+------------------------------------------------------------------+
//|                                         Kell_WedgePopDrop.mq5    |
//|  Oliver Kell: Wedge Pop / Wedge Drop（收窄後重奪 10/20 EMA）      |
//+------------------------------------------------------------------+
#property copyright "YW Concept Research"
#property version   "1.00"
#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

input int    InpEMA10=10;
input int    InpEMA20=20;
input int    InpLook=12;         // 收窄比較窗口
input double InpTightRatio=0.55; // 現差 / 前段均差 < 此值視為收窄
input int    InpSwing=8;         // SL 用近期高低
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
input int    InpMagic=1512;
input string InpComment="Kell-WD";

CTrade trade; CPositionInfo pos;
int h10,h20; datetime lastBar=0; double dayBal=0; int dayStamp=0;

int OnInit(){
  trade.SetExpertMagicNumber(InpMagic); trade.SetDeviationInPoints(20);
  trade.SetTypeFillingBySymbol(_Symbol);
  h10=iMA(_Symbol,PERIOD_CURRENT,InpEMA10,0,MODE_EMA,PRICE_CLOSE);
  h20=iMA(_Symbol,PERIOD_CURRENT,InpEMA20,0,MODE_EMA,PRICE_CLOSE);
  if(h10==INVALID_HANDLE||h20==INVALID_HANDLE) return INIT_FAILED;
  dayBal=AccountInfoDouble(ACCOUNT_BALANCE); dayStamp=DayOfYear(); return INIT_SUCCEEDED;
}
void OnDeinit(const int r){ IndicatorRelease(h10); IndicatorRelease(h20); }
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
  double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK), bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
  double pt=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
  double slPts=(dir==1?ask-sl:sl-bid)/pt; if(slPts<1) slPts=InpSL_Points;
  double lot=CalcLot(slPts);
  sl=NormalizeDouble(sl,dg); tp=NormalizeDouble(tp,dg);
  if(dir==1) trade.Buy(lot,_Symbol,ask,sl,tp,InpComment);
  else trade.Sell(lot,_Symbol,bid,sl,tp,InpComment);
}
void OnTick(){
  datetime t=iTime(_Symbol,PERIOD_CURRENT,0); if(t==lastBar) return; lastBar=t;
  if(DailyHit()) return; if(InpOnlyOnePos&&HasPos()) return;
  int n=InpLook+8;
  double e10[],e20[],c[],h[],l[];
  ArraySetAsSeries(e10,true); ArraySetAsSeries(e20,true);
  ArraySetAsSeries(c,true); ArraySetAsSeries(h,true); ArraySetAsSeries(l,true);
  if(CopyBuffer(h10,0,0,n,e10)<n) return;
  if(CopyBuffer(h20,0,0,n,e20)<n) return;
  if(CopyClose(_Symbol,PERIOD_CURRENT,0,n,c)<n) return;
  if(CopyHigh(_Symbol,PERIOD_CURRENT,0,n,h)<n) return;
  if(CopyLow(_Symbol,PERIOD_CURRENT,0,n,l)<n) return;
  double nowSpread=MathAbs(e10[1]-e20[1]);
  double avg=0; int cnt=0;
  for(int i=3;i<=InpLook+2;i++){ avg+=MathAbs(e10[i]-e20[i]); cnt++; }
  if(cnt==0) return; avg/=cnt;
  bool tight=(avg>0 && nowSpread<=avg*InpTightRatio);
  bool wasBelow=(c[2]<e10[2] && c[2]<e20[2]);
  bool nowAbove=(c[1]>e10[1] && c[1]>e20[1]);
  bool wasAbove=(c[2]>e10[2] && c[2]>e20[2]);
  bool nowBelow=(c[1]<e10[1] && c[1]<e20[1]);
  double pt=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
  if(InpAllowLong && tight && wasBelow && nowAbove){
    double sl=l[1];
    for(int i=1;i<=InpSwing;i++) if(l[i]<sl) sl=l[i];
    sl-=2*pt; if((c[1]-sl)/pt<InpSL_Points*0.3) sl=c[1]-InpSL_Points*pt;
    Send(1,sl,c[1]+(c[1]-sl)*InpRR);
  }
  if(InpAllowShort && tight && wasAbove && nowBelow){
    double sl=h[1];
    for(int i=1;i<=InpSwing;i++) if(h[i]>sl) sl=h[i];
    sl+=2*pt; if((sl-c[1])/pt<InpSL_Points*0.3) sl=c[1]+InpSL_Points*pt;
    Send(-1,sl,c[1]-(sl-c[1])*InpRR);
  }
}
