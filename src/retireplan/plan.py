"""Compiling a household + scenario into a `Plan`.

Everything that does *not* depend on market returns — who is working, what
they earn, what tax band that puts them in, what the household spends, when
debts clear, when a bond matures, when a pension unlocks — is computed once,
here, into a list of `PlanYear` records.

That is the difference between a Monte Carlo run that takes a minute and one
that takes ten seconds: a 2,000-trial simulation used to redo every date
comparison and expense lookup 2,000 times over. Only balances actually vary
between trials, so only balances belong in the hot loop.
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
    IncomeType,
    Phase,
)
from .mortality import FixedAge
from .scenario import Scenario
from .tax import TaxSystem
from .timeline import add_years, age_on, debt_payment_schedule, earliest, months_remaining, overlap_fraction

CASH_RESERVE = "__cash_reserve"
LADDER_RESERVE = "__ladder_reserve"
SURPLUS_GIA_NAME = "{name} — Surplus GIA (Global Tracker)"
SURPLUS_ISA_NAME = "{name} — Surplus ISA (Global Tracker)"


def _annual(amount: float, frequency: Frequency) -> float:
    return amount * 12 if frequency is Frequency.MONTHLY else amount


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
    """This year's tax system, not the household's.

    Thresholds frozen in nominal terms shrink in real ones, so the bands a
    projection faces in 2050 are not the bands it faces today. Resolving that
    here rather than in `cashflow` keeps it market-independent -- it is the
    same for every trial -- and means fiscal drag reaches income tax, NI, the
    pension gross-up, CGT, dividend tax, the ISA allowance and the PCLS cap
    without a single strategy having to know about it."""

    alive: frozenset[str]
    """Who is still living this plan-year.

    Deaths only ever remove people, so `compile_plan` precomputes one year
    tuple per alive-set rather than adjusting per trial -- see
    `Plan.year_variants`."""

    salary_gross_by_person: dict[str, float]     # before salary sacrifice (reporting only)
    employment_income_by_person: dict[str, float]  # after sacrifice: the NI-able figure

    # Taxable income kept in three buckets rather than one, because they
    # behave differently when someone dies: a State Pension stops outright and
    # does not transfer, a DB pension usually continues to the survivor at a
    # reduced rate, and rental or other unearned income passes whole under the
    # spouse exemption. Summed together they were indistinguishable, and a
    # first-death model would have halved rental income by accident.
    db_income_by_person: dict[str, float]
    state_pension_by_person: dict[str, float]
    taxable_other_by_person: dict[str, float]

    tax_free_income_by_person: dict[str, float]
    """Per person, not a household total: a tax-free income belonging to
    someone who has died must stop being paid to a household that no longer
    contains them."""

    contributions: tuple[tuple[int, float], ...]   # (asset slot, amount into it this year)
    lump_sums_by_person: dict[str, float]
    """DB pension lump sums (e.g. a Teachers' Pension retirement lump sum),
    by whose entitlement it is. Invested for that person (ISA then GIA), not
    pooled into shared cash -- see `cashflow.py`'s `_invest_for_person`."""
    maturities: tuple[tuple[int, int | None], ...]  # (from slot, rollover-to slot or None)

    essential: float
    nominal_discretionary: float

    debt_payment: float
    one_off: float
    gifts: float

    care_cost: float = 0.0
    """Set per trial by `project`, not at compile time: whether care happens
    is sampled, so it cannot be precomputed the way the rest of the schedule
    is. Held apart from `essential` on purpose -- it is fixed spending no
    withdrawal rule may cut, but a cash ladder must not size against it."""

    @property
    def fixed_spend(self) -> float:
        """Spending a withdrawal strategy is not allowed to cut."""
        return (
            self.essential + self.care_cost
            + self.debt_payment + self.one_off + self.gifts
        )

    @property
    def other_taxable_by_person(self) -> dict[str, float]:
        """DB pension, State Pension and other taxable income, recombined.

        The three are stored separately because they behave differently on a
        death; everything downstream that only needs the total reads it here.
        """
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
    series_keys: frozenset[str]

    year_variants: dict[frozenset[str], tuple[PlanYear, ...]]
    """One full year schedule per alive-set.

    Deaths only remove people, so for a couple there are three schedules worth
    having (both, one, the other) plus the empty one -- built once here rather
    than adjusted on every trial. `project` then picks a year with a dict
    lookup and an index, which keeps the compile-once/run-many split intact
    instead of pushing per-year work back into the hot loop."""

    slots_by_variant: dict[frozenset[str], "SlotMaps"]
    """Pot ownership per alive-set, with a dead person's pensions, ISAs and
    GIAs re-keyed to the survivor.

    Without this a drawdown strategy keeps drawing from the deceased's pension
    and stacking it against *their* tax bands -- reusing a personal allowance
    and a basic-rate band that no longer exist, every year, invisibly."""

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


#: Beyond this many people the alive-set variants (2^n) stop being cheap.
#: Two is the case this exists for; the guard is here so a larger household
#: fails loudly rather than quietly building 64 schedules.
MAX_PEOPLE_FOR_VARIANTS = 4


def _survivor_year(year: PlanYear, alive: frozenset[str], assumptions) -> PlanYear:
    """`year` as it would be with only `alive` still living.

    The dead person's salary and State Pension stop outright -- a State
    Pension does not transfer. Their DB pension continues to the survivor at
    `db_survivor_fraction`, and their rental and tax-free income pass whole
    under the spouse exemption. All of it is re-keyed to a survivor's name
    rather than left under the deceased's, because income sitting under a dead
    person's name would keep drawing on a personal allowance and a basic-rate
    band that no longer exist.

    Spending falls, but not by half: see `Assumptions.survivor_*_factor`.
    Debt payments, one-offs and gifts do not fall at all.
    """
    dead = set(year.alive) - set(alive)
    if not dead:
        return year
    if not alive:
        # Nobody left: no income, no spending. The estate is settled elsewhere.
        return dataclasses.replace(
            year, alive=alive,
            salary_gross_by_person={}, employment_income_by_person={},
            db_income_by_person={}, state_pension_by_person={},
            taxable_other_by_person={}, tax_free_income_by_person={},
            contributions=(), lump_sums_by_person={},
            essential=0.0, nominal_discretionary=0.0, debt_payment=0.0,
            one_off=0.0, gifts=0.0,
        )

    # Whoever inherits. With one survivor this is unambiguous; with more, the
    # eldest simply keeps the bookkeeping deterministic -- the tax difference
    # between recipients is a refinement this does not attempt.
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

    # --- ledger layout -----------------------------------------------------
    spendable = [a for a in household.assets if a.type is not AssetType.DB_PENSION]

    # A synthetic ISA per person who does not already have an explicit one --
    # unlike the GIA below, an ISA is not added unconditionally, because it
    # has a real annual subscription limit and a household that already
    # models one should not gain a second, mostly-dead slot alongside it.
    # Without this, a household intake built with no ISA `Asset` (because the
    # client currently holds none) has nowhere for surplus income, a PCLS, or
    # Bed-and-ISA to ever shelter money -- not a modelling choice, a silent
    # gap: `credit_isa` and `_bed_and_isa` both no-op with zero ISA headroom
    # rather than erroring, so the money just sits in the GIA, taxed, for the
    # whole plan. Not currently holding an ISA is a fact about the client's
    # past, not a ceiling on what the plan can consider -- anyone can open
    # one, so the engine now always makes it possible to.
    people_with_isa = {a.owner for a in household.assets_of(AssetType.ISA)}
    surplus_isa = [
        Asset(SURPLUS_ISA_NAME.format(name=name), AssetType.ISA, name, 0.0,
              returns=SampledSeries("global_equity"))
        for name in people
        if name not in people_with_isa
    ]
    spendable = spendable + surplus_isa

    # A synthetic GIA per person, present whether or not the household has an
    # explicit one, so surplus income above ISA headroom always has somewhere
    # to go instead of sitting idle in cash -- see `SURPLUS_GIA_NAME` and
    # `project()`'s surplus-sweep. Opens at zero: it is funded only by future
    # surplus, never backdated.
    surplus_gia = [
        Asset(SURPLUS_GIA_NAME.format(name=name), AssetType.GIA, name, 0.0,
              returns=SampledSeries("global_equity"))
        for name in people
    ]
    spendable = spendable + surplus_gia

    slot_names = [a.name for a in spendable] + [CASH_RESERVE, LADDER_RESERVE]
    slot_of = {name: i for i, name in enumerate(slot_names)}
    opening = [a.value for a in spendable] + [0.0, 0.0]

    isa_slots = tuple(slot_of[a.name] for a in spendable if a.type is AssetType.ISA)
    isa_slots_by_person: dict[str, tuple[int, ...]] = {
        name: tuple(slot_of[a.name] for a in spendable if a.type is AssetType.ISA and a.owner == name)
        for name in people
    }
    dc_slots: dict[str, tuple[int, ...]] = {
        name: tuple(
            slot_of[a.name]
            for a in spendable
            if a.type is AssetType.DC_PENSION and a.owner == name
        )
        for name in people
    }
    gia_slots_by_person: dict[str, tuple[int, ...]] = {
        name: tuple(slot_of[a.name] for a in spendable if a.type is AssetType.GIA and a.owner == name)
        for name in people
    }
    investable = tuple(
        sorted(
            {slot_of[CASH_RESERVE], slot_of[LADDER_RESERVE]}
            | set(isa_slots)
            | {s for slots in dc_slots.values() for s in slots}
            | {s for slots in gia_slots_by_person.values() for s in slots}
            | {slot_of[a.name] for a in spendable if a.type is AssetType.CASH}
        )
    )

    series_keys = frozenset({"inflation"}).union(
        *(a.returns.series_keys() for a in spendable)
    ) if spendable else frozenset({"inflation"})
    series_keys |= scenario.series_keys()

    # --- horizon -----------------------------------------------------------
    # With mortality sampled, the horizon has to cover the oldest age anyone
    # could reach, not the age they are expected to reach -- every trial runs
    # the full length with the estate frozen after the second death, which is
    # what keeps percentile bands well-defined across trials of different
    # actual lengths. With `FixedAge` the horizon is unchanged.
    horizon_age = (
        assumptions.life_expectancy_age
        if isinstance(assumptions.mortality, FixedAge)
        else assumptions.max_age
    )
    last_index = 0
    for p in people.values():
        end_of_life = add_years(p.date_of_birth, horizon_age)
        last_index = max(last_index, (end_of_life - as_of).days // 365)

    debt_by_index: dict[int, float] = {}
    for debt in household.debts:
        remaining = (
            debt.remaining_months if debt.remaining_months is not None
            else months_remaining(as_of, debt.last_payment)
        )
        for i, amount in enumerate(debt_payment_schedule(debt.monthly_payment, remaining)):
            debt_by_index[i] = debt_by_index.get(i, 0.0) + amount

    db_assets = household.assets_of(AssetType.DB_PENSION)

    drag = assumptions.fiscal_drag
    tax_by_index = _tax_by_year(tax, drag, as_of, last_index)
    everyone = frozenset(people)

    years: list[PlanYear] = []
    for i in range(last_index + 1):
        start = as_of if i == 0 else add_years(as_of, i)
        end = add_years(as_of, i + 1)
        is_retired = household_retirement is not None and start >= household_retirement

        salary_gross: dict[str, float] = {}
        employment_income: dict[str, float] = {}
        taxable_other: dict[str, float] = {}
        db_income: dict[str, float] = {}
        state_pension: dict[str, float] = {}
        tax_free: dict[str, float] = {}
        contributions: dict[int, float] = {}

        # --- income, and the contributions that ride on it ---
        for income in household.incomes:
            stop = retirement.get(income.owner) if income.stops_at_retirement else None
            fraction = overlap_fraction(start, end, income.start, earliest(income.end, stop))
            if fraction <= 0:
                continue
            amount = _annual(income.amount, income.frequency)
            amount *= (1 + income.annual_real_growth) ** i
            amount *= fraction

            if income.type is IncomeType.TAX_FREE:
                tax_free[income.owner] = tax_free.get(income.owner, 0.0) + amount
                continue
            if income.type is IncomeType.TAXABLE:
                taxable_other[income.owner] = taxable_other.get(income.owner, 0.0) + amount
                continue

            # SALARY: pension contributions are paid only while it is being earned
            salary_gross[income.owner] = salary_gross.get(income.owner, 0.0) + amount
            sacrificed = 0.0
            for asset in spendable:
                if asset.contributions is None or asset.owner != income.owner:
                    continue
                employee = asset.contributions.employee_monthly * 12 * fraction
                employer = asset.contributions.employer_monthly * 12 * fraction
                slot = slot_of[asset.name]
                contributions[slot] = contributions.get(slot, 0.0) + employee + employer
                sacrificed += employee
            employment_income[income.owner] = (
                employment_income.get(income.owner, 0.0) + amount - sacrificed
            )

        # --- defined benefit entitlements ---
        lump_sums: dict[str, float] = {}
        for asset in db_assets:
            db = asset.defined_benefit
            assert db is not None  # guaranteed by Asset.__post_init__
            db_start = add_years(people[asset.owner].date_of_birth, db.start_age)
            fraction = overlap_fraction(start, end, db_start, None)
            if fraction > 0:
                db_income[asset.owner] = (
                    db_income.get(asset.owner, 0.0) + db.annual_amount * fraction
                )
            if db.lump_sum and start <= db_start < end:
                lump_sums[asset.owner] = lump_sums.get(asset.owner, 0.0) + db.lump_sum

        # --- state pension ---
        for name, person in people.items():
            fraction = overlap_fraction(start, end, state_pension_date[name], None)
            if fraction > 0 and person.full_state_pension:
                state_pension[name] = (
                    state_pension.get(name, 0.0) + assumptions.state_pension_annual * fraction
                )

        # --- spending ---
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

        one_off = sum(
            item.amount for item in scenario.one_off_spends if start <= item.on < end
        )
        gifts = sum(g.amount for g in scenario.gifts if start <= g.on < end)

        maturities = tuple(
            (
                slot_of[a.name],
                slot_of[a.maturity.rollover_to] if a.maturity.rollover_to else None,
            )
            for a in spendable
            if a.maturity is not None and start <= a.maturity.on < end
        )

        years.append(
            PlanYear(
                index=i,
                calendar_year=start.year,
                start=start,
                end=end,
                ages={name: age_on(p.date_of_birth, start) for name, p in people.items()},
                is_retired=is_retired,
                # `end > access_date`, not `start >= access_date`: access begins in
                # the plan-year the birthday falls in, not the next one. The engine
                # has no finer resolution than a plan-year, so this can grant access
                # a few months before the exact day for a birthday early in the
                # year -- the alternative (the previous behaviour) silently denied
                # it for up to eleven months after the birthday, which is worse.
                dc_accessible=any(end > access_date[n] for n in people),
                dc_accessible_by_person={n: end > access_date[n] for n in people},
                tax=tax_by_index[i],
                alive=everyone,
                salary_gross_by_person=salary_gross,
                employment_income_by_person=employment_income,
                db_income_by_person=db_income,
                state_pension_by_person=state_pension,
                taxable_other_by_person=taxable_other,
                tax_free_income_by_person=tax_free,
                contributions=tuple(sorted(contributions.items())),
                lump_sums_by_person=lump_sums,
                maturities=maturities,
                essential=essential,
                nominal_discretionary=discretionary,
                debt_payment=debt_by_index.get(i, 0.0),
                one_off=one_off,
                gifts=gifts,
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
        alive: _slots_for(alive, isa_slots_by_person, dc_slots, gia_slots_by_person)
        for alive in _alive_sets(everyone)
    }

    death_index_by_person = {}
    for name, person in people.items():
        age = (scenario.death_ages or {}).get(name, assumptions.life_expectancy_age)
        death = add_years(person.date_of_birth, age)
        # The plan-year the death falls in is the last one they are alive for,
        # the same plan-year resolution the rest of the engine works at.
        # Floored at 1 to match the horizon, which is floored at index 0: a
        # household already past its stated life expectancy still gets the one
        # year the plan runs for, rather than being dead before it starts.
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
        slot_names=tuple(slot_names),
        assets=tuple(spendable),
        opening_balances=tuple(opening),
        isa_slots=isa_slots,
        isa_slots_by_person=isa_slots_by_person,
        dc_slots_by_person=dc_slots,
        gia_slots_by_person=gia_slots_by_person,
        investable_slots=investable,
        cash_slot=slot_of[CASH_RESERVE],
        ladder_slot=slot_of[LADDER_RESERVE],
        series_keys=series_keys,
    )
