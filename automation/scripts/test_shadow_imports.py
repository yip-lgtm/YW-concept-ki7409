#!/usr/bin/env python3
"""Regression test for function-local imports that shadow a module import.

A `from datetime import datetime` *inside* a function makes `datetime` a
local variable for the whole function, even for statements that come
before the import. tech_analyst.py had exactly that: the v3 circuit-breaker
block re-imported datetime inside main(), so the very first line of main()
— `datetime.now(HKT)` — raised

    UnboundLocalError: cannot access local variable 'datetime'

The Technical Analyst power died on every run for a month. The workflow
swallowed the traceback with `|| echo "tech_analyst done"`, so the job
stayed green and the "N/M charts failed" alerts people saw were stale
output from before the crash.

This check finds that bug class anywhere in the tree: if a function binds
a name by import, and reads that name *before* the binding, the read will
raise UnboundLocalError at runtime.

The second check loads tech_analyst.py and confirms its module-level
namespace is not shadowed inside main() — the specific regression.

Run it directly; it needs no network and no API key.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "automation" / "scripts"
SRC = REPO / "automation" / "src"

FAILURES: list[str] = []


def fatal_shadowing(tree: ast.AST, label: str) -> list[tuple[str, str, int, int]]:
    """Return (name, function, use_line, bind_line) for each fatal case.

    A name bound by an import inside a function is local to that whole
    function. Reading it before the binding raises UnboundLocalError.
    """
    out: list[tuple[str, str, int, int]] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        bound: dict[str, int] = {}
        for node in ast.walk(func):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    nm = (alias.asname or alias.name).split(".")[0]
                    bound.setdefault(nm, node.lineno)
        if not bound:
            continue
        for node in ast.walk(func):
            if not (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)):
                continue
            if node.id in bound and node.lineno < bound[node.id]:
                out.append((node.id, func.name, node.lineno, bound[node.id]))
    return out


def check_no_fatal_shadowing() -> None:
    targets = sorted(list(SCRIPTS.glob("*.py")) + list(SRC.glob("*.py")))
    scanned = 0
    for path in targets:
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError as e:
            FAILURES.append(f"{path.name}: does not parse ({e})")
            continue
        scanned += 1
        for name, func, use_line, bind_line in fatal_shadowing(tree, path.name):
            FAILURES.append(
                f"{path.name}:{use_line} {func}() reads '{name}' at line "
                f"{use_line} but a local import binds it at line {bind_line} — "
                f"this raises UnboundLocalError at runtime"
            )
    print(f"[static] scanned {scanned} files for fatal import shadowing")


def check_tech_analyst_main() -> None:
    """The specific regression: main() must not shadow datetime."""
    path = SCRIPTS / "tech_analyst.py"
    tree = ast.parse(path.read_text())
    main_fn = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.FunctionDef) and n.name == "main"),
        None,
    )
    if main_fn is None:
        FAILURES.append("tech_analyst.py has no main()")
        return
    shadows = set()
    for node in ast.walk(main_fn):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                nm = (alias.asname or alias.name).split(".")[0]
                if nm in ("datetime", "timezone", "timedelta"):
                    shadows.add(nm)
    if shadows:
        FAILURES.append(
            f"tech_analyst.py main() re-imports {sorted(shadows)} — that shadows "
            f"the module-level import and makes the first datetime.now() in "
            f"main() raise UnboundLocalError"
        )
    else:
        print("[functional] tech_analyst.main() does not shadow datetime")


def check_tech_analyst_runs() -> None:
    """main() must get past its first line without raising."""
    import importlib.util
    import os
    import types

    os.environ.setdefault("MINIMAX_API_KEY", "dummy-for-test")
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "")
    os.environ.setdefault("TELEGRAM_CHAT_ID", "")

    # matplotlib/yfinance are only needed to draw charts; stub the heavy
    # imports so this check stays fast and offline.
    for mod_name in ("mplfinance", "mplfinance.original_flavor",
                     "matplotlib", "matplotlib.pyplot", "matplotlib.dates",
                     "matplotlib.figure", "matplotlib.gridspec",
                     "matplotlib.ticker", "matplotlib.patches",
                     "matplotlib.lines", "matplotlib.colors"):
        if mod_name not in sys.modules:
            stub = types.ModuleType(mod_name)
            stub.__getattr__ = lambda _n: types.SimpleNamespace()  # type: ignore[attr-defined]
            sys.modules[mod_name] = stub

    spec = importlib.util.spec_from_file_location("ta_shadow_test", str(path_of_ta()))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ta_shadow_test"] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        FAILURES.append(f"tech_analyst.py failed to import: {type(e).__name__}: {e}")
        return

    # Exercise the exact statement that used to blow up, in main()'s scope,
    # without running the whole (network-bound) job.
    import datetime as _dt
    try:
        _dt.datetime.now(mod.HKT)
    except Exception as e:
        FAILURES.append(f"datetime.now(HKT) failed: {type(e).__name__}: {e}")
        return
    print("[functional] datetime.now(HKT) works in the analyst's scope")


def path_of_ta() -> Path:
    return SCRIPTS / "tech_analyst.py"


def main() -> int:
    check_no_fatal_shadowing()
    check_tech_analyst_main()
    check_tech_analyst_runs()
    if FAILURES:
        print("\nFAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\n✓ no fatal import shadowing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
