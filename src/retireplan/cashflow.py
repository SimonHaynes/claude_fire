"""The projection: run a compiled `Plan` forward through one path of returns.

Everything schedule-shaped was resolved in `compile_plan`, so this module does
only what genuinely depends on market outcomes: grow the balances, work out
what the household can afford, sell what it has to, and record the result.

Called once for a deterministic projection, or thousands of times by
`simulation.run_monte_carlo` with a different sampled path each time.
"""
from __future__ import annotations

import dataclasses
import random
from dataclasses import dataclass, field
from typing import Sequence

from .market import YearReturns
from .model import PensionAccess
from .plan import Plan, PlanYear, SlotMaps
from .portfolio import Portfolio
from .strategies import (
    DrawdownContext, WithdrawalContext, charge_cgt, credit_isa, isa_recipients,
)
from .tax import TaxSystem


@dataclass
class YearResult:
    year: int
    ages: dict[str, int]
    is_retired: bool
    alive: frozenset[str]
    """Who was living this year. Empty once the household has ended, which is
    how the statistics below know to exclude a year rather than count it as a
    year of zero spending."""
    gross_income: float
    employment_income: float
    """Salary before sacrifice, matching `gross_income`. The NI-able figure is
    lower; this is the one a client recognises as their pay."""
    state_pension_income: float
    db_income: float
    other_taxable_income: float
    """Rental and the like, plus `income_annuity_income` — an annuity is bought
    once and then paid like any other taxable income, so it lands here."""
    tax_free_income: float
    """`employment_income` through `tax_free_income` partition `gross_income`.
    Kept as five fields rather than one because a cash-flow chart has to show
    where a year's income came from, and the plan-year they were resolved from
    is not reachable from a `YearResult` alone."""
    tax_paid: float
    ni_paid: float
    essential_spending: float
    discretionary_spending: float
    nominal_discretionary: float
    debt_payments: float
    one_off_spending: float
    gifts_given: float
    isa_withdrawn: float
    gia_withdrawn: float
    dc_withdrawn_gross: float
    dividend_tax_paid: float
    cgt_paid: float
    pcls_taken: float
    """The one-off lump sum taken at first pension access, under
    `PensionAccess.PCLS`. Zero under `NONE` or `UFPLS` -- UFPLS's tax-free
    cash is reported year by year in `ufpls_tax_free_taken` instead, since
    it has no single crystallisation event to attribute it to."""
    net_cashflow: float
    """Income minus spending *before* any drawdown: negative means the
    portfolio had to make up the difference."""
    unmet_shortfall: float
    """What could not be funded even after selling everything accessible.
    Any year above zero is a plan failure."""
    balances: dict[str, float]
    total_wealth: float

    care_cost: float = 0.0
    """What the household actually paid towards care this year, after the
    means test."""
    care_state_funded: float = 0.0
    """What the local authority met. Not a shortfall — nobody in England goes
    without essential care for lack of money — but it means the capital is gone,
    so it is reported rather than absorbed silently."""
    ufpls_tax_free_taken: float = 0.0
    """The 25% tax-free portion of this year's UFPLS payments, until the Lump
    Sum Allowance runs out. `pcls_taken` is the `PensionAccess.PCLS` equivalent."""
    pension_lump_sum_taken: float = 0.0
    """Gross taken via `Scenario.pension_lump_sums`, independent of the
    scenario's ongoing `pension_access` mode."""
    income_annuity_premium: float = 0.0
    """Gross drawn from a DC pension to buy a `Scenario.income_annuity`: once
    per person, at first access."""
    income_annuity_income: float = 0.0
    """This year's guaranteed annuity income. Already inside `tax_paid` and
    `gross_income`; reported separately because it is guaranteed, not drawn."""


    @property
    def total_spending(self) -> float:
        return self.essential_spending + self.discretionary_spending


@dataclass
class Projection:
    plan: Plan
    years: list[YearResult]

    @property
    def succeeded(self) -> bool:
        return not any(y.unmet_shortfall > 0 for y in self.years)

    @property
    def first_shortfall_year(self) -> int | None:
        return next((y.year for y in self.years if y.unmet_shortfall > 0), None)

    @property
    def final_wealth(self) -> float:
        return self.years[-1].total_wealth if self.years else 0.0

    def balance_of(self, asset_name: str) -> list[float]:
        return [y.balances[asset_name] for y in self.years]


def _returns_for(plan: Plan, path: Sequence[YearReturns], i: int) -> YearReturns:
    base = path[i] if i < len(path) else path[-1]
    stress = plan.scenario.market_stress
    if i < len(stress):
        return {**base, **stress[i]}
    return base


def _dead_year(plan: Plan, year: PlanYear, portfolio: Portfolio) -> YearResult:
    """A plan-year after the last death: no flows, balances frozen.

    Emitted rather than skipped so every trial has the same number of years and
    the simulation can reduce fixed-size arrays across trials that ended at
    different times. `unmet_shortfall` is zero, so success means "never failed
    while someone was alive".
    """
    balances = {plan.slot_names[s]: b for s, b in enumerate(portfolio.balances)}
    return YearResult(
        year=year.calendar_year, ages=year.ages, is_retired=True, alive=frozenset(),
        gross_income=0.0, employment_income=0.0, state_pension_income=0.0,
        db_income=0.0, other_taxable_income=0.0, tax_free_income=0.0,
        tax_paid=0.0, ni_paid=0.0,
        essential_spending=0.0, discretionary_spending=0.0, nominal_discretionary=0.0,
        debt_payments=0.0, one_off_spending=0.0, gifts_given=0.0,
        isa_withdrawn=0.0, gia_withdrawn=0.0, dc_withdrawn_gross=0.0,
        dividend_tax_paid=0.0, cgt_paid=0.0, pcls_taken=0.0,
        net_cashflow=0.0, unmet_shortfall=0.0,
        balances=balances, total_wealth=sum(portfolio.balances),
    )



def _assessable_capital(person: str, accounts: _Accounts) -> float:
    """What a local authority would count as this person's own capital.

    Their ISA, GIA and pension, plus an equal share of the household cash. The
    home is excluded entirely: it is disregarded while a spouse, partner or
    dependent relative lives there, and care is only ever charged here while
    someone is alive. The case where nobody is left in the home is what the
    will-trust structures in `legal-and-trust-structuring` address, and is not
    modelled. Pension pots are counted — the cautious reading, since a local
    authority may take account of a pot that could be drawn.
    """
    owned = (
        accounts.slots.isa_slots_by_person.get(person, ())
        + accounts.slots.gia_slots_by_person.get(person, ())
        + accounts.slots.dc_slots_by_person.get(person, ())
    )
    people = len(accounts.slots.isa_slots_by_person) or 1
    return (
        accounts.portfolio.sum_of(owned)
        + accounts.portfolio.balances[accounts.plan.cash_slot] / people
    )


def _apply_care(
    accounts: _Accounts,
    year: PlanYear,
    alive: frozenset[str],
    care_needs: list,
    care_plan,
    annuity_bought: set[str],
) -> tuple[PlanYear, float, float]:
    """Charge this year's care, means-tested per person against their own
    capital — which is why who enters care first can matter more to an estate
    than how much the household has between them.

    Returns the adjusted year, what the household paid and what the state met.
    Care lands in `one_off` rather than `essential` so no withdrawal rule can
    cut it and `CashBondLadder` does not size its bucket against it: care can
    treble essential spending, and a ladder reading that would pull years of
    fees into cash in exactly the worst years.
    """
    if care_plan is None:
        return year, 0.0, 0.0

    household_pays = 0.0
    state_pays = 0.0
    premiums = 0.0
    offset = 0.0

    for need in care_needs:
        if need.person not in alive:
            continue
        age = year.ages.get(need.person)
        if age is None or not need.active_at(age):
            continue

        cost = care_plan.model.annual_cost
        annuity = care_plan.annuity
        if annuity is not None and annuity.enabled:
            if need.person not in annuity_bought:
                # Bought at the point of entering care, converting an open-ended
                # liability into a known one-off — the whole reason it protects
                # an estate.
                premiums += annuity.premium(cost)
                annuity_bought.add(need.person)
            continue  # the annuity pays the fees direct to the provider, tax-free

        capital = _assessable_capital(need.person, accounts)
        income = year.taxable_income_by_person.get(need.person, 0.0)
        mine, theirs = care_plan.means_test.contribution(cost, capital, income)
        household_pays += mine
        state_pays += theirs
        offset += care_plan.model.offsets_household_essential / max(1, len(alive))

    if not (household_pays or state_pays or premiums):
        return year, 0.0, 0.0

    adjusted = dataclasses.replace(
        year,
        one_off=year.one_off + household_pays + premiums,
        essential=year.essential * (1.0 - min(0.9, offset)),
        care_cost=household_pays,
    )
    return adjusted, household_pays, state_pays


@dataclass
class _Accounts:
    """The handles every money-moving step of a plan-year needs.

    Rebuilt each year, since `slots` and `tax` are year-variant and the ISA
    allowance is annual. `tax_free_cash_taken` is passed in instead, because
    the Lump Sum Allowance is a lifetime limit that PCLS, UFPLS and one-off
    lump sums all draw against.
    """

    plan: Plan
    slots: SlotMaps
    tax: TaxSystem
    portfolio: Portfolio
    tax_free_cash_taken: dict[str, float]
    crystallised: dict[str, float] = field(default_factory=dict)
    """How much of each person's DC pension is already in drawdown. Only
    uncrystallised funds carry a further tax-free entitlement, so this decides
    what a UFPLS may draw on and what a further crystallisation can relieve."""
    isa_headroom_used: dict[str, float] = field(default_factory=dict)
    cgt_exempt_used: dict[str, float] = field(default_factory=dict)

    def uncrystallised(self, person: str) -> float:
        dc = self.slots.dc_slots_by_person.get(person, ())
        return max(0.0, self.portfolio.sum_of(dc) - self.crystallised.get(person, 0.0))

    def invest_for(self, person: str, amount: float) -> None:
        """Shelter `amount` as `person`'s own money: their ISA first, a spouse's
        if theirs is full (see `credit_isa`), then their own GIA, and cash only
        if they have neither. A PCLS or a DB lump sum belongs to the person it
        came from, and has no more reason to sit idle in cash than surplus
        income does.
        """
        if amount <= 0:
            return
        remainder = credit_isa(
            amount, person, self.slots.isa_slots_by_person, self.tax,
            self.portfolio, self.isa_headroom_used,
        )
        gia_slots = self.slots.gia_slots_by_person.get(person, ())
        if gia_slots and remainder > 0:
            self.portfolio.balances[gia_slots[0]] += remainder
            self.portfolio.cost_basis[gia_slots[0]] += remainder  # fresh purchase: full basis
            remainder = 0.0
        if remainder > 0:
            self.portfolio.balances[self.plan.cash_slot] += remainder

    def invest_surplus(self, surplus: float) -> None:
        """Shelter leftover income, split equally across the household.

        A saving decision independent of the scenario's `DrawdownStrategy`,
        applied every year income exceeds spending, working or retired.
        """
        if surplus <= 0:
            return
        people = list(self.slots.gia_slots_by_person)
        if not people:
            self.portfolio.balances[self.plan.cash_slot] += surplus
            return
        for person in people:
            self.invest_for(person, surplus / len(people))

    def bed_and_isa(self, person: str, taxable_income: dict[str, float]) -> float:
        """Sell enough of `person`'s GIA to fill the household's remaining ISA
        headroom and subscribe the proceeds, sheltering it from CGT and dividend
        tax for good. Run every year, after every other mechanism has had first
        claim on the allowance.

        Returns the CGT paid: funding this is a real disposal, not a wash.
        """
        gia_slots = self.slots.gia_slots_by_person.get(person, ())
        if not gia_slots:
            return 0.0
        headroom = sum(
            max(0.0, self.tax.isa_annual_allowance - self.isa_headroom_used.get(recipient, 0.0))
            for recipient in isa_recipients(person, self.slots.isa_slots_by_person)
            if self.slots.isa_slots_by_person.get(recipient)
        )
        available = self.portfolio.sum_of(gia_slots)
        if headroom <= 0 or available <= 0:
            return 0.0
        already = taxable_income.get(person, 0.0)
        basis_fraction = self.portfolio.basis_fraction_of(gia_slots)
        exempt_used = self.cgt_exempt_used.get(person, 0.0)
        gross = min(
            self.tax.gia_gross_for_net(already, basis_fraction, headroom, exempt_used),
            available,
        )
        if gross <= 0:
            return 0.0
        cgt = charge_cgt(
            gross * (1.0 - basis_fraction), person, already, self.tax, self.cgt_exempt_used,
        )
        self.portfolio.draw_pro_rata(gia_slots, gross)
        credit_isa(
            gross - cgt, person, self.slots.isa_slots_by_person, self.tax,
            self.portfolio, self.isa_headroom_used,
        )
        return cgt

    def can_draw_pension(self, person: str, year: PlanYear) -> bool:
        """An inherited pot is drawable at any age: a beneficiary is held
        neither to the deceased's access age nor to their own.
        """
        return (
            person in self.slots.dc_accessible_override
            or year.dc_accessible_by_person.get(person, False)
        )


def _with_extra_taxable(year: PlanYear, person: str, amount: float) -> PlanYear:
    return dataclasses.replace(
        year,
        taxable_other_by_person={
            **year.taxable_other_by_person,
            person: year.taxable_other_by_person.get(person, 0.0) + amount,
        },
    )


def _accrue_gia_dividends(accounts: _Accounts, year: PlanYear) -> float:
    """Tax the assumed yield on each GIA's opening balance and reinvest it.

    Reinvestment raises cost basis rather than balance, since growth already
    carries the full total-return change. Stacked on this year's precompiled
    taxable income alone: any pension drawn later in the year is not yet known.
    """
    portfolio = accounts.portfolio
    tax_paid = 0.0
    for person, gia_slots in accounts.slots.gia_slots_by_person.items():
        opening = portfolio.sum_of(gia_slots)
        if opening <= 0:
            continue
        dividend = opening * accounts.tax.gia_dividend_yield
        tax_paid += accounts.tax.dividend_tax(
            dividend, year.taxable_income_by_person.get(person, 0.0)
        )
        for slot in gia_slots:
            if portfolio.balances[slot] > 0:
                portfolio.cost_basis[slot] += dividend * portfolio.balances[slot] / opening
    return tax_paid


def _grow_balances(
    accounts: _Accounts,
    allocation,
    market: YearReturns,
    year: PlanYear,
    rng: random.Random | None,
) -> None:
    before = {
        person: accounts.portfolio.sum_of(dc)
        for person, dc in accounts.slots.dc_slots_by_person.items()
    }
    for slot, asset in enumerate(accounts.plan.assets):
        override = (
            allocation.real_return(asset, market, year.index)
            if allocation is not None else None
        )
        rate = override if override is not None else asset.returns.real_return(market, rng)
        balance = accounts.portfolio.balances[slot] * (1 + rate - asset.annual_charge_pct)
        accounts.portfolio.balances[slot] = max(0.0, balance - asset.flat_annual_fee)

    # Crystallised funds stay invested, so the drawdown share of a pot has to
    # move with it — held as a value rather than a fraction because every other
    # mechanism here adds and removes cash amounts, not proportions.
    for person, opening in before.items():
        held = accounts.crystallised.get(person, 0.0)
        if held <= 0 or opening <= 0:
            continue
        closing = accounts.portfolio.sum_of(accounts.slots.dc_slots_by_person[person])
        accounts.crystallised[person] = min(held * closing / opening, closing)


def _settle_maturities(accounts: _Accounts, year: PlanYear) -> None:
    portfolio = accounts.portfolio
    for from_slot, to_slot in year.maturities:
        destination = to_slot if to_slot is not None else accounts.plan.cash_slot
        portfolio.balances[destination] += portfolio.balances[from_slot]
        portfolio.balances[from_slot] = 0.0


def _take_dated_lump_sums(
    accounts: _Accounts, requests, year: PlanYear
) -> tuple[PlanYear, float]:
    """Honour any `Scenario.pension_lump_sums` dated to this year.

    Independent of `pension_access`: cash now, without committing to
    crystallise the whole pot. Split 25/75 like a UFPLS payment and drawing on
    the same lifetime allowance. Resolved before the automatic PCLS below, so an
    explicit request is honoured in full rather than finding the allowance
    already claimed when both land in the same year.

    Returns the year with the taxable portion folded in — without that, 75% of
    the lump sum would escape tax — and the gross taken.
    """
    taken = 0.0
    for request in requests:
        if not (year.start <= request.on < year.end):
            continue
        dc = accounts.slots.dc_slots_by_person.get(request.person, ())
        if not dc or not accounts.can_draw_pension(request.person, year):
            continue
        # A 25/75 payment is a UFPLS, so it can only be met from funds that
        # have never been crystallised.
        gross = min(request.amount, accounts.uncrystallised(request.person))
        if gross <= 0:
            continue
        used = accounts.tax_free_cash_taken.get(request.person, 0.0)
        tax_free, taxable = accounts.tax.ufpls_split(gross, used)
        accounts.tax_free_cash_taken[request.person] = used + tax_free
        accounts.portfolio.draw_pro_rata(dc, gross)
        already = year.taxable_income_by_person.get(request.person, 0.0)
        tax_on_taxable = accounts.tax.income_tax(already + taxable) - accounts.tax.income_tax(already)
        accounts.invest_for(request.person, tax_free + taxable - tax_on_taxable)
        taken += gross
        year = _with_extra_taxable(year, request.person, taxable)
    return year, taken


def _take_pcls(accounts: _Accounts, year: PlanYear, already_fired: set[str]) -> float:
    """The one-off tax-free lump sum at each person's first pension access.

    `already_fired` gates on the PCLS event itself, not on the lifetime
    allowance: a dated lump sum taken before access would otherwise look like a
    PCLS that had already happened, and silently suppress it.
    """
    taken = 0.0
    for person, dc in accounts.slots.dc_slots_by_person.items():
        if person in already_fired or not dc:
            continue
        if not accounts.can_draw_pension(person, year):
            continue
        used = accounts.tax_free_cash_taken.get(person, 0.0)
        lump = accounts.tax.pcls_available(accounts.portfolio.sum_of(dc), used)
        already_fired.add(person)
        if lump <= 0:
            continue
        accounts.portfolio.draw_pro_rata(dc, lump)
        accounts.invest_for(person, lump)
        accounts.tax_free_cash_taken[person] = used + lump
        # The whole pot went through the crystallisation event, so what remains
        # is drawdown: no part of it carries a further tax-free entitlement.
        accounts.crystallised[person] = accounts.portfolio.sum_of(dc)
        taken += lump
    return taken


def _take_phased_tranche(accounts: _Accounts, year: PlanYear, tranche: float | None) -> float:
    """Crystallise a tranche for each person, sheltering the tax-free cash.

    The point of phasing is to harvest tax-free cash *ahead* of the taxable
    income it would otherwise be tied to: crystallise, shelter the 25%, and
    leave the 75% in drawdown to be drawn down over later years. Crystallising
    only what each withdrawal needs reduces exactly to UFPLS, which is why the
    tranche is a policy and not a consequence.

    `tranche` is the tax-free cash targeted per person per year; `None` sizes
    it to their remaining ISA subscription room, so the cash lands somewhere
    that shelters it rather than in a GIA paying dividend tax for a decade.
    """
    released = 0.0
    for person, dc in accounts.slots.dc_slots_by_person.items():
        if not dc or not accounts.can_draw_pension(person, year):
            continue
        want = tranche if tranche is not None else max(
            0.0,
            accounts.tax.isa_annual_allowance
            - accounts.isa_headroom_used.get(person, 0.0),
        )
        if want <= 0:
            continue
        used = accounts.tax_free_cash_taken.get(person, 0.0)
        headroom = max(0.0, accounts.tax.lump_sum_allowance - used)
        fraction = accounts.tax.pcls_fraction
        size = min(want / fraction, accounts.uncrystallised(person))
        tax_free = min(size * fraction, headroom)
        if tax_free <= 0:
            continue
        accounts.portfolio.draw_pro_rata(dc, tax_free)
        accounts.invest_for(person, tax_free)
        accounts.tax_free_cash_taken[person] = used + tax_free
        accounts.crystallised[person] = accounts.crystallised.get(person, 0.0) + size - tax_free
        released += tax_free
    return released


def _buy_income_annuity(
    accounts: _Accounts, annuity, year: PlanYear, bought: dict[str, dict]
) -> float:
    """Convert a fraction of each pot into guaranteed income, once, at first
    access. Returns the premium paid; `bought` records the benefit, which is
    fixed from that point however the market performs afterwards.
    """
    premiums = 0.0
    for person, dc in accounts.slots.dc_slots_by_person.items():
        if not dc or person in bought:
            continue
        if not accounts.can_draw_pension(person, year):
            continue
        premium = accounts.portfolio.sum_of(dc) * annuity.fraction_of_pot
        if premium <= 0:
            continue
        accounts.portfolio.draw_pro_rata(dc, premium)
        bought[person] = {"benefit": annuity.annual_benefit(premium), "start_index": year.index}
        premiums += premium
    return premiums


def _annuity_income(
    annuity, bought: dict[str, dict], year: PlanYear, alive: frozenset[str]
) -> tuple[PlanYear, float]:
    """This year's guaranteed annuity income, folded into taxable income."""
    total = 0.0
    for person, state in bought.items():
        if person not in alive:
            continue
        elapsed = year.index - state["start_index"]
        benefit = state["benefit"] * (1 + annuity.escalation) ** elapsed
        total += benefit
        year = _with_extra_taxable(year, person, benefit)
    return year, total


def project(
    plan: Plan,
    path: Sequence[YearReturns],
    rng: random.Random | None = None,
    deaths: dict[str, int] | None = None,
    care_needs: list | None = None,
) -> Projection:
    """Run `plan` through one path of annual real returns.

    `rng` is passed to each asset's return model, letting models with
    idiosyncratic risk (a concentrated bond ladder, say) draw actual outcomes
    rather than their average. Omit it for a readable deterministic run.

    `deaths` maps a person to the plan-year index from which they are no
    longer alive, overriding the plan's own schedule. Stochastic mortality
    passes a different one per trial; omit it for the plan's assumption.

    Once nobody is left, the remaining years are emitted with every flow zero
    and balances frozen. Keeping `len(projection.years) == plan.n_years` is
    what lets the simulation reduce fixed-size arrays across trials that end
    at different times.
    """
    scenario = plan.scenario
    scenario.reset_strategies()

    deaths = deaths if deaths is not None else plan.death_index_by_person
    care_needs = care_needs or []
    care_annuity_bought: set[str] = set()
    second_death = max(deaths.values()) if deaths else plan.n_years

    portfolio = Portfolio(list(plan.opening_balances))
    dc_slots = {s for slots in plan.dc_slots_by_person.values() for s in slots}
    bridge_slots = tuple(s for s in plan.investable_slots if s not in dc_slots)
    # Pension access is age-driven, so the base variant dates it for every
    # variant; a survivor who inherits an already-accessible pot only ever
    # gains access earlier, which `year.dc_accessible` reports directly.
    access_index = next((y.index for y in plan.years if y.dc_accessible), plan.n_years)
    tax_free_cash_taken: dict[str, float] = {name: 0.0 for name in plan.dc_slots_by_person}
    crystallised: dict[str, float] = {name: 0.0 for name in plan.dc_slots_by_person}
    pcls_fired: set[str] = set()
    annuities_bought: dict[str, dict] = {}
    results: list[YearResult] = []

    for base_year in plan.years:
        i = base_year.index
        alive = frozenset(n for n, d in deaths.items() if i < d)
        if not alive:
            results.append(_dead_year(plan, base_year, portfolio))
            continue

        year = plan.year_variants[alive][i]
        slots = plan.slots_by_variant[alive]
        accounts = _Accounts(
            plan=plan,
            slots=slots,
            tax=year.tax,
            portfolio=portfolio,
            tax_free_cash_taken=tax_free_cash_taken,
            crystallised=crystallised,
        )
        tax = year.tax
        market = _returns_for(plan, path, year.index)

        dividend_tax_paid = _accrue_gia_dividends(accounts, year)
        _grow_balances(accounts, scenario.allocation, market, year, rng)
        _settle_maturities(accounts, year)
        for _owner, slot, amount in year.contributions:
            portfolio.balances[slot] += amount
        for person, lump in year.lump_sums_by_person.items():
            accounts.invest_for(person, lump)

        year, lump_sum_this_year = _take_dated_lump_sums(
            accounts, scenario.pension_lump_sums, year
        )
        if scenario.pension_access is PensionAccess.PCLS:
            pcls_this_year = _take_pcls(accounts, year, pcls_fired)
        elif scenario.pension_access is PensionAccess.PHASED:
            pcls_this_year = _take_phased_tranche(accounts, year, scenario.phased_tranche)
        else:
            pcls_this_year = 0.0

        income_annuity = scenario.income_annuity
        annuity_premium_this_year = 0.0
        annuity_income_this_year = 0.0
        if income_annuity is not None and income_annuity.enabled:
            annuity_premium_this_year = _buy_income_annuity(
                accounts, income_annuity, year, annuities_bought
            )
            year, annuity_income_this_year = _annuity_income(
                income_annuity, annuities_bought, year, alive
            )

        taxable = year.taxable_income_by_person
        tax_paid = sum(tax.income_tax(v) for v in taxable.values()) + dividend_tax_paid
        ni_paid = sum(tax.national_insurance(v) for v in year.employment_income_by_person.values())
        net_income = year.net_income - dividend_tax_paid

        growth_return = market.get("global_equity", 0.0)
        bond_return = market.get("gov_bonds", 0.0)
        years_to_access = 0 if year.dc_accessible else max(0, access_index - i)

        care_cost = 0.0
        care_state_funded = 0.0
        if care_needs:
            year, care_cost, care_state_funded = _apply_care(
                accounts, year, alive, care_needs, scenario.care, care_annuity_bought,
            )

        draw_ctx = DrawdownContext(
            tax=tax,
            isa_slots=plan.isa_slots,
            isa_slots_by_person=slots.isa_slots_by_person,
            dc_slots_by_person=slots.dc_slots_by_person,
            gia_slots_by_person=slots.gia_slots_by_person,
            cash_slot=plan.cash_slot,
            ladder_slot=plan.ladder_slot,
            bond_slot=plan.bond_slot,
            dc_accessible_by_person={
                p: accounts.can_draw_pension(p, year) for p in slots.dc_slots_by_person
            },
            is_retired=year.is_retired,
            years_to_access=years_to_access,
            essential_spend=year.essential,
            growth_return=growth_return,
            bond_return=bond_return,
            isa_headroom_used=accounts.isa_headroom_used,
            cgt_exempt_used=accounts.cgt_exempt_used,
            pension_access=scenario.pension_access,
            tax_free_cash_used=tax_free_cash_taken,
            crystallised=crystallised,
        )

        def shortfall_for(discretionary: float) -> float:
            """Would this much spending leave anything uncovered? (dry run)"""
            need = year.fixed_spend + discretionary - net_income
            if need <= 0:
                return 0.0
            # `for_dry_run` matters as much as the portfolio copy: a probe also
            # consumes Lump Sum Allowance, ISA headroom and crystallisation
            # state, and `VariablePercentage` probes inside a bisection loop.
            return scenario.drawdown.resolve(
                need, portfolio.copy(), dict(taxable), draw_ctx.for_dry_run()
            ).unmet

        if scenario.withdrawal is None:
            discretionary = year.nominal_discretionary
        else:
            discretionary = scenario.withdrawal.decide(
                WithdrawalContext(
                    year_index=year.index,
                    is_retired=year.is_retired,
                    dc_accessible=year.dc_accessible,
                    nominal_discretionary=year.nominal_discretionary,
                    fixed_spend=year.fixed_spend,
                    net_income=net_income,
                    portfolio_value=portfolio.sum_of(plan.investable_slots),
                    growth_return=growth_return,
                    # Over the living only: a spend rate escalating off a
                    # dead person's age would keep rising after they died.
                    oldest_age=max(
                        (a for n, a in year.ages.items() if n in alive), default=0
                    ),
                    years_remaining=second_death - i,
                    bridge_value=portfolio.sum_of(bridge_slots),
                    years_to_access=years_to_access,
                    shortfall_for=shortfall_for,
                )
            )

        net_cashflow = net_income - (year.fixed_spend + discretionary)

        if net_cashflow >= 0:
            accounts.invest_surplus(net_cashflow)
            draw = None
        else:
            draw = scenario.drawdown.resolve(-net_cashflow, portfolio, taxable, draw_ctx)
            # Pension withdrawals are income: re-price the year's tax bill.
            tax_paid = sum(tax.income_tax(v) for v in taxable.values()) + dividend_tax_paid + draw.cgt_paid

        scenario.drawdown.end_of_year(portfolio, taxable, draw_ctx)

        bed_and_isa_cgt = sum(
            accounts.bed_and_isa(person, taxable)
            for person in slots.gia_slots_by_person
        )
        tax_paid += bed_and_isa_cgt

        employment = sum(year.salary_gross_by_person.values())
        state_pension = sum(year.state_pension_by_person.values())
        db = sum(year.db_income_by_person.values())
        other_taxable = sum(year.taxable_other_by_person.values())

        results.append(
            YearResult(
                year=year.calendar_year,
                ages=year.ages,
                is_retired=year.is_retired,
                alive=alive,
                gross_income=employment + state_pension + db + other_taxable
                + year.tax_free_income,
                employment_income=employment,
                state_pension_income=state_pension,
                db_income=db,
                other_taxable_income=other_taxable,
                tax_free_income=year.tax_free_income,
                tax_paid=tax_paid,
                ni_paid=ni_paid,
                essential_spending=year.essential + year.care_cost,
                discretionary_spending=discretionary,
                nominal_discretionary=year.nominal_discretionary,
                debt_payments=year.debt_payment,
                one_off_spending=year.one_off,
                gifts_given=year.gifts,
                isa_withdrawn=draw.isa_withdrawn if draw else 0.0,
                gia_withdrawn=draw.gia_withdrawn if draw else 0.0,
                dc_withdrawn_gross=draw.dc_withdrawn_gross if draw else 0.0,
                dividend_tax_paid=dividend_tax_paid,
                cgt_paid=(draw.cgt_paid if draw else 0.0) + bed_and_isa_cgt,
                care_cost=care_cost,
                care_state_funded=care_state_funded,
                pcls_taken=pcls_this_year,
                ufpls_tax_free_taken=draw.ufpls_tax_free if draw else 0.0,
                pension_lump_sum_taken=lump_sum_this_year,
                income_annuity_premium=annuity_premium_this_year,
                income_annuity_income=annuity_income_this_year,
                net_cashflow=net_cashflow,
                unmet_shortfall=draw.unmet if draw else 0.0,
                balances=dict(zip(plan.slot_names, portfolio.balances)),
                total_wealth=portfolio.total,
            )
        )

    return Projection(plan=plan, years=results)
