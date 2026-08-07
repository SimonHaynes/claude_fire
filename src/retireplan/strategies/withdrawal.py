"""Withdrawal strategies: how much to actually spend each year.

Essential spending, debt payments and one-off commitments are never touched —
a strategy only ever flexes the discretionary part, which is what makes these
rules something a household could plausibly agree to live by.

## How each rule decides

There are two families here, and they answer different questions.

**Needs-based** rules start from the spending plan — what the household said
it wants to live on — and cut only when the money will not stretch:

    SpendNominal          spend the plan, and let a shortfall be a shortfall.
    PostAccessStepUp      spend the plan, then permanently raise it once a
                          pension unlocks and the portfolio is clearly surplus.

A third, `FixedFloorGuardrail`, was removed rather than kept as an option. It
cut discretionary spending only once the accessible pots could no longer fund
the year -- the point of collapse -- so it acted far too late to protect
anything, and its recovery branch had nothing to recover from. Measured over
2,000 trials on a real household it cut 74 times and recovered zero times,
against 638 cuts and 561 recoveries for `GuytonKlinger`. Keeping a rule whose
name promised a safeguard it did not provide was worse than not offering it:
it was chosen for reports precisely because it sounded prudent.

`GuytonKlinger` is the needs-based rule that actually adjusts. If the goal is
flat, predictable spending with the shortfall risk stated openly, that is
`SpendNominal`.

**Portfolio-based** rules ignore the plan and derive spending from what the
portfolio is worth, so income falls automatically after a crash and rises
after a boom:

    PercentOfPortfolio    spend `rate` of the current portfolio (the "4% rule"
                          in its honest, endowment form: 4% of what you have
                          *now*, not 4% of what you had at retirement uprated
                          for inflation).
    VariablePercentage    spend a rate that rises with age, on the reasoning
                          that a 90-year-old can safely spend a far higher
                          fraction than a 60-year-old.

The trade is the same in both cases and there is no free option: needs-based
rules give a predictable income and put all the uncertainty into whether the
plan survives; portfolio-based rules almost never run out of money — they
cannot, since they spend a fraction of whatever remains — and put all the
uncertainty into how much you get to spend. A portfolio rule that never fails
can still deliver a 40% pay cut in a bad decade, which is why success
probability alone is a poor way to compare the two families. Read the spend
percentiles alongside it.

Guyton-Klinger sits between them: a needs-based plan with portfolio-based
guardrails that ratchet it up or down.

## The dry-run mechanism

Every strategy is handed `shortfall_for(amount)`, which reports what would be
left uncovered if it spent that much this year. That keeps the rules generic:
a strategy never needs to know the drawdown order, the tax rules, or which
pots are accessible, and it automatically respects whichever drawdown strategy
the scenario happens to be using.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class WithdrawalContext:
    year_index: int
    is_retired: bool
    dc_accessible: bool
    nominal_discretionary: float
    fixed_spend: float
    net_income: float
    portfolio_value: float
    growth_return: float
    oldest_age: int
    shortfall_for: Callable[[float], float]


class WithdrawalStrategy(ABC):
    def reset(self) -> None:
        """Clear per-run state. Called once at the start of every trial."""

    @abstractmethod
    def decide(self, ctx: WithdrawalContext) -> float:
        """Discretionary spending to actually make this year."""


def _largest_affordable(
    ctx: WithdrawalContext, floor: float, ceiling: float, iterations: int = 10
) -> float:
    """Largest multiple of nominal discretionary in [floor, ceiling] with no shortfall.

    Bisection rather than algebra because affordability depends on the
    drawdown strategy and the tax gross-up, which are pluggable. `floor` is
    assumed already checked as affordable, so the returned `lo` is always a
    verified-feasible point.
    """
    lo, hi = floor, ceiling
    for _ in range(iterations):
        mid = (lo + hi) / 2
        if ctx.shortfall_for(ctx.nominal_discretionary * mid) > 0:
            hi = mid
        else:
            lo = mid
    return ctx.nominal_discretionary * lo


@dataclass
class SpendNominal(WithdrawalStrategy):
    """Spend the plan regardless, and let a shortfall be a shortfall.

    The honest baseline: it measures whether the plan works, rather than
    whether the plan plus an assumed willingness to cut spending works.
    """

    def decide(self, ctx: WithdrawalContext) -> float:
        return ctx.nominal_discretionary


@dataclass
class GuytonKlinger(WithdrawalStrategy):
    """Guyton-Klinger dynamic withdrawal guardrails, adapted for pension income.

    Canonical Guyton-Klinger assumes the portfolio funds all of retirement.
    Here the household also has DB and State Pension income, so the
    "withdrawal rate" is redefined as the fraction of the *investable
    portfolio* drawn this year — `(spending - net income) / portfolio` — which
    is the quantity the rules exist to protect.

    Implemented:
      * Capital preservation — if the rate rises more than `guardrail` above
        the rate set in the first year of retirement, cut spending by
        `adjustment`.
      * Prosperity — if it falls more than `guardrail` below, raise spending
        by `adjustment`, but never immediately after a down year (a
        simplification of the original's inflation/freeze rule).

    Adjustments are cumulative and persist.
    Not implemented: the portfolio management rule (which pot to sell) — that
    is `DrawdownStrategy`'s job here, kept separate so the two can be varied
    independently.
    """

    guardrail: float = 0.20
    adjustment: float = 0.10
    floor: float = 0.5
    ceiling: float = 1.5

    initial_rate: float | None = field(default=None, init=False, repr=False)
    multiplier: float = field(default=1.0, init=False, repr=False)

    def reset(self) -> None:
        self.initial_rate = None
        self.multiplier = 1.0

    def decide(self, ctx: WithdrawalContext) -> float:
        if not ctx.is_retired:
            return ctx.nominal_discretionary

        candidate = ctx.nominal_discretionary * self.multiplier
        drawn = ctx.fixed_spend + candidate - ctx.net_income
        rate = drawn / ctx.portfolio_value if ctx.portfolio_value > 0 else float("inf")

        if self.initial_rate is None:
            # A zero baseline would make every later year look infinitely worse.
            self.initial_rate = max(rate, 1e-6)
        elif rate > self.initial_rate * (1 + self.guardrail):
            self.multiplier = max(self.floor, self.multiplier * (1 - self.adjustment))
        elif rate < self.initial_rate * (1 - self.guardrail) and ctx.growth_return >= 0:
            self.multiplier = min(self.ceiling, self.multiplier * (1 + self.adjustment))

        target = ctx.nominal_discretionary * self.multiplier
        if ctx.shortfall_for(target) <= 0:
            return target

        # The guardrail bounds are a heuristic, not a solvency guarantee. Fall
        # back to searching for what is genuinely affordable rather than
        # reporting a shortfall the strategy exists to prevent.
        floor_amount = ctx.nominal_discretionary * self.floor
        if ctx.shortfall_for(floor_amount) > 0:
            return floor_amount
        return _largest_affordable(ctx, self.floor, self.multiplier)


@dataclass
class PercentOfPortfolio(WithdrawalStrategy):
    """Spend a fixed percentage of the *current* portfolio each year.

    The endowment rule, and the honest version of "the 4% rule": 4% of what
    the portfolio is worth today, not 4% of its value at retirement uprated
    for inflation ever since. Because the draw is always a fraction of what
    remains, the money cannot run out — but income tracks the market, so a
    50% crash means a 50% pay cut in the same year.

    Since income and pensions already cover part of the spending, the rate is
    applied to the portfolio and the result used as the *total* spending
    target, with the discretionary part being whatever is left after fixed
    commitments. `floor`/`ceiling` bound it against the plan so the answer
    stays recognisable as a lifestyle rather than an arithmetic output.
    """

    rate: float = 0.04
    floor: float = 0.5
    ceiling: float = 1.5

    def decide(self, ctx: WithdrawalContext) -> float:
        if not ctx.is_retired or ctx.nominal_discretionary <= 0:
            return ctx.nominal_discretionary

        budget = ctx.portfolio_value * self.rate + ctx.net_income
        target = budget - ctx.fixed_spend
        target = max(ctx.nominal_discretionary * self.floor,
                     min(target, ctx.nominal_discretionary * self.ceiling))

        if ctx.shortfall_for(target) <= 0:
            return target
        floor_amount = ctx.nominal_discretionary * self.floor
        if ctx.shortfall_for(floor_amount) > 0:
            return floor_amount
        return _largest_affordable(ctx, self.floor, target / ctx.nominal_discretionary)


@dataclass
class VariablePercentage(WithdrawalStrategy):
    """A withdrawal rate that rises with age.

    Spending 4% at 60 and 4% at 90 makes little sense: the second has a far
    shorter horizon to fund. This raises the rate linearly from `start_rate`
    at `start_age` to `end_rate` at `end_age`, which spends the portfolio
    down deliberately rather than leaving an accidental estate — useful for a
    household that would rather enjoy the money than bequeath it, and a
    reasonable counterweight to rules that hoard by construction.

    Ages are taken from the oldest person in the household.
    """

    start_age: int = 60
    end_age: int = 95
    start_rate: float = 0.035
    end_rate: float = 0.10
    floor: float = 0.5
    ceiling: float = 2.0

    def rate_at(self, age: int) -> float:
        if age <= self.start_age:
            return self.start_rate
        if age >= self.end_age:
            return self.end_rate
        span = self.end_age - self.start_age
        t = (age - self.start_age) / span
        return self.start_rate + (self.end_rate - self.start_rate) * t

    def decide(self, ctx: WithdrawalContext) -> float:
        if not ctx.is_retired or ctx.nominal_discretionary <= 0:
            return ctx.nominal_discretionary

        budget = ctx.portfolio_value * self.rate_at(ctx.oldest_age) + ctx.net_income
        target = budget - ctx.fixed_spend
        target = max(ctx.nominal_discretionary * self.floor,
                     min(target, ctx.nominal_discretionary * self.ceiling))

        if ctx.shortfall_for(target) <= 0:
            return target
        floor_amount = ctx.nominal_discretionary * self.floor
        if ctx.shortfall_for(floor_amount) > 0:
            return floor_amount
        return _largest_affordable(ctx, self.floor, target / ctx.nominal_discretionary)


@dataclass
class PostAccessStepUp(WithdrawalStrategy):
    """Spend more, permanently, once the money is unlocked and clearly surplus.

    Triggers when a DC pension is accessible *and* the portfolio covers at
    least `surplus_years` of total spending — a legible proxy for "this is
    more than we need", not a formal sustainability test.

    Once triggered it never steps back down, which is the point and also the
    risk: households do not casually reverse a lifestyle, so a permanent rise
    cannot be offset by an earlier good decade the way a one-off cost can.
    The floor search still applies underneath, so a bad enough sequence can
    still force a cut — this is a target, not a promise.
    """

    step_up: float = 1.25
    surplus_years: float = 25.0
    floor: float = 0.6
    stepped_up: bool = field(default=False, init=False, repr=False)

    def reset(self) -> None:
        self.stepped_up = False

    def decide(self, ctx: WithdrawalContext) -> float:
        if not ctx.is_retired or ctx.nominal_discretionary <= 0:
            return ctx.nominal_discretionary

        if not self.stepped_up and ctx.dc_accessible:
            annual_need = ctx.fixed_spend + ctx.nominal_discretionary
            if annual_need > 0 and ctx.portfolio_value / annual_need >= self.surplus_years:
                self.stepped_up = True

        multiplier = self.step_up if self.stepped_up else 1.0
        target = ctx.nominal_discretionary * multiplier
        if ctx.shortfall_for(target) <= 0:
            return target

        floor_amount = ctx.nominal_discretionary * self.floor
        if ctx.shortfall_for(floor_amount) > 0:
            return floor_amount
        return _largest_affordable(ctx, self.floor, multiplier)
