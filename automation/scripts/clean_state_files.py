#!/usr/bin/env python3
"""Sanitize state files: remove git merge conflict markers from JSON/JSONL files."""
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
STATE_DIRS = [
    REPO / 'automation/reports/live_scan',
    REPO / 'automation/reports/tech_analyst',
    REPO / 'automation/reports/supervisor',
    REPO / 'automation/reports/strategy_ranking',
    REPO / 'automation/reports/ocs_btc_5m',
]

total = 0
for d in STATE_DIRS:
    if not d.exists():
        continue
    for f in list(d.glob('*.json')) + list(d.glob('*.jsonl')):
        try:
            lines = f.read_text().split('\n')
            cleaned = [l for l in lines if not l.startswith(('<<<<<<<', '=======', '>>>>>>>'))]
            cleaned = [l for l in cleaned if l.strip() or f.name.endswith('.json')]
            if len(cleaned) < len(lines):
                f.write_text('\n'.join(cleaned) + ('\n' if f.suffix in ('.jsonl', '.json') else ''))
                total += len(lines) - len(cleaned)
        except Exception:
            pass

print(f'Total cleaned: {total} conflict lines')
