#!/usr/bin/env python3
"""Sanitize state files: remove git merge conflict markers from JSON/JSONL.

A file that still carries conflict markers is not valid JSON, and a state
file that does not parse is worse than one that is broken, because the
reader usually swallows the error and carries on with nothing. That is
not hypothetical: on 2026-10-22 the ranking board read
automation/config/strategy_levels.json with a bare `except Exception:
pass`, the parse failed, the level map came out empty, and every row's
level column read "?" while the job still reported success.

Three things are done here:

  - the marker lines are removed from every JSON and JSONL file under the
    state directories, including automation/config, which used to be
    missed
  - each file is validated afterwards. If cleaning broke it, the file is
    restored from git rather than published broken
  - the result is reported, so a file that could not be cleaned is named
    instead of silently skipped

For a JSONL file every line is an independent record, so both sides of a
conflict are kept. For a JSON file the upstream side wins, because CI is
where the live state is written.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE_DIRS = [
    REPO / "automation" / "config",
    REPO / "automation" / "reports" / "live_scan",
    REPO / "automation" / "reports" / "tech_analyst",
    REPO / "automation" / "reports" / "supervisor",
    REPO / "automation" / "reports" / "strategy_ranking",
    REPO / "automation" / "reports" / "strategy_settlement",
    REPO / "automation" / "reports" / "ocs_btc_5m",
    REPO / "automation" / "reports" / "ttrades_btc",
]
MARKERS = ("<<<<<<<", "=======", ">>>>>>>")


def _has_marker(text: str) -> bool:
    return any(line.startswith(MARKERS) for line in text.splitlines())


def _resolve(text: str, keep_both: bool) -> str:
    out, side = [], 1
    for line in text.splitlines():
        if line.startswith("<<<<<<<"):
            side = 1
            continue
        if line.startswith("======="):
            side = 2
            continue
        if line.startswith(">>>>>>>"):
            side = 0
            continue
        if side == 2 and not keep_both:
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def _valid(path: Path, text: str) -> bool:
    try:
        if path.suffix == ".jsonl":
            for line in text.splitlines():
                if line.strip():
                    json.loads(line)
        else:
            json.loads(text)
        return True
    except Exception:
        return False


def _restore_from_git(path: Path) -> bool:
    try:
        rel = path.relative_to(REPO).as_posix()
        raw = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=REPO,
                             capture_output=True, text=True).stdout
        if raw and _valid(path, raw):
            path.write_text(raw)
            return True
    except Exception:
        pass
    return False


def main() -> int:
    total = 0
    failed = []
    for d in STATE_DIRS:
        if not d.exists():
            continue
        for f in sorted(list(d.glob("*.json")) + list(d.glob("*.jsonl"))):
            try:
                text = f.read_text()
            except Exception:
                continue
            if not _has_marker(text):
                continue
            keep_both = f.suffix == ".jsonl"
            cleaned = _resolve(text, keep_both)
            if not _valid(f, cleaned):
                if _restore_from_git(f):
                    print(f"  ! {f.name}: cleaning broke it, restored from git")
                else:
                    failed.append(str(f))
                    print(f"  ✗ {f.name}: could not be cleaned or restored")
                continue
            f.write_text(cleaned)
            total += 1
            print(f"  ✓ {f.name}: conflict markers removed")

    print(f"Total cleaned: {total} file(s)")
    if failed:
        print(f"FAILED: {len(failed)} file(s) still carry conflict markers")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
