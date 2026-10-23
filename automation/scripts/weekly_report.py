#!/usr/bin/env python3
"""Weekly report — the Friday trading journal card, and the arena standings.

The reference this is modelled on is a trader's weekly journal: a cumulative
points curve across the week, a headline box with the week's totals, and a
per-day breakdown listing every trade with its entry, its exit level and
its points. That is what this produces, from the live book's own trade log.

Two sources:
  live   — automation/reports/live_scan/trades.jsonl, the real book. One
           card: the week as a whole, day by day, trade by trade.
  arena  — the fifteen strategy agents' own trade logs. One card per agent
           plus the standings, because in a competition the interesting
           number is not one trader's week but whose week was better.

The points are price points in the instrument's own quote (MNQ at 4182
moving to 4092 is 90 points), signed by direction, so a short that closes
lower scores positive. Trades that closed without a fill — zero points —
are not counted as wins or losses and are left out of the breakdown, the
same way the reference leaves them out.

Rendering: one self-contained HTML file with the chart drawn as inline SVG,
rasterised to PNG with Playwright when a browser is available and left as
HTML when it is not. The PNG is what goes to Telegram.
"""
from __future__ import annotations
import os
import sys
import json
import argparse
import html
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path


def _find_repo() -> Path:
    if "GITHUB_WORKSPACE" in os.environ:
        return Path(os.environ["GITHUB_WORKSPACE"])
    for parent in Path(__file__).resolve().parents:
        if (parent / "automation").is_dir():
            return parent
    return Path("/workspace/YW-concept-ki7409")


REPO = _find_repo()
try:
    from zoneinfo import ZoneInfo
    NY_TZ = ZoneInfo("America/New_York")
except Exception:                                          # pragma: no cover
    NY_TZ = timezone(timedelta(hours=-4))

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID")

WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]

# Contract multipliers. Points are not comparable across instruments — a
# hundred BTC points is not a hundred MNQ points — so the week's headline is
# real dollars and the points stay on each trade line.
MULTIPLIERS = {"MNQ=F": 2.0, "MES=F": 5.0, "M2K=F": 5.0, "MGC=F": 10.0,
                "GC=F": 100.0, "MCL=F": 100.0, "BTC-USD": 1.0}


def log(msg: str):
    print(f"[weekly] {datetime.now(timezone.utc).strftime('%H:%M:%S')} {msg}", flush=True)


# ------------------------------------------------------------------- weeks

def week_bounds(ref: datetime) -> tuple[datetime, datetime]:
    """The Monday and Friday of the week that `ref` sits in (New York time)."""
    day = ref.astimezone(NY_TZ).date()
    monday = day - timedelta(days=day.weekday())
    friday = monday + timedelta(days=4)
    return (datetime.combine(monday, datetime.min.time(), tzinfo=NY_TZ),
            datetime.combine(friday, datetime.max.time(), tzinfo=NY_TZ))


def infer_sign(t: dict, entry: float) -> int:
    """Which way was this trade pointing, when the record does not say?

    The live book sometimes writes a blank direction. The stop and the
    target still say: a stop below the entry with a target above it is a
    long, the other way round is a short. 47 of the book's records are
    like that, and every one of them is a long — so the old fallback,
    which called anything that was not "long" a short, scored three of
    this week's losers as winners and moved the weekly total by $292.
    Zero means the direction could not be worked out; such a trade is
    left out rather than guessed at.
    """
    try:
        sl = float(t.get("sl") or 0)
        t2 = float(t.get("t2") or 0)
    except (TypeError, ValueError):
        return 0
    if not sl or not t2:
        return 0
    if sl < entry < t2:
        return 1
    if t2 < entry < sl:
        return -1


def normalise_trade(t: dict, entry: float, exit_p: float, agent: str,
                     ticker: str, exit_level: str, dt: datetime) -> dict | None:
    """One trade in the form the report needs.

    Two things can go wrong in the book's records and both have to be
    handled here rather than guessed at later:

    - The direction can be blank. The stop and the target still say which
      way the trade pointed, so `infer_sign` recovers it. The old
      fallback, which called anything that was not "long" a short, scored
      three of this week's losers as winners and moved the weekly total by
      $292.
    - The dollars must come from the R-multiple and the dollar risk, the
      same rule `contract_specs.trade_pnl_usd` uses. A trade that closed
      on a partial or a breakeven move has no single price move that
      explains it, while its R-multiple always does.
    """
    raw = str(t.get("direction", "")).lower()
    if raw in ("long", "buy", "up", "bullish"):
        sign = 1
    elif raw in ("short", "sell", "down", "bearish"):
        sign = -1
    else:
        sign = infer_sign(t, entry)
        if sign == 0:
            return None
    mult = MULTIPLIERS.get(ticker, float(t.get("usd_per_point") or 1))
    units = float(t.get("units") or 1)
    sl_dist = float(t.get("sl_dist") or 0)
    r_mult = t.get("R_multiple")
    pips = sign * (exit_p - entry)
    if r_mult is not None and sl_dist:
        usd = float(r_mult) * sl_dist * mult * units
    else:
        usd = pips * mult * units
    return {
        "agent": agent, "ticker": ticker,
        "direction": "long" if sign > 0 else "short",
        "entry": entry, "exit": exit_p,
        "exit_level": exit_level or "?",
        "pips": pips, "usd": usd,
        "dt": dt,
        "day": dt.astimezone(NY_TZ).strftime("%Y-%m-%d"),
        "r": r_mult,
        "grade": t.get("grade"),
    }


    return 0


def load_trades_live() -> list:
    path = REPO / "automation" / "reports" / "live_scan" / "trades.jsonl"
    out = []
    if not path.exists():
        return out
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line[0] not in "{[":
            continue
        try:
            t = json.loads(line)
        except Exception:
            continue
        if t.get("status") != "closed":
            continue
        try:
            entry = float(t["entry"])
            exit_p = float(t.get("exit_price") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        if not entry or not exit_p:
            continue
        ts = t.get("exit_time") or t.get("entry_time") or ""
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        row = normalise_trade(t, entry, exit_p, t.get("strategy", "?"),
                               t.get("ticker", "?"), t.get("exit_level") or "?", dt)
        if row:
            out.append(row)
    return out


def load_trades_arena() -> list:
    base = REPO / "automation" / "reports" / "arena" / "agents"
    out = []
    if not base.exists():
        return out
    for d in sorted(base.glob("*/trades.jsonl")):
        agent = d.parent.name
        for line in d.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line or line[0] != "{":
                continue
            try:
                t = json.loads(line)
            except Exception:
                continue
            entry = float(t.get("entry") or 0)
            exit_p = float(t.get("exit") or 0)
            if not entry or not exit_p:
                continue
            ts = t.get("closed") or t.get("opened") or ""
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            row = normalise_trade(t, entry, exit_p, agent, t.get("ticker", "?"),
                                   t.get("exit_level") or "?", dt)
            if row:
                out.append(row)
    return out


def in_week(trades: list, start: datetime, end: datetime) -> list:
    return [t for t in trades if start <= t["dt"] <= end]


# ------------------------------------------------------------------ stats

def summarise(trades: list) -> dict:
    counted = [t for t in trades if abs(t.get("usd", 0)) > 1e-9 or abs(t["pips"]) > 1e-9]
    wins = [t for t in counted if t.get("usd", t["pips"]) > 0]
    losses = [t for t in counted if t.get("usd", t["pips"]) <= 0]
    longs = [t for t in counted if t["direction"] == "long"]
    shorts = [t for t in counted if t["direction"] == "short"]
    by_day = defaultdict(list)
    for t in counted:
        by_day[t["day"]].append(t)
    for v in by_day.values():
        v.sort(key=lambda x: x["dt"])
    days = []
    for d in sorted(by_day):
        ts = by_day[d]
        w = [x for x in ts if x["pips"] > 0]
        l = [x for x in ts if x["pips"] < 0]
        days.append({
            "day": d, "trades": ts, "n": len(ts), "wins": len(w), "losses": len(l),
            "wr": (len(w) / len(ts)) if ts else 0.0,
            "pips": sum(x["pips"] for x in ts),
            "usd": sum(x.get("usd", x["pips"]) for x in ts),
        })
    cum = 0.0
    curve = []
    for d in days:
        cum += d["usd"]
        curve.append((d["day"], cum))
    by_inst = defaultdict(list)
    for t in counted:
        by_inst[t.get("ticker", "?")].append(t)
    instruments = []
    for tk, ts in by_inst.items():
        tw = [x for x in ts if x.get("usd", x["pips"]) > 0]
        instruments.append({
            "ticker": tk, "n": len(ts), "wins": len(tw), "losses": len(ts) - len(tw),
            "wr": len(tw) / len(ts) if ts else 0.0,
            "usd": sum(x.get("usd", x["pips"]) for x in ts),
            "pips": sum(x["pips"] for x in ts),
        })
    instruments.sort(key=lambda x: -x["usd"])
    return {
        "n": len(counted), "wins": len(wins), "losses": len(losses),
        "longs": len(longs), "shorts": len(shorts),
        "wr": (len(wins) / len(counted)) if counted else 0.0,
        "pips": sum(t["pips"] for t in counted),
        "usd": sum(t.get("usd", t["pips"]) for t in counted),
        "days": days, "curve": curve, "instruments": instruments,
        "skipped": len(trades) - len(counted),
    }


# ------------------------------------------------------------------- html

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 800px; background:
  radial-gradient(760px 420px at 78% -8%, rgba(198,142,44,.30), transparent 62%),
  radial-gradient(520px 300px at 10% -6%, rgba(150,98,26,.20), transparent 60%),
  linear-gradient(180deg,#0b0a10 0%,#07070c 55%,#0a0806 100%); color: #f3e9d2;
  font-family: "Noto Serif CJK TC", "Noto Serif CJK SC", "PingFang TC",
  "Microsoft JhengHei", serif; padding: 26px 26px 30px; }
.gold { background: linear-gradient(180deg,#ffe9a8 0%,#e8bd55 45%,#b8862b 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent; }
h1 { font-size: 30px; letter-spacing: 1px; }
h2 { font-size: 21px; color: #f0cb6a; }
.card { border: 1px solid rgba(224,178,76,.55); border-radius: 16px;
  padding: 14px 16px; margin: 12px 0;
  background: linear-gradient(180deg, rgba(60,44,16,.55), rgba(18,14,8,.55));
  box-shadow: 0 0 0 1px rgba(0,0,0,.35), 0 6px 24px rgba(0,0,0,.45); }
.row { display: flex; align-items: center; justify-content: space-between; }
.big { font-size: 26px; font-weight: 700; }
.tot { font-size: 30px; }
.up { color: #7ee08a; } .down { color: #ff8080; }
.pill { border: 1px solid rgba(224,178,76,.5); border-radius: 999px;
  padding: 2px 10px; font-size: 14px; color: #f0cb6a; }
.day { border: 1px solid rgba(224,178,76,.45); border-radius: 14px;
  padding: 10px 12px; margin: 8px 0;
  background: linear-gradient(180deg, rgba(48,36,14,.5), rgba(14,11,7,.5)); }
.day h3 { font-size: 18px; color: #f4d27a; margin-bottom: 6px; }
.tr { display: inline-block; width: 49%; font-size: 14px; line-height: 1.55;
  vertical-align: top; }
.tr b { color: #ffd97a; }
.long { color: #ff9a9a; } .short { color: #8fd0ff; } .flat { color: #b0a68c; }
.foot { color: #8d8367; font-size: 12px; margin-top: 14px; text-align: center; }
.legend { color: #a89a78; font-size: 13px; margin-top: 6px; }
"""


def esc(x) -> str:
    return html.escape(str(x))


def format_pts(p: float) -> str:
    v = round(p, 1)
    if abs(v - round(v)) < 0.05:
        v = int(round(v))
    return f"{v:+,.0f}" if abs(v) >= 1 else f"{v:+.1f}"


def chart_svg(curve: list, width: int = 690, height: int = 300) -> str:
    """The cumulative points curve, drawn as inline SVG."""
    if not curve:
        return '<svg width="0" height="0"></svg>'
    pad_l, pad_r, pad_t, pad_b = 96, 30, 40, 46
    w = width - pad_l - pad_r
    h = height - pad_t - pad_b
    vals = [v for _, v in curve]
    lo, hi = min(0.0, min(vals)), max(vals)
    if hi == lo:
        hi = lo + 1
    span = hi - lo

    def x(i):
        return pad_l + (w * i / max(1, len(curve) - 1))

    def y(v):
        return pad_t + h - ((v - lo) / span) * h

    pts = [(x(i), y(v)) for i, (_, v) in enumerate(curve)]
    line = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    area = f"{pts[0][0]:.1f},{y(lo):.1f} " + line + f" {pts[-1][0]:.1f},{y(lo):.1f}"
    grid = []
    ticks = 4
    for k in range(ticks + 1):
        v = lo + span * k / ticks
        yy = y(v)
        grid.append(f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{pad_l+w}" y2="{yy:.1f}" '
                    f'stroke="rgba(224,178,76,.20)" stroke-width="1"/>')
        grid.append(f'<text x="{pad_l-10}" y="{yy+5:.1f}" fill="#b09a62" '
                    f'font-size="13" text-anchor="end">${v:+,.0f}</text>')
    dots = []
    for i, ((day, v), (px, py)) in enumerate(zip(curve, pts)):
        wd = datetime.strptime(day, "%Y-%m-%d")
        label = f"{wd.month}/{wd.day} {WEEKDAYS[wd.weekday()]}"
        dots.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="#ffe9a8" '
                    f'stroke="#a97c22" stroke-width="2"/>')
        ly = max(py - 16, 16)
        dots.append(f'<text x="{px:.1f}" y="{ly:.1f}" fill="#ffe9a8" font-size="14" '
                    f'font-weight="700" text-anchor="middle">${v:+,.0f}</text>')
        dots.append(f'<text x="{px:.1f}" y="{height-14}" fill="#a89a78" font-size="13" '
                    f'text-anchor="middle">({label})</text>')
    return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0%" stop-color="rgba(255,214,120,.55)"/>'
            f'<stop offset="100%" stop-color="rgba(255,214,120,0)"/></linearGradient></defs>'
            + "".join(grid)
            + f'<polygon points="{area}" fill="url(#g)"/>'
            + f'<polyline points="{line}" fill="none" stroke="#ffd97a" stroke-width="3.5" '
              f'stroke-linejoin="round" stroke-linecap="round"/>'
            + "".join(dots) + "</svg>")


def trade_line(t: dict, idx: int) -> str:
    arrow = "🎯" if t["exit_level"] in ("T2", "T3", "T4", "T5") else \
            ("✅" if t.get("usd", t["pips"]) > 0 else "❌")
    side = "做多" if t["direction"] == "long" else "做空"
    cls = "long" if t["direction"] == "long" else "short"
    entry = f"{t['entry']:,.1f}".rstrip("0").rstrip(".")
    usd = t.get("usd", t["pips"])
    win = "up" if usd > 0 else "down"
    return (f'<span class="tr"><b>#{idx} </b>'
            f'<span class="{cls}">{side} {entry}</span> '
            f'{arrow} {t["exit_level"]} '
            f'<b class="{win}">{format_pts(t["pips"])}點</b>'
            f' <span class="{win}">${usd:+,.0f}</span></span>')


def render_card(title: str, subtitle: str, s: dict, extra_footer: str = "") -> str:
    days = s["days"]
    if not days:
        days_html = '<div class="legend">本週冇成交</div>'
    else:
        rows = []
        for d in days:
            wd = datetime.strptime(d["day"], "%Y-%m-%d")
            label = f"{wd.month}/{wd.day}（{WEEKDAYS[wd.weekday()]}）"
            wr_col = "up" if d["wr"] >= 0.5 else ("down" if d["wr"] < 0.4 else "")
            trades = []
            for i, t in enumerate(d["trades"], 1):
                trades.append(trade_line(t, i))
            while len(trades) % 2:
                trades.append('<span class="tr"></span>')
            rows.append(
                f'<div class="day"><h3>📅 {label} '
                f'<span class="{wr_col}">勝率 {d["wr"]:.0%} '
                f'(${d["usd"]:+,.0f})</span></h3>'
                f'{"".join(trades)}</div>')
        days_html = "".join(rows)

    wr_col = "up" if s["wr"] >= 0.5 else "down"
    pips_col = "up" if s["usd"] >= 0 else "down"
    headline = (f'{s["wins"]} 贏 {s["losses"]} 輸')
    if s["skipped"]:
        headline += f'（已無視 {s["skipped"]} 單無成交）'

    inst_rows = []
    for a in s.get("instruments", []):
        cls = "up" if a["usd"] >= 0 else "down"
        inst_rows.append(
            f'<span class="tr"><b>{a["ticker"]}</b> · {a["n"]} 單 · '
            f'WR {a["wr"]:.0%} · {a["wins"]}勝{a["losses"]}負 · '
            f'{a["pips"]:+,.0f} 點 · <b class="{cls}">${a["usd"]:+,.0f}</b></span>')
    while len(inst_rows) % 2:
        inst_rows.append('<span class="tr"></span>')
    instrument_rows = "".join(inst_rows)

    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>{CSS}</style></head><body>
<div style="display:flex;align-items:center;gap:14px;">
  <div style="font-size:40px">📈</div>
  <div><h1 class="gold">{esc(title)}</h1>
  <div class="legend">{esc(subtitle)}</div></div>
  <div style="margin-left:auto;font-size:46px;opacity:.9">🐂</div>
</div>

<div class="card" style="padding-top:8px">
  <h2 style="margin:4px 0 2px">📊 本週累計盈虧折線圖（真實美元）</h2>
  {chart_svg(s["curve"])}
</div>

<div class="card">
  <h2 style="margin-bottom:8px">【本週總結】<span class="pill">{s['n']} 單</span>
    <span class="pill {wr_col}">勝率 {s['wr']:.0%}</span>
    <span class="pill {pips_col}">合計 ${s['usd']:+,.0f}</span></h2>
  <div class="row" style="margin-top:6px">
    <div style="font-size:30px">🏆</div>
    <div>
      <div class="big" style="font-size:24px">本週 {s['n']} 單（做多 {s['longs']}，做空 {s['shorts']}）|
        <b class="{wr_col}">{headline}</b>| 勝率 <b class="{wr_col}">{s['wr']:.0%}</b> |
        合計 <b class="{pips_col}">${s['usd']:+,.0f}</b></div>
      <div class="legend">🎯 勝率　💰 合計真實美元（已計合約乘數 × 倉位）</div>
    </div>
  </div>
</div>

<div class="card">
  <h2 style="margin-bottom:6px">【分標的拆解】</h2>
  <div class="legend">（點數唔可以跨標的相加，所以主軸係真實美元）</div>
  {instrument_rows}
</div>

<div class="card">
  <h2 style="margin-bottom:6px">【每日交易細分】</h2>
  <div class="legend">（只列有成交嘅單）</div>
  {days_html}
</div>

<div class="foot">{extra_footer}</div>
</body></html>"""


def render_arena_card(s: dict, standings: list, title: str, subtitle: str) -> str:
    """The standings card. Every agent appears, even the ones that did not
    trade — an absent agent and an agent that made nothing are different
    facts and the board should show both."""
    rows = []
    for i, a in enumerate(standings, 1):
        rows.append(
            f'<tr><td>{i}</td><td>{esc(a["agent"])}</td>'
            f'<td>{a["level"]}</td>'
            f'<td class="{"up" if a.get("lv_delta", 0) > 0 else ("down" if a.get("lv_delta", 0) < 0 else "")}">'
            f'{a.get("lv_delta", 0):+d}</td><td>{a["n"]}</td>'
            f'<td class="{"up" if a["usd"] >= 0 else "down"}">${a["usd"]:+,.0f}</td>'
            f'<td class="{"up" if a["wins"] >= a["losses"] else "down"}">'
            f'{a["wins"]}勝{a["losses"]}輸</td></tr>')
    table = ("<table style='width:100%;border-collapse:collapse;font-size:15px'>"
             "<tr style='color:#f0cb6a'><th style='text-align:left'>#</th>"
             "<th style='text-align:left'>agent</th><th>lv</th><th>本週±lv</th>"
             "<th>n</th><th>美元</th><th>勝負</th></tr>" + "".join(rows) + "</table>")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>{CSS}
table td {{ padding: 4px 6px; border-bottom: 1px solid rgba(224,178,76,.18); }}
</style></head><body>
<div style="display:flex;align-items:center;gap:14px;">
  <div style="font-size:40px">🏆</div>
  <div><h1 class="gold">{esc(title)}</h1>
  <div class="legend">{esc(subtitle)}</div></div>
</div>
<div class="card">
  <h2 style="margin-bottom:8px">【本週競賽總結】</h2>
  <div class="big">15 個 agent · 總成交 <b>{s['n']}</b> 單 ·
    <b class="{"up" if s["wins"] >= s["losses"] else "down"}">{s['wins']} 贏 {s['losses']} 輸</b> ·
    勝率 <b class="{"up" if s["wr"] >= 0.5 else "down"}">{s['wr']:.0%}</b> ·
    合計 <b class="{"up" if s["usd"] >= 0 else "down"}">${s['usd']:+,.0f}</b></div>
  <div class="legend">（真實美元：價格變動 × 合約乘數 × 倉位，方向已計入）</div>
</div>
<div class="card"><h2 style="margin-bottom:6px">【本週逐 agent 戰績】</h2>{table}</div>
<div class="foot">紙上競賽：唔會落真單，只係郁各自帳戶數字。</div>
</body></html>"""


# ------------------------------------------------------------------ output

def render_png(html_text: str, out_png: Path) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        log(f"playwright missing: {e}")
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 800, "height": 900},
                                    device_scale_factor=2)
            page.set_content(html_text, wait_until="networkidle")
            h = page.evaluate("document.body.scrollHeight")
            page.set_viewport_size({"width": 800, "height": max(400, int(h) + 8)})
            page.screenshot(path=str(out_png), full_page=True)
            browser.close()
        log(f"png written: {out_png}")
        return True
    except Exception as e:
        log(f"png failed: {type(e).__name__}: {e}")
        return False


def already_posted(out_dir: Path, week: str, tag: str = "live") -> bool:
    """True when this week has already been published.

    The schedule fires every Friday but a week can be run twice — the first
    manual run and the first scheduled one, or a retried job. One weekly
    card per week, never two.
    """
    marker = out_dir / f"last_posted_{tag}_{week}"
    return marker.exists() and marker.read_text().strip() == week


def mark_posted(out_dir: Path, week: str, tag: str = "live"):
    (out_dir / f"last_posted_{tag}_{week}").write_text(week)


def _send_photo_urllib(path: Path, caption: str) -> bool:
    """Upload a photo with the standard library alone.

    `requests` is not installed in every environment this report runs in
    (the sandbox has no PyPI access), and a silent skip there means the
    weekly card never reaches Telegram. The multipart body is small and
    fixed, so it is cheaper to build it by hand than to depend on a
    package that may not be there.
    """
    boundary = uuid.uuid4().hex
    body = bytearray()

    def field(name: str, value: str):
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(value.encode() + b"\r\n")

    field("chat_id", str(TG_CHAT))
    field("caption", caption[:1000])
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="photo"; filename="{path.name}"\r\n'.encode())
    body.extend(b"Content-Type: image/png\r\n\r\n")
    body.extend(path.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return bool(json.loads(r.read().decode()).get("ok"))


def send_photo(path: Path, caption: str) -> bool:
    if not TG_TOKEN or not TG_CHAT:
        log("no telegram credentials — skipped")
        return False
    try:
        import requests
    except Exception:
        try:
            ok = _send_photo_urllib(path, caption)
        except Exception as e:
            log(f"telegram photo failed: {type(e).__name__}: {e}")
            return False
        log(f"telegram photo {'sent' if ok else 'FAILED'} (urllib): {path.name}")
        return ok
    try:
        with open(path, "rb") as f:
            files = {"photo": (path.name, f, "image/png")}
            data = {"chat_id": TG_CHAT, "caption": caption[:1000]}
            r = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                files=files, data=data, timeout=60)
        ok = r.json().get("ok")
        log(f"telegram photo {'sent' if ok else 'FAILED'}: {path.name}")
        return bool(ok)
    except Exception as e:
        log(f"telegram photo failed: {type(e).__name__}: {e}")
        return False


def send_text(text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT:
        return False
    try:
        data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": text[:4000]}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.loads(r.read().decode())
        return bool(body.get("ok"))
    except Exception as e:
        log(f"telegram text failed: {type(e).__name__}: {e}")
        return False


def markdown_digest(s: dict, title: str, subtitle: str) -> str:
    lines = [f"# {title}", "", subtitle, "",
             f"- 本週 {s['n']} 單（做多 {s['longs']}，做空 {s['shorts']}）",
             f"- **{s['wins']} 贏 {s['losses']} 輸** · 勝率 **{s['wr']:.0%}**",
             f"- 合計 **{s['usd']:+,.0f} 美元**", ""]
    lines.append("| 日期 | 單數 | 勝/負 | 勝率 | 美元 |")
    lines.append("|---|--:|--:|--:|--:|")
    for d in s["days"]:
        lines.append(f"| {d['day']} | {d['n']} | {d['wins']}/{d['losses']} | "
                     f"{d['wr']:.0%} | {d['usd']:+,.0f} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["live", "arena", "both"], default="both")
    ap.add_argument("--week-of", default=None,
                    help="any date inside the week (New York time). Default: today.")
    ap.add_argument("--out", default=str(REPO / "automation" / "reports" / "weekly"))
    ap.add_argument("--title", default=None)
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--no-telegram", action="store_true")
    args = ap.parse_args()

    ref = datetime.now(timezone.utc)
    if args.week_of:
        ref = datetime.fromisoformat(args.week_of)
    start, end = week_bounds(ref)
    label = f"{start.strftime('%m/%d')} 至 {end.strftime('%m/%d')}"
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"=== weekly report, week {start.date()} → {end.date()} ===")

    if args.source in ("live", "both"):
        trades = in_week(load_trades_live(), start, end)
        s = summarise(trades)
        title = args.title or "YW 交易週記"
        subtitle = f"本週總結（{label}）· {start.strftime('%Y')}"
        page = render_card(title, subtitle, s,
                           extra_footer=f"資料來源：live_scan trades.jsonl · "
                                        f"{start.date()} → {end.date()}")
        (out_dir / f"weekly_live_{start.date()}.html").write_text(page)
        (out_dir / f"weekly_live_{start.date()}.md").write_text(
            markdown_digest(s, title, subtitle))
        png = out_dir / f"weekly_live_{start.date()}.png"
        if not args.no_png:
            render_png(page, png)
        log(f"live week: {s['n']} trades, {s['wins']}W/{s['losses']}L, "
            f"${s['usd']:+,.0f}")
        if not args.no_telegram and png.exists() and not already_posted(out_dir, str(start.date()), "live"):
            if send_photo(png, f"📈 {title}（{label}）\n"
                            f"{s['n']} 單 · {s['wins']}贏{s['losses']}輸 · "
                            f"勝率 {s['wr']:.0%} · ${s['usd']:+,.0f}"):
                mark_posted(out_dir, str(start.date()), "live")
        elif png.exists():
            log("live card for this week was already published — no Telegram")

    if args.source in ("arena", "both"):
        trades = in_week(load_trades_arena(), start, end)
        s = summarise(trades)
        by_agent = defaultdict(list)
        for t in trades:
            by_agent[t["agent"]].append(t)
        standings = []
        base = REPO / "automation" / "reports" / "arena" / "agents"
        for d in sorted(base.glob("*/")):
            slug = d.name
            ts = by_agent.get(slug, [])
            a = summarise(ts)
            display, level, lv_delta = slug, 0, 0
            acct_file = d / "account.json"
            if acct_file.exists():
                try:
                    acct = json.loads(acct_file.read_text())
                    display = acct.get("agent", slug)
                    level = acct.get("level", 0)
                    days = acct.get("days", {})
                    for day, row in days.items():
                        if start.date() <= datetime.fromisoformat(day).date() <= end.date():
                            lv_delta += int(row.get("new_level", 0)) - int(row.get("old_level", 0))
                except Exception:
                    pass
            standings.append({"agent": display, "slug": slug, "level": level,
                              "lv_delta": lv_delta, "n": a["n"], "wins": a["wins"],
                              "losses": a["losses"], "usd": a["usd"], "pips": a["pips"]})
        standings.sort(key=lambda x: (-x["level"], -x["usd"]))
        title = "YW Arena 競賽場週榜"
        subtitle = f"本週總結（{label}）· 15 個策略 agent"
        page = render_arena_card(s, standings, title, subtitle)
        (out_dir / f"weekly_arena_{start.date()}.html").write_text(page)
        png = out_dir / f"weekly_arena_{start.date()}.png"
        if not args.no_png:
            render_png(page, png)
        log(f"arena week: {s['n']} trades, {s['wins']}W/{s['losses']}L, "
            f"${s['usd']:+,.0f}")
        if not args.no_telegram and png.exists() and not already_posted(out_dir, str(start.date()), "arena"):
            if send_photo(png, f"🏆 {title}（{label}）\n"
                            f"{s['n']} 單 · {s['wins']}贏{s['losses']}輸 · "
                            f"${s['usd']:+,.0f}"):
                mark_posted(out_dir, str(start.date()), "arena")
    return 0


if __name__ == "__main__":
    sys.exit(main())
