"""Contract specifications and position sizing.

Every CME micro future quotes a different number of dollars per point of
price movement: $2 on MNQ, $5 on MES and M2K, $10 on MGC, $100 on GC,
$12,500 on M6E. The live tracker recorded pnl_usd as the raw price
difference, which treats every one of them as $1 per point.

That was not a rounding error. It meant:

  - a 30-point MNQ stop was booked as $30 when it cost $61.50
  - a 6.7-point MGC stop was booked as $6.70 when it cost $67
  - a 5.8-point GC stop was booked as $5.85 when it cost $585

and, because there was no position sizing at all, the book risked
$154 on an average BTC trade against a $100 daily loss envelope, and
$581 on an average GC trade. 941 of 1,258 BTC trades and 6 of 6 GC
trades carried more risk than the entire daily kill.

The specifications live in automation/config/contract_specs.json so they
can be corrected without touching code.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPECS_FILE = REPO / "automation" / "config" / "contract_specs.json"

# Fallback multipliers, used only if the config file is missing. BTC is
# $1 per dollar of price, which is the one instrument where treating a
# point as a dollar happens to be right.
FALLBACK = {
    "MES=F": 5.0, "MNQ=F": 2.0, "M2K=F": 5.0, "MYM=F": 0.5,
    "MGC=F": 10.0, "MCL=F": 100.0, "M6E=F": 12500.0, "GC=F": 100.0,
    "BTC-USD": 1.0,
}

_cache: dict | None = None


def load_specs() -> dict:
    global _cache
    if _cache is None:
        try:
            d = json.loads(SPECS_FILE.read_text())
            _cache = d
        except Exception:
            _cache = {"specs": {}, "_risk_budget_usd": 100.0}
    return _cache


def usd_per_point(ticker: str) -> float:
    """Dollars per one point of price movement on this contract."""
    specs = load_specs().get("specs", {})
    v = specs.get(ticker)
    if v:
        return float(v.get("usd_per_point", 1.0))
    return FALLBACK.get(ticker, 1.0)


def risk_budget_usd() -> float:
    """The most that one trade may put at risk."""
    return float(load_specs().get("_risk_budget_usd", 100.0))


def max_stop_points(ticker: str) -> float:
    """The widest stop one contract can carry inside the risk budget."""
    m = usd_per_point(ticker)
    return (risk_budget_usd() / m) if m else 0.0


def size_position(ticker: str, stop_distance: float,
                  budget_usd: float | None = None):
    """Size a position so the trade risks the budget, not the stop distance.

    Returns (units, risk_usd, reason). `units` is None when the trade
    cannot be taken at all, which happens when a single contract's stop
    already exceeds the budget — M6E at $12,500 a point can never carry
    a stop that is wide enough to be meaningful.

    A fraction of a contract is allowed, because the alternative is
    either a risk that blows the budget or a strategy that cannot trade
    the instrument at all. The TTrades family already sizes this way.
    """
    budget = risk_budget_usd() if budget_usd is None else float(budget_usd)
    mult = usd_per_point(ticker)
    d = abs(float(stop_distance))
    if d <= 0 or mult <= 0:
        return None, 0.0, "no stop distance"
    risk_per_contract = d * mult
    units = budget / risk_per_contract
    return units, budget, f"{units:.4f} contract(s) at {mult:g}$/point"


def true_pnl(ticker: str, price_move: float, units: float = 1.0) -> float:
    """The dollar result of a price move on a sized position."""
    return float(price_move) * usd_per_point(ticker) * float(units)


def trade_pnl_usd(trade: dict) -> float:
    """The dollar result of a closed trade.

    Derived from the R-multiple and the dollar risk the position carried:
    pnl_usd = R x (stop distance x contract multiplier x units).

    Going through the R-multiple rather than through the price move
    matters. A trade opened with an unusable direction — which is what
    every B1-3in1 position used to get — has no price-move sign that
    means anything, while its R-multiple always does. Reading the price
    move directly turned those trades' losses into gains.

    The stored pnl_usd is a cache and is not comparable across the
    changeover: trades closed before the sizing fix recorded the bare
    price difference, which was dollars only on BTC-USD. Recomputing makes
    every trade comparable, before and after the fix.
    """
    r = trade.get("R_multiple")
    sl_dist = trade.get("sl_dist")
    if r is not None and sl_dist:
        mult = float(trade.get("usd_per_point") or usd_per_point(trade.get("ticker", "")))
        units = float(trade.get("units") or 1.0)
        return float(r) * float(sl_dist) * mult * units
    entry = trade.get("entry")
    exit_price = trade.get("exit_price")
    if entry is None or exit_price is None:
        try:
            return float(trade.get("pnl_usd", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0
    d = str(trade.get("direction", "")).strip().lower()
    sign = 1 if d in ("long", "buy", "up", "bullish", "l") else -1
    mult = float(trade.get("usd_per_point") or usd_per_point(trade.get("ticker", "")))
    units = float(trade.get("units") or 1.0)
    return sign * (float(exit_price) - float(entry)) * mult * units
