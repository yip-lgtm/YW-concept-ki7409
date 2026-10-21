#!/usr/bin/env python3
"""Regression test for the LLM call sites.

Three scripts called `chat(prompt, system=system)` where no `system`
variable existed in scope. The NameError was swallowed by a broad
`except Exception`, every graded signal came back with confidence 0,
and the live system confirmed no signals at all — with the reason field
reading "no parse" instead of the real cause.

Two checks:

  1. static — no `chat(..., system=<bare name>)` call may reference a
     name that is neither a parameter nor assigned in the enclosing
     function.
  2. functional — the three affected entry points are called with a
     stubbed `chat`, and the grade/diagnosis must come back parsed, with
     exactly one LLM call and a non-empty system prompt.

Run it directly; it needs no network and no API key.
"""
from __future__ import annotations

import ast
import importlib.util
import os
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "automation" / "scripts"
SRC = REPO / "automation" / "src"

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SRC))
os.environ.setdefault("MINIMAX_API_KEY", "dummy-for-test")

# live_scan imports requests at module level. The functions under test no
# longer call it, so a stub that raises if it is used proves the duplicate
# request really is gone.
if "requests" not in sys.modules:
    _stub = types.ModuleType("requests")

    def _boom(*_a, **_k):
        raise RuntimeError("requests must not be called by these functions")

    _stub.post = _boom
    _stub.get = _boom
    _stub.exceptions = types.SimpleNamespace(HTTPError=Exception, Timeout=Exception)
    sys.modules["requests"] = _stub

FAILURES: list[str] = []


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- 1. static check -------------------------------------------------------

def check_static() -> None:
    targets = ["live_scan.py", "llm_iteration_scientist.py", "sys_engineer.py",
               "llm_iterate_all.py", "settlement_llm_intervene.py"]
    for fname in targets:
        path = SCRIPTS / fname
        tree = ast.parse(path.read_text())
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = [a.arg for a in func.args.args] + [a.arg for a in func.args.kwonlyargs]
            stores = {n.id for n in ast.walk(func)
                      if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
            for node in ast.walk(func):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "chat"):
                    continue
                for kw in node.keywords:
                    if kw.arg != "system":
                        continue
                    if isinstance(kw.value, ast.Name) and kw.value.id not in args \
                            and kw.value.id not in stores:
                        FAILURES.append(
                            f"{fname}:{node.lineno} chat() in {func.name}() uses "
                            f"undefined name 'system'")
    print(f"[static] scanned {len(targets)} files")


# --- 2. functional check ----------------------------------------------------

def check_llm_grade() -> None:
    ls = load("live_scan", SCRIPTS / "live_scan.py")
    calls: list[dict] = []

    def fake_chat(prompt, system="", max_tokens=2048, temperature=0.2, timeout=45):
        calls.append({"system": system, "max_tokens": max_tokens})
        return "GRADE: A | CONFIDENCE: 82 | REASON: 結構完整", ""

    ls.chat = fake_chat
    det = {"strategy": "CRT", "ticker": "GC=F", "direction": "long",
           "signal": "buy", "last_close": 4140.0, "strength": 80,
           "entry": 4139.0, "sl": 4131.0, "t1": 4147.0, "t2": 4151.0,
           "atr": 5.0, "reason": "box break"}
    res = ls.llm_grade("CRT", "GC=F", det)
    if res.get("grade") != "A" or res.get("confidence") != 82:
        FAILURES.append(f"llm_grade did not parse the grade: {res}")
    if len(calls) != 1:
        FAILURES.append(f"llm_grade made {len(calls)} LLM calls, expected 1")
    if not calls or not calls[0]["system"]:
        FAILURES.append("llm_grade did not pass a system prompt")
    print(f"[functional] llm_grade -> {res.get('grade')}/{res.get('confidence')}, "
          f"{len(calls)} call(s)")

    def failing(prompt, system="", **_k):
        return "", "HTTP 429: rate limited"

    ls.chat = failing
    res2 = ls.llm_grade("CRT", "GC=F", det)
    if res2.get("confidence") != 0 or "429" not in str(res2.get("reason")):
        FAILURES.append(f"llm_grade swallowed the LLM error: {res2}")
    print(f"[functional] llm_grade error path -> {res2.get('reason')}")


def check_sys_engineer() -> None:
    se = load("sys_engineer", SCRIPTS / "sys_engineer.py")
    calls: list[str] = []

    def fake_chat(prompt, system="", **_k):
        calls.append(system)
        return "DIAGNOSIS: root cause\nFIX: change one line", ""

    se.chat = fake_chat
    out = se.diagnose_with_llm({"agent": "H-Pattern", "signals": 0})
    if "DIAGNOSIS" not in out:
        FAILURES.append(f"sys_engineer diagnosis not returned: {out!r}")
    if len(calls) != 1 or not calls[0]:
        FAILURES.append("sys_engineer did not make exactly one call with a system prompt")
    print(f"[functional] sys_engineer -> {out.splitlines()[0][:40]!r}")


def check_scientist() -> None:
    sci = load("llm_iteration_scientist", SCRIPTS / "llm_iteration_scientist.py")
    calls: list[str] = []

    def fake_chat(prompt, system="", **_k):
        calls.append(system)
        return ("GRADE: D | CONFIDENCE: 30 | DIAGNOSIS: weak edge | REASON: low "
                "sample | SUGGESTED_PARAMS: NONE", "")

    sci.chat = fake_chat
    agent = {"agent": "H-Pattern", "id": "yw-h-pattern", "ticker": "MNQ=F",
             "src": "live_scan", "fn": "h_pattern"}
    data = {"n_signals_7d": 5, "n_signals_24h": 0, "n_trades": 3, "n_wins": 1,
            "n_losses": 2, "win_rate": 33.3, "total_R": -1.0, "avg_R": -0.33,
            "profit_factor": 0.4, "by_grade": {}, "by_direction": {}, "by_ticker": {}}
    res = sci.call_llm_scientist(agent, data)
    if res.get("grade") != "D" or res.get("confidence") != 30:
        FAILURES.append(f"call_llm_scientist did not parse: {res}")
    if len(calls) != 1 or not calls[0]:
        FAILURES.append("call_llm_scientist did not make exactly one call with a system prompt")
    print(f"[functional] call_llm_scientist -> {res.get('grade')}/{res.get('confidence')}")


def main() -> int:
    check_static()
    check_llm_grade()
    check_sys_engineer()
    check_scientist()
    if FAILURES:
        print("\nFAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\n✓ all LLM call sites are sound")
    return 0


if __name__ == "__main__":
    sys.exit(main())
