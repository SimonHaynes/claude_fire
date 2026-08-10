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
from .model import PensionAccess

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


@dataclass(frozen=True)
class PensionLumpSum:
    """A one-off, dated withdrawal from one person's DC pension.

    Split 25% tax-free / 75% taxable, exactly like a UFPLS payment — and
    drawing against the same lifetime Lump Sum Allowance counter as PCLS or
    an ongoing `Scenario.pension_access = PensionAccess.UFPLS` — regardless
    of what `pension_access` the rest of the scenario actually uses. For "I
    want £50,000 of cash now" without crystallising the whole pot or
    committing to either ongoing mode: a partial crystallisation, in effect,
    without the engine needing to track crystallised-vs-not as separate
    pots — there is only ever one DC pension balance here, and what changes
    is how much of its *future* tax-free entitlement is still available.

    Proceeds are invested the same way a PCLS is (`_Accounts.invest_for`: ISA,
    then GIA, then cash) — pair with a `Scenario.one_off_spends` entry if
    the point is to actually spend it rather than reinvest it.
    """

    on: date
    person: str
    amount: float
    """Gross amount requested from the pot. Capped by what the pot actually
    holds; the tax-free portion is separately capped by remaining Lump Sum
    Allowance headroom, same as UFPLS."""
    description: str = ""


@dataclass(frozen=True)
class IncomeAnnuity:
    """A lifetime annuity bought from a DC pension at retirement -- the
    "floor" half of Zvi Bodie / Wade Pfau's floor-and-upside (safety-first)
    approach to retirement income: secure essential spending with guaranteed
    income first, then invest whatever remains for upside.

    Distinct from `care.ImmediateNeedsAnnuity`, which is a short, impaired-life
    annuity bought at the point of entering care and paid tax-free direct to
    the care provider. This is an ordinary lifetime annuity bought at a normal
    (unimpaired) life expectancy, and its income is taxed exactly like any
    other pension income, because that is what it is under UK rules.

    Single-life, bought once at first pension access: payments stop outright
    when the annuitant dies, with nothing passed to the estate -- annuitised
    money is gone in exchange for the income stream, which is the actual
    trade-off it protects against (running out of money) as much as it is a
    cost (nothing left to leave). No joint-life or guarantee-period option is
    modelled; a household that specifically wants the lower income a
    joint-life or guaranteed annuity would buy needs a different figure
    supplied by hand.

    Bought from whatever remains of the pot *after* any `PensionAccess.PCLS`
    tax-free cash has already been taken (if the scenario uses PCLS) -- the
    common real-world order of "take the tax-free cash, then annuitise part
    of what's left" -- so `fraction_of_pot` applies to the pot as it stands
    at the point this fires, not to the pot's original, pre-PCLS size.

    Pricing is a planning approximation, same style and same reason as
    `ImmediateNeedsAnnuity`: a real quote is medically underwritten and this
    model has no way to know an individual's health, and it is not discounted
    for the insurer's own investment return on the premium, which is
    conservative for the buyer -- a real insurer prices in that return, so a
    real quote would buy more income than this estimates.
    """

    enabled: bool = False
    fraction_of_pot: float = 0.0
    """Fraction of the DC pot to annuitise at first access. The rest stays
    invested for upside -- annuitise only what is needed to cover the floor,
    not the whole pot, or there is no upside left to invest."""

    life_expectancy_years: float = 25.0
    """Flat planning figure, deliberately independent of the household's own
    mortality model (`FixedAge`/`LifeTable`) so an annuity comparison is not
    silently coupled to whichever assumption the rest of the plan happens to
    use -- state a specific figure on purpose, the same way
    `ImmediateNeedsAnnuity` does."""

    loading: float = 1.15
    """Insurer's margin over a break-even price. Lower than
    `ImmediateNeedsAnnuity`'s default 1.25: that annuity prices a short,
    impaired-life risk with wide uncertainty, where insurers charge more for
    that uncertainty; this one prices a long, unimpaired life, a market
    insurers compete harder on."""

    escalation: float = 0.0
    """Annual real escalation of the income once in payment. Zero buys a
    level (flat real) annuity -- the common choice, since an escalating
    annuity starts markedly lower for the same premium."""

    def annual_benefit(self, premium: float) -> float:
        """Annual income `premium` buys -- the inverse of
        `ImmediateNeedsAnnuity.premium`: given the money, what income does it
        secure, rather than given the income, what money does it cost."""
        years = self.life_expectancy_years
        if years <= 0:
            return 0.0
        if self.escalation:
            factor = sum((1 + self.escalation) ** t for t in range(int(years) + 1))
        else:
            factor = years
        return premium / (factor * self.loading)

    def spec(self) -> dict:
        return {
            "enabled": self.enabled,
            "fraction_of_pot": self.fraction_of_pot,
            "life_expectancy_years": self.life_expectancy_years,
            "loading": self.loading,
            "escalation": self.escalation,
        }


@dataclass
class Scenario:
    name: str
    description: str = ""
    retirement_dates: dict[str, date] = field(default_factory=dict)
    spending_multiplier: float = 1.0
    one_off_spends: tuple[OneOffSpend, ...] = ()
    gifts: tuple[Gift, ...] = ()
    pension_lump_sums: tuple[PensionLumpSum, ...] = ()
    income_annuity: IncomeAnnuity | None = None
    """A floor-and-upside lifetime annuity, bought once from each accessible
    DC pension at first access. Off by default -- see `IncomeAnnuity`."""

    withdrawal: WithdrawalStrategy | None = None
    """None spends the plan as written and lets shortfalls fall where they may
    — see `strategies.SpendNominal` for the same behaviour stated explicitly."""

    drawdown: DrawdownStrategy = field(default_factory=StandardOrder)
    allocation: AllocationStrategy | None = None

    phased_tranche: float | None = None
    """Tax-free cash to release per person per year under
    `PensionAccess.PHASED`. `None` sizes each tranche to that person's
    remaining ISA subscription room, so the cash lands somewhere sheltered
    rather than in a GIA paying dividend tax for a decade. Ignored by every
    other `pension_access` mode."""

    pension_access: PensionAccess = PensionAccess.NONE
    """How each pension's tax-free entitlement is realised, once accessible.

    25% of the pot is tax-free either way, capped by the Lump Sum Allowance
    (£268,275) — a cap that binds for any pot above about £1.07m, so the
    familiar "25% tax-free" is not the whole 25% for exactly the people who
    assume it is. `PensionAccess.PCLS` takes it all in one event, at access;
    `PensionAccess.UFPLS` realises it gradually, 25% of each withdrawal,
    until the same allowance is used up.

    **Neither is the best route for a pot below about 90% of the pot size at
    which the cap binds.** That case wants phased crystallisation, which has no
    mode here -- approximate it with dated `pension_lump_sums` tranches rather
    than substituting `UFPLS`, whose forced taxable slice the real strategy
    avoids. `UFPLS` is never optimal on the modelled paths: it is dominated by
    phased below the cap and by `PCLS` above it, and it triggers the Money
    Purchase Annual Allowance immediately where `PCLS` alone does not. See
    `uk-pension-tax-strategy` for the thresholds and REVIEW.md 1.17 for why the
    missing crystallisation ledger understates both delayed routes.

    A PCLS's proceeds are invested via `_Accounts.invest_for`: the owner's own
    ISA first (then a spouse's if theirs is full), then the owner's GIA, and
    only cash if neither exists -- the same routing ordinary income surplus
    gets, since a PCLS belongs to the person it came from and has no more
    reason to sit idle than any other windfall. It is not spent down as a
    buffer before other assets; it is invested and drawn from alongside them
    by whichever `DrawdownStrategy` the scenario uses. Note the fallback GIA
    (present for every person whether or not the household has an explicit
    one) always uses `SampledSeries("global_equity")` -- real historical
    returns -- even in an otherwise fixed-return household, so a
    deterministic single-path check involving PCLS will still show
    market-path variation there.
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
        keys = keys | self.drawdown.series_keys()
        return keys.union(*(frozenset(m) for m in self.market_stress)) if self.market_stress else keys

    def reset_strategies(self) -> None:
        """Clear strategy state so one scenario object is safe across trials."""
        if self.withdrawal is not None:
            self.withdrawal.reset()
        self.drawdown.reset()
        if self.allocation is not None:
            self.allocation.reset()
