#!/usr/bin/env python3
"""Regenerate review manifests for review.html.

Outputs:
- docs/charts-manifest.json (latest 500 signal charts)
- docs/trades-manifest.json (latest 500 trades)
- docs/rankings-manifest.json (all daily rankings)
- docs/llm-iterations-manifest.json (latest 100 LLM iterations)
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

REPO = Path('/workspace/YW-concept-ki7409') if Path('/workspace/YW-concept-ki7409').exists() else Path('/workspace/YW-concept-ki7409')
UTC = timezone.utc


def safe_read_jsonl(path: Path) -> list:
    """Read JSONL skipping conflict markers + bad lines."""
    items = []
    if not path.exists():
        return items
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(('<', '=', '>')):
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                pass
    return items


def gen_charts_manifest() -> dict:
    """List latest 500 signal charts."""
    chart_dir = REPO / 'automation/reports/signal_charts'
    charts = []
    if chart_dir.exists():
        for f in sorted(chart_dir.glob('*.png'), reverse=True):
            name = f.stem
            parts = name.rsplit('_', 1)
            if len(parts) != 2:
                continue
            strat_ticker, ts_str = parts
            # Strategy_Ticker pattern - find ticker suffix
            for ticker in ['BTC-USD', 'MNQ=F', 'MES=F', 'M2K=F', 'MGC=F']:
                if strat_ticker.endswith('_' + ticker):
                    strategy = strat_ticker[:-(len(ticker) + 1)]
                    break
            else:
                strategy = strat_ticker
                ticker = '?'
            charts.append({
                'strategy': strategy,
                'ticker': ticker,
                'ts': ts_str,
                'file': f.name,
            })
    return {
        'generated_at': datetime.now(UTC).isoformat(),
        'count': len(charts),
        'charts': charts[:500],
    }


def gen_trades_manifest() -> dict:
    """Latest 500 trades from live_scan + OCS."""
    trades = safe_read_jsonl(REPO / 'automation/reports/live_scan/trades.jsonl')
    return {
        'generated_at': datetime.now(UTC).isoformat(),
        'count': len(trades),
        'trades': trades[-500:],
    }


def gen_rankings_manifest() -> dict:
    """All daily rankings."""
    ranking_dir = REPO / 'automation/reports/strategy_ranking'
    rankings = []
    if ranking_dir.exists():
        for f in sorted(ranking_dir.glob('ranking_2026-*.json'), reverse=True):
            try:
                d = json.loads(f.read_text())
                rankings.append({
                    'date': f.stem.replace('ranking_', ''),
                    'data': d,
                })
            except Exception:
                pass
    return {
        'generated_at': datetime.now(UTC).isoformat(),
        'count': len(rankings),
        'rankings': rankings,
    }


def gen_llm_iterations_manifest() -> dict:
    """Latest 100 LLM iteration files."""
    iter_dir = REPO / 'automation/reports/strategy_ranking/iterations'
    iterations = []
    if iter_dir.exists():
        for f in sorted(iter_dir.glob('*.json'), reverse=True)[:100]:
            try:
                d = json.loads(f.read_text())
                iterations.append({
                    'date': f.stem.replace('iteration_', ''),
                    'data': d,
                })
            except Exception:
                pass
    return {
        'generated_at': datetime.now(UTC).isoformat(),
        'count': len(iterations),
        'iterations': iterations,
    }


def main():
    docs = REPO / 'docs'
    docs.mkdir(exist_ok=True)

    charts_m = gen_charts_manifest()
    (docs / 'charts-manifest.json').write_text(json.dumps(charts_m, indent=2))
    print(f'✓ charts-manifest.json: {charts_m["count"]} charts')

    trades_m = gen_trades_manifest()
    (docs / 'trades-manifest.json').write_text(json.dumps(trades_m, indent=2, default=str))
    print(f'✓ trades-manifest.json: {trades_m["count"]} trades')

    rankings_m = gen_rankings_manifest()
    (docs / 'rankings-manifest.json').write_text(json.dumps(rankings_m, indent=2, default=str))
    print(f'✓ rankings-manifest.json: {rankings_m["count"]} rankings')

    llm_m = gen_llm_iterations_manifest()
    (docs / 'llm-iterations-manifest.json').write_text(json.dumps(llm_m, indent=2, default=str))
    print(f'✓ llm-iterations-manifest.json: {llm_m["count"]} iterations')

    print(f'\nAll manifests regenerated at {datetime.now(UTC).isoformat()}')


if __name__ == '__main__':
    main()
