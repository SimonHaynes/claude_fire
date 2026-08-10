"""Compiling a household + scenario into a `Plan`.

Everything independent of market returns — earnings, tax band, spending, debt
payoff, maturities, pension access — is resolved once here into `PlanYear`
records. Only balances vary between trials, so only balances belong in the hot
loop; precomputing the rest is what makes a 2,000-trial run seconds not minutes.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date

from .market import SampledSeries
from .model import (
    Assumptions,
    Asset,
    AssetType,
    ExpenseCategory,
    FiscalDrag,
    Frequency,
    Household,
    IncomeSource,
    IncomeType,
    Person,
    Phase,
)
from .mortality import FixedAge
from .scenario import Scenario
from .tax import TaxSystem
from .timeline import add_years, age_on, debt_payment_schedule, earliest, latest, months_remaining, overlap_fraction

CASH_RESERVE = "__cash_reserve"
LADDER_RESERVE = "__ladder_reserve"
BOND_RESERVE = "__bond_reserve"
"""Distinct from `LADDER_RESERVE`, which grows at a strategy-chosen fixed real
rate: this one earns a sampled series via `DrawdownContext.bond_return`, so a
three-bucket middle tier can be actual bonds. See `ThreeBucketStrategy`."""
SURPLUS_GIA_NAME = "{name} — Surplus GIA (Global Tracker)"
SURPLUS_ISA_NAME = "{name} — Surplus ISA (Global Tracker)"


def _annual(amount: float, frequency: Frequency) -> float:
    return amount * 12 if frequency is Frequency.MONTHLY else amount


def _add(bucket: dict, key, amount: float) -> None:
    bucket[key] = bucket.get(key, 0.0) + amount


@dataclass(frozen=True)
class PlanYear:
    """One projection year, with everything market-independent resolved."""

    index: int
    calendar_year: int
    start: date
    end: date
    ages: dict[str, int]
    is_retired: bool
    dc_accessible: bool
    dc_accessible_by_person: dict[str, bool]

    tax: TaxSystem
    """This year's tax system, not the household's: nominally frozen thresholds
    shrink in real terms. Resolving it here keeps it market-independent and
    reaches income tax, NI, the pension gross-up, CGT, dividend tax, the ISA
    allowance and the PCLS cap without any strategy knowing about it."""

    alive: frozenset[str]

    salary_gross_by_person: dict[str, float]
    """Before salary sacrifice; reporting only. `employment_income_by_person`
    is after sacrifice, and is the NI-able figure."""
    employment_income_by_person: dict[str, float]

    db_income_by_person: dict[str, float]
    """Taxable income is split three ways because death treats it three ways: a
    State Pension stops and does not transfer, a DB pension continues to the
    survivor at `db_survivor_fraction`, other income passes whole under the
    spouse exemption. Recombine with `other_taxable_by_person`."""
    state_pension_by_person: dict[str, float]
    taxable_other_by_person: dict[str, float]

    tax_free_income_by_person: dict[str, float]
    """Per person, not a household total: income belonging to someone who has
    died must stop being paid to a household that no longer contains them."""

    contributions: tuple[tuple[int, float], ...]
    """(asset slot, amount paid in this year)."""
    lump_sums_by_person: dict[str, float]
    """DB retirement lump sums, by whose entitlement they are. Invested for that
    person (ISA then GIA), not pooled into shared cash — see
    `cashflow._Accounts.invest_for`."""
    maturities: tuple[tuple[int, int | None], ...]
    """(maturing slot, rollover-to slot or None)."""

    essential: float
    nominal_discretionary: float

    debt_payment: float
    one_off: float
    gifts: float

    care_cost: float = 0.0
    """Sampled, so `project` sets it per trial rather than compile time. Kept
    out of `essential` because a cash ladder must not size against it, though
    no withdrawal rule may cut it."""

    @property
    def fixed_spend(self) -> float:
        """Spending a withdrawal strategy is not allowed to cut."""
        return (
            self.essential + self.care_cost
            + self.debt_payment + self.one_off + self.gifts
        )

    @property
    def other_taxable_by_person(self) -> dict[str, float]:
        names = (
            set(self.db_income_by_person)
            | set(self.state_pension_by_person)
            | set(self.taxable_other_by_person)
        )
        return {
            name: self.db_income_by_person.get(name, 0.0)
            + self.state_pension_by_person.get(name, 0.0)
            + self.taxable_other_by_person.get(name, 0.0)
            for name in names
        }

    @property
    def tax_free_income(self) -> float:
        return sum(self.tax_free_income_by_person.values())

    @property
    def taxable_income_by_person(self) -> dict[str, float]:
        other = self.other_taxable_by_person
        return {
            name: self.employment_income_by_person.get(name, 0.0) + other.get(name, 0.0)
            for name in set(self.employment_income_by_person) | set(other)
        }


@dataclass(frozen=True)
class SlotMaps:
    """Which ledger slots belong to whom, for one alive-set."""

    isa_slots_by_person: dict[str, tuple[int, ...]]
    dc_slots_by_person: dict[str, tuple[int, ...]]
    gia_slots_by_person: dict[str, tuple[int, ...]]
    dc_accessible_override: frozenset[str]
    """People whose DC pots are accessible regardless of age, because they
    were inherited. A beneficiary can draw an inherited pension at any age;
    without this the survivor would inherit the *deceased's* access age."""


@dataclass(frozen=True)
class Plan:
    """A compiled scenario: fixed schedule, asset layout, and tax rules."""

    household: Household
    scenario: Scenario
    tax: TaxSystem
    as_of: date
    years: tuple[PlanYear, ...]

    slot_names: tuple[str, ...]
    """Ledger layout. Real assets first, in order, then the synthetic cash and
    ladder reserves — so slot `i` is `assets[i]`, and a portfolio is a flat
    list of floats."""

    assets: tuple[Asset, ...]
    opening_balances: tuple[float, ...]
    isa_slots: tuple[int, ...]
    isa_slots_by_person: dict[str, tuple[int, ...]]
    dc_slots_by_person: dict[str, tuple[int, ...]]
    gia_slots_by_person: dict[str, tuple[int, ...]]
    investable_slots: tuple[int, ...]
    """Cash, reserves, ISAs and pensions — what a withdrawal strategy may
    count on. Excludes property, which grows in the ledger but is never sold
    by the built-in drawdown strategies."""

    cash_slot: int
    ladder_slot: int
    bond_slot: int
    series_keys: frozenset[str]

    year_variants: dict[frozenset[str], tuple[PlanYear, ...]]
    """One full year schedule per alive-set. Deaths only remove people, so all
    2^n schedules are built once here and `project` picks one with a dict
    lookup, keeping per-year work out of the hot loop."""

    slots_by_variant: dict[frozenset[str], "SlotMaps"]
    """Pot ownership per alive-set, with a dead person's pensions, ISAs and GIAs
    re-keyed to the survivor. Otherwise a drawdown strategy keeps drawing from
    the deceased's pension against a personal allowance and basic-rate band that
    no longer exist."""

    death_index_by_person: dict[str, int]
    """Plan-year in which each person dies, under this scenario's assumptions.
    Stochastic mortality overrides this per trial."""

    @property
    def n_years(self) -> int:
        return len(self.years)

    def years_for(self, alive: frozenset[str]) -> tuple[PlanYear, ...]:
        return self.year_variants[alive]

    def slot(self, name: str) -> int:
        return self.slot_names.index(name)


MAX_PEOPLE_FOR_VARIANTS = 4
"""Alive-set variants cost 2^n schedules; beyond this a household should fail
loudly rather than quietly build 64 of them."""


def _survivor_year(year: PlanYear, alive: frozenset[str], assumptions) -> PlanYear:
    """`year` as it would be with only `alive` still living.

    Surviving income is re-keyed to the heir rather than left under the
    deceased's name, which would keep drawing on a personal allowance and a
    basic-rate band that no longer exist. Spending falls by
    `Assumptions.survivor_*_factor`; debt, one-offs and gifts do not fall.
    """
    dead = set(year.alive) - set(alive)
    if not dead:
        return year
    if not alive:
        # The estate is settled elsewhere; this year just goes quiet.
        return dataclasses.replace(
            year, alive=alive,
            salary_gross_by_person={}, employment_income_by_person={},
            db_income_by_person={}, state_pension_by_person={},
            taxable_other_by_person={}, tax_free_income_by_person={},
            contributions=(), lump_sums_by_person={},
            essential=0.0, nominal_discretionary=0.0, debt_payment=0.0,
            one_off=0.0, gifts=0.0,
        )

    # With more than one survivor, first-by-name only keeps this deterministic;
    # the tax difference between recipients is a refinement not attempted here.
    heir = sorted(alive)[0]

    def drop_dead(source: dict[str, float]) -> dict[str, float]:
        return {k: v for k, v in source.items() if k not in dead}

    def move_to_heir(source: dict[str, float]) -> dict[str, float]:
        moved = drop_dead(source)
        transferred = sum(v for k, v in source.items() if k in dead)
        if transferred:
            moved[heir] = moved.get(heir, 0.0) + transferred
        return moved

    db = drop_dead(year.db_income_by_person)
    inherited_db = sum(
        v * assumptions.db_survivor_fraction
        for k, v in year.db_income_by_person.items() if k in dead
    )
    if inherited_db:
        db[heir] = db.get(heir, 0.0) + inherited_db

    return dataclasses.replace(
        year,
        alive=alive,
        salary_gross_by_person=drop_dead(year.salary_gross_by_person),
        employment_income_by_person=drop_dead(year.employment_income_by_person),
        db_income_by_person=db,
        state_pension_by_person=drop_dead(year.state_pension_by_person),
        taxable_other_by_person=move_to_heir(year.taxable_other_by_person),
        tax_free_income_by_person=move_to_heir(year.tax_free_income_by_person),
        # An unpaid DB lump sum dies with the entitlement it was attached to.
        lump_sums_by_person=drop_dead(year.lump_sums_by_person),
        essential=year.essential * assumptions.survivor_essential_factor,
        nominal_discretionary=(
            year.nominal_discretionary * assumptions.survivor_discretionary_factor
        ),
    )


def _slots_for(
    alive: frozenset[str],
    isa_slots_by_person: dict[str, tuple[int, ...]],
    dc_slots_by_person: dict[str, tuple[int, ...]],
    gia_slots_by_person: dict[str, tuple[int, ...]],
) -> "SlotMaps":
    """Pot ownership with a dead person's slots re-keyed to the survivor.

    Modelled as the pot passing to the spouse as successor drawdown, which is
    right for a death after 75 and conservative for one before it (where an
    inherited pot would in fact be drawable tax-free).
    """
    if not alive:
        return SlotMaps({}, {}, {}, frozenset())
    heir = sorted(alive)[0]

    def rekey(source: dict[str, tuple[int, ...]]) -> dict[str, tuple[int, ...]]:
        out: dict[str, tuple[int, ...]] = {}
        inherited: tuple[int, ...] = ()
        for name, slots in source.items():
            if name in alive:
                out[name] = out.get(name, ()) + slots
            else:
                inherited += slots
        if inherited:
            out[heir] = out.get(heir, ()) + inherited
        return out

    inherited_any = any(name not in alive for name in dc_slots_by_person)
    return SlotMaps(
        isa_slots_by_person=rekey(isa_slots_by_person),
        dc_slots_by_person=rekey(dc_slots_by_person),
        gia_slots_by_person=rekey(gia_slots_by_person),
        dc_accessible_override=frozenset({heir}) if inherited_any else frozenset(),
    )


def _alive_sets(names: frozenset[str]) -> list[frozenset[str]]:
    """Every subset of `names`, largest first."""
    ordered = sorted(names)
    sets = []
    for mask in range(1 << len(ordered)):
        sets.append(frozenset(n for i, n in enumerate(ordered) if mask & (1 << i)))
    return sorted(sets, key=len, reverse=True)


def real_terms_factor(inflation: float, years: float) -> float:
    """What £1 of a nominally-frozen threshold is worth after `years`.

    The clock starts at `as_of`, which is right by construction: today's
    £12,570 *is* today's real value, and only later years erode.
    """
    if inflation <= 0 or years <= 0:
        return 1.0
    return 1.0 / (1.0 + inflation) ** years


def _tax_by_year(
    tax: TaxSystem,
    drag: FiscalDrag,
    as_of: date,
    last_index: int,
) -> list[TaxSystem]:
    """One tax system per plan-year, with frozen thresholds eroded.

    Returns the same object for every year when `inflation` is zero, so the
    old behaviour is reproduced exactly -- and cheaply, since nothing is
    rebuilt. `TaxSystem` is a Protocol, so a jurisdiction that does not
    implement `with_thresholds_scaled` simply does not get dragged rather
    than crashing.
    """
    scaler = getattr(tax, "with_thresholds_scaled", None)
    if drag.inflation <= 0 or scaler is None:
        return [tax] * (last_index + 1)

    income_freeze_years = max(0.0, (drag.income_freeze_until - as_of).days / 365.25)

    by_index = []
    for i in range(last_index + 1):
        # Thresholds stop eroding when the announced freeze ends and uprating
        # resumes; allowances with no uprating mechanism keep going.
        income_years = min(float(i), income_freeze_years)
        allowance_years = float(i) if drag.never_uprated_freeze_forever else income_years
        by_index.append(scaler(
            real_terms_factor(drag.inflation, income_years),
            real_terms_factor(drag.inflation, allowance_years),
        ))
    return by_index


@dataclass(frozen=True)
class _Ledger:
    """Where every asset sits in the flat balance list."""

    assets: tuple[Asset, ...]
    slot_names: tuple[str, ...]
    slot_of: dict[str, int]
    opening: tuple[float, ...]
    isa_slots: tuple[int, ...]
    isa_slots_by_person: dict[str, tuple[int, ...]]
    dc_slots_by_person: dict[str, tuple[int, ...]]
    gia_slots_by_person: dict[str, tuple[int, ...]]
    investable_slots: tuple[int, ...]


def _surplus_shelters(household: Household, people: dict[str, Person]) -> list[Asset]:
    """Empty ISA and GIA slots for future surplus income to land in.

    A GIA for everyone; an ISA only for those without one, since an ISA has a
    real subscription limit and a household that already models one should not
    gain a second. Both open at zero and are never backdated. Without them a
    client who holds no ISA today has nowhere to shelter surplus income, a PCLS
    or a Bed-and-ISA — `credit_isa` and Bed-and-ISA no-op on zero headroom,
    so the money would sit taxed for the whole plan. Holding no ISA is a fact
    about the client's past, not a ceiling on what the plan may consider.
    """
    def shelter(name: str, template: str, type_: AssetType) -> Asset:
        return Asset(
            template.format(name=name), type_, name, 0.0,
            returns=SampledSeries("global_equity"),
        )

    already_holds_isa = {a.owner for a in household.assets_of(AssetType.ISA)}
    return [
        shelter(name, SURPLUS_ISA_NAME, AssetType.ISA)
        for name in people if name not in already_holds_isa
    ] + [
        shelter(name, SURPLUS_GIA_NAME, AssetType.GIA) for name in people
    ]


def _ledger_layout(household: Household, people: dict[str, Person]) -> _Ledger:
    spendable = [a for a in household.assets if a.type is not AssetType.DB_PENSION]
    spendable += _surplus_shelters(household, people)

    slot_names = [a.name for a in spendable] + [CASH_RESERVE, LADDER_RESERVE, BOND_RESERVE]
    slot_of = {name: i for i, name in enumerate(slot_names)}

    def slots_owned(type_: AssetType) -> dict[str, tuple[int, ...]]:
        return {
            name: tuple(
                slot_of[a.name] for a in spendable if a.type is type_ and a.owner == name
            )
            for name in people
        }

    isa_slots = tuple(slot_of[a.name] for a in spendable if a.type is AssetType.ISA)
    dc_by_person = slots_owned(AssetType.DC_PENSION)
    gia_by_person = slots_owned(AssetType.GIA)
    return _Ledger(
        assets=tuple(spendable),
        slot_names=tuple(slot_names),
        slot_of=slot_of,
        opening=tuple([a.value for a in spendable] + [0.0, 0.0, 0.0]),
        isa_slots=isa_slots,
        isa_slots_by_person=slots_owned(AssetType.ISA),
        dc_slots_by_person=dc_by_person,
        gia_slots_by_person=gia_by_person,
        investable_slots=tuple(sorted(
            {slot_of[CASH_RESERVE], slot_of[LADDER_RESERVE], slot_of[BOND_RESERVE]}
            | set(isa_slots)
            | {s for slots in dc_by_person.values() for s in slots}
            | {s for slots in gia_by_person.values() for s in slots}
            | {slot_of[a.name] for a in spendable if a.type is AssetType.CASH}
        )),
    )


@dataclass
class _YearIncome:
    salary_gross: dict[str, float] = field(default_factory=dict)
    employment: dict[str, float] = field(default_factory=dict)
    taxable_other: dict[str, float] = field(default_factory=dict)
    tax_free: dict[str, float] = field(default_factory=dict)
    contributions: dict[int, float] = field(default_factory=dict)


def _pay_contributions(
    into: dict[int, float],
    ledger: _Ledger,
    salary: IncomeSource,
    stop: date | None,
    start: date,
    end: date,
) -> float:
    """Pay this salary's pension contributions; returns the amount sacrificed."""
    sacrificed = 0.0
    for asset in ledger.assets:
        if asset.contributions is None or asset.owner != salary.owner:
            continue
        # A Contribution's own window narrows the salary's rather than replacing
        # it: Coast FIRE stops contributing while the salary (and its tax and NI)
        # carries on, and a contribution cannot outlive the salary funding it.
        lower = latest(salary.start, asset.contributions.start)
        upper = earliest(salary.end, stop, asset.contributions.end)
        fraction = overlap_fraction(start, end, lower, upper)
        if fraction <= 0:
            continue
        employee = asset.contributions.employee_monthly * 12 * fraction
        employer = asset.contributions.employer_monthly * 12 * fraction
        _add(into, ledger.slot_of[asset.name], employee + employer)
        sacrificed += employee
    return sacrificed


def _income_for_year(
    household: Household,
    ledger: _Ledger,
    retirement: dict[str, date],
    index: int,
    start: date,
    end: date,
) -> _YearIncome:
    year = _YearIncome()
    for income in household.incomes:
        stop = retirement.get(income.owner) if income.stops_at_retirement else None
        fraction = overlap_fraction(start, end, income.start, earliest(income.end, stop))
        if fraction <= 0:
            continue
        amount = (
            _annual(income.amount, income.frequency)
            * (1 + income.annual_real_growth) ** index
            * fraction
        )
        if income.type is IncomeType.TAX_FREE:
            _add(year.tax_free, income.owner, amount)
        elif income.type is IncomeType.TAXABLE:
            _add(year.taxable_other, income.owner, amount)
        else:
            _add(year.salary_gross, income.owner, amount)
            sacrificed = _pay_contributions(
                year.contributions, ledger, income, stop, start, end
            )
            _add(year.employment, income.owner, amount - sacrificed)
    return year


def _db_entitlements_for_year(
    db_assets: list[Asset],
    people: dict[str, Person],
    start: date,
    end: date,
) -> tuple[dict[str, float], dict[str, float]]:
    """This year's DB pension income and any lump sum falling due in it."""
    income: dict[str, float] = {}
    lump_sums: dict[str, float] = {}
    for asset in db_assets:
        db = asset.defined_benefit
        assert db is not None  # guaranteed by Asset.__post_init__
        db_start = add_years(people[asset.owner].date_of_birth, db.start_age)
        fraction = overlap_fraction(start, end, db_start, None)
        if fraction > 0:
            _add(income, asset.owner, db.annual_amount * fraction)
        if db.lump_sum and start <= db_start < end:
            _add(lump_sums, asset.owner, db.lump_sum)
    return income, lump_sums


def _state_pension_for_year(
    people: dict[str, Person],
    assumptions: Assumptions,
    payable_from: dict[str, date],
    start: date,
    end: date,
) -> dict[str, float]:
    paid: dict[str, float] = {}
    for name, person in people.items():
        fraction = overlap_fraction(start, end, payable_from[name], None)
        if fraction > 0 and person.full_state_pension:
            paid[name] = assumptions.state_pension_annual * fraction
    return paid


def _spending_for_year(
    household: Household,
    scenario: Scenario,
    household_retirement: date | None,
    start: date,
    end: date,
) -> tuple[float, float]:
    """Essential and discretionary spending, the latter already multiplied."""
    essential = 0.0
    discretionary = 0.0
    for expense in household.expenses:
        exp_start, exp_end = expense.start, expense.end
        if expense.phase is Phase.PRE_RETIREMENT:
            exp_end = earliest(exp_end, household_retirement)
        elif expense.phase is Phase.RETIREMENT:
            exp_start = household_retirement
            if expense.years_from_retirement is not None and household_retirement is not None:
                exp_end = earliest(
                    exp_end, add_years(household_retirement, expense.years_from_retirement)
                )
        fraction = overlap_fraction(start, end, exp_start, exp_end)
        if fraction <= 0:
            continue
        amount = _annual(expense.amount, expense.frequency) * fraction
        if expense.category is ExpenseCategory.ESSENTIAL:
            essential += amount
        else:
            discretionary += amount * scenario.spending_multiplier
    return essential, discretionary


def _last_year_index(
    people: dict[str, Person],
    assumptions: Assumptions,
    as_of: date,
) -> int:
    """How far the projection runs.

    Sampled mortality needs a horizon covering the oldest age anyone *could*
    reach, not the age they are expected to reach: every trial runs the full
    length with the estate frozen after the last death, which is what keeps
    percentile bands well-defined across trials that end at different times.
    """
    horizon_age = (
        assumptions.life_expectancy_age
        if isinstance(assumptions.mortality, FixedAge)
        else assumptions.max_age
    )
    return max([0, *(
        (add_years(p.date_of_birth, horizon_age) - as_of).days // 365
        for p in people.values()
    )])


def _debt_payments_by_index(household: Household, as_of: date) -> dict[int, float]:
    by_index: dict[int, float] = {}
    for debt in household.debts:
        remaining = (
            debt.remaining_months if debt.remaining_months is not None
            else months_remaining(as_of, debt.last_payment)
        )
        for i, amount in enumerate(debt_payment_schedule(debt.monthly_payment, remaining)):
            _add(by_index, i, amount)
    return by_index


def compile_plan(
    household: Household,
    scenario: Scenario,
    tax: TaxSystem,
    as_of: date,
) -> Plan:
    household.validate()
    assumptions = household.assumptions
    people = {p.name: p for p in household.people}

    retirement = dict(scenario.retirement_dates)
    unknown = set(retirement) - set(people)
    if unknown:
        raise ValueError(f"scenario retires people not in the household: {sorted(unknown)}")
    household_retirement = max(retirement.values()) if retirement else None

    access_date = {
        name: add_years(p.date_of_birth, tax.pension_access_age) for name, p in people.items()
    }
    state_pension_date = {
        name: add_years(p.date_of_birth, assumptions.state_pension_age) for name, p in people.items()
    }

    ledger = _ledger_layout(household, people)
    db_assets = household.assets_of(AssetType.DB_PENSION)

    series_keys = frozenset({"inflation"}).union(
        *(a.returns.series_keys() for a in ledger.assets)
    ) if ledger.assets else frozenset({"inflation"})
    series_keys |= scenario.series_keys()

    last_index = _last_year_index(people, assumptions, as_of)
    debt_by_index = _debt_payments_by_index(household, as_of)
    tax_by_index = _tax_by_year(tax, assumptions.fiscal_drag, as_of, last_index)
    everyone = frozenset(people)

    years: list[PlanYear] = []
    for i in range(last_index + 1):
        start = as_of if i == 0 else add_years(as_of, i)
        end = add_years(as_of, i + 1)

        income = _income_for_year(household, ledger, retirement, i, start, end)
        db_income, lump_sums = _db_entitlements_for_year(db_assets, people, start, end)
        essential, discretionary = _spending_for_year(
            household, scenario, household_retirement, start, end
        )

        years.append(
            PlanYear(
                index=i,
                calendar_year=start.year,
                start=start,
                end=end,
                ages={name: age_on(p.date_of_birth, start) for name, p in people.items()},
                is_retired=(
                    household_retirement is not None and start >= household_retirement
                ),
                # `end > access_date`, not `start >= access_date`: access begins in
                # the plan-year the birthday falls in. At plan-year resolution that
                # can grant it a few months early; denying it for up to eleven
                # months after the birthday is the worse error.
                dc_accessible=any(end > access_date[n] for n in people),
                dc_accessible_by_person={n: end > access_date[n] for n in people},
                tax=tax_by_index[i],
                alive=everyone,
                salary_gross_by_person=income.salary_gross,
                employment_income_by_person=income.employment,
                db_income_by_person=db_income,
                state_pension_by_person=_state_pension_for_year(
                    people, assumptions, state_pension_date, start, end
                ),
                taxable_other_by_person=income.taxable_other,
                tax_free_income_by_person=income.tax_free,
                contributions=tuple(sorted(income.contributions.items())),
                lump_sums_by_person=lump_sums,
                maturities=tuple(
                    (
                        ledger.slot_of[a.name],
                        ledger.slot_of[a.maturity.rollover_to] if a.maturity.rollover_to else None,
                    )
                    for a in ledger.assets
                    if a.maturity is not None and start <= a.maturity.on < end
                ),
                essential=essential,
                nominal_discretionary=discretionary,
                debt_payment=debt_by_index.get(i, 0.0),
                one_off=sum(
                    item.amount for item in scenario.one_off_spends if start <= item.on < end
                ),
                gifts=sum(g.amount for g in scenario.gifts if start <= g.on < end),
            )
        )

    if len(people) > MAX_PEOPLE_FOR_VARIANTS:
        raise ValueError(
            f"survivorship is precomputed per alive-set, which is 2^n schedules; "
            f"{len(people)} people exceeds the supported {MAX_PEOPLE_FOR_VARIANTS}"
        )

    base_years = tuple(years)
    year_variants = {
        alive: tuple(_survivor_year(y, alive, assumptions) for y in base_years)
        for alive in _alive_sets(everyone)
    }
    slots_by_variant = {
        alive: _slots_for(
            alive,
            ledger.isa_slots_by_person,
            ledger.dc_slots_by_person,
            ledger.gia_slots_by_person,
        )
        for alive in _alive_sets(everyone)
    }

    death_index_by_person = {}
    for name, person in people.items():
        age = (scenario.death_ages or {}).get(name, assumptions.life_expectancy_age)
        death = add_years(person.date_of_birth, age)
        # Floored at 1 to match a horizon floored at index 0: a household already
        # past its stated life expectancy still gets the one year the plan runs
        # for, rather than being dead before it starts.
        death_index_by_person[name] = max(1, (death - as_of).days // 365 + 1)

    return Plan(
        household=household,
        scenario=scenario,
        tax=tax,
        as_of=as_of,
        years=base_years,
        year_variants=year_variants,
        slots_by_variant=slots_by_variant,
        death_index_by_person=death_index_by_person,
        slot_names=ledger.slot_names,
        assets=ledger.assets,
        opening_balances=ledger.opening,
        isa_slots=ledger.isa_slots,
        isa_slots_by_person=ledger.isa_slots_by_person,
        dc_slots_by_person=ledger.dc_slots_by_person,
        gia_slots_by_person=ledger.gia_slots_by_person,
        investable_slots=ledger.investable_slots,
        cash_slot=ledger.slot_of[CASH_RESERVE],
        ladder_slot=ledger.slot_of[LADDER_RESERVE],
        bond_slot=ledger.slot_of[BOND_RESERVE],
        series_keys=series_keys,
    )
