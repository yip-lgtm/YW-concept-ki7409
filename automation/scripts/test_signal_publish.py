"""The Telegram caption and the publish gate.

The channel was showing "Entry: $?" on every chart because the caption read
`sig.get("entry")` and `sig.get("price")` — neither key exists in a signal
record; the price is `last_close`. It was also publishing signals the
scanner had rejected, and posting the same chart again on every run inside
its two-hour window. These are the three rules that stop that.

Run: python3 automation/scripts/test_signal_publish.py
"""
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    import requests  # noqa: F401
except ImportError:
    # tech_analyst imports requests for the Telegram call. The caption and
    # the gate do not use it, so a stub keeps this test runnable where the
    # dependency is not installed.
    _stub = types.ModuleType("requests")

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"ok": True}

    _stub.post = lambda *a, **k: _Resp()
    _stub.get = lambda *a, **k: _Resp()
    _stub.exceptions = types.SimpleNamespace(HTTPError=Exception, Timeout=Exception,
                                              RequestException=Exception)
    sys.modules["requests"] = _stub

import tg_ledger  # noqa: E402
import tech_analyst as ta  # noqa: E402

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"  ok    {label}")
    else:
        print(f"  FAIL  {label} {detail}")
        FAILURES.append(label)


def sig(**over):
    base = {
        "strategy": "CRT",
        "ticker": "MNQ=F",
        "grade": "A",
        "direction": "bearish",
        "last_close": 29224.0,
        "ts": "2026-10-22T17:28:40.956329+00:00",
        "position_id": "CRT|MNQ=F|2026-10-22T17:28:40.956329+00:00",
    }
    base.update(over)
    return base


print("== the entry price is printed, not a question mark ==")
cap = ta.build_caption(sig())
check("caption carries the price from last_close", "$29,224.00" in cap, cap)
check("caption has no bare question mark entry", "Entry: $?" not in cap, cap)
check("caption keeps the strategy, grade, ticker and time",
      all(x in cap for x in ("CRT", "[A]", "MNQ=F", "2026-10-22T17:28:40")), cap)

cap = ta.build_caption(sig(entry=1234.5))
check("an explicit entry wins over last_close", "$1,234.50" in cap, cap)

cap = ta.build_caption(sig(last_close=0, entry=None, price=None))
check("a signal with no price at all says so", "Entry: $?" in cap, cap)

print()
print("== a rejected signal is not published ==")
check("a fired signal publishes", ta.should_publish(sig()) is True)
check("a gate-blocked signal does not publish",
      ta.should_publish(sig(gate_blocked=True)) is False)
check("position_opened=False also blocks",
      ta.should_publish(sig(position_opened=False)) is False)

print()
print("== a chart goes out once ==")
with tempfile.TemporaryDirectory() as tmp:
    tg_ledger.LEDGER_FILE = Path(tmp) / "tg_sent.json"
    chart = Path(tmp) / "CRT_MNQ=F_2026-10-22T17-28-40.956329+00-00.png"
    chart.write_bytes(b"x")

    check("a chart that was never sent is not marked sent",
          tg_ledger.is_sent(chart) is False)
    tg_ledger.mark_sent(chart)
    check("after sending it is marked sent", tg_ledger.is_sent(chart) is True)

    other = Path(tmp) / "Stair_MES=F_other.png"
    check("a different chart is unaffected", tg_ledger.is_sent(other) is False)

    # A ledger that cannot be read must not raise into the live path.
    tg_ledger.LEDGER_FILE = Path(tmp) / "does-not-exist" / "nope.json"
    check("a missing ledger reads as not sent", tg_ledger.is_sent(chart) is False)
    check("writing to an unwritable ledger does not raise",
          tg_ledger.mark_sent(chart) is None)

print()
if FAILURES:
    print(f"SELF-TEST FAILED: {len(FAILURES)} check(s) — {', '.join(FAILURES)}")
    sys.exit(1)
print("SELF-TEST 全部通過")
