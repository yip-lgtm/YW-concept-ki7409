#!/usr/bin/env python3
"""Regenerate _dashboard_data.json from current state.

Run by GHA hourly to keep dashboard fresh.
"""
from __future__ import annotations
import sys, json, re
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone, timedelta

import os
REPO = Path(os.environ.get('GITHUB_WORKSPACE') or os.environ.get('YW_REPO') or '/workspace/YW-concept-ki7409')
sys.path.insert(0, str(REPO / 'automation/src'))
sys.path.insert(0, str(REPO / 'automation/scripts'))

HKT = timezone(timedelta(hours=8))
now = datetime.now(HKT)
HKT_STR = now.strftime("%Y-%m-%d %H:%M HKT")

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

# 2. yw_grader config
try:
    from yw_grader import STRATEGIES
    grader_cfg = STRATEGIES
except Exception:
    grader_cfg = {}

# 3. Live trades (24h window)
LS = REPO / 'automation/reports/live_scan'
OCS = REPO / 'automation/reports/ocs_btc_5m'
all_trades = []
if (LS / 'trades.jsonl').exists():
    with open(LS / 'trades.jsonl') as f:
        for line in f:
            all_trades.append(json.loads(line))
if (OCS / 'trades.jsonl').exists():
    with open(OCS / 'trades.jsonl') as f:
        for line in f:
            t = json.loads(line)
            t['strategy'] = 'OCS BTC 5m'
            all_trades.append(t)


def is_in_last_24h(trade):
    for k in ['entry_time', 'exit_time']:
        v = trade.get(k, '')
        if not v: continue
        try:
            ts_str = v.replace(' ', 'T')
            if 'Z' in ts_str or '+' in ts_str:
                ts = datetime.fromisoformat(ts_str)
            else:
                ts = datetime.fromisoformat(ts_str + '+00:00')
            if (now - ts.astimezone(HKT)).total_seconds() < 24*3600:
                return True
        except: pass
    return False


def is_today(trade):
    for k in ['entry_time', 'exit_time']:
        v = trade.get(k, '')
        if not v: continue
        try:
            ts_str = v.replace(' ', 'T')
            if 'Z' in ts_str or '+' in ts_str:
                ts = datetime.fromisoformat(ts_str)
            else:
                ts = datetime.fromisoformat(ts_str + '+00:00')
            if ts.astimezone(HKT).strftime('%Y-%m-%d') == now.strftime('%Y-%m-%d'):
                return True
        except: pass
    return False


# 24h stats
last24h = [t for t in all_trades if is_in_last_24h(t)]
today_trades = [t for t in all_trades if is_today(t)]

# 4. Live signals (defensive parse — skip blank/corrupt lines)
all_signals = []
if (LS / 'signals.jsonl').exists():
    with open(LS / 'signals.jsonl') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                all_signals.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # skip corrupt lines

def sig_in_last_24h(s):
    try:
        ts = datetime.fromisoformat(s.get('ts', '').replace('Z', '+00:00'))
        return (now - ts.astimezone(HKT)).total_seconds() < 24*3600
    except: return False

last24h_sigs = [s for s in all_signals if sig_in_last_24h(s)]

# 5. Latest iteration
iter_files = sorted((REPO / 'automation/reports/strategy_ranking/iterations').glob('iteration_all_*.json'), reverse=True)
latest_iter = {}
latest_iter_ts = '?'
if iter_files:
    d = json.loads(iter_files[0].read_text())
    latest_iter_ts = d.get('hkt_timestamp', iter_files[0].stem)
    for r in d['results']:
        agent = r.get('agent', '').replace('yw-', '')
        latest_iter[agent] = r

# 6. Backtest 4d
bt_path = REPO / 'automation/reports/strategy_ranking/backtest_4d_2026-08-25.json'
bt4 = {}
if bt_path.exists():
    d = json.loads(bt_path.read_text())
    for s in d.get('strategies', []):
        bt4[s.get('strategy', '')] = s

# 7. Backtest 20d
bt20_path = REPO / 'automation/reports/strategy_ranking/ranking_2026-08-25.json'
bt20 = {}
if bt20_path.exists():
    d = json.loads(bt20_path.read_text())
    for s in d.get('strategies', []):
        bt20[s.get('strategy_id', '')] = s

# Build unified per-strategy
ALL = ['H-Pattern', '3-Pushes', 'Two-Yang', 'RSI-Div', '50-20-Pullback',
       'Stair Pattern', 'CRT', 'Kell Cycle', 'OCS BTC 5m']

def perf_for(trades_list):
    closed = [t for t in trades_list if t.get('status') == 'closed']
    n = len(closed)
    wins = sum(1 for t in closed if t.get('R_multiple', 0) > 0)
    gw = sum(t.get('R_multiple', 0) for t in closed if t.get('R_multiple', 0) > 0)
    gl = abs(sum(t.get('R_multiple', 0) for t in closed if t.get('R_multiple', 0) <= 0))
    pf = gw / (gl + 1e-9) if gl > 0 else (10.0 if gw > 0 else 0.0)
    pf = min(pf, 10.0) if n else 0.0
    return {
        'n': n, 'wins': wins, 'losses': n - wins,
        'wr': round(wins / n * 100, 1) if n else 0,
        'R': round(sum(t.get('R_multiple', 0) for t in closed), 2),
        'pf': round(pf, 2),
        'pnl': round(sum(t.get('pnl_usd', 0) for t in closed), 2),
    }


# Map strategy_ranking id → name
sid_to_name = {v['id']: v['name'] for v in weights.values()}

strategies_out = []
for sid, w in weights.items():
    name = w['name']
    live_24h = [t for t in last24h if t.get('strategy') == name]
    today = [t for t in today_trades if t.get('strategy') == name]
    sigs_24h = [s for s in last24h_sigs if s.get('strategy') == name]
    iter_ = latest_iter.get(sid, {})

    cfg = grader_cfg.get({
        'h-pattern': 'H-Pattern', '3-pushes': '3-Pushes', 'two-yang': 'Two-Yang-One-Yin',
        'rsi-div': 'RSI-Divergence', '50-20-pullback': '50-20-Pullback',
        'stair-pattern': 'Stair-Pattern', 'crt': 'CRT', 'kell-cycle': 'Kell-Cycle',
    }.get(sid, ''), {})

    bt4_s = bt4.get(sid, {})
    bt20_s = bt20.get(sid, {})

    strategies_out.append({
        'id': sid,
        'name': name,
        'agent': f"yw-{sid}",
        'ticker': w['ticker'],
        'weight': w['weight'],
        'optim_date': w['optim_date'],
        'timeframe': cfg.get('timeframe', '5min'),
        'r_multiples': cfg.get('r_multiples', [1, 1.618, 2.618, 3.618, 5]),
        'live_24h': perf_for(live_24h),
        'live_today': perf_for(today),
        'signals_24h': len(sigs_24h),
        'backtest_4d': {
            'n_trades': bt4_s.get('n_trades', 0),
            'wr': bt4_s.get('win_rate', 0),
            'R': bt4_s.get('total_R', 0),
            'pf': bt4_s.get('profit_factor', 0),
        },
        'backtest_20d': {
            'n_trades': bt20_s.get('n_trades', 0),
            'wr': bt20_s.get('win_rate', 0),
            'R': bt20_s.get('total_R', 0),
            'pf': bt20_s.get('profit_factor', 0),
        },
        'iteration': {
            'grade': iter_.get('grade', '?'),
            'confidence': iter_.get('confidence', 0),
            'reason': iter_.get('reason', '')[:200],
        },
    })

# Aggregate
total_24h = sum(s['live_24h']['n'] for s in strategies_out)
total_today = sum(s['live_today']['n'] for s in strategies_out)
total_R_24h = sum(s['live_24h']['R'] for s in strategies_out)
total_sigs_24h = sum(s['signals_24h'] for s in strategies_out)
total_w_24h = sum(s['live_24h']['wins'] for s in strategies_out)

out = {
    'generated_at': HKT_STR,
    'hkt_timestamp': now.isoformat(),
    'window': 'last_24h + today',
    'aggregate': {
        'trades_24h': total_24h,
        'trades_today': total_today,
        'wins_24h': total_w_24h,
        'R_24h': round(total_R_24h, 2),
        'signals_24h': total_sigs_24h,
        'wr_24h': round(total_w_24h / total_24h * 100, 1) if total_24h else 0,
    },
    'strategies': strategies_out,
}

out_path = REPO / 'docs' / 'dashboard-data.json'
out_path.write_text(json.dumps(out, indent=2, default=str))
print(f"✓ Saved: {out_path} ({out_path.stat().st_size:,} bytes)")
print(f"  Trades 24h: {total_24h} | R: {total_R_24h:+.2f} | Sigs: {total_sigs_24h}")
