#!/usr/bin/env python3
"""Test the CRT gold de-duplication gate.

MGC=F and GC=F are the same metal quoted per troy ounce — measured, the
median difference is $0.10 on ~$4,140 and every sample was inside 0.05%.
A setup on both opens the same trade twice, which is why Argon-Gold is
restricted to GC=F. CRT was not, and on 2026-10-21 it opened both.

This test asserts the gate keeps CRT on MGC=F, blocks it on GC=F, and
leaves Argon-Gold on GC=F alone. No network, no API key.
"""
import importlib.util, sys, os, types
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/"automation/scripts")); sys.path.insert(0,str(REPO/"automation/src"))
os.environ.setdefault("MINIMAX_API_KEY","dummy")
if "requests" not in sys.modules:
    s=types.ModuleType("requests"); s.post=lambda *a,**k: None
    s.exceptions=types.SimpleNamespace(HTTPError=Exception,Timeout=Exception); s.get=lambda *a,**k: None
    sys.modules["requests"]=s
spec=importlib.util.spec_from_file_location("live_scan", str(REPO/"automation/scripts/live_scan.py"))
ls=importlib.util.module_from_spec(spec); spec.loader.exec_module(ls)

def sig(strategy, ticker, direction="bullish", grade="A", conf=80):
    return {"strategy":strategy,"ticker":ticker,"direction":direction,"grade":grade,
            "confidence":conf,"raw_confidence":conf,"signal":"buy","ts":"2026-10-21T17:00:00+00:00",
            "last_close":4150.0,"reason":"test","entry":4150.0,"sl":4143.0}

# 1) CRT on GC=F must be gated
kept, gated = ls._apply_open_gates([sig("CRT","GC=F")])
print("CRT GC=F  -> kept:", len(kept), "| gated:", [g.get('gate_skip') for g in gated])
assert len(kept)==0 and any("CRT ban ticker GC=F" in str(g.get('gate_skip','')) for g in gated), "CRT GC=F NOT gated!"
print("  ✓ CRT GC=F 被擋")

# 2) CRT on MGC=F must pass
kept2, gated2 = ls._apply_open_gates([sig("CRT","MGC=F")])
print("CRT MGC=F -> kept:", len(kept2), "| gated:", len(gated2))
assert len(kept2)==1, "CRT MGC=F was wrongly gated!"
print("  ✓ CRT MGC=F 正常放行")

# 3) Argon-Gold on GC=F must still pass (it is not CRT)
kept3, gated3 = ls._apply_open_gates([sig("Argon-Gold","GC=F")])
print("Argon GC=F-> kept:", len(kept3), "| gated:", len(gated3))
assert len(kept3)==1, "Argon-Gold on GC=F was wrongly gated!"
print("  ✓ Argon-Gold 喺 GC=F 正常放行（GC 留畀 Argon）")

# 4) other CRT tickers unaffected
kept4, gated4 = ls._apply_open_gates([sig("CRT","MNQ=F")])
assert len(kept4)==1, "CRT MNQ=F wrongly gated"
print("  ✓ CRT 其他標的不受影響")
print("\n✓ CRT 黃金去重閘正確：GC=F 擋、MGC=F 放、Argon 唔受影響")
