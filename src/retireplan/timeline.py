"""Date arithmetic for plan years.

A "plan year" is a rolling 12-month window anchored on the as-of date, not a
calendar year. That keeps every comparison the engine cares about — retirement
dates, pension access birthdays, debt payoff, bond maturities — exact, without
needing to pro-rate anything onto a January-to-December grid afterwards.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date


def add_years(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # 29 February in a non-leap target year
        return d.replace(year=d.year + n, day=28)


def add_months(d: date, n: int) -> date:
    """`d` plus `n` calendar months, clamped to the target month's last day.

    For bounds that are naturally stated in months rather than years — a
    notice period, a bond maturing "in 6 months" — so a caller never has to
    reach for a dependency (`dateutil.relativedelta`) the engine deliberately
    does not carry just to add months to a date."""
    month_index = d.month - 1 + n
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def months_remaining(as_of: date, last_payment: date) -> int:
    """Monthly payments still due, if the final one lands on `last_payment`
    and today is `as_of`. The inverse of `add_months` for the common case of
    a debt (or a notice period) quoted as an end date rather than a
    countdown, so the count is recomputed fresh from `as_of` every time
    rather than drifting the moment time actually passes.

    Whole calendar months between the two, plus one more if `last_payment`'s
    day-of-month is on or after `as_of`'s — i.e. that final month's payment
    has not yet happened as of `as_of`. Never negative: a `last_payment`
    already in the past reads as zero, not a negative countdown."""
    months = (last_payment.year - as_of.year) * 12 + (last_payment.month - as_of.month)
    if last_payment.day >= as_of.day:
        months += 1
    return max(0, months)


def age_on(date_of_birth: date, on: date) -> int:
    return on.year - date_of_birth.year - ((on.month, on.day) < (date_of_birth.month, date_of_birth.day))


def earliest(*dates: date | None) -> date | None:
    """The earliest of several bounds, treating None as 'no bound'."""
    present = [d for d in dates if d is not None]
    return min(present) if present else None


def overlap_fraction(
    window_start: date,
    window_end: date,
    active_from: date | None,
    active_until: date | None,
) -> float:
    """Fraction of [window_start, window_end) covered by [active_from, active_until).

    Returning a fraction rather than a yes/no is what lets someone retire on
    1 July and have exactly half a year of salary, half a year of pension
    contributions, and the right amount of tax — instead of the whole year
    landing on one side of the line.
    """
    lo = max(window_start, active_from) if active_from else window_start
    hi = min(window_end, active_until) if active_until else window_end
    if hi <= lo:
        return 0.0
    return (hi - lo).days / (window_end - window_start).days


def debt_payment_schedule(monthly_payment: float, remaining_months: int) -> list[float]:
    """Total paid in each plan year until a debt clears."""
    out: list[float] = []
    months_left = remaining_months
    while months_left > 0:
        months = min(12, months_left)
        out.append(monthly_payment * months)
        months_left -= months
    return out
