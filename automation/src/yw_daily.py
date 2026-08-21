"""YW Concept Daily Reminder — LLM grading + priority ranking.

Runs each YW strategy (H-Pattern / 3-Pushes / 兩陽夾一陰) across
the watchlist (MNQ primary, MES + M2K secondary), grades A/B/C,
ranks by composite priority score, sends to Telegram.

Pushes to Telegram at 21:00 HKT weekdays.

Pipeline:
  1. Fetch intraday data for 3 tickers
  2. LLM-grade each (strategy × ticker) — 9 grades
  3. Rank by priority_score
  4. Build reminder text (4 sections)
  5. Send text + commit artifacts to GitHub
"""
from __future__ import annotations
import os
import sys
import json
import time
import shutil
import warnings
import logging
import subprocess
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

import requests

# Load env
from env_loader import load_env
load_env()

HKT = timezone(timedelta(hours=8))
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


# --- Repo / paths ---
REPO_DIR = Path(__file__).resolve().parents[2]  # /workspace/YW-concept-ki7409
ARTIFACTS_DIR = REPO_DIR / "automation" / "reports" / "daily"


def send_telegram_text(text: str) -> int:
    """Send text message to TG. Returns HTTP code."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("FATAL: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set", file=sys.stderr)
        return 0
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    return r.status_code


def build_reminder(
    today_hkt: str,
    weekday: str,
    snapshot: list[dict],
    grades: list[dict],
    candidates: list[dict],
    n_strategies: int = 3,
    n_tickers: int = 3,
) -> str:
    """Build the 4-section TG message."""

    # Section 1: Snapshot
    snap_lines = ["📊 **當前快照 (MNQ primary)**", "```"]
    snap_lines.append(f"{'Ticker':<8} {'Last':>10}  {'%Chg':>7}  Bias")
    snap_lines.append("-" * 50)
    for s in snapshot:
        if "err" in s:
            snap_lines.append(f"{s['tk']:<8} {'n/a':>10}  {'-':>7}  ?")
            continue
        arrow = "🟢" if s["pct"] > 0.1 else "🔴" if s["pct"] < -0.1 else "🟡"
        bias = "LONG" if s["pct"] > 0.3 else "SHORT" if s["pct"] < -0.3 else "NEUTRAL"
        snap_lines.append(
            f"{s['tk']:<8} {s['last']:>10.2f}  {arrow}{s['pct']:>+5.2f}  {bias}"
        )
    snap_lines.append("```")
    snap_text = "\n".join(snap_lines)

    # Section 2: LLM grades per (strategy × ticker)
    grade_lines = [f"🎯 **LLM 評級 ({n_strategies} strategies × {n_tickers} tickers)**", "```"]
    grade_lines.append(f"{'Strategy':<18} {'Ticker':<7} {'Gr':<3} {'Conf':<5} Reason")
    grade_lines.append("-" * 80)
    for g in grades:
        emoji = {"A": "🟢A", "B": "🟡B", "C": "🔴C"}.get(g["grade"], "❓")
        grade_lines.append(
            f"{g['strategy']:<18} {g['ticker']:<7} {emoji:<3} {g['confidence']:<5} {g['reason'][:40]}"
        )
    grade_lines.append("```")
    grade_text = "\n".join(grade_lines)

    # Section 3: Ranked candidates
    cand_lines = ["📋 **交易候選 (按優先級排序)**", "```"]
    cand_lines.append(f"{'#':<3} {'Strategy':<18} {'Ticker':<7} {'Gr':<3} {'Score':<6} {'Size':<6} Reason")
    cand_lines.append("-" * 90)
    for i, c in enumerate(candidates, 1):
        if c["actionable"]:
            emoji = {"A": "🟢A", "B": "🟡B"}.get(c["grade"], "❓")
            size = "1.0µ" if c["grade"] == "A" else "0.5µ"
            cand_lines.append(
                f"#{i:<3} {c['strategy']:<18} {c['ticker']:<7} {emoji:<3} "
                f"{c['priority_score']:<6} {size:<6} {c['reason'][:35]}"
            )
        else:
            cand_lines.append(
                f"#{i:<3} {c['strategy']:<18} {c['ticker']:<7} {c['grade']:<3} "
                f"{c['priority_score']:<6} {'skip':<6} {c['reason'][:35]}"
            )
    actionable = [c for c in candidates if c["actionable"]]
    if not actionable:
        cand_lines.append("")
        cand_lines.append("⚠️ 今日 0 actionable — 全部 C 級或更低")
        cand_lines.append("   嚴守紀律：空手觀望，保護本金")
    cand_lines.append("```")
    cand_text = "\n".join(cand_lines)

    # Section 4: Rules
    rules = """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## ⚠️ 風險規則
- 1 micro 限制 | Daily SL -$100 | Max DD -$2,000
- TP $150-250 (種田流), RR 1.5+
- Same-day exit (EOD 強制平倉)
- Killzone: NY AM 09-11 ET (進場) | NY PM 13:30-15 ET (減倉)

**優先級評分**: (Grade Weight + Confidence) × Strategy Weight
  - A=100, B=60, C=20
  - Strategy: H-Pattern 1.2×, 3-Pushes 1.0×, 兩陽夾一陰 0.8×
  - **Size**: A=1.0µ, B=0.5µ, C=skip

🔗 https://github.com/yip-lgtm/YW-concept-ki7409
"""

    msg = f"""🚨 **A 皮盤房 YW Concept 每日提醒** 🚨
📅 {today_hkt} ({weekday})  ⏰ 21:00 HKT / 13:00 UTC / 09:00 ET

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 1️⃣ 當前快照
{snap_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 2️⃣ 評級 ({n_strategies} strategies × {n_tickers} tickers)
{grade_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 3️⃣ 交易候選 (按優先級排序)
{cand_text}

{rules}

**Slogan**: 「等好 Setup，唔好追價。保護本金 > 一切。」
"""
    return msg


def send_escalation_alert(candidates: list[dict]) -> int:
    """Send a TG alert when any candidate has score > 80.

    Returns HTTP code (0 if not sent).
    """
    hot = [c for c in candidates if c.get("priority_score", 0) > 80 and c.get("actionable")]
    if not hot:
        return 0

    print(f"[yw_daily] 🔥 ESCALATION: {len(hot)} hot candidate(s) score > 80")

    lines = [f"🔥 *Hot Setup Alert — {len(hot)} candidate(s) score > 80*\n"]
    for i, c in enumerate(hot[:5], 1):
        emoji = {"A": "🟢", "B": "🟡", "C": "🔴"}.get(c["grade"], "❓")
        size = "1.0µ" if c["grade"] == "A" else "0.5µ"
        lines.append(
            f"{i}. {emoji} {c['strategy']} on *{c['ticker']}*\n"
            f"   Grade: *{c['grade']}* | Score: *{c['priority_score']:.1f}* | Size: {size}\n"
            f"   💡 {c['reason'][:100]}"
        )
    lines.append("\n📊 Full reminder follows below")

    msg = "\n".join(lines)
    return send_telegram_text(msg)


def main() -> int:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("FATAL: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set", file=sys.stderr)
        return 1

    now_hkt = datetime.now(HKT)
    today_str = now_hkt.strftime("%Y-%m-%d")
    weekday = now_hkt.strftime("%a")

    if weekday in ("Sat", "Sun"):
        print(f"[yw_daily] {weekday} - skipping (weekend)")
        return 0

    print(f"[yw_daily] Generating reminder for {today_str} ({weekday})")

    # Step 1: Snapshot
    print("[yw_daily] Pulling watchlist snapshot...")
    import yfinance as yf
    snapshot = []
    for tk, name in [("MNQ=F", "Micro Nasdaq"), ("MES=F", "Micro S&P"), ("M2K=F", "Micro Russell")]:
        try:
            d = yf.download(tk, period="5d", interval="1d", progress=False, auto_adjust=True)
            if d.empty:
                snapshot.append({"tk": tk, "name": name, "err": "no data"})
                continue
            if isinstance(d.columns, pd := __import__('pandas').MultiIndex):
                d.columns = d.columns.get_level_values(0)
            last = d.iloc[-1]
            prev = d.iloc[-2] if len(d) > 1 else last
            chg = float(last["Close"] - prev["Close"])
            pct = float(chg / prev["Close"] * 100) if prev["Close"] else 0.0
            snapshot.append({"tk": tk, "name": name, "last": float(last["Close"]), "chg": chg, "pct": pct})
        except Exception as e:
            snapshot.append({"tk": tk, "name": name, "err": str(e)[:40]})
    print(f"  ✓ {len(snapshot)} tickers")

    # Step 2: Grade each (strategy × ticker) — 9 calls
    from yw_grader import grade_strategy, rank_candidates, STRATEGIES, WATCHLIST

    print(f"[yw_daily] LLM grading {len(STRATEGIES)} strategies × {len(WATCHLIST)} tickers = {len(STRATEGIES) * len(WATCHLIST)} calls...")

    def _grade_one(args):
        sk, tk = args
        return grade_strategy(sk, tk)

    grades = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futs = {
            pool.submit(_grade_one, (sk, tk[0] if isinstance(tk, tuple) else tk)): (sk, tk[0] if isinstance(tk, tuple) else tk)
            for sk in STRATEGIES
            for tk in WATCHLIST
        }
        for fut in as_completed(futs):
            sk, tk = futs[fut]
            g = fut.result()
            grades.append(g)
            print(f"  {sk:<18} {tk:<7} → {g['grade']} (conf {g['confidence']})  {g['reason'][:50]}")

    # Step 3: Rank
    print("[yw_daily] Ranking candidates...")
    candidates = rank_candidates(grades)
    for i, c in enumerate(candidates, 1):
        if c["actionable"]:
            print(f"  #{i} {c['strategy']:<18} {c['ticker']:<7} [{c['grade']}] {c['priority_score']:.1f}")
        else:
            print(f"  #{i} {c['strategy']:<18} {c['ticker']:<7} [{c['grade']}] skip")

    # Step 4: Build message
    msg = build_reminder(today_str, weekday, snapshot, grades, candidates,
                         n_strategies=len(STRATEGIES), n_tickers=len(WATCHLIST))

    # Step 5: Save artifacts
    print("[yw_daily] Saving artifacts...")
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_dir = ARTIFACTS_DIR / today_str
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"reminder-{today_str}.md").write_text(msg, encoding="utf-8")
    (out_dir / f"grades-{today_str}.json").write_text(json.dumps({
        "date": today_str,
        "weekday": weekday,
        "generated_hkt": now_hkt.isoformat(),
        "grades": [{k: v for k, v in g.items() if k != "summary"} for g in grades],
        "candidates": [{k: v for k, v in c.items() if k != "summary"} for c in candidates],
        "snapshot": snapshot,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ {out_dir.relative_to(REPO_DIR)}")

    # Step 6: Send TG
    print("[yw_daily] Sending to Telegram...")
    code = send_telegram_text(msg)
    print(f"[yw_daily] HTTP {code}")

    # Step 6.4: Generate 4-Chart Standard charts (D / H4 / H1 / 5m) per ticker
    print("[yw_daily] Generating 4-Chart Standard charts...")
    try:
        from chart_gen import generate_for_ticker
        chart_dir = Path("/tmp/yw-charts")
        chart_dir.mkdir(parents=True, exist_ok=True)
        chart_paths = []
        with ThreadPoolExecutor(max_workers=3) as pool:
            futs = {
                pool.submit(generate_for_ticker, tk, name, chart_dir): tk
                for tk, name in [("MNQ=F", "Micro Nasdaq"), ("MES=F", "Micro S&P"), ("M2K=F", "Micro Russell")]
            }
            for fut in as_completed(futs):
                tk = futs[fut]
                p, _ = fut.result()
                if p:
                    chart_paths.append(p)
                    print(f"  ✓ {tk:6s} → {p.name}")
    except Exception as e:
        print(f"[yw_daily] ⚠️  Chart gen failed: {e}")
        chart_paths = []

    # Step 6.5: Escalation alert (if any candidate score > 80)
    print("[yw_daily] Checking escalation threshold (score > 80)...")
    esc_code = send_escalation_alert(candidates)
    if esc_code:
        print(f"[yw_daily] 🔥 Escalation HTTP {esc_code}")
    else:
        print(f"[yw_daily] No hot setups today (no candidate > 80)")

    # Step 7: Git push
    print("[yw_daily] Committing + pushing...")
    try:
        # Copy charts to tracked dir
        if chart_paths:
            for cp in chart_paths:
                try:
                    shutil.copy2(cp, out_dir / cp.name)
                except Exception as e:
                    print(f"[yw_daily] ⚠️  copy {cp.name} failed: {e}")

        # Set up git remote with PAT if available
        pat = os.environ.get("GITHUB_PAT", "") or os.environ.get("GITHUB_TOKEN", "")
        if pat:
            subprocess.run(
                ["git", "-C", str(REPO_DIR), "remote", "set-url", "origin",
                 f"https://x-access-token:{pat}@github.com/yip-lgtm/YW-concept-ki7409.git"],
                check=False, capture_output=True
            )
        # Stash any in-progress edits, fetch + reset, then re-apply
        subprocess.run(
            ["git", "-C", str(REPO_DIR), "fetch", "origin", "main"],
            check=False, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(REPO_DIR), "stash", "--include-untracked"],
            check=False, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(REPO_DIR), "reset", "--hard", "origin/main"],
            check=False, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(REPO_DIR), "stash", "pop"],
            check=False, capture_output=True
        )
        # Add + commit + push
        rel_paths = [
            str((out_dir / f"reminder-{today_str}.md").relative_to(REPO_DIR)),
            str((out_dir / f"grades-{today_str}.json").relative_to(REPO_DIR)),
        ] + [
            str((out_dir / cp.name).relative_to(REPO_DIR))
            for cp in chart_paths
        ]
        subprocess.run(
            ["git", "-C", str(REPO_DIR), "add"] + rel_paths,
            check=True, capture_output=True
        )
        r = subprocess.run(
            ["git", "-C", str(REPO_DIR), "diff", "--cached", "--name-only"],
            capture_output=True, text=True, check=True
        )
        if r.stdout.strip():
            subprocess.run(
                ["git", "-C", str(REPO_DIR), "-c", "user.name=YW bot",
                 "-c", "user.email=bot@apex.local",
                 "commit", "-m", f"auto(yw): daily analysis {today_str} ({weekday})"],
                check=True, capture_output=True
            )
            r2 = subprocess.run(
                ["git", "-C", str(REPO_DIR), "push", "origin", "main"],
                capture_output=True, text=True
            )
            if r2.returncode == 0:
                print(f"[yw_daily] ✓ Pushed: auto(yw) {today_str}")
            else:
                print(f"[yw_daily] ❌ Push failed: {r2.stderr[:200]}")
        else:
            print("[yw_daily] Nothing to commit")
    except Exception as e:
        print(f"[yw_daily] ❌ Git error: {e}")

    return 0 if code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
