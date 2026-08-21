#!/usr/bin/env python3
"""OCS BTC 5m — act on signal (TG alert + AI-Trader publish + log)."""
import os
import json
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta

HKT = timezone(timedelta(hours=8))


def main():
    sig_path = Path("/tmp/ocs_btc/latest.json")
    if not sig_path.exists():
        print("❌ No signal file")
        return 0
    data = json.loads(sig_path.read_text())
    signal = data.get("signal")
    vote = data.get("vote", 0)
    conf = data.get("conf", 0)
    direction = data.get("direction")
    last_close = data.get("last_close", 0)
    atr = data.get("atr", 0)

    print(f"Vote: {vote}, Conf: {conf:.2f}, Signal: {signal}")

    if signal not in ("buy", "sell"):
        print(f"⚠️  No actionable signal (vote={vote}, need ±4)")
        return 0

    # Compute SL/TP
    sl_dist = atr * 1.6
    t1 = sl_dist * 1.0
    t2 = sl_dist * 1.618
    t3 = sl_dist * 2.618
    t4 = sl_dist * 3.618
    t5 = sl_dist * 5.0

    if signal == "buy":
        sl = last_close - sl_dist
        t1_p = last_close + t1
        t2_p = last_close + t2
        t3_p = last_close + t3
        t4_p = last_close + t4
        t5_p = last_close + t5
    else:
        sl = last_close + sl_dist
        t1_p = last_close - t1
        t2_p = last_close - t2
        t3_p = last_close - t3
        t4_p = last_close - t4
        t5_p = last_close - t5

    emoji = "🟢" if signal == "buy" else "🔴"
    arrow = "LONG" if signal == "buy" else "SHORT"
    tg_msg = f"""{emoji} *OCS BTC 5m Signal — {arrow}*

*Ticker*: BTC-USD @ ${last_close:,.2f}
*Signal*: {signal.upper()} (vote {vote:+d}/±7, conf {conf:.2f})
*Direction*: {direction}

*Risk Plan* (1.6× ATR stop, R-multiple targets):
• *Stop*: ${sl:,.2f} (${sl_dist:,.2f} away)
• *T1* (1R): ${t1_p:,.2f}
• *T2* (1.618R): ${t2_p:,.2f}
• *T3* (2.618R): ${t3_p:,.2f}
• *T4* (3.618R): ${t4_p:,.2f}
• *T5* (5.0R): ${t5_p:,.2f}

⚠️ Treat T1 as first scale-out, stop is catastrophic invalidation.
"""

    # 1. TG alert
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat:
        r = requests.post(
            f"https://api.telegram.org/bot{tg_token}/sendMessage",
            json={"chat_id": tg_chat, "text": tg_msg,
                  "parse_mode": "Markdown", "disable_web_page_preview": True},
            timeout=15,
        )
        print(f"TG: HTTP {r.status_code}")
    else:
        print("TG: SKIPPED (no token)")

    # 2. Publish to AI-Trader
    ai_token = os.environ.get("AI_TRADER_TOKEN", "")
    signal_id = None
    points = 0
    if ai_token:
        payload = {
            "market": "crypto",
            "title": f"BTC-USD OCS {signal.upper()} (vote {vote:+d}, conf {conf:.2f})"[:100],
            "content": tg_msg[:1500],
            "symbols": "BTC-USD",
            "tags": ",".join(["ocs-ai", "btc", "5m", signal]),
        }
        r2 = requests.post(
            "https://ai4trade.ai/api/signals/strategy",
            headers={"Authorization": f"Bearer {ai_token}",
                     "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        if r2.status_code == 200:
            result = r2.json()
            signal_id = result.get("signal_id")
            points = result.get("points_earned", 0)
            print(f"AI-Trader: signal_id={signal_id} +{points} points")
        else:
            print(f"AI-Trader: HTTP {r2.status_code} {r2.text[:200]}")
    else:
        print("AI-Trader: SKIPPED (no token)")

    # 3. Save log
    log_dir = Path(os.environ.get("OCS_LOG_DIR", "automation/reports/ocs_btc_5m"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "signals.jsonl"
    now = datetime.now(HKT).strftime("%Y%m%d_%H%M%S")
    with log_file.open("a") as f:
        f.write(json.dumps({
            "ts": now,
            "signal": signal,
            "direction": direction,
            "vote": vote,
            "conf": conf,
            "last_close": last_close,
            "atr": atr,
            "sl": sl,
            "t1": t1_p,
            "t2": t2_p,
            "t3": t3_p,
            "t4": t4_p,
            "t5": t5_p,
            "signal_id": signal_id,
        }, default=str) + "\n")
    print(f"Log: {log_file}")
    return 0


if __name__ == "__main__":
    main()
