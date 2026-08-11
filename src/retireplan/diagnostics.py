"""What a compiled plan says about itself before any market is simulated.

Choosing which withdrawal rules to test is otherwise a judgement call made
from a nine-row results table, and the numbers that decide it are all fixed
at compile time: how long the pension is locked, how much money can be
reached while it is, and how hard the plan draws. Computing them costs one
pass over the schedule, against six Monte Carlo runs to discover the same
thing.

Everything here is deliberately **zero-return**: no growth is assumed on the
money that has to survive the bridge. That is the pessimistic reading, which
is the right bias for a screen whose job is to decide whether to worry — a
60/40 mix over seven years would multiply the coverage ratios by roughly 1.3,
so a plan at 0.8 coverage is genuinely marginal rather than doomed.

The bands these numbers are read against are measured, not asserted, and live
where the measurement does: REVIEW.md 1.18/1.19 and the selection table in the
`define-scenarios` skill. This module reports; it does not advise.
"""
from __future__ import annotations

from dataclasses import dataclass

from .plan import Plan, PlanYear

INFINITE_COVER = float("inf")
"""Returned when there is nothing to cover — no bridge, or a bridge whose
spending is already met by income. Distinguishable from a very large ratio,
and it means "this constraint does not apply" rather than "this is fine"."""


@dataclass(frozen=True)
class PlanDiagnostics:
    """Screening numbers for one compiled plan. All real GBP, zero-return."""

    bridge_years: int
    """Years of retirement before any DC pension unlocks. Zero means every
    bridge-specific strategy is inert by construction, so testing one costs a
    simulation and learns nothing.

    For a couple this is the *first* unlock, not the last: one accessible
    pension can fund the household, so the bridge ends there. The younger
    partner's own lock is then a tax question, not a liquidity one."""

    accessible_at_retirement: float
    """Investable assets outside a DC pension when retirement starts —
    opening balances plus scheduled contributions to those pots, no growth."""

    portfolio_at_retirement: float
    """All investable assets at retirement, pension included, no growth."""

    bridge_coverage: float
    """`accessible_at_retirement` ÷ everything the plan needs to draw before
    access. 1.0 means the accessible money covers the bridge exactly, with no
    help from growth; below 1.0 the bridge depends on returns."""

    essential_bridge_coverage: float
    """The same ratio against essential spending alone — the floor a
    withdrawal rule cannot cut through. Below 1.0, no spending rule can make
    the bridge reach, and the levers are the retirement date, deferred
    spending, or moving money into a reachable wrapper."""

    initial_draw_rate: float
    """First retired year's draw ÷ `portfolio_at_retirement`. The quantity
    every published safe-withdrawal-rate study is about."""


def _accessible_slots(plan: Plan) -> tuple[int, ...]:
    dc = {s for slots in plan.dc_slots_by_person.values() for s in slots}
    return tuple(s for s in plan.investable_slots if s not in dc)


def _draw_needed(year: PlanYear, *, essential_only: bool) -> float:
    """What this year's plan must take from the portfolio, at zero return."""
    spend = year.fixed_spend if essential_only else year.fixed_spend + year.nominal_discretionary
    return max(0.0, spend - year.net_income)


def _balance_at(plan: Plan, slots: tuple[int, ...], up_to: int) -> float:
    wanted = set(slots)
    opening = sum(plan.opening_balances[s] for s in wanted)
    paid_in = sum(
        amount
        for year in plan.years[:up_to]
        for slot, amount in year.contributions
        if slot in wanted
    )
    return opening + paid_in


def diagnose(plan: Plan) -> PlanDiagnostics | None:
    """Screening numbers for `plan`, or `None` if it contains no retirement.

    Reads the compiled schedule only — no returns, no strategies, no
    simulation — so it is safe to call on every scenario before deciding
    which are worth running.
    """
    retirement = next((y.index for y in plan.years if y.is_retired), None)
    if retirement is None:
        return None

    access = next(
        (y.index for y in plan.years if y.index >= retirement and y.dc_accessible),
        len(plan.years),
    )
    bridge_years = access - retirement
    bridge = plan.years[retirement:access]

    accessible = _balance_at(plan, _accessible_slots(plan), retirement)
    portfolio = _balance_at(plan, plan.investable_slots, retirement)

    def coverage(*, essential_only: bool) -> float:
        needed = sum(_draw_needed(y, essential_only=essential_only) for y in bridge)
        return accessible / needed if needed > 0 else INFINITE_COVER

    first_draw = _draw_needed(plan.years[retirement], essential_only=False)
    return PlanDiagnostics(
        bridge_years=bridge_years,
        accessible_at_retirement=accessible,
        portfolio_at_retirement=portfolio,
        bridge_coverage=coverage(essential_only=False),
        essential_bridge_coverage=coverage(essential_only=True),
        initial_draw_rate=first_draw / portfolio if portfolio > 0 else INFINITE_COVER,
    )
