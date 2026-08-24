#!/usr/bin/env python3
"""LLM-driven strategy iteration.

Reads daily ranking + per-strategy backtest results, asks MiniMax-M3 LLM
to suggest parameter improvements for the worst-performing strategy.

Workflow:
1. Read strategy_ranking/history.jsonl (last N days)
2. Identify worst performer (lowest PF)
3. Query MiniMax-M3 with strategy + backtest details
4. Save iteration log to iterations/iteration_*.md
"""
from __future__ import annotations
import os
import sys
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# Auto-detect repo
if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

# Strategy param templates
STRATEGY_PARAMS = {
    "h-pattern": {"weight": 1.2, "timeframe": "3min/5min", "indicators": ["pivot", "momentum", "support"]},
    "3-pushes": {"weight": 1.0, "timeframe": "5min/15min", "indicators": ["trend", "push_count"]},
    "two-yang": {"weight": 0.8, "timeframe": "15min", "indicators": ["candle_pattern"]},
    "rsi-div": {"weight": 1.1, "timeframe": "1/3/5min", "indicators": ["rsi", "divergence"]},
    "50-20-pullback": {"weight": 1.0, "timeframe": "5min", "indicators": ["ema20", "sma50", "pullback"]},
    "stair-pattern": {"weight": 0.9, "timeframe": "5min", "indicators": ["step_pattern"]},
    "crt": {"weight": 1.1, "timeframe": "5min+4H", "indicators": ["candle_range", "htf_confirm"]},
    "kell-cycle": {"weight": 0.9, "timeframe": "5min", "indicators": ["cycle", "5_subdetectors"]},
    "ocs-btc": {"weight": 1.0, "timeframe": "5min", "indicators": ["8_features", "knn_k7"]},
}


def call_minimax(prompt: str) -> str:
    """Call MiniMax-M3 LLM (Anthropic-compatible API)."""
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        return ""

    # MiniMax-M3 (OpenAI-compatible API)
    url = "https://api.minimax.io/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "MiniMax-M3",
        "max_tokens": 1500,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": "You are a quantitative trading strategy optimizer. Analyze strategy performance and suggest specific parameter changes. Output as JSON only with keys: weight (0.5-1.5), timeframe, indicators (list), r_multiples (list), rationale."},
            {"role": "user", "content": prompt},
        ],
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            data = r.json()
            choices = data.get("choices", [])
            if choices and isinstance(choices, list):
                return choices[0].get("message", {}).get("content", "")
        else:
            print(f"  LLM HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"  LLM error: {e}")
    return ""


def load_history(days: int = 7) -> list:
    """Load last N days of ranking history."""
    history_path = REPO / "automation/reports/strategy_ranking/history.jsonl"
    if not history_path.exists():
        return []
    lines = history_path.read_text().strip().split("\n")
    return [json.loads(line) for line in lines[-days:] if line.strip()]


def find_worst_strategy(history: list) -> dict:
    """Find strategy with worst avg PF over history."""
    if not history:
        return None
    pf_by_strat = {}
    for day in history:
        for r in day.get("ranking", []):
            sid = r["strategy_id"]
            pf_by_strat.setdefault(sid, []).append(r["pf"])
    if not pf_by_strat:
        return None
    avg_pf = {sid: sum(pfs) / len(pfs) for sid, pfs in pf_by_strat.items()}
    worst_id = min(avg_pf, key=avg_pf.get)
    for day in reversed(history):
        for r in day.get("ranking", []):
            if r["strategy_id"] == worst_id:
                return {**r, "avg_pf": round(avg_pf[worst_id], 3)}
    return None


def build_prompt(worst: dict, history: list) -> str:
    """Build LLM prompt for strategy improvement."""
    sid = worst["strategy_id"]
    params = STRATEGY_PARAMS.get(sid, {})

    history_text = "\n".join([
        f"  {day['date']}: rank #{r.get('rank', '?')} - PF {r['pf']}, R {r['total_R']}, WR {r['win_rate']}%, N={r['n_trades']}"
        for day in history[-7:]
        for r in day.get("ranking", [])
        if r["strategy_id"] == sid
    ])

    return f"""# Strategy Optimization Request

## Current Strategy: {sid} ({worst['name']})

## Current Performance
- Rank: #{worst.get('rank', 'N/A')}
- Profit Factor: {worst['pf']}
- Total R: {worst['total_R']}
- Win Rate: {worst['win_rate']}%
- Trades: {worst['n_trades']}
- 7d Avg PF: {worst['avg_pf']}

## Current Parameters
{json.dumps(params, indent=2)}

## 7-Day History
{history_text if history_text else '(no history)'}

## Task
Suggest specific parameter changes to improve this strategy. Focus on:
1. **weight** (0.5-1.5): priority in daily reminder ranking
2. **timeframe**: which candle intervals to focus on
3. **indicators**: which technical indicators to combine
4. **r_multiples**: take-profit targets [T1, T2, T3, T4, T5] in R units

Output as JSON only. Example:
{{"weight": 1.1, "timeframe": "5min", "indicators": ["rsi", "ema"], "r_multiples": [1.0, 1.5, 2.0, 3.0, 4.0], "rationale": "..."}}"""


def parse_llm_response(text: str) -> dict:
    """Extract JSON from LLM response."""
    if not text:
        return {"_empty": True}
    json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"rationale": text, "_parse_error": True}


def main():
    HKT = timezone(timedelta(hours=8))
    today_hkt = datetime.now(HKT).strftime("%Y-%m-%d")
    now_hkt = datetime.now(HKT).strftime("%Y%m%d_%H%M%S")

    print(f"[iterate] Loading ranking history...")
    history = load_history(days=7)
    if not history:
        print("[iterate] No history available, skipping iteration")
        return 0

    worst = find_worst_strategy(history)
    if not worst:
        print("[iterate] No worst strategy identified")
        return 0

    print(f"[iterate] Worst strategy: {worst['name']} (PF {worst['pf']}, avg {worst['avg_pf']})")

    prompt = build_prompt(worst, history)
    print(f"[iterate] Querying MiniMax-M3 LLM...")
    response = call_minimax(prompt)

    if not response:
        print("[iterate] LLM returned no response")
        out_dir = REPO / "automation/reports/strategy_ranking/iterations"
        out_dir.mkdir(parents=True, exist_ok=True)
        log_path = out_dir / f"iteration_{now_hkt}.json"
        log_path.write_text(json.dumps({
            "date": today_hkt,
            "worst_strategy": worst,
            "llm_response": "",
            "suggested_params": None,
            "_note": "LLM unavailable (rate limit, no key, or no quota)",
        }, indent=2))
        return 0

    suggested = parse_llm_response(response)
    print(f"[iterate] LLM suggested: {json.dumps(suggested, default=str)[:200]}")

    out_dir = REPO / "automation/reports/strategy_ranking/iterations"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"iteration_{now_hkt}.json"
    log_path.write_text(json.dumps({
        "date": today_hkt,
        "worst_strategy": worst,
        "llm_response": response[:1500],
        "suggested_params": suggested,
    }, indent=2, default=str))
    print(f"[iterate] Saved: {log_path}")

    md_path = out_dir / f"iteration_{now_hkt}.md"
    md_content = f"""# Strategy Iteration - {today_hkt}

## Worst Performer
**{worst['name']}** (rank #{worst.get('rank', '?')})

- Profit Factor: {worst['pf']}
- Total R: {worst['total_R']:+.0f}
- Win Rate: {worst['win_rate']}%
- Trades: {worst['n_trades']}
- 7d Avg PF: {worst['avg_pf']}

## Current Parameters
```json
{json.dumps(STRATEGY_PARAMS.get(worst['strategy_id'], {}), indent=2)}
```

## LLM-Suggested Parameters
```json
{json.dumps(suggested, indent=2, default=str)}
```

## LLM Response (raw)
{response[:800]}

## Action
Review suggested params. If confident, manually update STRATEGY_PARAMS in:
- `automation/src/yw_indicators.py` (for YW strategies)
- `automation/src/ocs_btc_5m.py` (for OCS)

Then re-run `python scripts/strategy_ranking.py` to verify improvement.
"""
    md_path.write_text(md_content)
    print(f"[iterate] MD: {md_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
