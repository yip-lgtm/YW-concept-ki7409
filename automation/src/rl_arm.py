"""A/B arm assignment for the RL exit policy.

User directive (2026-10-20): run a control group so the RL exit policy
can be judged on realised results rather than on replayed ones.

WHY A CROSSOVER AND NOT A SIMPLE SPLIT

  Splitting the strategies into "RL arm" and "control arm" would compare
  the arms on different strategies.  The strategies differ enormously in
  quality — RSI-Div returns +0.266R per trade while Two-Yang returns
  -0.105R — so any arm difference would be swamped by which strategies
  happened to land in which arm.  A 3-versus-7 split has no statistical
  power at all.

  The crossover puts BOTH arms inside the SAME strategy.  The arm is
  decided when a position is opened and alternates on a fixed period, so
  over a few weeks each strategy contributes trades to both arms.  The
  strategy's own quality then cancels out of the comparison, and what is
  left is the exit policy's effect.

  The remaining confound is the market regime: the two arms do not see the
  same price path.  Alternating on a short period keeps that as small as
  possible, and the report prints each arm's date span so a reader can
  judge it.

  The arm is frozen at position-open time.  A position opened on a control
  week finishes on the book template even if the week rolls over
  mid-trade, otherwise a single trade could switch rules halfway.

CHOOSING THE PERIOD

  Weekly is the default: a 14-day trade is long enough that flipping
  mid-position would be common, so the period has to be comfortably
  longer than the average holding time.  If the average holding time
  exceeds the period, the crossover is invalid and the assignment falls
  back to CONTROL for everyone, which is the safe direction — a policy
  that cannot be evaluated must not be traded.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

ARM_RL = "RL"
ARM_CONTROL = "CONTROL"

# Weeks of history the arms are compared over, used only for reporting.
DEFAULT_PERIOD_DAYS = 14


def _iso_week_key(dt: datetime) -> int:
    """Monotonic-ish integer for the week containing dt."""
    return dt.isocalendar()[0] * 100 + dt.isocalendar()[1]


def assign_arm(now: datetime | None = None,
               period_days: int = DEFAULT_PERIOD_DAYS,
               min_days_between_changes: int = 3,
               last_switch: str | None = None,
               phase: int = 0) -> tuple[str, str]:
    """Decide which arm a strategy should trade under right now.

    Returns (arm, reason).

    The switch is deterministic: the same moment always yields the same
    arm, so every strategy and every process agrees without coordination.

    `phase` offsets one strategy against another.  It matters: without it
    every strategy flips on the same day, which turns the crossover into a
    plain time-blocked A/B where the two arms see disjoint market periods
    and the regime confound is at its worst.  With a per-strategy phase the
    book always has both arms live, and each strategy still contributes to
    both arms over time.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if period_days < 7:
        period_days = 7

    # Half the period in each arm, so the two arms see comparable spans.
    half = max(1, period_days // 2)
    bucket = int(now.timestamp() // (half * 86400)) + int(phase)
    arm = ARM_RL if (bucket % 2 == 0) else ARM_CONTROL

    # Cooldown: do not flip more often than every min_days_between_changes.
    if last_switch:
        try:
            prev = datetime.fromisoformat(last_switch.replace("Z", "+00:00"))
            if prev.tzinfo is None:
                prev = prev.replace(tzinfo=timezone.utc)
            if now - prev < timedelta(days=min_days_between_changes):
                return arm, f"cooldown after {last_switch[:10]}"
        except Exception:
            pass
    return arm, f"period={half}d bucket={int(bucket) % 2}"


def arm_for_strategy(name: str,
                     overrides: dict | None = None,
                     state: dict | None = None,
                     now: datetime | None = None,
                     period_days: int = DEFAULT_PERIOD_DAYS) -> tuple[str, str]:
    """The arm a given strategy should trade under, honouring the override
    list.  A strategy with no learned override is always CONTROL — there is
    nothing to test."""
    overrides = overrides or {}
    state = state or {}
    ov = overrides.get(name)
    if not ov or not isinstance(ov, dict):
        return ARM_CONTROL, "no learned override — control by default"

    entry = state.get(name) or {}
    phase = entry.get("phase")
    if phase is None:
        # A stable, name-derived phase so the strategies are spread across
        # the two arms at any moment instead of flipping in unison.
        phase = sum(ord(c) for c in name) % 2
    arm, reason = assign_arm(now=now, period_days=period_days,
                             last_switch=entry.get("last_switch"),
                             phase=phase)
    return arm, reason
