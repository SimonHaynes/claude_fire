"""The domain model: who the household is, what it owns, owes, earns and spends.

This is the shared vocabulary between data intake, scenario design, the
projection engine and the report. Every field maps onto something a client can
actually state in plain language — if a field cannot be sourced from a
conversation or a statement, it does not belong here.

Amounts are in **today's money**. The engine works in real terms throughout, so
there is no inflation uplift applied to any figure below; a salary of £50,000
means £50,000 of today's purchasing power in every year it is paid.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from .market import FixedReal, ReturnModel
from .mortality import FixedAge, MortalityModel


class Frequency(str, Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class IncomeType(str, Enum):
    SALARY = "salary"        # employment income: NI-able, and stops at retirement
    TAXABLE = "taxable"      # income tax but no NI (rental, unearned)
    TAX_FREE = "tax_free"


class AssetType(str, Enum):
    DC_PENSION = "dc_pension"   # taxable on withdrawal, locked until pension access age
    DB_PENSION = "db_pension"   # an entitlement, not a pot: pays income from start_age
    ISA = "isa"                 # tax-free on withdrawal
    GIA = "gia"                 # taxable general account: CGT on withdrawal, dividend tax yearly
    CASH = "cash"
    PROPERTY = "property"       # not treated as spendable by the default drawdown order


class ExpenseCategory(str, Enum):
    ESSENTIAL = "essential"          # never cut by a withdrawal strategy
    DISCRETIONARY = "discretionary"  # what guardrails flex


class Phase(str, Enum):
    """When in life an expense applies.

    An enum rather than a pair of booleans, because `pre_retirement_only` and
    `retirement_only` both being true is a state that should not be
    representable.
    """

    ALWAYS = "always"
    PRE_RETIREMENT = "pre_retirement"
    RETIREMENT = "retirement"


class PensionAccess(str, Enum):
    """How a DC pension's tax-free entitlement is realised, if at all.

    Lives here rather than in `scenario.py` so both `scenario.py` and
    `strategies/drawdown.py` can import it without a circular import --
    `scenario.py` already imports from `strategies`.
    """

    NONE = "none"
    """Every withdrawal is fully taxable. No lump sum is ever taken -- the
    previous, and still default, behaviour."""

    PCLS = "pcls"
    """Crystallise the whole pot the moment it becomes accessible and take
    the maximum tax-free lump sum in one event (25%, capped by the Lump Sum
    Allowance). Every withdrawal after that is fully taxable."""

    UFPLS = "ufpls"
    """No crystallisation event. Every withdrawal from the pot is
    automatically split 25% tax-free / 75% taxable, until the Lump Sum
    Allowance is used up, after which further withdrawals are fully
    taxable. See `uk-pension-tax-strategy` for when this beats PCLS."""


@dataclass
class Person:
    name: str
    date_of_birth: date
    full_state_pension: bool = True
    sex: str | None = None
    """"male" or "female", for mortality rates only.

    Unstated blends the two evenly. That is a real error of a few years each
    way -- a unisex table applied to a mixed couple is roughly three and a
    half years out per person -- so intake should ask rather than leave it,
    but averaging beats guessing."""


@dataclass
class IncomeSource:
    owner: str
    type: IncomeType
    amount: float
    frequency: Frequency = Frequency.YEARLY
    start: date | None = None
    end: date | None = None
    annual_real_growth: float = 0.0
    stops_at_retirement: bool = True


@dataclass
class Expense:
    name: str
    amount: float
    frequency: Frequency
    category: ExpenseCategory
    start: date | None = None
    end: date | None = None
    phase: Phase = Phase.ALWAYS
    years_from_retirement: int | None = None
    """With `phase=RETIREMENT`, also stop this many years after retiring.

    Whichever of this and `end` comes first wins, which is how you express
    "a big trip every year, but only for the first five years, and only
    while we're young enough to enjoy it".
    """


@dataclass
class Debt:
    name: str
    balance: float
    monthly_payment: float
    remaining_months: int | None = None
    last_payment: date | None = None
    """When the debt clears, as an actual date rather than a countdown.

    Prefer this over `remaining_months` whenever the client can give a date:
    a month count is only ever correct on the day it was stated and silently
    drifts by exactly the time between then and whenever the plan is next
    compiled — this is not hypothetical, it is what a real mortgage balance
    updated one time and not the other exposed. `compile_plan` recomputes
    the number of payments left from `as_of` and `last_payment` every time,
    so a plan regenerated later gets the right answer automatically instead
    of carrying forward a number that was only ever true once.

    Exactly one of `remaining_months` or `last_payment` must be given.
    """
    interest_rate: float | None = None
    """Recorded for the report only.

    The payment schedule is taken from `monthly_payment` and the debt's
    remaining term as stated, rather than re-derived from the rate: the
    client knows their actual schedule, and re-deriving it would drift from
    reality whenever the quoted rate is approximate or the deal is fixed.
    """

    def __post_init__(self) -> None:
        if (self.remaining_months is None) == (self.last_payment is None):
            raise ValueError(
                f"debt {self.name!r} needs exactly one of remaining_months or last_payment"
            )


@dataclass(frozen=True)
class Contribution:
    """Ongoing pension contributions, paid only while the owner is working.

    `employee_monthly` is treated as salary sacrifice: it reduces both taxable
    pay and NI-able pay. `employer_monthly` was never the employee's salary,
    so it simply lands in the pot.
    """

    employee_monthly: float = 0.0
    employer_monthly: float = 0.0
    start: date | None = None
    end: date | None = None
    """Bounds the contribution's own active window, independent of the
    linked salary `IncomeSource`'s -- `None` means "the whole time the
    salary is active" (the original behaviour, and still correct for anyone
    who contributes at a flat rate for their whole working life).

    Set `end` to model Coast FIRE precisely: contribute until a date, then
    stop, while the salary -- and its tax and NI -- carries on unaffected.
    Bounded by the salary's own window either way: a `Contribution.end`
    after the salary stops (or after retirement, if it `stops_at_retirement`)
    has no further effect once the salary itself is gone."""


@dataclass(frozen=True)
class Maturity:
    """A fixed-term holding that ends on a date, optionally rolling elsewhere."""

    on: date
    rollover_to: str | None = None


@dataclass(frozen=True)
class DefinedBenefit:
    """A DB pension entitlement: income for life from an age, plus any lump sum."""

    annual_amount: float
    start_age: int
    lump_sum: float = 0.0


@dataclass
class Asset:
    name: str
    type: AssetType
    owner: str = "joint"
    value: float = 0.0
    returns: ReturnModel = field(default_factory=lambda: FixedReal(0.0))
    annual_charge_pct: float = 0.0
    flat_annual_fee: float = 0.0
    contributions: Contribution | None = None
    maturity: Maturity | None = None
    defined_benefit: DefinedBenefit | None = None

    def __post_init__(self) -> None:
        if self.type is AssetType.DB_PENSION and self.defined_benefit is None:
            raise ValueError(f"DB pension {self.name!r} needs a defined_benefit")
        if self.defined_benefit is not None and self.type is not AssetType.DB_PENSION:
            raise ValueError(f"{self.name!r} has defined_benefit but is not a DB_PENSION")


@dataclass
class Goal:
    """A stated intention, recorded so the report can restate it.

    The engine does *not* act on these. Turning a costed goal into money
    leaving the plan is a judgement about timing and amount, so it is done
    deliberately when scenarios are written -- add a `Scenario.one_off_spend`
    (see the `define-scenarios` skill). A goal listed here and never costed
    shows up in the report's current-position section and nowhere else, which
    is the intended behaviour, not an oversight.
    """

    description: str
    target_amount: float | None = None
    target_date: date | None = None
    priority: int = 1


@dataclass(frozen=True)
class FiscalDrag:
    """Tax thresholds frozen in nominal terms, and so shrinking in real ones.

    This engine works in today's money, which means leaving a threshold alone
    silently assumes it rises with inflation every year. Most of them do not.
    The personal allowance, the basic-rate ceiling, the £100k taper and the
    nil-rate bands are frozen in *nominal* terms by announced policy, and the
    Lump Sum Allowance, the ISA subscription limit, the CGT exempt amount and
    the dividend allowance have no uprating mechanism at all.

    Holding them constant in real terms is therefore not neutral -- it is a
    quiet gift to every projection, compounding over decades, and it flatters
    the IHT numbers worst of all: a nil-rate band frozen while an estate grows
    in real terms is a steadily shrinking shelter.

    `inflation=0.0` reproduces the old behaviour exactly, which is what makes
    the change attributable rather than lost in noise.

    Note what is deliberately *not* dragged: the State Pension, which is
    triple-locked and rises in real terms. Scaling it down would be wrong, and
    wrong in the expensive direction.
    """

    inflation: float = 0.0
    """Assumed annual inflation. Only ever used to erode frozen thresholds --
    every other figure in the engine is already in real terms."""

    income_freeze_until: date = date(2028, 4, 6)
    """Announced end of the income tax and NI threshold freeze."""

    iht_freeze_until: date = date(2031, 4, 6)
    """Announced end of the inheritance tax band freeze. A different horizon
    from income tax, so the two are tracked separately."""

    never_uprated_freeze_forever: bool = True
    """Whether allowances with no uprating mechanism -- the Lump Sum
    Allowance, the ISA limit, the CGT exempt amount, the dividend allowance --
    keep eroding after the announced freezes end. They have not risen in
    years, so the honest default is that they continue not to."""


@dataclass
class Assumptions:
    life_expectancy_age: int = 95
    state_pension_age: int = 68
    state_pension_annual: float = 11_973.0
    risk_tolerance: str = "medium"
    fiscal_drag: FiscalDrag = field(default_factory=FiscalDrag)

    mortality: "MortalityModel" = field(default_factory=FixedAge)
    """How age at death is decided. `FixedAge` is the previous behaviour and
    the default, so switching to a life table is a deliberate act whose effect
    on the numbers is attributable to it."""

    max_age: int = 105
    """Horizon when mortality is sampled. Trials run this far with the estate
    frozen after the second death, which keeps every trial the same length so
    percentile bands stay well-defined across trials that ended at different
    times."""

    db_survivor_fraction: float = 0.50
    """What fraction of a DB pension continues to a surviving spouse.

    Around half is typical -- the Teachers' Pension and most public-sector
    schemes pay roughly 50%. The remainder stops. Note the survivor benefit is
    paid to, and taxed on, the *survivor*: leaving it under the deceased's
    name would hand a dead person a personal allowance every year."""

    survivor_essential_factor: float = 0.90
    survivor_discretionary_factor: float = 0.75
    """How household spending changes when one of two people dies.

    It falls, but nothing like in half. Fixed costs -- the mortgage,
    maintenance, insurance, standing charges -- do not move at all; council
    tax gets a 25% single-person discount in England; one person's food,
    travel and holidays stop. So essentials fall a little and discretionary
    spending falls more, landing near 85% of a couple's total for a typical
    60/40 split.

    For reference, the OECD-modified equivalence scale implies a single person
    needs 0.67 of a couple's income, the square-root scale 0.71, and the PLSA
    Retirement Living Standards put a single "moderate" household at roughly
    70-75%. These defaults sit deliberately *above* that range: keeping
    spending high makes plans look worse, which is the right direction to err
    for a correction whose entire purpose is to expose a missing downside.

    Debt payments, one-off spends, gifts and care costs are never scaled by
    these -- a mortgage does not shrink because someone died."""


@dataclass
class Household:
    people: list[Person] = field(default_factory=list)
    incomes: list[IncomeSource] = field(default_factory=list)
    expenses: list[Expense] = field(default_factory=list)
    debts: list[Debt] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)
    goals: list[Goal] = field(default_factory=list)
    assumptions: Assumptions = field(default_factory=Assumptions)

    def person(self, name: str) -> Person:
        for p in self.people:
            if p.name == name:
                return p
        raise KeyError(f"no person named {name!r}")

    def assets_of(self, *types: AssetType) -> list[Asset]:
        return [a for a in self.assets if a.type in types]

    def validate(self) -> None:
        """Catch the mistakes that would otherwise surface as silent zeroes."""
        names = {p.name for p in self.people}
        problems: list[str] = []
        for income in self.incomes:
            if income.owner not in names:
                problems.append(f"income {income.type.value!r} names unknown owner {income.owner!r}")
        asset_names = {a.name for a in self.assets}
        if len(asset_names) != len(self.assets):
            problems.append("asset names must be unique (they key the balance ledger)")
        for asset in self.assets:
            if asset.owner not in names and asset.owner != "joint":
                problems.append(f"asset {asset.name!r} names unknown owner {asset.owner!r}")
            if asset.maturity and asset.maturity.rollover_to:
                if asset.maturity.rollover_to not in asset_names:
                    problems.append(
                        f"asset {asset.name!r} rolls over into unknown asset "
                        f"{asset.maturity.rollover_to!r}"
                    )
        if problems:
            raise ValueError("invalid household:\n  - " + "\n  - ".join(problems))
