//+------------------------------------------------------------------+
//|                                           Kell_Exhaustion.mq5    |
//|  Oliver Kell: Exhaustion Extension（第2/3次遠離10EMA）            |
//|  模式A：反向入場（fade）  模式B：只平倉現有同Magic單              |
//+------------------------------------------------------------------+
#property copyright "YW Concept Research"
#property version   "1.00"
#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

input int    InpEMA10=10;
input int    InpLook=80;        // 回看幾根數延伸次數
input double InpExtATR=1.6;     // 視為延伸的 ATR 倍
input int    InpMinExt=2;       // 至少第幾次延伸才動作
input bool   InpFadeEntry=true; // true=反向開單；false=只平倉
input int    InpManageMagic=0;  // 0=平本EA單；其他=平指定Magic
input bool   InpAllowLong=true; // fade 時允許做多（下跌耗盡）
input bool   InpAllowShort=true;
input bool   InpOnlyOnePos=true;
input double InpSL_Points=50;
input double InpRR=1.5;
input double InpLotSize=0.1;
input double InpRiskMoney=100;
input double InpDailyTP=200;
input double InpDailySL=600;
input bool   InpUseDailyLimit=true;
input int    InpMagic=1515;
input string InpComment="Kell-EX";

CTrade trade; CPositionInfo pos;
int h10,hATR; datetime lastBar=0; double dayBal=0; int dayStamp=0;

int OnInit(){
  trade.SetExpertMagicNumber(InpMagic); trade.SetDeviationInPoints(20);
  trade.SetTypeFillingBySymbol(_Symbol);
  h10=iMA(_Symbol,PERIOD_CURRENT,InpEMA10,0,MODE_EMA,PRICE_CLOSE);
  hATR=iATR(_Symbol,PERIOD_CURRENT,14);
  if(h10==INVALID_HANDLE||hATR==INVALID_HANDLE) return INIT_FAILED;
  dayBal=AccountInfoDouble(ACCOUNT_BALANCE); dayStamp=DayOfYear(); return INIT_SUCCEEDED;
}
void OnDeinit(const int r){ IndicatorRelease(h10); IndicatorRelease(hATR); }
int DayOfYear(){ MqlDateTime d; TimeToStruct(TimeCurrent(),d); return d.day_of_year+d.year*1000; }
void ResetDay(){ int d=DayOfYear(); if(d!=dayStamp){ dayStamp=d; dayBal=AccountInfoDouble(ACCOUNT_BALANCE);} }
bool DailyHit(){ if(!InpUseDailyLimit) return false; ResetDay(); double pnl=AccountInfoDouble(ACCOUNT_EQUITY)-dayBal; return (pnl>=InpDailyTP||pnl<=-InpDailySL); }
bool HasPos(){ for(int i=PositionsTotal()-1;i>=0;i--) if(pos.SelectByIndex(i)&&pos.Symbol()==_Symbol&&pos.Magic()==InpMagic) return true; return false; }
void CloseMagic(int mg,int onlyDir){
  for(int i=PositionsTotal()-1;i>=0;i--){
    if(!pos.SelectByIndex(i) || pos.Symbol()!=_Symbol) continue;
    if(mg!=0 && pos.Magic()!=mg && pos.Magic()!=InpMagic) continue;
    if(onlyDir==1 && pos.PositionType()!=POSITION_TYPE_BUY) continue;
    if(onlyDir==-1 && pos.PositionType()!=POSITION_TYPE_SELL) continue;
    trade.PositionClose(pos.Ticket());
  }
}
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
  if(DailyHit()) return;
  int n=InpLook+5;
  double e10[],atr[],c[],h[],l[],o[];
  ArraySetAsSeries(e10,true); ArraySetAsSeries(atr,true);
  ArraySetAsSeries(c,true); ArraySetAsSeries(h,true); ArraySetAsSeries(l,true); ArraySetAsSeries(o,true);
  if(CopyBuffer(h10,0,0,n,e10)<n) return;
  if(CopyBuffer(hATR,0,0,n,atr)<n) return;
  if(CopyClose(_Symbol,PERIOD_CURRENT,0,n,c)<n) return;
  if(CopyHigh(_Symbol,PERIOD_CURRENT,0,n,h)<n) return;
  if(CopyLow(_Symbol,PERIOD_CURRENT,0,n,l)<n) return;
  if(CopyOpen(_Symbol,PERIOD_CURRENT,0,n,o)<n) return;
  int upExt=0, dnExt=0;
  bool inUp=false, inDn=false;
  for(int i=InpLook;i>=1;i--){
    bool u=(c[i]-e10[i])>=atr[i]*InpExtATR;
    bool d=(e10[i]-c[i])>=atr[i]*InpExtATR;
    if(u && !inUp){ upExt++; inUp=true; } if(!u) inUp=false;
    if(d && !inDn){ dnExt++; inDn=true; } if(!d) inDn=false;
  }
  bool extUpNow=(c[1]-e10[1])>=atr[1]*InpExtATR;
  bool extDnNow=(e10[1]-c[1])>=atr[1]*InpExtATR;
  bool revDn=c[1]<o[1] && c[1]<=(h[1]+l[1])/2.0;
  bool revUp=c[1]>o[1] && c[1]>=(h[1]+l[1])/2.0;
  double pt=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
  // 上升耗盡 → 平多 / fade 空
  if(extUpNow && upExt>=InpMinExt && revDn){
    CloseMagic(InpManageMagic,1);
    if(InpFadeEntry && InpAllowShort){
      if(!(InpOnlyOnePos&&HasPos())){
        double sl=h[1]+2*pt; if((sl-c[1])/pt<InpSL_Points*0.3) sl=c[1]+InpSL_Points*pt;
        Send(-1,sl,c[1]-(sl-c[1])*InpRR);
      }
    }
  }
  // 下跌耗盡 → 平空 / fade 多
  if(extDnNow && dnExt>=InpMinExt && revUp){
    CloseMagic(InpManageMagic,-1);
    if(InpFadeEntry && InpAllowLong){
      if(!(InpOnlyOnePos&&HasPos())){
        double sl=l[1]-2*pt; if((c[1]-sl)/pt<InpSL_Points*0.3) sl=c[1]-InpSL_Points*pt;
        Send(1,sl,c[1]+(c[1]-sl)*InpRR);
      }
    }
  }
}
