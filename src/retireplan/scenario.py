"""A scenario: one set of what-if choices to run against a household.

A scenario holds everything that is a *decision* — when to stop working, how
much to spend, what to buy, and which strategies to live by — while the
household holds everything that is a *fact*. Keeping the two apart is what
makes it possible to run a dozen futures against one set of accounts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Mapping

from .care import CarePlan

from .strategies import (
    AllocationStrategy,
    DrawdownStrategy,
    StandardOrder,
    WithdrawalStrategy,
)


@dataclass(frozen=True)
class OneOffSpend:
    """A dated lump sum: a holiday home, a house deposit for a child, a new roof.

    Dated rather than year-numbered, because *when* in a plan a large cost
    lands matters as much as its size — the same purchase can be comfortable
    after a pension unlocks and close to fatal during a bridge.
    """

    on: date
    amount: float
    description: str = ""


@dataclass(frozen=True)
class Gift:
    """Money given away during life.

    Distinct from a one-off spend because it does two things a purchase does
    not: it still counts as reaching the family, and it leaves the estate for
    IHT once the donor survives seven years. For an estate far above the
    nil-rate bands, gifting early is usually the single largest lever
    available — larger than any drawdown tuning.
    """

    on: date
    amount: float
    description: str = ""


@dataclass
class Scenario:
    name: str
    description: str = ""
    retirement_dates: dict[str, date] = field(default_factory=dict)
    spending_multiplier: float = 1.0
    one_off_spends: tuple[OneOffSpend, ...] = ()
    gifts: tuple[Gift, ...] = ()

    withdrawal: WithdrawalStrategy | None = None
    """None spends the plan as written and lets shortfalls fall where they may
    — see `strategies.SpendNominal` for the same behaviour stated explicitly."""

    drawdown: DrawdownStrategy = field(default_factory=StandardOrder)
    allocation: AllocationStrategy | None = None

    take_pcls: bool = False
    """Take the tax-free lump sum when each pension first becomes accessible.

    25% of the pot, capped by the Lump Sum Allowance (£268,275) — a cap that
    binds for any pot above about £1.07m, so the familiar "25% tax-free" is
    not the whole 25% for exactly the people who assume it is.

    The proceeds land in the cash reserve, which is spent before anything
    else. That is deliberately conservative: it neither assumes ISA
    subscription room that may not exist, nor credits the lump sum with
    tax-free growth it would only earn once actually reinvested.
    """

    market_stress: tuple[Mapping[str, float], ...] = ()
    """Force the first N years' returns instead of sampling them.

    For deliberate sequence-of-returns tests: `({"global_equity": -0.35},
    {"global_equity": -0.10})` opens every trial with a crash, so the question
    becomes "does the plan survive a bad start" rather than "how often is the
    start bad". Keys left unspecified still come from the sampled year."""

    care: CarePlan | None = None
    """Late-life residential care, off by default and analysed separately.

    Whether care is needed is sampled per person per trial, means-tested per
    person, and backed by the state once capital hits the limit -- see
    `care.py`. Off by default because it answers a different question from the
    rest of the plan: not "when can we stop working" but "what happens to the
    estate if one of us needs a care home". Mixing the two produces a headline
    number that is neither."""

    death_ages: Mapping[str, int] | None = None
    """Force when each person dies, instead of everyone reaching life expectancy.

    For deliberate first-death tests: `{"Pat": 80}` leaves Robin alone for
    fifteen years on one State Pension and half a DB pension, while spending
    barely falls. That gap is the single largest downside this engine used to
    miss, and it is a question a plan should be able to answer directly rather
    than only in aggregate.

    Anyone unlisted dies at `Assumptions.life_expectancy_age`, so the default
    (`None`) reproduces the old behaviour exactly."""

    def series_keys(self) -> frozenset[str]:
        keys = self.allocation.series_keys() if self.allocation else frozenset()
        return keys.union(*(frozenset(m) for m in self.market_stress)) if self.market_stress else keys

    def reset_strategies(self) -> None:
        """Clear strategy state so one scenario object is safe across trials."""
        if self.withdrawal is not None:
            self.withdrawal.reset()
        self.drawdown.reset()
        if self.allocation is not None:
            self.allocation.reset()
