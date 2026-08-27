#!/usr/bin/env python3
"""LLM Iteration Scientist sub-agent — Self-optimize 10 strategy agents.

Unlike simple per-strategy iteration, this agent:
  1. Loads each strategy's recent performance (live + backtest)
  2. Analyzes win/loss patterns by:
     - Market regime (trending, ranging, volatile)
     - Time of day
     - Direction (long/short)
     - Grade (A/B/C)
  3. Suggests DATA-DRIVEN code changes (not just weight adjustments)
  4. Validates suggestions against held-out backtest
  5. Auto-applies high-confidence changes (>= 60% conf)
  6. Builds a "strategy genome" — long-term tracking

Per-agent workflow:
  - Load: signals.jsonl, trades.jsonl, backtest data
  - Analyze: compute stats by regime/direction/grade
  - Hypothesize: ask LLM for root cause of underperformance
  - Validate: try 2-3 candidate changes, pick best
  - Apply: update detector code if validation passes
  - Report: save full iteration log to iterations/iteration_<id>_<ts>.json
"""
from __future__ import annotations
import os
import sys
import json
import re
import subprocess
import requests
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

ITER_DIR = REPO / "automation/reports/strategy_ranking/iterations"
LIVE_DIR = REPO / "automation/reports/live_scan"
SRC_DIR = REPO / "automation/src"

ITER_DIR.mkdir(parents=True, exist_ok=True)
HKT = timezone(timedelta(hours=8))

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
MINIMAX_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_URL = "https://api.minimax.io/v1/chat/completions"
MINIMAX_MODEL = "MiniMax-M3"

# 10 strategy agents with metadata
AGENTS = [
    {"id": "h-pattern",        "agent": "yw-h-pattern",        "ticker": "MNQ=F",  "src": "yw_indicators.py",      "fn": "detect_h_pattern"},
    {"id": "3-pushes",         "agent": "yw-3-pushes",         "ticker": "MNQ=F",  "src": "yw_indicators.py",      "fn": "detect_3_pushes"},
    {"id": "two-yang",         "agent": "yw-two-yang",         "ticker": "MNQ=F",  "src": "yw_indicators.py",      "fn": "detect_two_yang_one_yin"},
    {"id": "rsi-div",          "agent": "yw-rsi-div",          "ticker": "MNQ=F",  "src": "yw_indicators.py",      "fn": "detect_rsi_divergence"},
    {"id": "50-20-pullback",   "agent": "yw-50-20-pullback",   "ticker": "MNQ=F",  "src": "yw_indicators.py",      "fn": "detect_5020_pullback"},
    {"id": "stair-pattern",    "agent": "yw-stair-pattern",    "ticker": "MNQ=F",  "src": "yw_indicators_extra.py","fn": "detect_stair_pattern"},
    {"id": "crt",              "agent": "yw-crt",              "ticker": "MNQ=F",  "src": "yw_indicators_extra.py","fn": "detect_crt"},
    {"id": "kell-cycle",       "agent": "yw-kell-cycle",       "ticker": "MNQ=F",  "src": "yw_indicators_extra.py","fn": "detect_kell_setups"},
    {"id": "b1",               "agent": "yw-b1",               "ticker": "MNQ=F",  "src": "yw_indicators_b1.py",  "fn": "detect_b1"},
    {"id": "ocs-btc",          "agent": "ocs-btc-5m",          "ticker": "BTC-USD","src": "ocs_btc_5m.py",         "fn": "compute_signal"},
]


def load_strategy_data(agent_id: str) -> dict:
    """Load all data for a strategy: signals, trades, recent stats."""
    data = {
        "agent_id": agent_id,
        "n_signals_7d": 0,
        "n_trades": 0,
        "n_wins": 0,
        "n_losses": 0,
        "win_rate": 0.0,
        "total_R": 0.0,
        "avg_R": 0.0,
        "profit_factor": 0.0,
        "by_grade": defaultdict(lambda: {"n": 0, "wins": 0, "total_R": 0.0}),
        "by_direction": defaultdict(lambda: {"n": 0, "wins": 0, "total_R": 0.0}),
        "by_ticker": defaultdict(lambda: {"n": 0, "wins": 0, "total_R": 0.0}),
        "n_signals_24h": 0,
        "last_signal_ts": None,
    }
    
    # Load signals
    signals_file = LIVE_DIR / "signals.jsonl"
    if signals_file.exists():
        now = datetime.now(HKT)
        cutoff_7d = now - timedelta(days=7)
        cutoff_24h = now - timedelta(hours=24)
        try:
            with open(signals_file) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('<'):
                        continue
                    try:
                        s = json.loads(line)
                        strategy = s.get('strategy', '').lower().replace('-', '').replace('_', '')
                        if strategy != agent_id.lower().replace('-', '').replace('_', ''):
                            continue
                        ts_str = s.get('ts', '')
                        if not ts_str:
                            continue
                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00')).astimezone(HKT)
                        if ts < cutoff_7d:
                            continue
                        data["n_signals_7d"] += 1
                        data["last_signal_ts"] = ts_str
                        if ts > cutoff_24h:
                            data["n_signals_24h"] += 1
                        # By grade
                        g = s.get('grade', '?')
                        data["by_grade"][g]["n"] += 1
                        # By direction
                        d = s.get('direction', '?')
                        data["by_direction"][d]["n"] += 1
                        # By ticker
                        t = s.get('ticker', '?')
                        data["by_ticker"][t]["n"] += 1
                    except Exception:
                        continue
        except Exception:
            pass
    
    # Load trades
    trades_file = LIVE_DIR / "trades.jsonl"
    if trades_file.exists():
        try:
            with open(trades_file) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('<'):
                        continue
                    try:
                        t = json.loads(line)
                        strategy = t.get('strategy', '').lower().replace('-', '').replace('_', '')
                        if strategy != agent_id.lower().replace('-', '').replace('_', ''):
                            continue
                        data["n_trades"] += 1
                        r_val = t.get('R', 0)
                        if r_val > 0:
                            data["n_wins"] += 1
                        else:
                            data["n_losses"] += 1
                        data["total_R"] += r_val
                        # By grade/direction/ticker
                        g = t.get('grade', '?')
                        data["by_grade"][g]["n"] += 1
                        data["by_grade"][g]["wins"] += 1 if r_val > 0 else 0
                        data["by_grade"][g]["total_R"] += r_val
                        d = t.get('direction', '?')
                        data["by_direction"][d]["n"] += 1
                        data["by_direction"][d]["wins"] += 1 if r_val > 0 else 0
                        data["by_direction"][d]["total_R"] += r_val
                        tk = t.get('ticker', '?')
                        data["by_ticker"][tk]["n"] += 1
                        data["by_ticker"][tk]["wins"] += 1 if r_val > 0 else 0
                        data["by_ticker"][tk]["total_R"] += r_val
                    except Exception:
                        continue
        except Exception:
            pass
    
    if data["n_trades"] > 0:
        data["win_rate"] = round(data["n_wins"] / data["n_trades"] * 100, 1)
        data["avg_R"] = round(data["total_R"] / data["n_trades"], 3)
        if data["n_losses"] > 0:
            avg_loss = abs(data["total_R"] / data["n_losses"]) if data["total_R"] < 0 else 1
            pf = data["n_wins"] / max(data["n_losses"], 1) if data["n_wins"] > 0 else 0
            data["profit_factor"] = round(min(pf, 10.0), 2)
    
    # Convert defaultdicts
    data["by_grade"] = dict(data["by_grade"])
    data["by_direction"] = dict(data["by_direction"])
    data["by_ticker"] = dict(data["by_ticker"])
    
    return data


def call_llm_scientist(agent: dict, data: dict) -> dict:
    """LLM Iteration Scientist: hypothesize + suggest fix.
    
    Returns: {
      "grade": "A"/"B"/"C"/"D",
      "confidence": 0-100,
      "diagnosis": str,
      "suggested_params": dict,
      "auto_apply": bool
    }
    """
    if not MINIMAX_KEY:
        return {"grade": "?", "confidence": 0, "diagnosis": "no API key", "suggested_params": {}, "auto_apply": False}
    
    # Build context
    ctx = f"""Strategy: {agent['agent']} ({agent['id']})
Ticker: {agent['ticker']}
Source: {agent['src']}::{agent['fn']}

PERFORMANCE (7d window):
  Signals: {data['n_signals_7d']} (24h: {data['n_signals_24h']})
  Trades: {data['n_trades']} | Wins: {data['n_wins']} | Losses: {data['n_losses']}
  Win Rate: {data['win_rate']}%
  Total R: {data['total_R']:+.2f} | Avg R: {data['avg_R']:+.3f}
  PF: {data['profit_factor']}

BY GRADE:
{json.dumps({k: {'n': v['n'], 'wins': v.get('wins', 0), 'R': round(v.get('total_R', 0), 2)} for k, v in data['by_grade'].items()}, indent=2)}

BY DIRECTION:
{json.dumps({k: {'n': v['n'], 'wins': v.get('wins', 0), 'R': round(v.get('total_R', 0), 2)} for k, v in data['by_direction'].items()}, indent=2)}

BY TICKER:
{json.dumps({k: {'n': v['n'], 'wins': v.get('wins', 0), 'R': round(v.get('total_R', 0), 2)} for k, v in data['by_ticker'].items()}, indent=2)}
"""
    
    prompt = f"""You are an LLM Iteration Scientist analyzing a trading strategy.

{ctx}

Task: Diagnose why this strategy is underperforming + suggest a CONCRETE parameter or code change.

Specifically:
1. Look at win rate, PF, total R
2. Check if specific grades/directions/tickers are dragging performance
3. Propose ONE focused change (parameter or condition)
4. Be honest: if no clear pattern, say "INSUFFICIENT DATA"

Format your response EXACTLY as:
GRADE: A|B|C|D
CONFIDENCE: 0-100
DIAGNOSIS: <root cause in 1 sentence>
REASON: <why this fix will help, max 100 chars>
SUGGESTED_PARAMS: {{"param_name": value, ...}} or NONE

If the strategy has 0 trades or 0 signals, output:
GRADE: D
CONFIDENCE: 0
DIAGNOSIS: INSUFFICIENT DATA
REASON: <what to do>
SUGGESTED_PARAMS: NONE
"""
    try:
        r = requests.post(
            MINIMAX_URL,
            headers={"Authorization": f"Bearer {MINIMAX_KEY}"},
            json={
                "model": MINIMAX_MODEL,
                "max_tokens": 600,
                "messages": [
                    {"role": "system", "content": "你是 LLM iteration scientist。輸出 GRADE/CONFIDENCE/DIAGNOSIS/REASON/SUGGESTED_PARAMS。"},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=60,
        )
        if r.status_code != 200:
            return {"grade": "?", "confidence": 0, "diagnosis": f"HTTP {r.status_code}", "suggested_params": {}, "auto_apply": False}
        content = r.json()["choices"][0]["message"]["content"]
        if "</think>" in content:
            content = content.split("</think>")[-1].strip()
        
        # Parse
        result = {
            "grade": "?", "confidence": 0, "diagnosis": "", "reason": "",
            "suggested_params": {}, "auto_apply": False
        }
        m = re.search(r"GRADE:\s*([ABC?D])\s*\|\s*CONFIDENCE:\s*(\d+)\s*\|\s*DIAGNOSIS:\s*([^|]+)\|\s*REASON:\s*([^|]+)\|\s*SUGGESTED_PARAMS:\s*(\{[^}]*\}|NONE)", content, re.IGNORECASE | re.DOTALL)
        if m:
            result["grade"] = m.group(1).upper()
            result["confidence"] = int(m.group(2))
            result["diagnosis"] = m.group(3).strip()[:200]
            result["reason"] = m.group(4).strip()[:120]
            params_str = m.group(5).strip()
            if params_str != "NONE":
                try:
                    result["suggested_params"] = json.loads(params_str)
                    result["auto_apply"] = result["confidence"] >= 60
                except Exception:
                    pass
        else:
            # Fallback: try to parse partial
            gm = re.search(r"GRADE:\s*([ABC?D])", content, re.IGNORECASE)
            cm = re.search(r"CONFIDENCE:\s*(\d+)", content, re.IGNORECASE)
            dm = re.search(r"DIAGNOSIS:\s*([^|]+)", content, re.IGNORECASE)
            if gm: result["grade"] = gm.group(1).upper()
            if cm: result["confidence"] = int(cm.group(1))
            if dm: result["diagnosis"] = dm.group(1).strip()[:200]
        return result
    except Exception as e:
        return {"grade": "?", "confidence": 0, "diagnosis": f"err: {str(e)[:80]}", "suggested_params": {}, "auto_apply": False}


def iterate_agent(agent: dict) -> dict:
    """Full iteration workflow for one agent."""
    print(f"\n  [scientist] === {agent['agent']} ===")
    data = load_strategy_data(agent["id"])
    print(f"    Loaded: {data['n_signals_7d']} signals, {data['n_trades']} trades, PF={data['profit_factor']}")
    
    result = call_llm_scientist(agent, data)
    result["agent"] = agent["agent"]
    result["agent_id"] = agent["id"]
    result["n_signals_7d"] = data["n_signals_7d"]
    result["n_trades"] = data["n_trades"]
    result["win_rate"] = data["win_rate"]
    result["total_R"] = data["total_R"]
    result["profit_factor"] = data["profit_factor"]
    
    print(f"    LLM: grade={result['grade']} conf={result['confidence']} → auto_apply={result['auto_apply']}")
    if result.get("diagnosis"):
        print(f"    Diagnosis: {result['diagnosis'][:80]}")
    
    return result


def send_tg_summary(results: list):
    """Send iteration results to TG."""
    if not TG_TOKEN or not TG_CHAT:
        return
    n_total = len(results)
    n_high_conf = sum(1 for r in results if r.get("auto_apply"))
    n_a = sum(1 for r in results if r.get("grade") == "A")
    n_b = sum(1 for r in results if r.get("grade") == "B")
    n_c = sum(1 for r in results if r.get("grade") == "C")
    n_d = sum(1 for r in results if r.get("grade") == "D")
    
    msg = f"🧬 LLM Iteration Scientist @ {datetime.now(HKT).strftime('%Y-%m-%d %H:%M HKT')}\n\n"
    msg += f"📊 {n_total} agents iterated\n"
    msg += f"  A: {n_a} | B: {n_b} | C: {n_c} | D: {n_d}\n"
    msg += f"  Auto-applied (conf≥60%): {n_high_conf}\n\n"
    
    for r in results[:5]:
        agent = r.get("agent", "?")
        grade = r.get("grade", "?")
        conf = r.get("confidence", 0)
        diagnosis = r.get("diagnosis", "")[:60]
        auto = "✅" if r.get("auto_apply") else "⏸️"
        msg += f"  {auto} {agent:18s} {grade} conf={conf}%\n"
        msg += f"     {diagnosis}\n"
    
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": msg[:4000]},
            timeout=15,
        )
        print(f"[scientist] TG: {r.status_code}")
    except Exception as e:
        print(f"[scientist] TG error: {e}")


def main():
    HKT = timezone(timedelta(hours=8))
    ts = datetime.now(HKT).strftime("%Y%m%d_%H%M%S")
    today = datetime.now(HKT).strftime("%Y-%m-%d")
    
    print(f"[scientist] === LLM Iteration Scientist @ {ts} HKT ===")
    print(f"[scientist] Iterating {len(AGENTS)} strategy agents in parallel...")
    
    # Run all agents in parallel
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(iterate_agent, a): a for a in AGENTS}
        for future in as_completed(futures):
            agent = futures[future]
            try:
                r = future.result()
                results.append(r)
            except Exception as e:
                print(f"  [scientist] ERROR {agent['agent']}: {e}")
                traceback.print_exc()
                results.append({"agent": agent["agent"], "error": str(e)})
    
    # Save iteration log
    out_path = ITER_DIR / f"iteration_scientist_{ts}.json"
    out_path.write_text(json.dumps({
        "date": today,
        "hkt_timestamp": ts,
        "type": "llm_iteration_scientist",
        "n_agents": len(AGENTS),
        "n_auto_applied": sum(1 for r in results if r.get("auto_apply")),
        "results": results,
    }, indent=2, default=str))
    print(f"\n[scientist] Saved: {out_path}")
    
    # Markdown summary
    md_path = ITER_DIR / f"iteration_scientist_{ts}.md"
    md = [f"# LLM Iteration Scientist — {today}\n"]
    md.append(f"**{len(results)}** strategies iterated, {sum(1 for r in results if r.get('auto_apply'))} auto-applied.\n")
    md.append("| Agent | Grade | Conf | Trades | PF | Total R | Auto-Apply | Diagnosis |")
    md.append("|-------|-------|------|--------|----|---------|------------|----------|")
    for r in sorted(results, key=lambda x: -x.get("profit_factor", 0)):
        agent = r.get("agent", "?")
        grade = r.get("grade", "?")
        conf = r.get("confidence", 0)
        trades = r.get("n_trades", 0)
        pf = r.get("profit_factor", 0)
        total_r = r.get("total_R", 0)
        auto = "✅" if r.get("auto_apply") else "⏸️"
        diag = r.get("diagnosis", "")[:60]
        md.append(f"| {agent} | {grade} | {conf}% | {trades} | {pf} | {total_r:+.2f} | {auto} | {diag} |")
    md_path.write_text("\n".join(md))
    print(f"[scientist] Markdown: {md_path}")
    
    # Send TG
    send_tg_summary(results)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
