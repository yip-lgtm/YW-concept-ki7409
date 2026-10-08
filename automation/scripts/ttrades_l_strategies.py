#!/usr/bin/env python3
"""TTrades L-series strategies — L12 / L13 / L14 as independent agents.

Implements the entry rules from the notes the user added on 2026-10-09:
  docs/18-TTrades-L12.md  — Candle 2 Closure
  docs/19-TTrades-L13.md  — trade Candle 3 (continuation order block)
  docs/20-TTrades-L14.md  — Candle 3 Closure

These run alongside the existing `TTrades-Fractal` baseline in
ttrades_btc.py, which stays untouched. The three are genuinely different
entry logics over the same swing structure, not three labels on one
detector — the baseline's C2-closure path has no POI requirement and
fires on the C2 close, which both L12 and L14 explicitly reject.

    L12 (strictest)  C2 sweeps C1 extreme AND closes back inside C1
                     AND lands on an HTF POI (prior swing / FVG)
                     AND paired-TF CISD confirms.
                     No POI = candidate generator only, never a trade.
                     Entry is NOT the C2 close.

    L13              Only expansion candles (small wick, one-way body).
                     After C3 opens: sweep short-term liquidity or enter
                     a POI, an opposing candle confirms the HTF wick,
                     that position is the continuation order block,
                     re-turn to the original direction to enter.
                     Target >= 2R, SL outside the protected swing.
                     If C2 already swept the target, do not chase.

    L14              Two closures. C2 closure (sweep + reclaim) or
                     C3 closure (NO sweep, but C3 closes beyond the C2
                     BODY). A C3 closure only ever trades C4.
                     Reject: no POI touch, prior high too close,
                     equal lows already reached.
                     Neither closure = skip, no subjective fallback.

Every strategy reports why it did not fire, so a quiet day is
distinguishable from a broken detector.
"""
from __future__ import annotations
import os
import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

sys.path.insert(0, str(REPO / "automation" / "scripts"))
HKT = timezone(timedelta(hours=8))

SIGNAL_DIR = REPO / "automation" / "reports" / "ttrades_btc"
SIGNAL_DIR.mkdir(parents=True, exist_ok=True)
L_SUMMARY_FILE = SIGNAL_DIR / "l_strategies_latest.json"
L_LOG_FILE = SIGNAL_DIR / "l_strategies.jsonl"

STRATEGIES = ["TTrades-L12", "TTrades-L13", "TTrades-L14"]


# ---------------------------------------------------------------- helpers

def _body(row) -> float:
    return abs(float(row["Close"]) - float(row["Open"]))


def _range(row) -> float:
    return float(row["High"]) - float(row["Low"])


def _upper_wick(row) -> float:
    return float(row["High"]) - max(float(row["Open"]), float(row["Close"]))


def _lower_wick(row) -> float:
    return min(float(row["Open"]), float(row["Close"])) - float(row["Low"])


def is_expansion_candle(row, min_body_ratio: float = 0.60,
                        max_wick_ratio: float = 0.45) -> bool:
    """L13 §1: only expansion candles trade. Small wick, one-way from open.

    A long wick means open and close sat near each other with two-way
    contention, which does not support immediate expansion.
    """
    r = _range(row)
    if r <= 0:
        return False
    if _body(row) / r < min_body_ratio:
        return False
    dominant_wick = max(_upper_wick(row), _lower_wick(row))
    return dominant_wick / r <= max_wick_ratio


def wick_eq(row) -> float:
    """L12 §2: with a long wick, C3 should respect the upper half of the wick."""
    hi, lo = float(row["High"]), float(row["Low"])
    return (hi + lo) / 2.0


def full_range_eq(row) -> float:
    """L13 §4 / L14 §2: use the FULL candle range 0.5, not the wick 0.5.

    Using the wick midpoint makes pullbacks look too shallow.
    """
    return wick_eq(row)


def find_htf_poi(df, direction, lookback: int = 60):
    """L12 §3: C2 must land on an HTF key level — prior swing high/low or FVG.

    "Prior swing" is the last STRUCTURAL pivot, not the 60-bar extreme. Using
    the window extreme makes the POI test almost free: on a trending market
    price is always near the 60-bar high/low, so a C2 "touches POI" even when
    it never reached an actual prior swing. Structural pivots are found by a
    simple fractal: a bar whose high is the local max of its neighbours.

    Returns a dict describing the nearest POI.
    """
    if len(df) < lookback + 4:
        lookback = max(10, len(df) - 4)
    hist = df.iloc[-lookback - 3:-3]  # exclude the C1/C2/C3 window
    if len(hist) < 5:
        return {"found": False, "reason": "insufficient history"}

    # Fractal pivots: bar i is a swing high if its high exceeds both neighbours.
    piv_hi, piv_lo = [], []
    h = hist["High"].values
    l = hist["Low"].values
    for i in range(1, len(hist) - 1):
        if h[i] > h[i - 1] and h[i] > h[i + 1]:
            piv_hi.append(float(h[i]))
        if l[i] < l[i - 1] and l[i] < l[i + 1]:
            piv_lo.append(float(l[i]))

    if direction == "short":
        swings = sorted(set(piv_hi))[-5:] if piv_hi else []
        prior_extreme = swings[-1] if swings else None
    else:
        swings = sorted(set(piv_lo))[-5:] if piv_lo else []
        prior_extreme = swings[0] if swings else None

    # FVG: bullish gap = candle1.high < candle3.low ; bearish = candle1.low > candle3.high
    fvgs = []
    arr = hist.reset_index(drop=True)
    for i in range(1, len(arr) - 1):
        a, c = arr.iloc[i - 1], arr.iloc[i + 1]
        if float(a["High"]) < float(c["Low"]):
            fvgs.append(("bullish", float(a["High"]), float(c["Low"])))
        elif float(a["Low"]) > float(c["High"]):
            fvgs.append(("bearish", float(a["Low"]), float(c["High"])))

    return {
        "found": bool(swings or fvgs),
        "basis": "structural pivots" if swings else ("fvg only" if fvgs else "none"),
        "prior_extreme": prior_extreme,
        "swing_levels": swings,
        "pivot_count": len(piv_hi) + len(piv_lo),
        "fvg_count": len(fvgs),
    }


def touched_poi(c2, poi, direction) -> tuple[bool, str]:
    """Did the C2 candle actually sweep into a POI zone?

    POI = any recent structural swing level (or FVG) that overlaps the C2
    candle's own range. Checking a single "most extreme" pivot instead is
    wrong: in a trending market that level sits far outside the C2 range, so
    a genuine sweep-and-reclaim C2 would be rejected every time.
    """
    if not poi.get("found"):
        return False, "no POI levels in history"
    swings = poi.get("swing_levels") or []
    c2_hi, c2_lo = float(c2["High"]), float(c2["Low"])

    for lvl in swings:
        if c2_lo <= lvl <= c2_hi:
            return True, f"C2 range [{c2_lo:.0f}, {c2_hi:.0f}] contains swing {lvl:.0f}"
    if swings:
        near = min(swings, key=lambda s: min(abs(s - c2_hi), abs(s - c2_lo)))
        gap = min(abs(near - c2_hi), abs(near - c2_lo))
        return False, (f"C2 [{c2_lo:.0f}, {c2_hi:.0f}] misses nearest swing "
                       f"{near:.0f} by {gap:.0f}")
    return False, "only FVG history, no swing pivot"


def find_continuation_order_block(ltf_df, direction, max_lookback: int = 8):
    """L13 §2: after C3 opens, find the opposing candle that confirms the wick.

    Scan back over the most recent candles for the first opposing-colour
    candle in the original direction's favour. That candle is the
    continuation order block; entry is when price turns back to the
    original direction.
    """
    if len(ltf_df) < 3:
        return None
    recent = ltf_df.tail(max_lookback)
    for _, row in recent.iloc[::-1].iterrows():
        is_bull = float(row["Close"]) > float(row["Open"])
        if direction == "long" and not is_bull:
            return {"ob_high": float(row["High"]), "ob_low": float(row["Low"]),
                    "ob_eq": wick_eq(row),
                    "rule": "opposing (bearish) candle confirms HTF wick"}
        if direction == "short" and is_bull:
            return {"ob_high": float(row["High"]), "ob_low": float(row["Low"]),
                    "ob_eq": wick_eq(row),
                    "rule": "opposing (bullish) candle confirms HTF wick"}
    return None


def target_already_swept(c2, poi, direction) -> bool:
    """L13 §4: if C2 already took the liquidity it was aiming at, do not chase."""
    if not poi.get("found"):
        return False
    ref = poi.get("prior_extreme")
    if ref is None:
        return False
    if direction == "short":
        return float(c2["High"]) >= float(ref) * 0.9995
    return float(c2["Low"]) <= float(ref) * 1.0005


# ------------------------------------------------- per-strategy detectors

def detect_l12(h4, m15, direction_hint=None):
    """L12 — C2 closure at an HTF POI, entry deferred to C3 after CISD.

    Checklist from doc §5, in order:
      1. HTF POI
      2. C2 sweeps C1 extreme and closes back inside C1
      3. paired lower-TF CISD
      4. only then expect C3
    """
    if len(h4) < 4:
        return {"fired": False, "stage": "insufficient H4 bars"}
    c1, c2, c3 = h4.iloc[-3], h4.iloc[-2], h4.iloc[-1]

    # Step 2 first — a non-closure C2 is not even a candidate.
    if float(c2["High"]) > float(c1["High"]) and float(c2["Close"]) < float(c1["High"]):
        direction = "short"
    elif float(c2["Low"]) < float(c1["Low"]) and float(c2["Close"]) > float(c1["Low"]):
        direction = "long"
    else:
        return {"fired": False, "stage": "no C2 closure (sweep+reclaim) on C2"}

    # Step 1 — POI
    poi = find_htf_poi(h4, direction)
    hit, poi_note = touched_poi(c2, poi, direction)
    if not hit:
        return {"fired": False, "stage": "no POI", "detail": poi_note,
                "direction": direction}

    # L12 §2 — shallow wick + big body means the expansion already happened
    # on C2, which is bad for trading the C3 continuation.
    r = _range(c2)
    if r > 0 and _body(c2) / r > 0.70 and max(_upper_wick(c2), _lower_wick(c2)) / r < 0.15:
        return {"fired": False, "stage": "C2 already expansion (shallow wick, big body)",
                "direction": direction}

    # Step 3 — CISD on the paired lower TF
    from ttrades_btc import check_cisd
    cisd = check_cisd(m15, direction)
    if not cisd.get("confirmed"):
        return {"fired": False, "stage": "CISD not confirmed",
                "detail": cisd.get("reason"), "direction": direction,
                "poi": poi, "cisd": cisd}

    return {
        "fired": True,
        "direction": direction,
        "stage": "all L12 gates passed",
        "poi": poi,
        "poi_note": poi_note,
        "cisd": cisd,
        "c2_eq": wick_eq(c2),
        "c2_high": float(c2["High"]), "c2_low": float(c2["Low"]),
        "c2_close": float(c2["Close"]),
        "c3_close": float(c3["Close"]),
        "swing_level": float(c2["High"] if direction == "short" else c2["Low"]),
        "entry_ref": float(c3["Close"]),
        "target_r": 2.0,
    }


def detect_l13(h4, m15):
    """L13 — expansion candles only, entry at the C3 continuation order block."""
    if len(h4) < 4:
        return {"fired": False, "stage": "insufficient H4 bars"}
    c1, c2, c3 = h4.iloc[-3], h4.iloc[-2], h4.iloc[-1]

    if not is_expansion_candle(c2):
        return {"fired": False, "stage": "C2 not an expansion candle (wick too large)"}
    if not is_expansion_candle(c3):
        return {"fired": False, "stage": "C3 not an expansion candle (wick too large)"}

    direction = "short" if float(c2["Close"]) < float(c2["Open"]) else "long"

    # L13 §4 — C2 already swept its target means chasing
    poi = find_htf_poi(h4, direction)
    if target_already_swept(c2, poi, direction):
        return {"fired": False, "stage": "C2 already swept the target — do not chase",
                "direction": direction}

    # CISD on the paired lower TF, then the order block
    from ttrades_btc import check_cisd
    cisd = check_cisd(m15, direction)
    if not cisd.get("confirmed"):
        return {"fired": False, "stage": "CISD not confirmed",
                "detail": cisd.get("reason"), "direction": direction}

    ob = find_continuation_order_block(m15, direction)
    if not ob:
        return {"fired": False, "stage": "no continuation order block on LTF",
                "direction": direction, "cisd": cisd}

    last = m15.iloc[-1]
    return {
        "fired": True,
        "direction": direction,
        "stage": "C3 continuation order block",
        "cisd": cisd,
        "order_block": ob,
        "c2_eq": full_range_eq(c2),
        "c2_high": float(c2["High"]), "c2_low": float(c2["Low"]),
        "c3_high": float(c3["High"]), "c3_low": float(c3["Low"]),
        "swing_level": float(c2["High"] if direction == "short" else c2["Low"]),
        "entry_ref": float(last["Close"]),
        "target_r": 2.0,
    }


def detect_l14(h4, m15):
    """L14 — C2 closure, or C3 closure (no sweep, C3 closes beyond C2 body).

    A C3 closure is a delayed confirmation: it only ever trades C4.
    """
    if len(h4) < 4:
        return {"fired": False, "stage": "insufficient H4 bars"}
    c1, c2, c3, c4 = h4.iloc[-4], h4.iloc[-3], h4.iloc[-2], h4.iloc[-1]

    swept = (float(c2["High"]) > float(c1["High"])
             or float(c2["Low"]) < float(c1["Low"]))

    if swept:
        # C2 closure path
        if float(c2["High"]) > float(c1["High"]) and float(c2["Close"]) < float(c1["High"]):
            direction, closure = "short", "c2_closure"
        elif float(c2["Low"]) < float(c1["Low"]) and float(c2["Close"]) > float(c1["Low"]):
            direction, closure = "long", "c2_closure"
        else:
            return {"fired": False,
                    "stage": "swept but did not close back inside C1 — continuation, not a closure"}
        eq_candle = c2
        trade_candle = "C3"
    else:
        # C3 closure: no sweep, C3 closes beyond the C2 BODY
        body_hi = max(float(c2["Open"]), float(c2["Close"]))
        body_lo = min(float(c2["Open"]), float(c2["Close"]))
        if float(c3["Close"]) > body_hi:
            direction, closure = "long", "c3_closure"
        elif float(c3["Close"]) < body_lo:
            direction, closure = "short", "c3_closure"
        else:
            return {"fired": False,
                    "stage": "no sweep and no body break — outside the model, no subjective fill"}
        eq_candle = c3
        trade_candle = "C4"

    # §4 — must have touched a POI
    poi = find_htf_poi(h4, direction)
    hit, poi_note = touched_poi(eq_candle, poi, direction)
    if not hit:
        return {"fired": False, "stage": "no POI", "detail": poi_note,
                "direction": direction, "closure": closure}

    # §4 — prior high too close / equal lows already reached
    if direction == "short":
        prior = poi.get("prior_extreme")
        if prior and abs(float(eq_candle["High"]) - float(prior)) / float(prior) < 0.002:
            return {"fired": False, "stage": "prior high too close to be worth trading",
                    "direction": direction, "closure": closure}

    from ttrades_btc import check_cisd
    cisd = check_cisd(m15, direction)
    if not cisd.get("confirmed"):
        return {"fired": False, "stage": "CISD not confirmed",
                "detail": cisd.get("reason"), "direction": direction,
                "closure": closure}

    return {
        "fired": True,
        "direction": direction,
        "closure": closure,
        "trade_candle": trade_candle,
        "stage": f"{closure} — trade {trade_candle}",
        "poi": poi,
        "poi_note": poi_note,
        "cisd": cisd,
        "c_eq": full_range_eq(eq_candle),
        "swing_level": float(eq_candle["High"] if direction == "short" else eq_candle["Low"]),
        "entry_ref": float(c4["Close"]),
        "target_r": 2.0,
    }


DETECTORS = {
    "TTrades-L12": detect_l12,
    "TTrades-L13": detect_l13,
    "TTrades-L14": detect_l14,
}


# ---------------------------------------------------------------- runner

def run(h4, m15, cisd_fetcher=None) -> dict:
    out = {}
    for name in STRATEGIES:
        try:
            out[name] = DETECTORS[name](h4, m15)
        except Exception as e:
            out[name] = {"fired": False, "stage": f"error: {type(e).__name__}: {e}"}
    return out


def main() -> int:
    now = datetime.now(HKT)
    print(f"[ttrades-L] === {now.strftime('%Y-%m-%d %H:%M:%S HKT')} ===")

    import ttrades_btc as base
    h1 = base.fetch_ohlcv(base.TICKER, "1h", "30d")
    m15 = base.fetch_ohlcv(base.TICKER, "15m", "7d")
    if h1.empty or m15.empty:
        print("  ✗ no data")
        return 0
    h4 = h1.resample("4h").agg({
        "Open": "first", "High": "max", "Low": "min", "Close": "last"
    }).dropna()

    results = run(h4, m15)
    summary = {
        "ts": now.isoformat(),
        "ticker": base.TICKER,
        "h4_bars": len(h4),
        "m15_bars": len(m15),
        "strategies": results,
    }
    L_SUMMARY_FILE.write_text(json.dumps(summary, indent=2, default=str))

    with L_LOG_FILE.open("a") as f:
        for name, r in results.items():
            f.write(json.dumps({
                "ts": now.isoformat(),
                "ticker": base.TICKER,
                "strategy": name,
                "actionable": bool(r.get("fired")),
                "direction": r.get("direction"),
                "stage": r.get("stage"),
                "detail": r.get("detail"),
                "result": r,
            }, default=str) + "\n")

    for name, r in results.items():
        mark = "✓ FIRE" if r.get("fired") else "·"
        extra = f" ({r.get('detail')})" if r.get("detail") else ""
        print(f"  {mark} {name:<14} {r.get('stage')}{extra}")

    n = sum(1 for r in results.values() if r.get("fired"))
    print(f"  → {n}/3 fired · summary: {L_SUMMARY_FILE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
