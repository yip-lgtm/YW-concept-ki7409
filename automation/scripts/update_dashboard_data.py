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

def parse_ts_safe(ts_str):
    """Parse ISO timestamp with mixed tz (UTC +00:00, EDT -04:00) → UTC datetime."""
    if not ts_str: return None
    try:
        ts_str = ts_str.replace("Z", "+00:00").replace(" ", "T")
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None
now = datetime.now(HKT)
HKT_STR = now.strftime("%Y-%m-%d %H:%M HKT")

def regenerate_24h_ranking():
    """Regenerate ranking_24h.json from real trades (handles mixed tz)."""
    from collections import defaultdict
    UTC = timezone.utc
    now_utc = datetime.now(UTC)
    cutoff_dt = now_utc - timedelta(hours=24)
    
    trades = []
    for path in [REPO / "automation/reports/live_scan/trades.jsonl",
                 REPO / "automation/reports/ocs_btc_5m/trades.jsonl"]:
        try:
            with open(path) as f:
                for l in f:
                    l = l.strip()
                    if not l or l.startswith(("<", "=", ">")): continue
                    try: trades.append(json.loads(l))
                    except: pass
        except FileNotFoundError:
            pass
    
    # 24h with proper tz parse
    last24 = []
    for t in trades:
        et = parse_ts_safe(t.get("exit_time", ""))
        if et and et >= cutoff_dt:
            last24.append(t)
    
    # Group by strategy
    by_strat = defaultdict(list)
    for t in last24:
        s = t.get("strategy", "unknown")
        by_strat[s].append(t)
    
    ranking = []
    for strat, tlist in by_strat.items():
        n = len(tlist)
        wins = [t for t in tlist if t.get("R_multiple", 0) > 0]
        losses = [t for t in tlist if t.get("R_multiple", 0) <= 0]
        total_R = sum(t.get("R_multiple", 0) for t in tlist)
        total_pnl = sum(t.get("pnl_usd", 0) for t in tlist)
        wr = len(wins) / n * 100 if n > 0 else 0
        gross_win = sum(t.get("R_multiple", 0) for t in wins)
        gross_loss = abs(sum(t.get("R_multiple", 0) for t in losses))
        pf = gross_win / gross_loss if gross_loss > 0 else (10.0 if gross_win > 0 else 0)
        # Extract ticker from first trade
        tk = tlist[0].get("ticker", "—")
        ranking.append({
            "strategy": strat,
            "ticker": tk,
            "n_trades": n, "n_wins": len(wins), "n_losses": len(losses),
            "win_rate": round(wr, 1),
            "total_R": round(total_R, 2),
            "avg_R": round(total_R / n, 3) if n > 0 else 0,
            "total_pnl_usd": round(total_pnl, 2),
            "profit_factor": round(pf, 2),
        })

    # 9/22 收緊版: sort by total_pnl_usd, then PF, then WR (NOT by total_R)
    ranking.sort(key=lambda x: (x["total_pnl_usd"], x["profit_factor"], x["win_rate"]),
                 reverse=True)
    n_disqualified = sum(1 for r in ranking if r["n_trades"] < 10)
    for i, r in enumerate(ranking):
        r["rank"] = i + 1
        r["medal_eligible"] = r["n_trades"] >= 10

    out = {
        "date": now_utc.astimezone(HKT).strftime("%Y-%m-%d"),
        "window_hours": 24,
        "hkt_timestamp": now_utc.isoformat(),
        "type": "24h_live_ranking",
        "sort": "Total $ → PF → WR (R as footnote, per 9/22 收緊版)",
        "n_total": len(last24),
        "n_disqualified_medal": n_disqualified,
        "ranking": ranking,
    }
    ranking_24h_path = REPO / "automation/reports/strategy_ranking/24h/ranking_24h.json"
    ranking_24h_path.write_text(json.dumps(out, indent=2))
    print(f"  [regen] 24h ranking: {len(ranking)} strategies, {len(last24)} trades")
    return out

# Auto-regenerate 24h ranking on every dashboard update
regenerate_24h_ranking()

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
            line = line.strip()
            if not line or line.startswith(('<', '=', '>')): continue
            try: all_trades.append(json.loads(line))
            except: pass
if (OCS / 'trades.jsonl').exists():
    with open(OCS / 'trades.jsonl') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(('<', '=', '>')): continue
            try:
                t = json.loads(line)
                t['strategy'] = 'OCS BTC 5m'
                all_trades.append(t)
            except: pass


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

# 4b. 24h Live Ranking (from real closed trades)
RANKING_24H_FILE = REPO / 'automation/reports/strategy_ranking/24h/ranking_24h.json'
ranking_24h_list = []
ranking_24h_agg = {"n_trades": 0, "n_wins": 0, "win_rate": 0, "total_R": 0, "total_pnl_usd": 0}
ranking_24h_updated = None
r24 = None
if RANKING_24H_FILE.exists():
    try:
        with open(RANKING_24H_FILE) as f:
            r24 = json.load(f)
        ranking_24h_list = r24.get("ranking", [])
        if ranking_24h_list:
            n_total = sum(r.get("n_trades", 0) for r in ranking_24h_list)
            n_wins = sum(r.get("n_wins", 0) for r in ranking_24h_list)
            total_R = sum(r.get("total_R", 0) for r in ranking_24h_list)
            total_pnl = sum(r.get("total_pnl_usd", 0) for r in ranking_24h_list)
            ranking_24h_agg = {
                "n_trades": n_total,
                "n_wins": n_wins,
                "win_rate": round(n_wins / n_total * 100, 1) if n_total > 0 else 0,
                "total_R": round(total_R, 2),
                "total_pnl_usd": round(total_pnl, 2),
            }
        ranking_24h_updated = r24.get("hkt_timestamp") if r24 else None
        print(f"  24h ranking: {len(ranking_24h_list)} strategies, {n_total} trades")
    except Exception as e:
        print(f"  24h ranking load error: {e}")

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
    # Fuzzy match: handle "Stair" vs "Stair Pattern", "Kell-Cycle" vs "Kell Cycle", etc.
    def _match(t_or_s_name, target_name):
        if t_or_s_name == target_name:
            return True
        t = t_or_s_name.lower().replace('-', '').replace('_', '')
        n = target_name.lower().replace('-', '').replace('_', '')
        return (t in n) or (n in t)
    live_24h = [t for t in last24h if _match(t.get('strategy', ''), name)]
    today = [t for t in today_trades if _match(t.get('strategy', ''), name)]
    sigs_24h = [s for s in last24h_sigs if _match(s.get('strategy', ''), name)]
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

# ================== AGENT CONTROL (2026-10-08) ==================
# Settlement levels + data-driven weight optimization, so the Review Hub
# shows what the pipeline decided overnight instead of only reporting
# performance after the fact.
def _load_json(p):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None

# Settlement: current level per agent + promotion/demotion history
levels_state = _load_json(REPO / 'automation' / 'config' / 'strategy_levels.json') or {}
agent_levels = []
for name, v in levels_state.items():
    if name.startswith('_') or not isinstance(v, dict):
        continue
    hist = v.get('history') or []
    last = hist[-1] if hist else None
    agent_levels.append({
        'strategy': name,
        'level': v.get('level', 1),
        'last_settled': v.get('last_settled'),
        'n_changes': len(hist),
        'last_action': (last or {}).get('action'),
        'last_reason': (last or {}).get('reason'),
        'last_change_date': (last or {}).get('date'),
    })
agent_levels.sort(key=lambda x: (-x['level'], x['strategy']))

# Settlement overrides (LLM auto-lowered conditions for stuck agents)
sett_ov_raw = _load_json(REPO / 'automation' / 'config' / 'settlement_overrides.json') or {}
settlement_overrides = []
for name, v in sett_ov_raw.items():
    if name.startswith('_') or not isinstance(v, dict):
        continue
    settlement_overrides.append({
        'strategy': name,
        'action': v.get('action'),
        'reasoning': v.get('reasoning', ''),
        'overrides': v.get('overrides', {}),
        'last_revised': v.get('last_revised'),
        'stuck_days_at_revision': v.get('stuck_days_at_revision'),
    })

# Weight optimization: latest report + effective weights
weight_files = sorted((REPO / 'automation' / 'reports' / 'weight_optimization').glob('weight_*.json'))
weight_opt = None
if weight_files:
    wj = _load_json(weight_files[-1]) or {}
    weight_opt = {
        'date': wj.get('date'),
        'window_days': wj.get('window_days'),
        'generated_from': weight_files[-1].name,
        'candidates': [
            {
                'strategy': c['strategy'],
                'n': c['metrics']['n'],
                'pf': c['metrics']['pf'],
                'wr': c['metrics']['wr'],
                'rr': c['metrics']['rr'],
                'edge': c['detail'].get('edge_index'),
                'shrink': c['detail'].get('shrink'),
                'current': c['current'],
                'target': c['target'],
                'delta': c['delta'],
                'status': c['status'],
                'llm': (c.get('llm_check') or {}).get('llm'),
            }
            for c in wj.get('candidates', [])
        ],
    }

# Effective weights = live_scan defaults < LLM overrides < data-driven overrides
w_ov = _load_json(REPO / 'automation' / 'config' / 'weight_overrides.json') or {}
effective_weights = []
for s in strategies_out:
    nm = s.get('name')
    if not nm:
        continue
    w = s.get('weight', 1.0)
    src = 'default'
    lo = (w_ov or {}).get(nm)
    if isinstance(lo, dict) and isinstance(lo.get('weight'), (int, float)):
        w = float(lo['weight']); src = 'data-driven'
    effective_weights.append({'strategy': nm, 'weight': round(float(w), 3), 'source': src})
effective_weights.sort(key=lambda x: -x['weight'])

# ================== TTRADES FAMILY (2026-10-09) ==================
# 4 strategies (Fractal base + L12/L13/L14) x 3 tickers (MNQ/MGC/BTC).
# The L-series detectors publish a fired/not-fired verdict with a readable
# rejection reason rather than trade levels, so the useful thing to surface
# is the current gate state per agent, not a P&L number.
TT_DIR = REPO / 'automation/reports/ttrades_btc'
TT_TICKERS = [('MNQ=F', 'MNQF'), ('MGC=F', 'MGCF'), ('BTC-USD', 'BTCUSD')]


def _tt_agents():
    out = []
    for tk, slug in TT_TICKERS:
        base_f = _load_json(TT_DIR / f'latest_{slug}.json') or {}
        l_f = _load_json(TT_DIR / f'l_strategies_latest_{slug}.json') or {}
        l_res = l_f.get('strategies') or {}
        out.append({
            'ticker': tk,
            'updated': l_f.get('ts') or base_f.get('ts'),
            'base': {
                'strategy': 'TTrades-Fractal',
                'actionable': bool(base_f.get('actionable')),
                'reason': base_f.get('reason'),
                'ts': base_f.get('ts'),
            },
            'l_series': [
                {
                    'strategy': name,
                    'fired': bool(r.get('fired')),
                    'stage': r.get('stage'),
                    'detail': r.get('detail'),
                    'direction': r.get('direction'),
                    'closure': r.get('closure'),
                    'trade_candle': r.get('trade_candle'),
                    'poi_note': r.get('poi_note'),
                    'entry_ref': r.get('entry_ref'),
                    'swing_level': r.get('swing_level'),
                    'target_r': r.get('target_r'),
                    'has_levels': bool(r.get('has_levels')),
                    'entry': r.get('entry'),
                    'sl': r.get('sl'), 't1': r.get('t1'),
                    't2_close': r.get('t2_close'), 'risk': r.get('risk'),
                    'sl_basis': r.get('sl_basis'),
                }
                for name, r in l_res.items()
            ],
        })
    return out


_tt_trades = []
try:
    _tp = TT_DIR / 'trades.jsonl'
    if _tp.exists():
        for line in _tp.read_text(errors='ignore').splitlines():
            line = line.strip()
            if not line or line[0] in '<=>':
                continue
            try:
                _tt_trades.append(json.loads(line))
            except Exception:
                continue
except Exception:
    pass
_tt_positions = _load_json(TT_DIR / 'positions.json') or {}

_tt_by_agent = defaultdict(list)
for _t in _tt_trades:
    _tt_by_agent[_t.get('strategy', '?')].append(_t)

_tt_perf = []
for _name in ['TTrades-Fractal', 'TTrades-L12', 'TTrades-L13', 'TTrades-L14']:
    _ts = _tt_by_agent.get(_name, [])
    if not _ts:
        _tt_perf.append({'strategy': _name, 'n': 0, 'pf': 0, 'wr': 0,
                         'total_r': 0, 'pnl': 0, 'tickers': {}})
        continue
    _R = [float(t.get('R_multiple', 0) or 0) for t in _ts]
    _w = [r for r in _R if r > 0]
    _l = [r for r in _R if r <= 0]
    _gw, _gl = sum(_w), abs(sum(_l))
    _tkc = defaultdict(int)
    for t in _ts:
        _tkc[t.get('ticker', '?')] += 1
    _tt_perf.append({
        'strategy': _name,
        'n': len(_ts),
        'pf': round(_gw / _gl, 2) if _gl > 0 else (10.0 if _gw > 0 else 0.0),
        'wr': round(len(_w) / len(_R) * 100, 1),
        'total_r': round(sum(_R), 2),
        'pnl': round(sum(float(t.get('pnl_usd', 0) or 0) for t in _ts), 2),
        'tickers': dict(_tkc),
    })

ttrades = {
    'agents': _tt_agents(),
    'performance': _tt_perf,
    'open_positions': [
        {
            'strategy': p.get('strategy'), 'ticker': p.get('ticker'),
            'direction': p.get('direction'), 'entry': p.get('entry'),
            'sl': p.get('sl'), 't2': p.get('t2'),
            'entry_time': p.get('entry_time'), 'status': p.get('status'),
        }
        for p in (_tt_positions.values() if isinstance(_tt_positions, dict) else [])
        if p.get('status') == 'open'
    ],
    'n_closed': len(_tt_trades),
    'note': ('All four agents publish entry/SL/T1/T2 (T2 closes at 1.618R) as of '
             '2026-10-09, so the whole family is trackable and scoreable. A fired '
             'row with has_levels=false means the stop reference sat on the wrong '
             'side of entry, which is reported rather than papered over.'),
}

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
    'ranking_24h': ranking_24h_list,
    'ranking_24h_aggregate': ranking_24h_agg,
    'ranking_24h_updated': r24.get("hkt_timestamp") if r24 else None,
    'strategies': strategies_out,
    'ttrades': ttrades,
    'agent_control': {
        'levels': agent_levels,
        'settlement_overrides': settlement_overrides,
        'weight_optimization': weight_opt,
        'effective_weights': effective_weights,
    },
}

out_path = REPO / 'docs' / 'dashboard-data.json'
out_path.write_text(json.dumps(out, indent=2, default=str))
print(f"✓ Saved: {out_path} ({out_path.stat().st_size:,} bytes)")
print(f"  Trades 24h: {total_24h} | R: {total_R_24h:+.2f} | Sigs: {total_sigs_24h}")
