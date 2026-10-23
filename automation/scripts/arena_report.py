#!/usr/bin/env python3
"""Arena report — render the day's board and the agents' trash talk, and
publish it.

The leaderboard comes from arena.py. The trash talk comes from the fifteen
agent sessions, each of which writes a short file into the taunts folder
after it sees its own score for the day. This script puts the two together,
writes the digest into the repo, and posts it to Telegram.

Run it without arguments in CI to publish the board alone. Run it with
--taunts pointing at a folder to include the banter — that is how the host
session publishes the full version after the agents have written theirs.
"""
from __future__ import annotations
import os
import sys
import json
import argparse
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def _find_repo() -> Path:
    if "GITHUB_WORKSPACE" in os.environ:
        return Path(os.environ["GITHUB_WORKSPACE"])
    for parent in Path(__file__).resolve().parents:
        if (parent / "automation").is_dir():
            return parent
    return Path("/workspace/YW-concept-ki7409")


REPO = _find_repo()
ARENA_DIR = REPO / "automation" / "reports" / "arena"

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID")


def load_board() -> dict | None:
    p = ARENA_DIR / "leaderboard.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def load_taunts(day: str, taunts_dir: Path) -> list:
    """Read the agents' trash talk for the day, in board order."""
    out = []
    if not taunts_dir.exists():
        return out
    for f in sorted(taunts_dir.glob(f"{day}*.md")):
        try:
            text = f.read_text().strip()
        except Exception:
            continue
        if not text:
            continue
        # The file name carries the agent slug; the first line carries the
        # display name, usually with a marker the agent added.
        name = f.stem.split("_", 1)[1].replace("_", "-") if "_" in f.stem else f.stem
        display = text.splitlines()[0].lstrip("# ").strip() if text else name
        for marker in ("💬", "🗣", "🎤"):
            if display.startswith(marker):
                display = display[len(marker):].strip()
        body = "\n".join(text.splitlines()[1:]).strip() or text
        out.append({"slug": name, "display": display, "text": body})
    return out


def render(board: dict, taunts: list) -> str:
    day = board["day"]
    rows = board["board"]
    lines = [f"🏆 ARENA — {day}", ""]
    lines.append("紙上競技場：15 個策略 agent 各自揸住自己個帳戶，全標的、可同時持倉。"
                 "目標：日日 +1 level。")
    lines.append(f"（成績 = 已結算嗰日 {day}；最後一欄係進行中嗰日）")
    lines.append("")
    lines.append("| # | agent | lv | 昨日結果 | n | WR | PF | RR | 昨日 P&L | equity | 今日進行中 |")
    lines.append("|---:|---|--:|---|--:|--:|--:|--:|--:|--:|---|")
    for r in rows:
        m = r["today"]
        pf = "—" if m["PF"] is None else f"{m['PF']:.2f}"
        rr = "—" if m.get("RR") is None else f"{m['RR']:.2f}"
        wr_col = "up" if m["WR"] >= 0.5 else "down"
        pf_col = "up" if (m["PF"] or 0) > 1 else "down"
        rr_col = "up" if (m.get("RR") or 0) > 1 else "down"
        live = r.get("live") or {}
        live_txt = "—" if not live.get("n") else (
            f"{live['n']} 單 · ${live['pnl_usd']:+,.0f}")
        lines.append(
            f"| {r['rank']} | {r['agent']} | {r['level']} | {r['action']} | "
            f"{m['n']} | {wr_col} {m['WR']:.0%} | {pf_col} {pf} | {rr_col} {rr} | "
            f"${m['pnl_usd']:+,.0f} | "
            f"${r['equity_usd']:+,.0f} | {live_txt} |")
    leaders = [r for r in rows if r["action"] == "promote"]
    if leaders:
        names = "、".join(r["agent"] for r in leaders)
        lines += ["", f"⬆️ 升級：{names}"]
    losers = [r for r in rows if r["action"] == "demote"]
    if losers:
        names = "、".join(r["agent"] for r in losers)
        lines += [f"⬇️ 降級：{names}"]
    if taunts:
        lines += ["", "──── 互噴環節 ────", ""]
        for t in taunts:
            lines.append(f"💬 {t['display']}")
            lines.append(t["text"])
            lines.append("")
    return "\n".join(lines).strip()


def post_tg(text: str) -> bool:
    """Publish to Telegram as plain text, split into chunks that fit.

    No parse_mode: the agents write ordinary prose with angle brackets and
    ampersands in it, and Telegram rejects the whole message when the HTML
    parser chokes on one stray character.
    """
    if not TG_TOKEN or not TG_CHAT:
        print("[arena-report] no Telegram credentials — skipped")
        return False
    chunks = []
    current = []
    for line in text.splitlines():
        if sum(len(x) + 1 for x in current) + len(line) > 3800:
            chunks.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        chunks.append("\n".join(current))
    ok_all = True
    for i, chunk in enumerate(chunks):
        try:
            data = urllib.parse.urlencode({
                "chat_id": TG_CHAT, "text": chunk,
                "disable_web_page_preview": "true",
            }).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data)
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.loads(r.read().decode())
            ok = bool(body.get("ok"))
            if not ok:
                ok_all = False
                print(f"[arena-report] telegram chunk {i+1} rejected: {body}")
            else:
                print(f"[arena-report] telegram chunk {i+1}/{len(chunks)} sent")
        except Exception as e:
            ok_all = False
            print(f"[arena-report] telegram chunk {i+1} failed: "
                  f"{type(e).__name__}: {e}")
    return ok_all


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--taunts", default=str(ARENA_DIR / "taunts"),
                    help="folder holding the agents' trash talk")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--tag", default="board",
                    help="which one-post-per-day marker to use. The CI "
                         "publishes the board, the host session publishes the "
                         "banter, and they must not share a marker or one "
                         "would suppress the other.")
    ap.add_argument("--out", default=str(ARENA_DIR))
    args = ap.parse_args()

    board = load_board()
    if not board:
        print("[arena-report] no leaderboard.json — nothing to report")
        return 1
    day = board["day"]
    taunts = load_taunts(day, Path(args.taunts))
    text = render(board, taunts)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"arena_digest_{day}.md").write_text(text + "\n")
    print(f"[arena-report] wrote arena_digest_{day}.md ({len(text)} chars, "
          f"{len(taunts)} taunts)")

    if args.no_telegram:
        return 0
    # The engine runs every fifteen minutes, but the board is published once
    # a day. The marker file is what keeps it to one post per New York day,
    # and the tag keeps the board's marker and the banter's marker apart.
    marker = out_dir / f"last_posted_{args.tag}"
    if marker.exists() and marker.read_text().strip() == day:
        print(f"[arena-report] already published {args.tag} today — "
              "skipping Telegram")
        return 0
    if post_tg(text):
        marker.write_text(day)
    return 0


if __name__ == "__main__":
    sys.exit(main())
