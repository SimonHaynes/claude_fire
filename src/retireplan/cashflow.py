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
from dataclasses import dataclass
from typing import Sequence

from .market import YearReturns
from .model import PensionAccess
from .plan import Plan, PlanYear, SlotMaps
from .portfolio import Portfolio
from .strategies import DrawdownContext, WithdrawalContext, credit_isa, isa_recipients
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
    """What the local authority met. Not a shortfall: nobody in England is
    left without essential care for lack of money, so this is a real outcome
    rather than a plan failure -- but it means the capital is gone, which is
    why it is reported rather than absorbed silently."""
    ufpls_tax_free_taken: float = 0.0
    """Tax-free cash generated this year by UFPLS withdrawals -- the 25%
    portion of every payment, until the Lump Sum Allowance runs out. See
    `pcls_taken` for the equivalent under `PensionAccess.PCLS`."""
    pension_lump_sum_taken: float = 0.0
    """Gross amount taken this year via `Scenario.pension_lump_sums` -- a
    one-off, dated, partial-crystallisation-style withdrawal, independent
    of the scenario's ongoing `pension_access` mode."""
    income_annuity_premium: float = 0.0
    """Gross amount drawn from a DC pension this year to buy a
    `Scenario.income_annuity` -- a one-off event, at most once per person,
    at first pension access."""
    income_annuity_income: float = 0.0
    """This year's guaranteed income from a previously-bought
    `Scenario.income_annuity`, already folded into taxable income and hence
    into `tax_paid` -- reported separately because it is guaranteed rather
    than drawn, unlike the rest of `gross_income`."""


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


def _dc_accessible(year: PlanYear, slots: SlotMaps, person: str) -> bool:
    """Whether `person` can draw the pension slots now keyed to them.

    An inherited pot is drawable at any age -- a beneficiary is not held to
    the deceased's access age, and is not held to their own either. Without
    the override a survivor would inherit a pension they could not touch for
    years, which is simply not the rule.
    """
    if person in slots.dc_accessible_override:
        return True
    return year.dc_accessible_by_person.get(person, False)


def _dead_year(plan: Plan, year: PlanYear, portfolio: Portfolio) -> YearResult:
    """A plan-year after the last death: no flows, balances frozen.

    Emitted rather than skipped so every trial has the same number of years
    and the simulation can still reduce fixed-size arrays across trials that
    ended at different times. `unmet_shortfall` is zero, so a household that
    no longer exists cannot fail to fund itself -- success then means "never
    failed while someone was alive", which is what it should always have
    meant.
    """
    balances = {plan.slot_names[s]: b for s, b in enumerate(portfolio.balances)}
    return YearResult(
        year=year.calendar_year, ages=year.ages, is_retired=True, alive=frozenset(),
        gross_income=0.0, tax_paid=0.0, ni_paid=0.0,
        essential_spending=0.0, discretionary_spending=0.0, nominal_discretionary=0.0,
        debt_payments=0.0, one_off_spending=0.0, gifts_given=0.0,
        isa_withdrawn=0.0, gia_withdrawn=0.0, dc_withdrawn_gross=0.0,
        dividend_tax_paid=0.0, cgt_paid=0.0, pcls_taken=0.0,
        net_cashflow=0.0, unmet_shortfall=0.0,
        balances=balances, total_wealth=sum(portfolio.balances),
    )



def _assessable_capital(person: str, plan: Plan, slots: SlotMaps, portfolio: Portfolio) -> float:
    """What a local authority would count as this person's own capital.

    Their ISA, GIA and pension, plus an equal share of the household cash.
    **The home is excluded entirely** -- it is disregarded while a spouse,
    partner or dependent relative still lives there, and this engine only
    charges care while someone is alive, so the disregard always applies. A
    household where nobody is left living in the home would see it assessed,
    which is exactly the case the will-trust structures in the
    `legal-and-trust-structuring` skill are designed for, and which this does
    not attempt to model.

    Pension pots are counted, which is the cautious reading: a local authority
    can take account of a pot that could be drawn, and treating it as
    invisible would flatter every result here.
    """
    owned = (
        slots.isa_slots_by_person.get(person, ())
        + slots.gia_slots_by_person.get(person, ())
        + slots.dc_slots_by_person.get(person, ())
    )
    people = len(slots.isa_slots_by_person) or 1
    return portfolio.sum_of(owned) + portfolio.balances[plan.cash_slot] / people


def _apply_care(
    year: PlanYear,
    alive: frozenset[str],
    care_needs: list,
    plan: Plan,
    slots: SlotMaps,
    portfolio: Portfolio,
    care_plan,
    annuity_bought: set[str],
) -> tuple[PlanYear, float, float]:
    """Charge this year's care, means-tested per person.

    Returns the adjusted year plus what the household paid and what the state
    met. Care is added to `one_off` rather than to `essential` so that no
    withdrawal rule can cut it and `CashBondLadder` does not size its bucket
    against it -- care can treble essential spending, and a ladder reading
    that would pull years of care fees into cash in exactly the worst years.
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
        if annuity is not None and annuity.enabled and need.person not in annuity_bought:
            # Bought once, at the point of entering care: converts an
            # open-ended liability into a known one-off, which is the whole
            # reason it protects an estate.
            premiums += annuity.premium(cost)
            annuity_bought.add(need.person)
        if annuity is not None and annuity.enabled:
            # The annuity pays the fees direct to the provider, tax-free.
            continue

        capital = _assessable_capital(need.person, plan, slots, portfolio)
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


def _invest_for_person(
    amount: float, person: str, portfolio: Portfolio, plan: Plan, slots: SlotMaps,
    tax: TaxSystem, isa_headroom_used: dict[str, float],
) -> None:
    """Route `amount` into an ISA -- `person`'s own first, then a spouse's
    if theirs is full (see `credit_isa`) -- then `person`'s own GIA for
    whatever is left, falling back to cash only if nobody in the household
    has an ISA and `person` has no GIA either. Shared by `_invest_surplus`
    (split across the household first) and anything that is unambiguously
    one person's money already -- a PCLS or a DB pension lump sum belongs to
    the person it came from, not the household in general, and has no more
    reason to sit idle in cash than ordinary income surplus does.
    """
    if amount <= 0:
        return
    remainder = credit_isa(amount, person, slots.isa_slots_by_person, tax, portfolio, isa_headroom_used)
    gia_slots = slots.gia_slots_by_person.get(person, ())
    if gia_slots and remainder > 0:
        portfolio.balances[gia_slots[0]] += remainder
        portfolio.cost_basis[gia_slots[0]] += remainder  # a fresh purchase: full basis
        remainder = 0.0
    if remainder > 0:
        portfolio.balances[plan.cash_slot] += remainder


def _invest_surplus(
    surplus: float, portfolio: Portfolio, plan: Plan, slots: SlotMaps, tax: TaxSystem,
    isa_headroom_used: dict[str, float],
) -> None:
    """Where leftover income actually goes, rather than sitting idle in cash.

    Split equally across the household's people, into each person's own ISA
    up to the annual subscription headroom, then their GIA for the rest --
    see `_invest_for_person`. This is a saving decision, independent of
    whichever `DrawdownStrategy` the scenario uses, and applies every year
    -- working or retired -- that income exceeds spending.
    """
    people = list(slots.gia_slots_by_person)
    if surplus <= 0:
        return
    if not people:
        portfolio.balances[plan.cash_slot] += surplus
        return
    share = surplus / len(people)
    for person in people:
        _invest_for_person(share, person, portfolio, plan, slots, tax, isa_headroom_used)


def _bed_and_isa(
    person: str, portfolio: Portfolio, plan: Plan, slots: SlotMaps, tax: TaxSystem,
    taxable_income: dict[str, float], isa_headroom_used: dict[str, float],
) -> float:
    """Progressively move `person`'s GIA balance into an ISA: sell just
    enough to net whatever ISA headroom is left across the household this
    plan-year -- `person`'s own first, a spouse's if theirs is full, after
    every other mechanism has already had first claim on it -- and
    subscribe the proceeds. A GIA has no reason to hold a balance
    indefinitely once ISA room exists to shelter it from CGT and dividend
    tax for good; this is the standard "Bed and ISA" move, run automatically
    every year rather than left for someone to remember to do by hand.

    Returns the CGT paid, so the caller can fold it into the year's tax
    bill -- selling to fund this is a real disposal, not a wash.
    """
    gia_slots = slots.gia_slots_by_person.get(person, ())
    if not gia_slots:
        return 0.0
    headroom = sum(
        max(0.0, tax.isa_annual_allowance - isa_headroom_used.get(recipient, 0.0))
        for recipient in isa_recipients(person, slots.isa_slots_by_person)
        if slots.isa_slots_by_person.get(recipient)
    )
    if headroom <= 0:
        return 0.0
    available = portfolio.sum_of(gia_slots)
    if available <= 0:
        return 0.0
    already = taxable_income.get(person, 0.0)
    basis_fraction = portfolio.basis_fraction_of(gia_slots)
    wanted_gross = tax.gia_gross_for_net(already, basis_fraction, headroom)
    gross = min(wanted_gross, available)
    if gross <= 0:
        return 0.0
    gain = gross * (1.0 - basis_fraction)
    cgt = tax.capital_gains_tax(gain, already)
    portfolio.draw_pro_rata(gia_slots, gross)
    net = gross - cgt
    credit_isa(net, person, slots.isa_slots_by_person, tax, portfolio, isa_headroom_used)
    return cgt


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
    annuity_bought: set[str] = set()
    second_death = max(deaths.values()) if deaths else plan.n_years

    portfolio = Portfolio(list(plan.opening_balances))
    # Lifetime tracker, not reset per year: the Lump Sum Allowance is a
    # lifetime limit, and PCLS, UFPLS and a one-off `PensionLumpSum` all
    # draw against the same one per person.
    tax_free_cash_taken: dict[str, float] = {name: 0.0 for name in plan.dc_slots_by_person}
    # Separate from the above: PCLS is a one-off event, gated on whether it
    # has *itself* already fired for this person, not on whether the
    # allowance has any use against it yet -- a `PensionLumpSum` taken
    # before access begins would otherwise be mistaken for "PCLS already
    # happened" and silently suppress it.
    pcls_fired: set[str] = set()
    # A `Scenario.income_annuity`, once bought for a person, keeps paying for
    # the rest of that person's life -- tracked here rather than recomputed,
    # since the benefit is fixed (subject only to its own escalation) at the
    # point of purchase, independent of how the market performs afterwards.
    income_annuity_state: dict[str, dict] = {}
    results: list[YearResult] = []

    for base_year in plan.years:
        i = base_year.index
        alive = frozenset(n for n, d in deaths.items() if i < d)
        if not alive:
            results.append(_dead_year(plan, base_year, portfolio))
            continue

        year = plan.year_variants[alive][i]
        slots = plan.slots_by_variant[alive]
        # Per-year, not per-plan: thresholds frozen in nominal terms shrink in
        # real ones, so the bands differ by year. `compile_plan` resolved this
        # once, since it does not depend on the market.
        tax = year.tax
        market = _returns_for(plan, path, year.index)
        # Fresh every plan-year: how much of each person's £20,000 ISA
        # allowance every ISA-crediting mechanism below has used so far.
        isa_headroom_used: dict[str, float] = {}

        # --- GIA dividend accrual, before growth touches the balance ----
        # Assumed yield on the balance coming *into* the year, taxed as
        # dividend income and reinvested (raises cost basis, not balance --
        # growth already carries the full total-return change). Positioned
        # against this year's precompiled taxable income only: any pension
        # drawn later this year is not yet known at this point in the loop.
        dividend_tax_paid = 0.0
        for person, gia_slots in slots.gia_slots_by_person.items():
            start_balance = portfolio.sum_of(gia_slots)
            if start_balance <= 0:
                continue
            dividend = start_balance * tax.gia_dividend_yield
            dividend_tax_paid += tax.dividend_tax(
                dividend, year.taxable_income_by_person.get(person, 0.0)
            )
            for slot in gia_slots:
                if portfolio.balances[slot] <= 0:
                    continue
                share = portfolio.balances[slot] / start_balance
                portfolio.cost_basis[slot] += dividend * share

        # --- growth, charges, maturities -------------------------------
        for slot, asset in enumerate(plan.assets):
            override = (
                scenario.allocation.real_return(asset, market, year.index)
                if scenario.allocation is not None
                else None
            )
            rate = override if override is not None else asset.returns.real_return(market, rng)
            balance = portfolio.balances[slot] * (1 + rate - asset.annual_charge_pct)
            portfolio.balances[slot] = max(0.0, balance - asset.flat_annual_fee)

        for from_slot, to_slot in year.maturities:
            if to_slot is not None:
                portfolio.balances[to_slot] += portfolio.balances[from_slot]
            else:
                portfolio.balances[plan.cash_slot] += portfolio.balances[from_slot]
            portfolio.balances[from_slot] = 0.0

        for slot, amount in year.contributions:
            portfolio.balances[slot] += amount
        for person, lump in year.lump_sums_by_person.items():
            _invest_for_person(lump, person, portfolio, plan, slots, tax, isa_headroom_used)

        # --- one-off, dated partial-crystallisation lump sums -----------
        # Independent of `pension_access`: "I want £50,000 of cash now"
        # without committing to crystallise the whole pot, or on top of an
        # ongoing UFPLS/PCLS mode. Split 25%/75% like a UFPLS payment,
        # sharing the same lifetime Lump Sum Allowance counter. Resolved
        # before any automatic PCLS-at-access event below, so an explicit
        # request is honoured in full rather than finding the allowance
        # already claimed by PCLS greedily taking the maximum available the
        # moment access begins, if both land in the same plan-year.
        lump_sum_this_year = 0.0
        for request in scenario.pension_lump_sums:
            if not (year.start <= request.on < year.end):
                continue
            dc = slots.dc_slots_by_person.get(request.person, ())
            if not dc or not _dc_accessible(year, slots, request.person):
                continue
            available = portfolio.sum_of(dc)
            if available <= 0:
                continue
            gross = min(request.amount, available)
            used = tax_free_cash_taken.get(request.person, 0.0)
            tax_free, taxable = tax.ufpls_split(gross, used)
            tax_free_cash_taken[request.person] = used + tax_free
            portfolio.draw_pro_rata(dc, gross)
            already = year.taxable_income_by_person.get(request.person, 0.0)
            tax_before = tax.income_tax(already)
            net = tax_free + taxable - (tax.income_tax(already + taxable) - tax_before)
            _invest_for_person(net, request.person, portfolio, plan, slots, tax, isa_headroom_used)
            lump_sum_this_year += gross
            # The taxable portion has to reach the year's real tax bill, or
            # this would be a lump sum with no tax on 75% of it.
            year = dataclasses.replace(
                year,
                taxable_other_by_person={
                    **year.taxable_other_by_person,
                    request.person: year.taxable_other_by_person.get(request.person, 0.0) + taxable,
                },
            )

        # --- tax-free lump sum, once per person at pension access ------
        pcls_this_year = 0.0
        if scenario.pension_access is PensionAccess.PCLS:
            for person, dc in slots.dc_slots_by_person.items():
                if not _dc_accessible(year, slots, person):
                    continue
                if person in pcls_fired or not dc:
                    continue
                pot = portfolio.sum_of(dc)
                lump = tax.pcls_available(pot, tax_free_cash_taken.get(person, 0.0))
                pcls_fired.add(person)
                if lump <= 0:
                    continue
                portfolio.draw_pro_rata(dc, lump)
                _invest_for_person(lump, person, portfolio, plan, slots, tax, isa_headroom_used)
                tax_free_cash_taken[person] = tax_free_cash_taken.get(person, 0.0) + lump
                pcls_this_year += lump

        # --- floor-and-upside annuity: bought once, at first access -----
        income_annuity = scenario.income_annuity
        annuity_premium_this_year = 0.0
        if income_annuity is not None and income_annuity.enabled:
            for person, dc in slots.dc_slots_by_person.items():
                if not dc or person in income_annuity_state:
                    continue
                if not _dc_accessible(year, slots, person):
                    continue
                pot = portfolio.sum_of(dc)
                premium = pot * income_annuity.fraction_of_pot
                if premium <= 0:
                    continue
                portfolio.draw_pro_rata(dc, premium)
                benefit = income_annuity.annual_benefit(premium)
                income_annuity_state[person] = {"benefit": benefit, "start_index": year.index}
                annuity_premium_this_year += premium

        # --- floor-and-upside annuity: this year's guaranteed income -----
        annuity_income_this_year = 0.0
        for person, state in income_annuity_state.items():
            if person not in alive:
                continue
            elapsed = year.index - state["start_index"]
            benefit = state["benefit"] * (1 + income_annuity.escalation) ** elapsed
            annuity_income_this_year += benefit
            year = dataclasses.replace(
                year,
                taxable_other_by_person={
                    **year.taxable_other_by_person,
                    person: year.taxable_other_by_person.get(person, 0.0) + benefit,
                },
            )

        # --- income and tax before any drawdown ------------------------
        taxable = year.taxable_income_by_person
        tax_paid = sum(tax.income_tax(v) for v in taxable.values()) + dividend_tax_paid
        ni_paid = sum(tax.national_insurance(v) for v in year.employment_income_by_person.values())
        net_income = (
            sum(taxable.values()) - tax_paid - ni_paid + year.tax_free_income
        )

        growth_return = market.get("global_equity", 0.0)
        bond_return = market.get("gov_bonds", 0.0)
        # --- care, means-tested per person -----------------------------
        # Sampled per trial, so it cannot be precompiled the way the rest of
        # the schedule is. Assessed on each person's OWN capital, which is how
        # the rule actually works and why who enters care first can matter
        # more to an estate than how much the household has.
        care_cost = 0.0
        care_state_funded = 0.0
        if care_needs:
            # The annuity premium is folded into the year's fixed spending
            # rather than drawn separately: it is a one-off cost the drawdown
            # order should cover exactly as it covers any other, and treating
            # it that way keeps a single path through the tax arithmetic.
            year, care_cost, care_state_funded = _apply_care(
                year, alive, care_needs, plan, slots, portfolio,
                scenario.care, annuity_bought,
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
                p: _dc_accessible(year, slots, p) for p in slots.dc_slots_by_person
            },
            is_retired=year.is_retired,
            essential_spend=year.essential,
            growth_return=growth_return,
            bond_return=bond_return,
            isa_headroom_used=isa_headroom_used,
            pension_access=scenario.pension_access,
            tax_free_cash_used=tax_free_cash_taken,
        )

        def shortfall_for(discretionary: float) -> float:
            """Would this much spending leave anything uncovered? (dry run)"""
            need = year.fixed_spend + discretionary - net_income
            if need <= 0:
                return 0.0
            return scenario.drawdown.resolve(need, portfolio.copy(), dict(taxable), draw_ctx).unmet

        # --- how much to spend -----------------------------------------
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
                    shortfall_for=shortfall_for,
                )
            )

        net_cashflow = net_income - (year.fixed_spend + discretionary)

        # --- settle the year -------------------------------------------
        if net_cashflow >= 0:
            _invest_surplus(net_cashflow, portfolio, plan, slots, tax, isa_headroom_used)
            draw = None
        else:
            draw = scenario.drawdown.resolve(-net_cashflow, portfolio, taxable, draw_ctx)
            # Pension withdrawals are income: re-price the year's tax bill.
            tax_paid = sum(tax.income_tax(v) for v in taxable.values()) + dividend_tax_paid + draw.cgt_paid

        scenario.drawdown.end_of_year(portfolio, taxable, draw_ctx)

        # --- Bed and ISA: move GIA money into the ISA wrapper while any -
        # allowance is still unclaimed, after every other mechanism above
        # has already had first claim on it this plan-year.
        bed_and_isa_cgt = sum(
            _bed_and_isa(person, portfolio, plan, slots, tax, taxable, isa_headroom_used)
            for person in slots.gia_slots_by_person
        )
        tax_paid += bed_and_isa_cgt

        results.append(
            YearResult(
                year=year.calendar_year,
                ages=year.ages,
                is_retired=year.is_retired,
                alive=alive,
                gross_income=sum(year.salary_gross_by_person.values())
                + sum(year.other_taxable_by_person.values())
                + year.tax_free_income,
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
