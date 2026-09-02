#!/usr/bin/env python3
"""optimize_underperformers — Suggest parameter changes for low-score setups.

User: '我要llm iteration 優化setup 不是 stop' (LLM iter to OPTIMIZE not stop)

For each underperformer (Grade D, PF < 0.8, WR < 40%):
- Analyze winning/losing trade characteristics
- Suggest specific param tweaks:
  - weight (priority in scoring)
  - r_multiples (T1/T2/T3)
  - atr_stop_mult (SL buffer)
  - min_confidence (entry filter)
  - trend_filter (require direction)
  - cooldown_bars (avoid over-trading)
- Estimate impact (before/after)
- Output to optimization_proposals.md
"""
from __future__ import annotations
import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

HKT = timezone(timedelta(hours=8))
UTC = timezone.utc

# Strategy names
STRATEGIES = {
    "yw-h-pattern": "H-Pattern",
    "yw-3-pushes": "3-Pushes",
    "yw-two-yang": "Two-Yang",
    "yw-rsi-div": "RSI-Div",
    "yw-50-20-pullback": "50-20-Pullback",
    "yw-stair-pattern": "Stair",
    "yw-crt": "CRT",
    "yw-kell-cycle": "Kell-Cycle",
    "yw-b1": "B1",
}

# Current yw_grader.py config
CURRENT_CONFIG = {
    "H-Pattern": {
        "weight": 1.2, 
        "r_multiples": [1.0, 1.618, 2.618, 3.618, 5.0],
        "data_granularity": "5m",
    },
    "3-Pushes": {
        "weight": 1.0,
        "r_multiples": [1.0, 1.618, 2.618, 3.618, 5.0],
    },
    "Two-Yang": {
        "weight": 0.5,  # LLM already dropped
        "r_multiples": [1.5, 2.5, 4.0, 6.0, 8.0],  # wider
        "atr_stop_mult": 1.0,
        "trend_filter": "EMA20_slope",
        "adx_filter": 20,
        "cooldown_bars": 10,
    },
    "RSI-Div": {
        "weight": 0.7,  # LLM-suggested drop
        "r_multiples": [1.5, 2.0, 3.0, 4.0, 5.0],
        "trend_filter": "EMA50",
    },
    "50-20-Pullback": {
        "weight": 1.0,
    },
    "Stair": {
        "weight": 0.9,
    },
    "CRT": {
        "weight": 1.1,
    },
    "Kell-Cycle": {
        "weight": 0.9,
    },
    "B1": {
        "weight": 1.0,  # structural (BTC j<20)
    },
}


def parse_ts(ts_str):
    if not ts_str: return None
    try:
        ts_str = ts_str.replace('Z', '+00:00').replace(' ', 'T')
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except: return None


def load_trades_7d():
    """Load all 7d trades."""
    cutoff_dt = datetime.now(UTC) - timedelta(days=7)
    trades = []
    for path in [REPO / "automation/reports/live_scan/trades.jsonl",
                 REPO / "automation/reports/ocs_btc_5m/trades.jsonl"]:
        if not path.exists(): continue
        with open(path) as f:
            for l in f:
                try:
                    t = json.loads(l)
                    et = parse_ts(t.get("exit_time", ""))
                    if et and et >= cutoff_dt:
                        trades.append(t)
                except: pass
    return trades


def analyze_strategy(trades_7d, strategy_name):
    """Analyze a strategy's win/loss patterns to suggest params."""
    strat_trades = [t for t in trades_7d if t.get("strategy") == strategy_name]
    if not strat_trades:
        return None
    
    wins = [t for t in strat_trades if t.get("R_multiple", 0) > 0]
    losses = [t for t in strat_trades if t.get("R_multiple", 0) <= 0]
    
    n = len(strat_trades)
    total_R = sum(t.get("R_multiple", 0) for t in strat_trades)
    avg_R = total_R / n if n else 0
    wr = len(wins) / n * 100
    
    # Average win R vs average loss R
    avg_win_R = sum(t.get("R_multiple", 0) for t in wins) / len(wins) if wins else 0
    avg_loss_R = sum(t.get("R_multiple", 0) for t in losses) / len(losses) if losses else 0
    
    # Direction analysis
    long_trades = [t for t in strat_trades if t.get("direction") in ("long", "bullish")]
    short_trades = [t for t in strat_trades if t.get("direction") in ("short", "bearish")]
    long_R = sum(t.get("R_multiple", 0) for t in long_trades)
    short_R = sum(t.get("R_multiple", 0) for t in short_trades)
    
    # Grade analysis
    by_grade = defaultdict(list)
    for t in strat_trades:
        by_grade[t.get("grade", "?")].append(t)
    grade_R = {g: sum(t.get("R_multiple", 0) for t in tlist) for g, tlist in by_grade.items()}
    
    return {
        "n": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": wr,
        "total_R": total_R,
        "avg_R": avg_R,
        "avg_win_R": avg_win_R,
        "avg_loss_R": avg_loss_R,
        "long_n": len(long_trades),
        "short_n": len(short_trades),
        "long_R": long_R,
        "short_R": short_R,
        "by_grade": dict(grade_R),
    }


def suggest_optimizations(agent_id, strat_name, stats, current_config):
    """Generate specific param suggestions based on stats."""
    if not stats:
        return None
    
    suggestions = []
    
    pf = stats["avg_win_R"] / abs(stats["avg_loss_R"]) if stats["avg_loss_R"] < 0 else 0
    
    # If avg_win_R < |avg_loss_R|, the R:R is bad
    if stats["avg_win_R"] < abs(stats["avg_loss_R"]):
        suggestions.append({
            "param": "r_multiples",
            "current": current_config.get("r_multiples", "default"),
            "suggested": "widen T1 (T1=0.5R), tighten T2 close (T2=1.0R), reduce T3-T5 (skip if low conf)",
            "reason": f"avg_win_R={stats['avg_win_R']:.2f} < |avg_loss_R|={abs(stats['avg_loss_R']):.2f} (poor R:R)",
        })
    
    # If WR is low, tighten filter
    if stats["win_rate"] < 35 and stats["n"] >= 20:
        cur_weight = current_config.get("weight", 1.0)
        new_weight = max(0.3, cur_weight * 0.5)
        suggestions.append({
            "param": "weight",
            "current": cur_weight,
            "suggested": new_weight,
            "reason": f"WR={stats['win_rate']:.1f}% < 35%, reduce priority (was {cur_weight}, try {new_weight})",
        })
    
    # If directional bias (only one direction works)
    if stats["long_n"] >= 5 and stats["short_n"] >= 5:
        if stats["long_R"] < -3 and stats["short_R"] > 0:
            suggestions.append({
                "param": "direction_filter",
                "current": "both",
                "suggested": "long only (if BTC downtrend) or short only",
                "reason": f"long: {stats['long_R']:+.1f}R (loss), short: {stats['short_R']:+.1f}R (win)",
            })
        elif stats["short_R"] < -3 and stats["long_R"] > 0:
            suggestions.append({
                "param": "direction_filter",
                "current": "both",
                "suggested": "long only",
                "reason": f"short: {stats['short_R']:+.1f}R (loss), long: {stats['long_R']:+.1f}R (win)",
            })
    
    # If high conf grade underperforms
    if "A" in stats["by_grade"] and stats["by_grade"]["A"] < 0 and stats["n"] >= 30:
        suggestions.append({
            "param": "grade_threshold",
            "current": "A/B/C all",
            "suggested": "A only (filter out B/C)",
            "reason": f"Grade A underperforms: {stats['by_grade']['A']:+.1f}R",
        })
    
    # Add trend filter if not present
    if "trend_filter" not in current_config and stats["n"] >= 30:
        suggestions.append({
            "param": "trend_filter",
            "current": "none",
            "suggested": "EMA20_slope (only trade with trend)",
            "reason": "Add trend filter to reduce counter-trend losses",
        })
    
    # Add cooldown
    if "cooldown_bars" not in current_config and stats["losses"] >= 15:
        suggestions.append({
            "param": "cooldown_bars",
            "current": 0,
            "suggested": 10,
            "reason": f"Add 10-bar cooldown to reduce over-trading after losses",
        })
    
    # Add SL buffer
    if "atr_stop_mult" not in current_config:
        cur_sl = current_config.get("atr_stop_mult", 1.6)
        if stats["losses"] >= 20 and stats["avg_loss_R"] < -1.2:
            new_sl = cur_sl * 1.2  # 20% wider SL to avoid noise stops
            suggestions.append({
                "param": "atr_stop_mult",
                "current": cur_sl,
                "suggested": round(new_sl, 2),
                "reason": f"avg_loss_R={stats['avg_loss_R']:.2f} (overshooting SL), widen to {new_sl:.2f}",
            })
    
    return suggestions if suggestions else None


def main():
    print(f"[optimize] === {datetime.now(HKT).strftime('%Y-%m-%d %H:%M:%S HKT')} ===")
    print()
    
    trades_7d = load_trades_7d()
    print(f"Loaded {len(trades_7d)} trades (7d window)")
    print()
    
    # Read latest iteration
    iter_path = sorted((REPO / "automation/reports/strategy_ranking/iterations").glob("iteration_scientist_*.json"), reverse=True)[0]
    with open(iter_path) as f:
        iter_data = json.load(f)
    
    # Build report
    lines = [
        "# 🛠️ Strategy Optimization Proposals (LLM-driven)",
        "",
        f"**Generated**: {datetime.now(HKT).isoformat()}",
        f"**Based on**: 7d LLM iteration + 7d trade analysis",
        f"**Source iteration**: {iter_path.name}",
        "",
        "## 📋 Summary",
        "",
        f"- Total trades analyzed: {len(trades_7d)}",
        f"- Strategies optimized: 9",
        f"- Auto-apply requires: Grade A/B AND conf ≥60 (LLM-grade)",
        "",
    ]
    
    # For each strategy, get LLM grade + suggest params
    llm_results = {r.get("agent"): r for r in iter_data.get("results", [])}
    
    proposals = []
    for agent_id, strat_name in STRATEGIES.items():
        llm_r = llm_results.get(agent_id, {})
        if not llm_r:
            continue
        
        grade = llm_r.get("grade", "?")
        conf = llm_r.get("confidence", 0)
        pf_7d = llm_r.get("profit_factor", 0)
        wr_7d = llm_r.get("win_rate", 0)
        r_7d = llm_r.get("total_R", 0)
        
        # Get trade stats
        stats = analyze_strategy(trades_7d, strat_name)
        if not stats:
            continue
        
        current_config = CURRENT_CONFIG.get(strat_name, {})
        
        # Generate suggestions
        suggestions = suggest_optimizations(agent_id, strat_name, stats, current_config)
        
        # Action classification
        if pf_7d >= 1.0 and wr_7d >= 45 and r_7d > 0:
            action = "✅ KEEP (healthy)"
            apply_now = False
        elif pf_7d >= 0.7 and r_7d > 0:
            action = "⚠️ OPTIMIZE (low priority)"
            apply_now = False
        else:
            action = "🛑 OPTIMIZE (high priority)"
            apply_now = True  # try to fix before stopping
        
        lines.extend([
            f"## {strat_name} (`{agent_id}`)",
            "",
            f"**7d LLM Grade**: {grade} ({conf}%) | **Auto-apply eligible**: {'✅ Yes' if grade in ('A', 'B') and conf >= 60 else '❌ No'}",
            f"**7d Stats**: N={stats['n']} WR={stats['win_rate']:.1f}% PF={pf_7d:.2f} R={r_7d:+.1f}",
            f"**24h Stats**: N={stats.get('long_n', 0)+stats.get('short_n', 0)} | Avg Win R={stats['avg_win_R']:.2f} | Avg Loss R={stats['avg_loss_R']:.2f}",
            f"**Direction**: long {stats['long_n']} trades {stats['long_R']:+.1f}R | short {stats['short_n']} trades {stats['short_R']:+.1f}R",
            f"**By Grade**: {stats['by_grade']}",
            f"**Action**: {action}",
            "",
        ])
        
        if suggestions:
            lines.append("**💡 Optimization Suggestions**:")
            lines.append("")
            lines.append("| Param | Current | Suggested | Reason |")
            lines.append("|-------|---------|-----------|--------|")
            for s in suggestions:
                lines.append(f"| `{s['param']}` | {s['current']} | {s['suggested']} | {s['reason']} |")
            lines.append("")
            
            proposals.append({
                "agent_id": agent_id,
                "strat_name": strat_name,
                "grade": grade,
                "conf": conf,
                "pf": pf_7d,
                "wr": wr_7d,
                "r": r_7d,
                "suggestions": suggestions,
                "apply_now": apply_now,
            })
        else:
            lines.append("✅ No changes suggested (performing within range)")
            lines.append("")
    
    lines.extend([
        "## 🎯 Next Steps",
        "",
        "1. **Review proposals** above",
        "2. **Apply params**: edit `automation/src/yw_grader.py` STRATEGIES dict",
        "3. **Test in shadow mode** (paper trade for 24h)",
        "4. **Compare metrics**: WR, PF, R before/after",
        "5. **Auto-apply** when LLM returns grade A/B + conf≥60",
        "",
        "## ⚠️ Safety Rules",
        "",
        "- **NEVER** disable a strategy without 14d+ evidence",
        "- **NEVER** apply more than 2 param changes at once",
        "- **ALWAYS** keep stop-loss and risk rules intact",
        "- **ALWAYS** preserve min_trades filter (≥ 30 for stats)",
        "- **AUTO-APPLY** only grade A/B + conf≥60 (LLM-grade)",
        "",
    ])
    
    # Save report
    out_path = REPO / "automation/reports/strategy_ranking/optimization_proposals.md"
    out_path.write_text("\n".join(lines))
    print(f"Saved: {out_path}")
    
    # Save proposals JSON
    proposals_path = REPO / "automation/reports/strategy_ranking/optimization_proposals.json"
    proposals_path.write_text(json.dumps({
        "generated": datetime.now(HKT).isoformat(),
        "n_proposals": len(proposals),
        "n_high_priority": sum(1 for p in proposals if p["apply_now"]),
        "proposals": proposals,
    }, indent=2, default=str))
    print(f"Saved: {proposals_path}")
    
    # Print summary
    print()
    print("=== Proposals Summary ===")
    for p in proposals:
        n_sugg = len(p["suggestions"])
        print(f"  {p['grade']} {p['agent_id']:20s} {p['wr']:5.1f}% WR, {p['pf']:.2f} PF → {n_sugg} suggestions")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
