#!/usr/bin/env python3
"""Daily Reward — Top 3 PnL Strategy Agents.

Reads latest ranking, awards:
- 🥇 #1: 50 AI-Trader reputation points
- 🥈 #2: 30 AI-Trader reputation points
- 🥉 #3: 20 AI-Trader reputation points

Sends TG notification with rankings + awards.
Saves to awards.jsonl for lifetime tracking.

Schedule: 21:35 HKT (after strategy_ranking at 21:30)
GHA workflow: strategy-reward.yml
"""
from __future__ import annotations
import os
import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# Auto-detect repo
if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

# Award tiers
AWARDS = [
    {"rank": 1, "emoji": "🥇", "points": 50, "label": "Champion"},
    {"rank": 2, "emoji": "🥈", "points": 30, "label": "Runner-up"},
    {"rank": 3, "emoji": "🥉", "points": 20, "label": "Third place"},
]


def load_latest_ranking() -> dict:
    """Load most recent ranking from history.jsonl."""
    history_path = REPO / "automation/reports/strategy_ranking/history.jsonl"
    if not history_path.exists():
        return None
    lines = history_path.read_text().strip().split("\n")
    if not lines:
        return None
    return json.loads(lines[-1])


def publish_signal_to_ai_trader(strategy_name: str, pf: float, total_r: float,
                                award_points: int) -> int:
    """Publish reward signal to AI-Trader for reputation points.

    Uses the AI-Trader signal endpoint to claim reputation for the strategy.
    """
    ai_token = os.environ.get("AI_TRADER_TOKEN", "")
    if not ai_token:
        return None

    try:
        payload = {
            "market": "crypto",
            "title": f"Daily Top 3 Award: {strategy_name} (PF {pf:.2f}, +{total_r:.0f}R, +{award_points} pts)",
            "content": f"Strategy {strategy_name} ranked in top 3 by profit factor. "
                       f"PF {pf:.2f}, Total R {total_r:+.0f}, awarded {award_points} reputation points.",
            "symbols": "BTC-USD",
            "tags": ",".join(["strategy-award", "daily-top3", strategy_name.lower().replace(" ", "-")]),
        }
        r = requests.post(
            "https://ai4trade.ai/api/signals/strategy",
            headers={"Authorization": f"Bearer {ai_token}",
                     "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        if r.status_code == 200:
            return r.json().get("signal_id")
        else:
            print(f"  AI-Trader HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"  AI-Trader error: {e}")
    return None


def send_tg_message(text: str) -> int:
    """Send message to Telegram."""
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not tg_token or not tg_chat:
        print("  TG: no token/chat_id")
        return 0
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{tg_token}/sendMessage",
            json={"chat_id": tg_chat, "text": text, "disable_web_page_preview": True},
            timeout=15,
        )
        return r.status_code
    except Exception as e:
        print(f"  TG error: {e}")
        return 0


def main():
    HKT = timezone(timedelta(hours=8))
    today_hkt = datetime.now(HKT).strftime("%Y-%m-%d")

    print(f"[reward] Loading latest ranking for {today_hkt}...")
    ranking_data = load_latest_ranking()
    if not ranking_data:
        print("[reward] No ranking data found")
        return 1

    ranking = ranking_data.get("ranking", [])
    if len(ranking) < 3:
        print(f"[reward] Not enough strategies ({len(ranking)})")
        return 1

    top3 = ranking[:3]
    print(f"[reward] Top 3:")
    for r in top3:
        sid = r["strategy_id"]
        pf = r["pf"]
        total_r = r["total_R"]
        pnl = r["pnl_usd"]
        name = r["name"]
        rank = r["rank"]
        # Find matching award
        award = next((a for a in AWARDS if a["rank"] == rank), None)
        if award:
            print(f"  {award['emoji']} #{rank} {name} (PF {pf}, +{total_r}R, ${pnl:+,}) → {award['points']} pts")

    # Build TG message
    lines = [f"🏆 Daily Strategy Awards — {today_hkt}\n"]
    lines.append("Top 3 by Profit Factor:\n")
    total_lifetime_awards = 0
    awards_record = {"date": today_hkt, "awards": []}

    for r in top3:
        award = next((a for a in AWARDS if a["rank"] == r["rank"]), None)
        if not award:
            continue
        sid = r["strategy_id"]
        name = r["name"]
        pf = r["pf"]
        total_r = r["total_R"]
        pnl = r["pnl_usd"]
        wr = r["win_rate"]
        n = r["n_trades"]
        award_pts = award["points"]
        emoji = award["emoji"]
        label = award["label"]
        lines.append(
            f"{emoji} {label}: {name}\n"
            f"   PF {pf:.2f} | +{total_r:.0f}R | WR {wr:.1f}% | N={n} | ${pnl:+,.0f}\n"
            f"   Award: +{award_pts} reputation points\n"
        )

        # Publish reward signal
        signal_id = publish_signal_to_ai_trader(name, pf, total_r, award_pts)
        if signal_id:
            print(f"  AI-Trader: signal_id={signal_id}")

        awards_record["awards"].append({
            "rank": r["rank"],
            "strategy_id": sid,
            "name": name,
            "pf": pf,
            "total_R": total_r,
            "pnl_usd": pnl,
            "win_rate": wr,
            "n_trades": n,
            "points": award_pts,
            "ai_trader_signal_id": signal_id,
        })
        total_lifetime_awards += award_pts

    # Add total
    lines.append(f"\nTotal daily awards: {total_lifetime_awards} points")

    msg = "\n".join(lines)
    print(f"\n[reward] TG message ({len(msg)} chars):")
    print(msg)

    # Send TG
    tg_status = send_tg_message(msg)
    print(f"\n[reward] TG: HTTP {tg_status}")

    # Save to awards.jsonl
    awards_path = REPO / "automation/reports/strategy_ranking/awards.jsonl"
    awards_path.parent.mkdir(parents=True, exist_ok=True)
    with awards_path.open("a") as f:
        f.write(json.dumps(awards_record, default=str) + "\n")
    print(f"[reward] Saved: {awards_path}")

    # Update lifetime stats
    lifetime_path = REPO / "automation/reports/strategy_ranking/lifetime_awards.json"
    if lifetime_path.exists():
        lifetime = json.loads(lifetime_path.read_text())
    else:
        lifetime = {"total_points_awarded": 0, "by_strategy": {}, "by_date": {}}
    lifetime["total_points_awarded"] = lifetime.get("total_points_awarded", 0) + total_lifetime_awards
    lifetime.setdefault("by_date", {})[today_hkt] = total_lifetime_awards
    for a in awards_record["awards"]:
        sid = a["strategy_id"]
        lifetime.setdefault("by_strategy", {}).setdefault(sid, {"name": a["name"], "total_points": 0, "wins": 0})
        lifetime["by_strategy"][sid]["total_points"] += a["points"]
        lifetime["by_strategy"][sid]["wins"] += 1
    lifetime_path.write_text(json.dumps(lifetime, indent=2, default=str))
    print(f"[reward] Lifetime: {lifetime['total_points_awarded']} total points awarded")

    return 0


if __name__ == "__main__":
    sys.exit(main())
