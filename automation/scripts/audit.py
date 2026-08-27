#!/usr/bin/env python3
"""Audit Trail — records all 4-power actions for accountability.

Each power logs its actions to: automation/reports/audit/<date>/actions.jsonl

Usage:
  from audit import log_action
  log_action("supervisor", "health_check", "yw-50-20-pullback", "BUG", "KeyError: ...")
"""
from __future__ import annotations
import os
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

HKT = timezone(timedelta(hours=8))
AUDIT_DIR = REPO / "automation/reports/audit"


def log_action(power: str, action: str, target: str = "", result: str = "", details: str = "",
               accountable_to: str = "") -> None:
    """Log a power action to audit trail.
    
    Args:
        power: "supervisor" | "sys-engineer" | "strategy-agent" | "iter-scientist"
        action: "health_check" | "auto_fix" | "signal" | "iteration" | ...
        target: which agent/file is affected
        result: "OK" | "BUG" | "WARN" | "FAIL" | "AUTO_APPLIED" | "SKIPPED"
        details: short description
        accountable_to: which power is accountable
    """
    try:
        now = datetime.now(HKT)
        date_str = now.strftime("%Y-%m-%d")
        audit_path = AUDIT_DIR / date_str
        audit_path.mkdir(parents=True, exist_ok=True)
        audit_file = audit_path / "actions.jsonl"
        entry = {
            "timestamp": now.isoformat(),
            "power": power,
            "action": action,
            "target": target,
            "result": result,
            "details": details[:300],
            "accountable_to": accountable_to or f"Power {power}",
        }
        with open(audit_file, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[audit] Failed to log: {e}")


def get_audit_report(date: str = None, power: str = None) -> list[dict]:
    """Read audit entries for a date and optional power filter."""
    if date is None:
        date = datetime.now(HKT).strftime("%Y-%m-%d")
    audit_file = AUDIT_DIR / date / "actions.jsonl"
    if not audit_file.exists():
        return []
    entries = []
    try:
        with open(audit_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if power is None or entry.get("power") == power:
                        entries.append(entry)
                except Exception:
                    continue
    except Exception:
        pass
    return entries


def summary_today() -> str:
    """Get summary of today's audit actions."""
    today = datetime.now(HKT).strftime("%Y-%m-%d")
    entries = get_audit_report(today)
    if not entries:
        return "📊 Audit: no actions today"
    by_power = {}
    for e in entries:
        p = e.get("power", "?")
        by_power.setdefault(p, []).append(e)
    msg = f"📊 Audit Summary ({today})\n"
    for p, es in sorted(by_power.items()):
        n = len(es)
        n_fail = sum(1 for e in es if e.get("result") in ("BUG", "FAIL"))
        n_ok = sum(1 for e in es if e.get("result") not in ("BUG", "FAIL"))
        msg += f"  • {p}: {n} actions ({n_ok} OK, {n_fail} fail)\n"
    return msg


if __name__ == "__main__":
    # Demo: log some sample actions
    log_action("supervisor", "health_check", "yw-50-20-pullback", "BUG", "KeyError: yw_indicators", "Power 1 (Supervisor)")
    log_action("sys-engineer", "auto_fix", "yw-50-20-pullback", "AUTO_APPLIED", "Removed del sys.modules", "Power 2 (System Engineer)")
    log_action("strategy-agent", "signal", "CRT MGC=F", "OK", "Grade B, conf 72", "Power 3 (Strategy Agent)")
    log_action("iter-scientist", "iteration", "yw-50-20-pullback", "OK", "Suggest add ticker param", "Power 4 (LLM Iteration Scientist)")
    print(summary_today())
