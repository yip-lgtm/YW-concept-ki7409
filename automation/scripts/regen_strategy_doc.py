#!/usr/bin/env python3
"""Regenerate docs/STRATEGY-SETUP.md from current source files.

Reads:
  - automation/scripts/strategy_ranking.py (STRATEGIES weights)
  - automation/src/yw_grader.py (STRATEGIES per-strategy config)
  - automation/reports/strategy_ranking/iterations/iteration_all_*.json (LLM iter history)

Writes:
  - docs/STRATEGY-SETUP.md
"""
from __future__ import annotations
import os, sys, json, re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'automation/src'))

from yw_grader import STRATEGIES


def main():
    # 1. Weights
    sr = (REPO / 'automation/scripts/strategy_ranking.py').read_text()
    weights = {}
    for m in re.finditer(r'"id":\s*"([^"]+)",\s*"name":\s*"([^"]+)",\s*"ticker":\s*"([^"]+)",\s*"type":\s*"([^"]+)",\s*"weight":\s*([0-9.]+)(?:,\s*"llm_optimized":\s*True,\s*"optim_date":\s*"([^"]+)")?', sr):
        weights[m.group(1)] = {
            'id': m.group(1),
            'name': m.group(2),
            'ticker': m.group(3),
            'type': m.group(4),
            'weight': float(m.group(5)),
            'optim_date': m.group(6) or '—',
        }

    # 2. Latest iteration
    iter_files = sorted((REPO / 'automation/reports/strategy_ranking/iterations').glob('iteration_all_*.json'), reverse=True)
    latest_iter = {}
    latest_iter_ts = '?'
    if iter_files:
        d = json.loads(iter_files[0].read_text())
        latest_iter_ts = d.get('hkt_timestamp', iter_files[0].stem)
        for r in d['results']:
            sid = r.get('strategy_id', r.get('agent', '').replace('yw-', ''))
            latest_iter[sid] = r

    grader_key_map = {
        'h-pattern': 'H-Pattern', '3-pushes': '3-Pushes', 'two-yang': 'Two-Yang-One-Yin',
        'rsi-div': 'RSI-Divergence', '50-20-pullback': '50-20-Pullback',
        'stair-pattern': 'Stair-Pattern', 'crt': 'CRT', 'kell-cycle': 'Kell-Cycle',
    }

    md = ['# 9 Strategy Sub-Agents — Latest Setup (auto-generated)\n']
    md.append('> **Auto-updated** from `automation/scripts/strategy_ranking.py` + `automation/src/yw_grader.py`')
    md.append(f'> **Last iter**: `{latest_iter_ts}`')
    md.append('')
    md.append('## 9 Strategies Current Config\n')
    md.append('| # | Strategy | Agent | Ticker | Weight | Timeframe | R-Multiples | LLM Optim |')
    md.append('|---|----------|-------|--------|--------|-----------|-------------|-----------|')

    for i, (sid, w) in enumerate(weights.items(), 1):
        grader_key = grader_key_map.get(sid)
        cfg = STRATEGIES.get(grader_key, {}) if grader_key else {}
        tf = cfg.get('timeframe', '5min' if sid == 'ocs-btc' else '?')
        rm = cfg.get('r_multiples', [1, 1.618, 2.618, 3.618, 5])
        optim = w['optim_date']
        optim_badge = f"✅ {optim}" if optim and optim != '—' else '—'
        md.append(f"| {i} | **{w['name']}** | `yw-{sid}` | {w['ticker']} | **{w['weight']}** | {tf} | `{rm}` | {optim_badge} |")

    md.append('\n## LLM Iterations Applied (cumulative)\n')
    md.append('| Iter | Strategy | Before → After | Conf | LLM Reason |')
    md.append('|------|----------|----------------|------|------------|')

    applied_history = [
        ('v1 2026-08-25 17:00', 'RSI-Divergence', 'w=1.1, tf=1/3/5min', 'w=0.7, tf=15min', '~80%', 'Live PF 0.92 < 1, wider R targets'),
        ('v2 2026-08-25 20:22', 'Two-Yang-One-Yin', 'w=0.8, tf=15min, R=[1,1.618,2.618]', 'w=0.3, tf=5/15min, R=[1.5,2.5,4,6,8]', '72%', 'Live PF 0.67 = no edge, wider R'),
        ('v2 2026-08-25 20:22', 'Kell-Cycle', 'w=0.9, tf=5min', 'w=0.5, tf=5min', '72%', '5 sub-detectors noisy, lower exposure'),
        ('v3 2026-08-25 20:36', 'Stair-Pattern', 'w=0.9, tf=5min', 'w=1.2, tf=15min', '85%', '20d 383 trades PF 1.08 = solid edge, raise'),
        ('v4 2026-08-26 00:35', 'Kell-Cycle', 'w=0.5, tf=5min', 'w=0.6, tf=15min', '72%', '4d 16 trades WR 56% R +2.36 = edge confirmed, raise'),
    ]
    for h in applied_history:
        md.append(f"| {h[0]} | {h[1]} | `{h[2]}` → `{h[3]}` | {h[4]} | {h[5]} |")

    md.append(f'\n## Latest Iteration ({latest_iter_ts})\n')
    md.append('| # | Strategy | Grade | Conf | Current | LLM Suggests | Status |')
    md.append('|---|----------|-------|------|---------|--------------|--------|')
    for i, (sid, w) in enumerate(weights.items(), 1):
        iter_ = latest_iter.get(sid, {})
        if not iter_:
            continue
        grade = iter_.get('grade', '?')
        conf = iter_.get('confidence', 0)
        new_w = iter_.get('weight', '?')
        new_tf = iter_.get('timeframe', '?')
        new_rm = iter_.get('r_multiples', [])
        cur_w = iter_.get('current_weight', w['weight'])
        cur_tf = iter_.get('current_timeframe', '?')
        applied = '✅ APPLIED' if conf >= 60 else f'⏭️ skip'
        md.append(f"| {i} | {w['name']} | {grade} | {conf}% | w={cur_w} tf={cur_tf} | w={new_w} tf={new_tf} R={new_rm} | {applied} |")

    out = REPO / 'docs' / 'STRATEGY-SETUP.md'
    out.write_text('\n'.join(md) + '\n')
    print(f"✓ Regenerated: {out} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
