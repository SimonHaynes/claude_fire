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

from .annuity import AnnuityOptions
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
    """A lifetime annuity bought from a DC pension at first pension access.

    The "floor" half of floor-and-upside: secure essential spending with
    guaranteed income, then invest what remains for upside. Annuitised money is
    gone in exchange for the income stream — which is the point as much as the
    cost, since nothing else removes longevity risk.

    Distinct from `care.ImmediateNeedsAnnuity`, which is a short impaired-life
    annuity bought on entering care and paid tax-free direct to the provider.
    This one's income is ordinary taxable pension income.

    Bought from whatever remains *after* any `PensionAccess.PCLS` cash, so
    `fraction_of_pot` applies to the pot as it stands when this fires.

    Priced by `retireplan.annuity` from the gilt curve and a mortality basis at
    the annuitant's actual age. The one thing that needs stating here is
    `assumed_inflation`, because this engine works in real terms and **the
    market sells nominal annuities**: a level annuity is flat in pounds and
    therefore falling in purchasing power every year it is paid.
    """

    enabled: bool = False
    fraction_of_pot: float = 0.0
    """Fraction of the DC pot to annuitise. Annuitise the floor, not the whole
    pot, or there is no upside left to invest."""

    joint_life_proportion: float = 0.0
    """Fraction of the income continuing to a surviving spouse. 0 leaves the
    survivor nothing, which is the right default only for a single person."""

    guarantee_years: int = 0
    escalation: float = 0.0
    """Fixed *nominal* increase each year. Note the change of frame from the
    rest of this engine: 0 buys a level annuity, which declines in real terms
    at `assumed_inflation`, and only escalation above that grows in real
    terms."""

    rpi_linked: bool = False
    """Income rises with prices, so it is flat in real terms. Costs about 30%
    of the starting income against level."""

    health_uplift: float = 0.0
    """Enhanced underwriting, as a fraction added to the income. Only a real
    underwriter can price this; the model applies what it is told."""

    assumed_inflation: float = 0.02
    """What a level annuity's income loses in real terms each year.

    Non-zero by default, and deliberately not tied to `FiscalDrag.inflation`:
    that governs whether *announced threshold freezes* are modelled and is
    opt-in, whereas a nominal annuity decaying in a real-terms projection is
    arithmetic rather than a policy assumption. 2% is the Bank of England
    target, matching `standard-assumptions`."""

    def options(self) -> "AnnuityOptions":
        return AnnuityOptions(
            joint_life_proportion=self.joint_life_proportion,
            guarantee_years=self.guarantee_years,
            escalation=self.escalation,
            rpi_linked=self.rpi_linked,
            health_uplift=self.health_uplift,
        )

    def real_income_factor(self, years_in_payment: int) -> float:
        """Multiplier on the starting income, in today's money.

        RPI-linking holds real value by construction. Anything else drifts at
        the gap between its nominal escalation and inflation — downwards for a
        level annuity, which is the fact this method exists to stop anyone
        forgetting.
        """
        if self.rpi_linked:
            return 1.0
        drift = (1 + self.escalation) / (1 + self.assumed_inflation)
        return drift ** years_in_payment

    def spec(self) -> dict:
        return {
            "enabled": self.enabled,
            "fraction_of_pot": self.fraction_of_pot,
            "joint_life_proportion": self.joint_life_proportion,
            "guarantee_years": self.guarantee_years,
            "escalation": self.escalation,
            "rpi_linked": self.rpi_linked,
            "health_uplift": self.health_uplift,
            "assumed_inflation": self.assumed_inflation,
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
