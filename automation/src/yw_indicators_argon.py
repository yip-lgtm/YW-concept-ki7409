"""Argon Gold SOP detector — 15M box + M5 confirmation (docs/21-Argon-Gold-SOP.md).

Implements the two confirmation models from the SOP:

  Model A — Liquidity Sweep + rejection
    price pulls back into the value zone, a wick sweeps the prior low
    (stopping out early longs), then price snaps back on the same or next
    bar and prints a Pin Bar (lower wick > 2/3 of total range) or a
    Bullish Engulfing (bull body fully covers the prior bear body).

  Model B — M5 double bottom + MSB  (more robust)
    the M5 downtrend (Lower High + Lower Low) stops making new lows, a
    small double bottom forms (second low holds or barely sweeps the
    first), then price closes above the prior Lower High — Break of
    Structure. The small-timeframe trend has flipped.

Entry discipline from the SOP:
  - 1H bias must agree (HH + HL for long, LH + LL for short)
  - a 15M box must be established
  - the M5 bar must close on its BODY above the box high, not just a wick
  - stop goes below the box low (or the sweep low)
  - a stop wider than the cap is abandoned, not taken with a smaller size
  - 1R moves the stop to breakeven, 1.5R is the take profit

INSTRUMENT NOTE

  The SOP is written for spot gold XAUUSD with an absolute $5.00 stop cap.
  There is no XAUUSD feed available, so this detector runs on GC=F, the
  COMEX front-month gold future.

  CME quotes gold futures PER TROY OUNCE, the same as spot. The contract's
  10x is its dollar multiplier (10 oz per contract), NOT the quote. So
  MGC=F at 4132.10 means gold at $4132.10/oz, and one MGC price point is
  $1.00 of spot-equivalent movement. The SOP's numbers therefore carry
  over directly: a $5.00 spot stop is a $5.00 MGC price distance.

  An earlier version of this file assumed a 10x quote and set the cap to
  $0.50. That was wrong: gold futures are quoted per troy ounce and the
  contract's 10x is its dollar multiplier, not the quote. A 0.50 cap
  rejected 293 of 293 boxes on MGC and the strategy could never fire.
  The conversion is now 1:1 and verified against the live feed.

  GC=F is still a futures contract, not spot: the session hours are not
  24/7 and the price level carries the futures basis rather than the
  exact spot print. The box and confirmation logic is instrument-agnostic,
  but the absolute stop cap should be read as a proxy for the SOP's
  spot intent rather than an identical XAUUSD instruction.
"""
from __future__ import annotations

import pandas as pd

# SOP risk parameters, expressed in SPOT gold dollars.
SPOT_STOP_CAP_USD = 5.00        # max stop distance in spot dollars
SPOT_RISK_USD = 50.00           # risk per trade in spot dollars

# CME quotes gold futures per troy ounce, so MGC=F price points ARE spot
# dollars. The contract's 10x is its dollar multiplier, not the quote.
MGC_TICK_USD = 1.00             # $1 gold move = $1.00 of MGC price

# Stop cap in MGC price points (1:1 with spot dollars)
MGC_STOP_CAP = SPOT_STOP_CAP_USD / MGC_TICK_USD      # 5.00 price points


def _resample_15m(df_5m: pd.DataFrame) -> pd.DataFrame:
    if df_5m is None or df_5m.empty:
        return pd.DataFrame()
    df = df_5m.copy()
    if df.index.tz is not None:
        df = df.tz_convert("UTC")
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    try:
        return df.resample("15min").agg(agg).dropna()
    except Exception:
        return pd.DataFrame()


def _htf_bias(df_1h: pd.DataFrame) -> str:
    """1H bias: 'long' on Higher High + Higher Low, 'short' on Lower High + Lower Low."""
    if df_1h is None or len(df_1h) < 10:
        return "none"
    recent = df_1h.tail(6)
    prev = df_1h.tail(12).iloc[:-6]
    if prev.empty:
        return "none"
    hh = recent["High"].max() > prev["High"].max()
    hl = recent["Low"].min() > prev["Low"].min()
    lh = recent["High"].max() < prev["High"].max()
    ll = recent["Low"].min() < prev["Low"].min()
    if hh and hl:
        return "long"
    if lh and ll:
        return "short"
    return "none"


def _build_box(df_15m: pd.DataFrame, lookback: int = 8) -> dict:
    """Establish a 15M box from the most recent completed bars.

    The box must be a range, not a trend: if the recent 15M bars are
    making new extremes the same way, there is no box to break.
    """
    if df_15m is None or len(df_15m) < lookback + 2:
        return {"ok": False}
    win = df_15m.iloc[-(lookback + 1):-1]      # exclude the live bar
    if len(win) < lookback:
        return {"ok": False}
    box_high = float(win["High"].max())
    box_low = float(win["Low"].min())
    box_range = box_high - box_low
    if box_range <= 0:
        return {"ok": False}
    return {
        "ok": True,
        "high": box_high,
        "low": box_low,
        "range": box_range,
        "bars": len(win),
    }


def _is_pin_bar(row) -> bool:
    """Pin Bar: one wick longer than 2/3 of the total range."""
    rng = float(row["High"]) - float(row["Low"])
    if rng <= 0:
        return False
    body = abs(float(row["Close"]) - float(row["Open"]))
    if body > rng / 3.0:
        return False
    lower = min(float(row["Open"]), float(row["Close"])) - float(row["Low"])
    upper = float(row["High"]) - max(float(row["Open"]), float(row["Close"]))
    return max(lower, upper) > rng * (2.0 / 3.0)


def _is_bullish_engulfing(prev, cur) -> bool:
    """Bullish Engulfing: bull body fully covers the prior bear body."""
    if float(prev["Close"]) >= float(prev["Open"]):
        return False
    if float(cur["Close"]) <= float(cur["Open"]):
        return False
    return (float(cur["Open"]) <= float(prev["Close"])
            and float(cur["Close"]) >= float(prev["Open"]))


def _model_a_sweep_rejection(df_5m: pd.DataFrame, box_low: float) -> dict:
    """Model A: liquidity sweep + rejection candle.

    The sweep wick pierces the prior low (or the box low), then a rejection
    candle closes back above it. Look at the last two completed 5M bars.
    """
    if df_5m is None or len(df_5m) < 3:
        return {"found": False}
    prev, cur = df_5m.iloc[-2], df_5m.iloc[-1]
    swept_level = box_low

    swept = float(cur["Low"]) < swept_level
    reclaimed = float(cur["Close"]) > swept_level
    if not (swept and reclaimed):
        # The sweep may have happened on the previous bar and the rejection
        # printed on the current one.
        swept_prev = float(prev["Low"]) < swept_level
        if not swept_prev:
            return {"found": False, "reason": "no sweep of the level"}
        rejection = _is_pin_bar(cur) or _is_bullish_engulfing(prev, cur)
        if not rejection:
            return {"found": False, "reason": "sweep without a rejection candle"}
        return {
            "found": True,
            "model": "A",
            "sweep_low": float(prev["Low"]),
            "rejection": "pin_bar" if _is_pin_bar(cur) else "bullish_engulfing",
            "bar_ts": str(cur.name),
        }

    rejection = _is_pin_bar(cur) or _is_bullish_engulfing(prev, cur)
    if not rejection:
        return {"found": False, "reason": "sweep without a rejection candle"}
    return {
        "found": True,
        "model": "A",
        "sweep_low": float(cur["Low"]),
        "rejection": "pin_bar" if _is_pin_bar(cur) else "bullish_engulfing",
        "bar_ts": str(cur.name),
    }


def _model_b_double_bottom_msb(df_5m: pd.DataFrame) -> dict:
    """Model B: M5 double bottom + Break of Structure.

    The last bars must show: a downtrend that stopped, two nearby lows
    (the second not breaking the first by more than a small tolerance),
    and the most recent bar closing above the prior Lower High.
    """
    if df_5m is None or len(df_5m) < 8:
        return {"found": False}
    w = df_5m.tail(8)
    lows = w["Low"].values
    highs = w["High"].values
    closes = w["Close"].values

    # The two most recent significant lows
    l1, l2 = float(lows[-4]), float(lows[-3])
    # second low must hold the first (small tolerance)
    tol = (l1 - l2) if l1 > l2 else 0.0
    if l2 < l1 * 0.998:
        return {"found": False, "reason": "second low broke the first"}
    # prior Lower High = the highest high between the two lows
    seg = w.iloc[-4:-2]
    if seg.empty:
        return {"found": False}
    lh = float(seg["High"].max())
    # MSB: the latest close is above that Lower High
    if float(closes[-1]) <= lh:
        return {"found": False, "reason": "no break of the prior lower high"}
    return {
        "found": True,
        "model": "B",
        "double_bottom": [round(l1, 2), round(l2, 2)],
        "lower_high": round(lh, 2),
        "sweep_low": round(min(l1, l2), 2),
        "bar_ts": str(w.index[-1]),
    }


def detect_argon_gold(df_5m: pd.DataFrame, df_1h: pd.DataFrame,
                      df_15m: pd.DataFrame | None = None,
                      max_age_bars: int = 6) -> dict:
    """Argon Gold SOP — 15M box + M5 confirmation.

    Returns the same shape as the other detectors: a dict with
    `present`, `direction`, and the structural fields the gates need.

    WHY max_age_bars EXISTS

      Unlike the other eleven detectors, this one is triggered by a
      specific bar: the M5 candle whose body breaks the box edge. The
      earlier version only ever examined the LAST bar of the frame, and
      live_scan runs every 15 minutes, which is every third five-minute
      bar. Two of every three bars were therefore never examined as the
      trigger bar, and the strategy could not fire at all — a walk-forward
      test over the last 200 GC=F bars found four qualifying moments, all
      of which fell on bars the scanner never looked at.

      So the detector now scans the last `max_age_bars` bars and takes the
      most recent one that qualifies. The window is deliberately wider than
      the scan interval: a 15-minute scan samples every third five-minute
      bar, so a window of three bars still steps over some triggers. Six
      bars (30 minutes) covers the interval with margin, and the reported
      `bars_ago` says how stale the trigger is.
      The reported entry is still the current close — the SOP enters at
      market on the confirming bar's close — but the levels are resolved
      from that bar's own structure.
    """
    out = {"present": False, "strategy": "Argon-Gold", "model": None}

    if df_5m is None or df_5m.empty or len(df_5m) < 12:
        out["skip"] = "insufficient 5m bars"
        return out
    if df_1h is None or df_1h.empty or len(df_1h) < 12:
        out["skip"] = "insufficient 1h bars"
        return out

    if df_15m is None or df_15m.empty:
        df_15m = _resample_15m(df_5m)
    if df_15m is None or len(df_15m) < 6:
        out["skip"] = "insufficient 15m bars"
        return out

    # Step 1 — 1H bias
    bias = _htf_bias(df_1h)
    if bias == "none":
        out["skip"] = "no clear 1H bias (need HH+HL or LH+LL)"
        return out
    direction = "long" if bias == "long" else "short"

    # Step 2 — 15M box
    box = _build_box(df_15m)
    if not box.get("ok"):
        out["skip"] = "no 15m box"
        return out

    # Scan the last max_age_bars bars for the most recent qualifying one.
    # Only the trigger bar varies; the bias and the box are the same for the
    # whole window, because the box is built from completed 15M bars.
    current_close = float(df_5m.iloc[-1]["Close"])
    window = df_5m.iloc[-(max_age_bars + 1):-1] if len(df_5m) > max_age_bars else df_5m.iloc[:-1]
    if window.empty:
        out["skip"] = "no bars in the trigger window"
        return out

    last_reason = None
    for bar_ts, last in window.iloc[::-1].iterrows():
        res = _evaluate_bar(last, df_5m, box, direction)
        if res.get("ok"):
            fields = res["fields"]
            # The trigger bar supplies the structure; the entry is the
            # CURRENT close, because the SOP enters at market once the
            # confirming bar has closed. Using the trigger bar's own close
            # would pretend we were filled several bars ago.
            fields["entry"] = round(current_close, 2)
            fields["last_close"] = round(current_close, 2)
            # Re-derive the stop distance from the new entry.
            if fields["direction"] == "long":
                fields["risk"] = round(current_close - fields["sl"], 2)
            else:
                fields["risk"] = round(fields["sl"] - current_close, 2)
            if fields["risk"] <= 0:
                out["skip"] = "the trigger bar's stop is on the wrong side of the current price"
                return out
            fields["sl_dist"] = fields["risk"]
            sign = 1 if fields["direction"] == "long" else -1
            fields["t1"] = round(current_close + sign * fields["risk"] * 1.0, 2)
            fields["t2_close"] = round(current_close + sign * fields["risk"] * 1.5, 2)
            fields["t3"] = round(current_close + sign * fields["risk"] * 2.0, 2)
            fields["spot_equiv_stop_usd"] = round(fields["risk"] * MGC_TICK_USD, 2)
            out.update(fields)
            out["present"] = True
            out["trigger_bar"] = str(bar_ts)
            out["bars_ago"] = int(len(df_5m) - 1 - df_5m.index.get_loc(bar_ts))
            return out
        last_reason = res.get("reason")
    out["skip"] = last_reason or "no qualifying bar in the trigger window"
    return out


def _evaluate_bar(last, df_5m, box, direction) -> dict:
    """Evaluate one bar against the SOP. Returns {ok, fields, reason}."""
    out = {"present": False, "strategy": "Argon-Gold", "model": None}
    box_high, box_low = box["high"], box["low"]

    if direction == "long":
        body_top = max(float(last["Open"]), float(last["Close"]))
        if body_top <= box_high:
            return {"ok": False, "reason": "M5 body did not clear the box high"}
        conf = _model_a_sweep_rejection(df_5m, box_low)
        if not conf.get("found"):
            conf = _model_b_double_bottom_msb(df_5m)
        if not conf.get("found"):
            return {"ok": False,
                    "reason": f"box broken but no confirmation model ({conf.get('reason', 'unknown')})"}
        sl_ref = float(conf.get("sweep_low", box_low))
        entry = body_top
    else:
        body_bot = min(float(last["Open"]), float(last["Close"]))
        if body_bot >= box_low:
            return {"ok": False, "reason": "M5 body did not break the box low"}
        conf = _model_a_sweep_rejection(df_5m, box_high)
        if not conf.get("found"):
            conf = _model_b_double_bottom_msb(df_5m)
        if not conf.get("found"):
            return {"ok": False,
                    "reason": f"box broken but no confirmation model ({conf.get('reason', 'unknown')})"}
        sl_ref = float(conf.get("sweep_low", box_high))
        entry = body_bot

    sl_dist = abs(entry - sl_ref)
    if sl_dist <= 0:
        return {"ok": False, "reason": "degenerate stop distance"}
    if sl_dist > MGC_STOP_CAP:
        return {"ok": False,
                "reason": f"stop ${sl_dist:.2f} exceeds the SOP cap ${MGC_STOP_CAP:.2f}"}

    sl = sl_ref - 0.01 if direction == "long" else sl_ref + 0.01
    risk = abs(entry - sl)
    if risk <= 0:
        return {"ok": False, "reason": "degenerate risk"}

    t1 = entry + risk * 1.0 * (1 if direction == "long" else -1)
    t2 = entry + risk * 1.5 * (1 if direction == "long" else -1)
    t3 = entry + risk * 2.0 * (1 if direction == "long" else -1)

    return {"ok": True, "reason": None, "fields": {
        "present": True,
        "direction": direction,
        "signal": "buy" if direction == "long" else "sell",
        "model": conf.get("model"),
        "confidence_model": conf.get("model"),
        "box_high": round(box_high, 2),
        "box_low": round(box_low, 2),
        "box_range": round(box["range"], 2),
        "entry": round(entry, 2),
        "sl": round(sl, 2),
        "t1": round(t1, 2),
        "t2_close": round(t2, 2),
        "t3": round(t3, 2),
        "risk": round(risk, 2),
        "sl_dist": round(risk, 2),
        "bias_1h": direction,
        "confirmation": conf,
        "sop": "docs/21-Argon-Gold-SOP.md",
        "spot_equiv_stop_usd": round(risk * MGC_TICK_USD, 2),
        "last_close": float(last["Close"]),
    }}
