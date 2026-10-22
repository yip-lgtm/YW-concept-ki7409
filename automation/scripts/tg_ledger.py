"""Remember which signal charts have already been posted to Telegram.

live_scan posts the chart the moment a signal fires. tech_analyst then runs
every fifteen minutes and used to post the same picture again for every
signal still inside its two-hour window, so one trade reached the channel
two or three times with the same caption. The chart file name is the only
identifier both scripts agree on, so that is what the ledger keys on.

The ledger is a convenience, not a gate: if it cannot be written, the
signal is still sent rather than silently dropped.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# Inside live_scan/ on purpose: that is the one directory the live-scan
# workflow commits, and the tech-analyst job commits all of automation/reports,
# so both writers' marks survive to the next run.
LEDGER_FILE = REPO / "automation" / "reports" / "live_scan" / "tg_sent.json"
KEEP_DAYS = 7


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load() -> dict:
    try:
        d = json.loads(LEDGER_FILE.read_text())
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def _key(chart_path: str | Path) -> str:
    """The chart file name without extension — the id both scripts share."""
    return Path(chart_path).stem


def is_sent(chart_path: str | Path) -> bool:
    if not chart_path:
        return False
    try:
        return _key(chart_path) in _load().get("sent", {})
    except Exception:
        return False


def mark_sent(chart_path: str | Path) -> None:
    if not chart_path:
        return
    try:
        data = _load()
        sent = data.get("sent", {})
        if not isinstance(sent, dict):
            sent = {}
        now = _now()
        sent[_key(chart_path)] = now.isoformat()
        cutoff = (now - timedelta(days=KEEP_DAYS)).isoformat()
        data["sent"] = {k: v for k, v in sent.items() if str(v) >= cutoff}
        data["updated"] = now.isoformat()
        LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        LEDGER_FILE.write_text(json.dumps(data, indent=2, sort_keys=True))
    except Exception:
        # A missing ledger means a duplicate picture, which is survivable.
        # A crash in the live path is not.
        pass
