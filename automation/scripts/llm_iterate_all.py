#!/usr/bin/env python3
"""Per-strategy LLM iteration - each of 9 strategy agents gets its own iteration.

Each strategy's sub-agent (yw-h-pattern, yw-3-pushes, etc.) reviews its own
performance and queries MiniMax-M3 for optimization suggestions specific to
that strategy's behavior. Suggestions are logged + applied (if high confidence).
"""
from __future__ import annotations
import os
import sys
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

ITER_DIR = REPO / "automation/reports/strategy_ranking/iterations"
ITER_DIR.mkdir(parents=True, exist_ok=True)

# 9 strategy sub-agents (matching Mavis agent names)
AGENTS = [
    {"id": "h-pattern",        "agent": "yw-h-pattern",        "ticker": "MNQ=F",  "weight": 1.2, "tf": "3min/5min", "indicators": ["pivot", "momentum", "support"]},
    {"id": "3-pushes",         "agent": "yw-3-pushes",         "ticker": "MNQ=F",  "weight": 1.0, "tf": "5min/15min", "indicators": ["trend", "push_count"]},
    {"id": "two-yang",         "agent": "yw-two-yang",         "ticker": "MNQ=F",  "weight": 0.5, "tf": "5min",      "indicators": ["candle_pattern", "ema20", "adx", "volume"]},
    {"id": "rsi-div",          "agent": "yw-rsi-div",          "ticker": "MNQ=F",  "weight": 0.7, "tf": "15min",     "indicators": ["rsi", "divergence", "ema50", "volume"]},
    {"id": "50-20-pullback",   "agent": "yw-50-20-pullback",   "ticker": "MNQ=F",  "weight": 1.0, "tf": "5min",      "indicators": ["ema20", "sma50", "pullback"]},
    {"id": "stair-pattern",    "agent": "yw-stair-pattern",    "ticker": "MNQ=F",  "weight": 0.9, "tf": "5min",      "indicators": ["step_pattern"]},
    {"id": "crt",              "agent": "yw-crt",              "ticker": "MNQ=F",  "weight": 1.1, "tf": "5min+4H",   "indicators": ["candle_range", "htf_confirm"]},
    {"id": "kell-cycle",       "agent": "yw-kell-cycle",       "ticker": "MNQ=F",  "weight": 0.9, "tf": "5min",      "indicators": ["cycle", "5_subdetectors"]},
    {"id": "ocs-btc",          "agent": "ocs-btc-5m",          "ticker": "BTC-USD","weight": 1.0, "tf": "5min",      "indicators": ["8_features", "knn_k7"]},
]


def call_minimax(prompt: str, system: str = "") -> str:
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        return ""
    r = requests.post(
        "https://api.minimax.io/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "MiniMax-M3",
            "max_tokens": 1024,
            "messages": [
                {"role": "system", "content": system or "你是策略 sub-agent。直接輸出 GRADE/CONFIDENCE/REASON + suggested_params。"},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=45,
    )
    return r.json()["choices"][0]["message"]["content"]


def parse_response(content: str) -> dict:
    if "</think>" in content:
        content = content.split("</think>")[-1].strip()
    m = re.search(r"GRADE:\s*([ABCD?])\s*\|\s*CONFIDENCE:\s*(\d+)\s*\|\s*REASON:\s*(.+)", content, re.IGNORECASE)
    grade = m.group(1).upper() if m else "?"
    conf = int(m.group(2)) if m else 0
    reason = m.group(3).strip()[:200] if m else "no parse"
    weight_m = re.search(r"weight['\"]?\s*[:=]\s*([0-9.]+)", content)
    tf_m = re.search(r"timeframe['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9/+]+)", content)
    r_m = re.search(r"r_multiples['\"]?\s*[:=]\s*\[([^\]]+)\]", content)
    ind_m = re.search(r"indicators['\"]?\s*[:=]\s*\[([^\]]+)\]", content)
    rat_m = re.search(r'rationale["\']?\s*[:=]\s*["\']?([^"\']{20,500})', content)
    return {
        "grade": grade,
        "confidence": conf,
        "reason": reason,
        "weight": float(weight_m.group(1)) if weight_m else None,
        "timeframe": tf_m.group(1) if tf_m else None,
        "r_multiples": [float(x.strip()) for x in r_m.group(1).split(",")] if r_m else None,
        "indicators": [x.strip().strip("'\"") for x in ind_m.group(1).split(",")] if ind_m else None,
        "rationale": rat_m.group(1) if rat_m else reason,
    }


def load_live_trades_for(strategy_id: str) -> list:
    """Load recent live trades for a strategy from live_scan/trades.jsonl."""
    trades = []
    fp = REPO / "automation/reports/live_scan/trades.jsonl"
    if not fp.exists():
        return []
    with open(fp) as f:
        for line in f:
            t = json.loads(line)
            # Match strategy (e.g. "Two-Yang" vs "two-yang")
            if strategy_id.replace("-", " ").lower() in t.get("strategy", "").lower():
                trades.append(t)
    return trades


def iterate_strategy(agent: dict) -> dict:
    """Run LLM iteration for one strategy agent."""
    # Get live trade data
    live_trades = load_live_trades_for(agent["id"])
    n = len(live_trades)
    if n == 0:
        # No live trades — use static backtest stats
        # Find in today's ranking
        today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        ranking_fp = REPO / f"automation/reports/strategy_ranking/ranking_{today}.json"
        if ranking_fp.exists():
            data = json.loads(ranking_fp.read_text())
            strat_data = next((s for s in data.get("strategies", []) if s.get("strategy_id") == agent["id"]), None)
            if strat_data:
                pf = strat_data.get("pf", 1.0)
                wr = strat_data.get("win_rate", 0)
                total_r = strat_data.get("total_R", 0)
                n = strat_data.get("n_trades", 0)
            else:
                pf, wr, total_r, n = 1.0, 50, 0, 0
        else:
            pf, wr, total_r, n = 1.0, 50, 0, 0
        live_section = f"Backtest: {n} trades, WR {wr}%, PF {pf}, R {total_r:+.0f}"
        ticker_breakdown = ""
    else:
        wins = sum(1 for t in live_trades if t["R_multiple"] > 0)
        losses = n - wins
        gross_win = sum(t["R_multiple"] for t in live_trades if t["R_multiple"] > 0)
        gross_loss = abs(sum(t["R_multiple"] for t in live_trades if t["R_multiple"] <= 0))
        pf = gross_win / (gross_loss + 1e-9) if gross_loss > 0 else (10.0 if gross_win > 0 else 1.0)
        # Cap PF for LLM context (avoid inf)
        pf = min(pf, 10.0)
        total_r = sum(t["R_multiple"] for t in live_trades)
        wr = wins / n * 100
        live_section = f"Live: {n} trades ({wins}W {losses}L), WR {wr:.0f}%, PF {pf:.2f}, R {total_r:+.1f}"

        # Per ticker
        by_ticker = {}
        for t in live_trades:
            by_ticker.setdefault(t["ticker"], []).append(t)
        ticker_lines = []
        for tk, ts in by_ticker.items():
            tw = sum(1 for t in ts if t["R_multiple"] > 0)
            tr_ = sum(t["R_multiple"] for t in ts)
            ticker_lines.append(f"  {tk}: {len(ts)} trades, {tw} wins, R={tr_:+.2f}")
        ticker_breakdown = "\n".join(ticker_lines)

    prompt = f"""你是 {agent['agent']} sub-agent。Review 自己嘅 live performance:

{live_section}

{ticker_breakdown if ticker_breakdown else "(no ticker breakdown)"}

Current config:
- weight: {agent['weight']}
- timeframe: {agent['tf']}
- indicators: {agent['indicators']}

請用呢個 EXACT format 回答（否則 parse 失敗）:

GRADE: <A/B/C/D> | CONFIDENCE: <0-100> | REASON: <50字內>

suggested_params = {{
  "weight": <0.1-2.0>,
  "timeframe": "<例: 5min 或 15min 或 5min/15min>",
  "indicators": ["<list", "of", "indicators>"],
  "r_multiples": [<T1>, <T2>, <T3>, <T4>, <T5>],
  "rationale": "<具體原因 50字>"
}}

禁止 <think> 標籤。直接輸出。"""

    response = call_minimax(prompt, system=f"你是 {agent['agent']} sub-agent，負責自己嘅 strategy 優化。")
    if not response:
        return {"agent": agent["agent"], "error": "no LLM response"}

    parsed = parse_response(response)
    parsed["agent"] = agent["agent"]
    parsed["strategy_id"] = agent["id"]
    parsed["ticker"] = agent["ticker"]
    parsed["live_n"] = n
    parsed["live_pf"] = round(pf, 2)
    parsed["live_wr"] = round(wr, 1)
    parsed["live_R"] = round(total_r, 2)
    parsed["current_weight"] = agent["weight"]
    parsed["current_timeframe"] = agent["tf"]
    parsed["response_raw"] = response[:1500]
    return parsed


def main():
    HKT = timezone(timedelta(hours=8))
    now = datetime.now(HKT)
    today = now.strftime("%Y-%m-%d")
    ts = now.strftime("%Y%m%d_%H%M%S")

    print(f"[iterate-all] Starting 9-agent LLM iteration @ {ts} HKT")
    print(f"[iterate-all] Using 9 workers in parallel")

    # Run all 9 in parallel
    results = []
    with ThreadPoolExecutor(max_workers=9) as executor:
        futures = {executor.submit(iterate_strategy, agent): agent for agent in AGENTS}
        for future in as_completed(futures):
            agent = futures[future]
            try:
                r = future.result()
                results.append(r)
                grade = r.get("grade", "?")
                conf = r.get("confidence", 0)
                new_w = r.get("weight", "?")
                new_tf = r.get("timeframe", "?")
                print(f"  [{agent['agent']:18s}] grade={grade} conf={conf:3d} → weight={new_w} tf={new_tf}")
            except Exception as e:
                print(f"  [{agent['agent']:18s}] ERROR: {e}")
                results.append({"agent": agent["agent"], "error": str(e)})

    # Save aggregated log
    out_path = ITER_DIR / f"iteration_all_{ts}.json"
    out_path.write_text(json.dumps({
        "date": today,
        "hkt_timestamp": ts,
        "n_strategies": 9,
        "results": results,
    }, indent=2, default=str))
    print(f"\n[iterate-all] Saved: {out_path}")

    # Markdown summary
    md_path = ITER_DIR / f"iteration_all_{ts}.md"
    md_lines = [f"# 9-Agent Per-Strategy LLM Iteration — {today}\n"]
    md_lines.append(f"**{len(results)}** strategies iterated in parallel.\n")
    md_lines.append("| Agent | Live PF | Live R | LLM Grade | LLM Conf | New Weight | New TF | New R-Multiples |")
    md_lines.append("|-------|---------|--------|-----------|----------|------------|--------|-----------------|")
    for r in sorted(results, key=lambda x: x.get("live_pf", 99)):
        if "error" in r:
            md_lines.append(f"| {r['agent']} | ? | ? | ERROR | - | - | - | - |")
            continue
        rm = r.get("r_multiples")
        rm_str = str(rm) if rm else "?"
        md_lines.append(
            f"| {r['agent']:18s} | {r.get('live_pf', 0):.2f} | {r.get('live_R', 0):+.1f}R | "
            f"{r.get('grade', '?')} | {r.get('confidence', 0)} | "
            f"{r.get('weight', '?')} | {r.get('timeframe', '?')} | {rm_str} |"
        )
    md_path.write_text("\n".join(md_lines) + "\n")
    print(f"[iterate-all] MD: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
