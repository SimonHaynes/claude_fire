"""The projection engine: schedule compilation and the year-by-year mechanics."""
from __future__ import annotations

from datetime import date

import pytest

from retireplan import (
    Asset,
    AssetType,
    Assumptions,
    Contribution,
    Debt,
    DefinedBenefit,
    Expense,
    ExpenseCategory,
    FixedNominal,
    FixedReal,
    Frequency,
    Household,
    IncomeSource,
    IncomeType,
    MarketData,
    Maturity,
    OneOffSpend,
    Person,
    Phase,
    SampledSeries,
    Scenario,
    SpendNominal,
    compile_plan,
    project,
)
from retireplan.tax.uk import UK
from retireplan.timeline import add_years, debt_payment_schedule, months_remaining, overlap_fraction

AS_OF = date(2026, 1, 1)


def run(household, scenario, market, as_of=AS_OF):
    plan = compile_plan(household, scenario, UK, as_of)
    path = [market.by_year[2020]] * plan.n_years
    return project(plan, path)


class TestTimeline:
    def test_add_years_handles_29_february(self):
        assert add_years(date(2024, 2, 29), 1) == date(2025, 2, 28)

    def test_overlap_fraction_full_and_empty(self):
        start, end = date(2026, 1, 1), date(2027, 1, 1)
        assert overlap_fraction(start, end, None, None) == 1.0
        assert overlap_fraction(start, end, date(2030, 1, 1), None) == 0.0

    def test_overlap_fraction_is_partial_for_a_mid_year_stop(self):
        start, end = date(2026, 1, 1), date(2027, 1, 1)
        fraction = overlap_fraction(start, end, None, date(2026, 7, 2))
        assert fraction == pytest.approx(0.5, abs=0.01)

    def test_debt_schedule_splits_into_plan_years(self):
        assert debt_payment_schedule(100.0, 26) == [1200.0, 1200.0, 200.0]

    def test_debt_schedule_of_a_cleared_debt_is_empty(self):
        assert debt_payment_schedule(100.0, 0) == []


class TestDebtByLastPaymentDate:
    """`Debt.last_payment` recomputes the term from `as_of` at compile time,
    instead of a `remaining_months` count that is only ever correct on the
    day it was written down."""

    def test_needs_exactly_one_of_remaining_months_or_last_payment(self):
        with pytest.raises(ValueError, match="exactly one"):
            Debt("Loan", 1_000, 100, remaining_months=10, last_payment=date(2027, 1, 1))
        with pytest.raises(ValueError, match="exactly one"):
            Debt("Loan", 1_000, 100)

    def test_produces_the_same_schedule_as_the_equivalent_month_count(self):
        last_payment = date(2028, 5, 6)
        equivalent_months = months_remaining(AS_OF, last_payment)
        by_date = Household(
            people=[Person("A", date(1966, 1, 1))],
            expenses=[Expense("Living", 5_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[Asset("ISA", AssetType.ISA, "A", 500_000, returns=FixedReal(0.0))],
            debts=[Debt("Loan", 2_600, 100, last_payment=last_payment)],
            assumptions=Assumptions(life_expectancy_age=64),
        )
        by_count = Household(
            people=[Person("A", date(1966, 1, 1))],
            expenses=[Expense("Living", 5_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[Asset("ISA", AssetType.ISA, "A", 500_000, returns=FixedReal(0.0))],
            debts=[Debt("Loan", 2_600, 100, remaining_months=equivalent_months)],
            assumptions=Assumptions(life_expectancy_age=64),
        )
        scenario = Scenario("retire", retirement_dates={"A": date(2028, 1, 1)}, withdrawal=SpendNominal())
        plan_by_date = compile_plan(by_date, scenario, UK, AS_OF)
        plan_by_count = compile_plan(by_count, scenario, UK, AS_OF)
        assert [y.debt_payment for y in plan_by_date.years] == [y.debt_payment for y in plan_by_count.years]

    def test_the_term_recomputes_when_as_of_moves(self):
        """The whole point: compiling the same household a year later, with
        the same `last_payment`, must show a year less remaining -- not the
        same stale count a `remaining_months` household would."""
        household = Household(
            people=[Person("A", date(1966, 1, 1))],
            debts=[Debt("Loan", 1_200, 100, last_payment=date(2028, 1, 1))],
            assumptions=Assumptions(life_expectancy_age=70),
        )
        scenario = Scenario("no retirement", withdrawal=SpendNominal())
        today = compile_plan(household, scenario, UK, date(2026, 1, 1))
        a_year_later = compile_plan(household, scenario, UK, date(2027, 1, 1))
        assert sum(y.debt_payment for y in today.years) > sum(y.debt_payment for y in a_year_later.years)


class TestIncomeAndContributions:
    def test_salary_sacrifice_reduces_taxable_and_ni_able_pay(self, contributing_household, flat_market):
        scenario = Scenario("no retirement", withdrawal=SpendNominal())
        plan = compile_plan(contributing_household, scenario, UK, AS_OF)
        year = plan.years[0]
        # £60,000 salary less £12,000 of employee sacrifice
        assert year.employment_income_by_person["Sam"] == pytest.approx(48_000)
        assert year.salary_gross_by_person["Sam"] == pytest.approx(60_000)

    def test_contributions_land_in_the_pension(self, contributing_household, flat_market):
        scenario = Scenario("no retirement", withdrawal=SpendNominal())
        projection = run(contributing_household, scenario, flat_market)
        # (1,000 + 500) x 12 added to a pot earning nothing
        assert projection.years[0].balances["Pension"] == pytest.approx(118_000)

    def test_contributions_stop_at_retirement(self, contributing_household, flat_market):
        """A retiree has no salary to sacrifice, so the pot only grows by returns."""
        retire = date(2028, 1, 1)
        scenario = Scenario("retire 2028", retirement_dates={"Sam": retire},
                            withdrawal=SpendNominal())
        projection = run(contributing_household, scenario, flat_market)
        before = projection.years[1].balances["Pension"]
        after = projection.years[2].balances["Pension"]
        assert projection.years[2].is_retired
        assert after == pytest.approx(before)  # flat market, no contributions

    def test_a_mid_year_retirement_gets_half_the_salary(self, contributing_household, flat_market):
        scenario = Scenario("mid-year", retirement_dates={"Sam": date(2026, 7, 2)},
                            withdrawal=SpendNominal())
        plan = compile_plan(contributing_household, scenario, UK, AS_OF)
        assert plan.years[0].salary_gross_by_person["Sam"] == pytest.approx(30_000, rel=0.01)

    def test_contribution_end_stops_contributing_while_the_salary_continues(self, flat_market):
        """Coast FIRE, modelled precisely: contribute until a date, then
        stop, while still working (and still sacrificing nothing further)
        until retirement proper."""
        household = Household(
            people=[Person("Sam", date(1976, 1, 1))],
            incomes=[IncomeSource("Sam", IncomeType.SALARY, 60_000, Frequency.YEARLY)],
            expenses=[Expense("Living", 20_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[
                Asset("Pension", AssetType.DC_PENSION, "Sam", 100_000, returns=FixedReal(0.0),
                      contributions=Contribution(employee_monthly=1_000, employer_monthly=500,
                                                 end=date(2028, 1, 1))),
            ],
            assumptions=Assumptions(life_expectancy_age=56, state_pension_age=68),
        )
        scenario = Scenario("no retirement", withdrawal=SpendNominal())
        plan = compile_plan(household, scenario, UK, AS_OF)
        projection = run(household, scenario, flat_market)
        # Two full years of (1,000 + 500) x 12, then nothing.
        assert projection.years[1].balances["Pension"] == pytest.approx(100_000 + 2 * 18_000)
        assert projection.years[2].balances["Pension"] == pytest.approx(projection.years[1].balances["Pension"])
        # The salary itself -- and its sacrifice-free taxable pay -- is
        # unaffected: Sam is still working, just no longer contributing.
        assert plan.years[3].salary_gross_by_person["Sam"] == pytest.approx(60_000)
        assert plan.years[3].employment_income_by_person["Sam"] == pytest.approx(60_000)


class TestSpending:
    def test_phase_gates_expenses(self, flat_market):
        household = Household(
            people=[Person("A", date(1966, 1, 1))],
            expenses=[
                Expense("Commuting", 1_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL,
                        phase=Phase.PRE_RETIREMENT),
                Expense("Golf", 2_000, Frequency.YEARLY, ExpenseCategory.DISCRETIONARY,
                        phase=Phase.RETIREMENT),
            ],
            assets=[Asset("ISA", AssetType.ISA, "A", 500_000, returns=FixedReal(0.0))],
            assumptions=Assumptions(life_expectancy_age=64),
        )
        scenario = Scenario("retire", retirement_dates={"A": date(2028, 1, 1)},
                            withdrawal=SpendNominal())
        projection = run(household, scenario, flat_market)
        assert projection.years[0].essential_spending == pytest.approx(1_000)
        assert projection.years[0].discretionary_spending == 0.0
        assert projection.years[2].essential_spending == 0.0
        assert projection.years[2].discretionary_spending == pytest.approx(2_000)

    def test_years_from_retirement_ends_an_expense(self, flat_market):
        household = Household(
            people=[Person("A", date(1966, 1, 1))],
            expenses=[
                Expense("Big trip", 10_000, Frequency.YEARLY, ExpenseCategory.DISCRETIONARY,
                        phase=Phase.RETIREMENT, years_from_retirement=2),
            ],
            assets=[Asset("ISA", AssetType.ISA, "A", 500_000, returns=FixedReal(0.0))],
            assumptions=Assumptions(life_expectancy_age=65),
        )
        scenario = Scenario("retire now", retirement_dates={"A": AS_OF}, withdrawal=SpendNominal())
        projection = run(household, scenario, flat_market)
        assert projection.years[0].discretionary_spending == pytest.approx(10_000)
        assert projection.years[1].discretionary_spending == pytest.approx(10_000)
        assert projection.years[2].discretionary_spending == 0.0

    def test_start_defers_a_retirement_expense(self, flat_market):
        """A retirement-phase expense starts at the later of the two dates.

        `start` used to be overwritten by the retirement date, so deferring a
        holiday or a replacement fund past a bridge silently did nothing and
        scored identically to not deferring it.
        """
        household = Household(
            people=[Person("A", date(1966, 1, 1))],
            expenses=[
                Expense("Big trip", 10_000, Frequency.YEARLY, ExpenseCategory.DISCRETIONARY,
                        phase=Phase.RETIREMENT, start=date(2028, 1, 1)),
            ],
            assets=[Asset("ISA", AssetType.ISA, "A", 500_000, returns=FixedReal(0.0))],
            assumptions=Assumptions(life_expectancy_age=64),
        )
        scenario = Scenario("retire now", retirement_dates={"A": AS_OF}, withdrawal=SpendNominal())
        projection = run(household, scenario, flat_market)
        assert projection.years[0].discretionary_spending == 0.0
        assert projection.years[1].discretionary_spending == 0.0
        assert projection.years[2].discretionary_spending == pytest.approx(10_000)

    def test_one_off_spend_lands_in_its_own_year(self, simple_household, flat_market):
        scenario = Scenario(
            "with a purchase",
            retirement_dates={"Alex": AS_OF},
            one_off_spends=(OneOffSpend(on=date(2028, 6, 1), amount=50_000, description="Boat"),),
            withdrawal=SpendNominal(),
        )
        projection = run(simple_household, scenario, flat_market)
        by_year = {y.year: y.one_off_spending for y in projection.years}
        assert by_year[2028] == pytest.approx(50_000)
        assert by_year[2027] == 0.0
        assert by_year[2029] == 0.0

    def test_a_one_off_spend_costs_more_than_its_price_tag(self, simple_household, flat_market):
        """A lump sum drains the tax-free ISA sooner, so later spending has to
        come from the taxable pension. The true cost is the purchase *plus*
        the extra tax that displacement causes — which is exactly the kind of
        second-order effect a spreadsheet estimate misses."""
        base = run(simple_household, Scenario("base", retirement_dates={"Alex": AS_OF},
                                              withdrawal=SpendNominal()), flat_market)
        with_boat = run(
            simple_household,
            Scenario("boat", retirement_dates={"Alex": AS_OF},
                     one_off_spends=(OneOffSpend(date(2028, 6, 1), 50_000),),
                     withdrawal=SpendNominal()),
            flat_market,
        )
        cost = base.final_wealth - with_boat.final_wealth
        assert cost > 50_000, "a purchase cannot cost less than its price"
        assert cost < 60_000, "but the tax drag should be modest, not enormous"


class TestPensionAccess:
    def test_dc_pension_is_locked_before_the_access_age(self, flat_market):
        """Alex is 55 at the as-of date; the pension unlocks at 57."""
        household = Household(
            people=[Person("Alex", date(1971, 1, 1))],
            expenses=[Expense("Living", 40_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[
                Asset("Pension", AssetType.DC_PENSION, "Alex", 1_000_000, returns=FixedReal(0.0)),
                Asset("ISA", AssetType.ISA, "Alex", 50_000, returns=FixedReal(0.0)),
            ],
            assumptions=Assumptions(life_expectancy_age=60),
        )
        scenario = Scenario("retired", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal())
        projection = run(household, scenario, flat_market)

        first, second = projection.years[0], projection.years[1]
        assert first.dc_withdrawn_gross == 0.0          # ISA covers year one
        assert second.dc_withdrawn_gross == 0.0         # ISA exhausted, pension still locked
        assert second.unmet_shortfall > 0               # so the year genuinely fails
        # Age 57 arrives in plan year 2, and the pension becomes available.
        assert projection.years[2].dc_withdrawn_gross > 0
        assert projection.years[2].unmet_shortfall == 0.0

    def test_access_begins_in_the_plan_year_the_birthday_falls_in(self, flat_market):
        """Alex turns 57 on 15 June 2028 -- mid plan-year, not on a plan-year
        boundary. Access must open in the plan-year containing that birthday
        (year 2, starting 1 Jan 2028), not the following one: rounding up to
        the next boundary would deny access for up to eleven months after the
        birthday actually arrives, which is the bug this test guards against."""
        household = Household(
            people=[Person("Alex", date(1971, 6, 15))],
            expenses=[Expense("Living", 40_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[
                Asset("Pension", AssetType.DC_PENSION, "Alex", 1_000_000, returns=FixedReal(0.0)),
                Asset("ISA", AssetType.ISA, "Alex", 50_000, returns=FixedReal(0.0)),
            ],
            assumptions=Assumptions(life_expectancy_age=60),
        )
        scenario = Scenario("retired", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal())
        plan = compile_plan(household, scenario, UK, AS_OF)

        assert plan.years[1].dc_accessible_by_person["Alex"] is False   # 2027: still 56
        assert plan.years[2].dc_accessible_by_person["Alex"] is True    # 2028: turns 57 on 15 Jun

        projection = run(household, scenario, flat_market)
        assert projection.years[1].unmet_shortfall > 0    # ISA exhausted, pension still locked
        assert projection.years[2].dc_withdrawn_gross > 0  # available the year the birthday lands in
        assert projection.years[2].unmet_shortfall == 0.0

    def test_pension_withdrawals_are_grossed_up_for_tax(self, flat_market):
        household = Household(
            people=[Person("Alex", date(1960, 1, 1))],
            expenses=[Expense("Living", 30_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[Asset("Pension", AssetType.DC_PENSION, "Alex", 1_000_000, returns=FixedReal(0.0))],
            assumptions=Assumptions(life_expectancy_age=67, state_pension_age=99),
        )
        scenario = Scenario("retired", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal())
        projection = run(household, scenario, flat_market)
        year = projection.years[0]
        assert year.dc_withdrawn_gross > 30_000       # more than the net need
        assert year.tax_paid == pytest.approx(UK.income_tax(year.dc_withdrawn_gross))
        net = year.dc_withdrawn_gross - year.tax_paid
        assert net == pytest.approx(30_000, rel=1e-6)


class TestSurplusInvesting:
    """Leftover income must not sit idle in cash -- see `_Accounts.invest_surplus`."""

    def test_surplus_goes_to_isa_up_to_the_allowance(self, simple_household, flat_market):
        scenario = Scenario("no retirement", withdrawal=SpendNominal())
        projection = run(simple_household, scenario, flat_market)
        year = projection.years[0]
        assert year.net_cashflow > 0
        assert year.balances["ISA"] == pytest.approx(100_000 + year.net_cashflow, abs=0.01)
        assert year.balances["__cash_reserve"] == pytest.approx(0.0)

    def test_surplus_above_the_isa_allowance_overflows_to_gia(self, flat_market):
        household = Household(
            people=[Person("Alex", date(1975, 1, 1))],
            incomes=[IncomeSource("Alex", IncomeType.SALARY, 150_000, Frequency.YEARLY)],
            expenses=[Expense("Living", 30_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[Asset("ISA", AssetType.ISA, "Alex", 10_000, returns=FixedReal(0.0))],
            assumptions=Assumptions(life_expectancy_age=60),
        )
        scenario = Scenario("no retirement", withdrawal=SpendNominal())
        projection = run(household, scenario, flat_market)
        year = projection.years[0]
        assert year.net_cashflow > 20_000
        assert year.balances["ISA"] == pytest.approx(10_000 + 20_000)  # capped at the allowance
        assert year.balances["Alex — Surplus GIA (Global Tracker)"] == pytest.approx(
            year.net_cashflow - 20_000
        )
        assert year.balances["__cash_reserve"] == pytest.approx(0.0)

    def test_surplus_splits_equally_between_two_people(self, flat_market):
        household = Household(
            people=[Person("A", date(1975, 1, 1)), Person("B", date(1977, 1, 1))],
            incomes=[IncomeSource("A", IncomeType.SALARY, 60_000, Frequency.YEARLY)],
            expenses=[Expense("Living", 10_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[
                Asset("A ISA", AssetType.ISA, "A", 0, returns=FixedReal(0.0)),
                Asset("B ISA", AssetType.ISA, "B", 0, returns=FixedReal(0.0)),
            ],
            assumptions=Assumptions(life_expectancy_age=55),
        )
        scenario = Scenario("no retirement", withdrawal=SpendNominal())
        projection = run(household, scenario, flat_market)
        year = projection.years[0]
        assert year.balances["A ISA"] == pytest.approx(year.net_cashflow / 2, abs=0.01)
        assert year.balances["B ISA"] == pytest.approx(year.net_cashflow / 2, abs=0.01)

    def test_a_person_with_no_explicit_isa_still_gets_one_synthesised(self, flat_market):
        """A household built with no ISA `Asset` (the client holds none
        today) must not lose the ability to shelter surplus in one -- see
        `SURPLUS_ISA_NAME` in plan.py. Fills the synthetic ISA to the annual
        allowance first, same as an explicit one would, then overflows to
        the GIA."""
        household = Household(
            people=[Person("Alex", date(1975, 1, 1))],
            incomes=[IncomeSource("Alex", IncomeType.SALARY, 80_000, Frequency.YEARLY)],
            expenses=[Expense("Living", 10_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[],
            assumptions=Assumptions(life_expectancy_age=55),
        )
        scenario = Scenario("no retirement", withdrawal=SpendNominal())
        projection = run(household, scenario, flat_market)
        year = projection.years[0]
        assert year.balances["Alex — Surplus ISA (Global Tracker)"] == pytest.approx(20_000, abs=0.01)
        assert year.balances["Alex — Surplus GIA (Global Tracker)"] == pytest.approx(
            year.net_cashflow - 20_000, abs=0.01
        )
        assert year.balances["__cash_reserve"] == pytest.approx(0.0)


class TestGIA:
    def test_gia_is_drawn_after_isa_and_before_pension(self, flat_market):
        household = Household(
            people=[Person("Alex", date(1969, 1, 1))],
            expenses=[Expense("Living", 60_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[
                Asset("ISA", AssetType.ISA, "Alex", 20_000, returns=FixedReal(0.0)),
                Asset("GIA", AssetType.GIA, "Alex", 200_000, returns=FixedReal(0.0)),
                Asset("Pension", AssetType.DC_PENSION, "Alex", 1_000_000, returns=FixedReal(0.0)),
            ],
            assumptions=Assumptions(life_expectancy_age=63),
        )
        scenario = Scenario("retired", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal())
        projection = run(household, scenario, flat_market)
        first, second = projection.years[0], projection.years[1]
        # The ISA is drained by spending, then refilled to the £20,000
        # annual allowance by the end-of-year Bed-and-ISA sweep -- balance
        # and subscription headroom are independent, so both are correct.
        assert first.balances["ISA"] == pytest.approx(20_000, abs=1.0)
        assert first.gia_withdrawn > 0
        assert first.dc_withdrawn_gross == 0.0        # GIA covers year one, untouched pension
        assert second.balances["GIA"] < 200_000        # still being drawn down in year two

    def test_realising_a_gain_pays_cgt(self, flat_market):
        """A GIA bought at cost (no embedded gain) pays no CGT on sale; one
        that has grown pays CGT on the gain portion only."""
        no_gain = Household(
            people=[Person("Alex", date(1969, 1, 1))],
            expenses=[Expense("Living", 100_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[Asset("GIA", AssetType.GIA, "Alex", 500_000, returns=FixedReal(0.0))],
            assumptions=Assumptions(life_expectancy_age=60),
        )
        scenario = Scenario("retired", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal())
        projection = run(no_gain, scenario, flat_market)
        assert projection.years[0].cgt_paid == pytest.approx(0.0)

        grown = Household(
            people=[Person("Alex", date(1969, 1, 1))],
            expenses=[Expense("Living", 100_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL,
                              phase=Phase.RETIREMENT)],
            assets=[Asset("GIA", AssetType.GIA, "Alex", 500_000, returns=FixedReal(0.10))],
            assumptions=Assumptions(life_expectancy_age=60),
        )
        # Grow for a year with nothing spent (spending is RETIREMENT-phase
        # only), then retire into year two so the balance has a real
        # embedded gain before anything is sold.
        scenario2 = Scenario("retired", retirement_dates={"Alex": add_years(AS_OF, 1)},
                             withdrawal=SpendNominal())
        projection2 = run(grown, scenario2, flat_market)
        assert projection2.years[1].cgt_paid > 0


class TestBedAndISA:
    """Progressively moving GIA money into the ISA wrapper, using whatever
    allowance is left each year -- money always ends up in the most
    tax-efficient wrapper available, not just wherever it first landed."""

    def test_gia_fully_migrates_into_the_isa_over_several_years(self, flat_market):
        household = Household(
            people=[Person("Alex", date(1966, 1, 1))],
            assets=[
                Asset("ISA", AssetType.ISA, "Alex", 0.0, returns=FixedReal(0.0)),
                Asset("GIA", AssetType.GIA, "Alex", 100_000, returns=FixedReal(0.0)),
            ],
            assumptions=Assumptions(life_expectancy_age=70),
        )
        scenario = Scenario("no retirement", withdrawal=SpendNominal())
        projection = run(household, scenario, flat_market)
        years = projection.years
        assert years[0].balances["ISA"] == pytest.approx(20_000, abs=1.0)
        assert years[0].balances["GIA"] == pytest.approx(79_868.75, abs=1.0)
        # Six years, not five: the ISA subscription limit has no uprating
        # mechanism and erodes in real terms by default, so each year moves a
        # little less across. Dividend tax along the way trims the total too.
        assert years[4].balances["GIA"] == pytest.approx(3_714.18, abs=1.0)
        assert years[5].balances["GIA"] == pytest.approx(0.0, abs=1.0)
        assert years[5].balances["ISA"] == pytest.approx(99_677.88, abs=1.0)

    def test_migration_pays_cgt_on_a_real_embedded_gain(self, flat_market):
        household = Household(
            people=[Person("Alex", date(1966, 1, 1))],
            assets=[
                Asset("ISA", AssetType.ISA, "Alex", 0.0, returns=FixedReal(0.0)),
                Asset("GIA", AssetType.GIA, "Alex", 500_000, returns=FixedReal(0.20)),
            ],
            assumptions=Assumptions(life_expectancy_age=70),
        )
        scenario = Scenario("no retirement", withdrawal=SpendNominal())
        projection = run(household, scenario, flat_market)
        # By year two the GIA has grown well past its original cost basis,
        # so sweeping £20,000 of headroom into the ISA realises a real gain.
        assert projection.years[1].cgt_paid > 0

    def test_isa_headroom_is_shared_with_the_ordinary_surplus_sweep(self, flat_market):
        """A person with both leftover income *and* a GIA balance in the
        same year must not be credited more than the real £20,000 -- the
        surplus sweep and the Bed-and-ISA sweep share one counter."""
        household = Household(
            people=[Person("Alex", date(1966, 1, 1))],
            incomes=[IncomeSource("Alex", IncomeType.SALARY, 150_000, Frequency.YEARLY)],
            expenses=[Expense("Living", 30_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[
                Asset("ISA", AssetType.ISA, "Alex", 0.0, returns=FixedReal(0.0)),
                Asset("GIA", AssetType.GIA, "Alex", 500_000, returns=FixedReal(0.0)),
            ],
            assumptions=Assumptions(life_expectancy_age=70),
        )
        scenario = Scenario("working", retirement_dates={"Alex": add_years(AS_OF, 10)},
                            withdrawal=SpendNominal())
        projection = run(household, scenario, flat_market)
        # A large salary surplus alone would already claim the full £20,000
        # allowance; the GIA must not also add another £20,000 on top.
        assert projection.years[0].balances["ISA"] == pytest.approx(20_000, abs=1.0)


class TestDefinedBenefitAndStatePension:
    def test_db_pension_starts_at_its_age_with_a_lump_sum(self, flat_market):
        household = Household(
            people=[Person("Pat", date(1968, 1, 1))],  # turns 60 in 2028
            expenses=[Expense("Living", 5_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[
                Asset("ISA", AssetType.ISA, "Pat", 100_000, returns=FixedReal(0.0)),
                Asset("Teachers", AssetType.DB_PENSION, "Pat",
                      defined_benefit=DefinedBenefit(annual_amount=9_000, start_age=60,
                                                     lump_sum=15_000)),
            ],
            assumptions=Assumptions(life_expectancy_age=63, state_pension_age=99),
        )
        scenario = Scenario("retired", retirement_dates={"Pat": AS_OF}, withdrawal=SpendNominal())
        plan = compile_plan(household, scenario, UK, AS_OF)
        assert plan.years[1].other_taxable_by_person.get("Pat", 0.0) == 0.0
        assert plan.years[2].other_taxable_by_person["Pat"] == pytest.approx(9_000)
        assert plan.years[2].lump_sums_by_person["Pat"] == pytest.approx(15_000)

    def test_db_lump_sum_is_invested_in_the_recipients_isa_not_left_in_cash(self, flat_market):
        """A real finding, not a hypothetical: this used to land straight in
        the shared cash reserve and sit there, earning nothing, until spent
        down -- the same idle-cash problem ordinary surplus income already
        got fixed for, just missed for lump sums. Confirmed against a real
        client's report as a visible bulge in a "cash" fan chart that should
        never have shown anything there."""
        household = Household(
            people=[Person("Pat", date(1968, 1, 1))],  # turns 60 in 2028
            expenses=[Expense("Living", 5_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[
                Asset("ISA", AssetType.ISA, "Pat", 100_000, returns=FixedReal(0.0)),
                Asset("Teachers", AssetType.DB_PENSION, "Pat",
                      defined_benefit=DefinedBenefit(annual_amount=9_000, start_age=60,
                                                     lump_sum=15_000)),
            ],
            assumptions=Assumptions(life_expectancy_age=63, state_pension_age=99),
        )
        scenario = Scenario("retired", retirement_dates={"Pat": AS_OF}, withdrawal=SpendNominal())
        projection = run(household, scenario, flat_market)
        year = projection.years[2]
        assert year.balances["__cash_reserve"] == pytest.approx(0.0)
        assert year.balances["ISA"] > 100_000  # the lump landed here, not in cash

    def test_state_pension_starts_at_its_age(self, simple_household, flat_market):
        scenario = Scenario("retired", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal())
        plan = compile_plan(simple_household, scenario, UK, AS_OF)
        # Alex turns 68 in 2034, which is plan year 8.
        assert plan.years[7].other_taxable_by_person.get("Alex", 0.0) == 0.0
        assert plan.years[8].other_taxable_by_person["Alex"] == pytest.approx(11_973.0)


class TestAssetMechanics:
    def test_maturity_rolls_a_holding_into_its_target(self, flat_market):
        household = Household(
            people=[Person("A", date(1966, 1, 1))],
            assets=[
                Asset("Main ISA", AssetType.ISA, "A", 10_000, returns=FixedReal(0.0)),
                Asset("Bond", AssetType.ISA, "A", 5_000, returns=FixedReal(0.0),
                      maturity=Maturity(on=date(2027, 6, 1), rollover_to="Main ISA")),
            ],
            assumptions=Assumptions(life_expectancy_age=62),
        )
        projection = run(household, Scenario("hold", withdrawal=SpendNominal()), flat_market)
        assert projection.years[0].balances["Bond"] == pytest.approx(5_000)
        assert projection.years[1].balances["Bond"] == 0.0
        assert projection.years[1].balances["Main ISA"] == pytest.approx(15_000)

    def test_charges_and_flat_fees_are_deducted(self, flat_market):
        household = Household(
            people=[Person("A", date(1966, 1, 1))],
            assets=[Asset("ISA", AssetType.ISA, "A", 100_000, returns=FixedReal(0.0),
                          annual_charge_pct=0.01, flat_annual_fee=180)],
            assumptions=Assumptions(life_expectancy_age=61),
        )
        projection = run(household, Scenario("hold", withdrawal=SpendNominal()), flat_market)
        assert projection.years[0].balances["ISA"] == pytest.approx(100_000 * 0.99 - 180)

    def test_fixed_nominal_is_eroded_by_inflation(self):
        """A quoted 8% is not 8% real — this is the whole point of FixedNominal."""
        household = Household(
            people=[Person("A", date(1966, 1, 1))],
            assets=[Asset("Bond", AssetType.ISA, "A", 100_000, returns=FixedNominal(0.08))],
            assumptions=Assumptions(life_expectancy_age=61),
        )
        plan = compile_plan(household, Scenario("hold", withdrawal=SpendNominal()), UK, AS_OF)
        # Every household gets a synthetic per-person GIA (see `plan.py`'s
        # SURPLUS_GIA_NAME) that samples "global_equity", so even a household
        # with no equity asset of its own needs that key in the market path.
        high_inflation = project(plan, [{"inflation": 0.10, "global_equity": 0.0}] * plan.n_years)
        low_inflation = project(plan, [{"inflation": 0.02, "global_equity": 0.0}] * plan.n_years)
        # 8% nominal against 10% inflation is a real loss.
        assert high_inflation.years[0].balances["Bond"] < 100_000
        assert low_inflation.years[0].balances["Bond"] > 100_000

    def test_property_is_never_sold_to_fund_spending(self, flat_market):
        household = Household(
            people=[Person("A", date(1966, 1, 1))],
            expenses=[Expense("Living", 40_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[
                Asset("House", AssetType.PROPERTY, "A", 500_000, returns=FixedReal(0.0)),
                Asset("ISA", AssetType.ISA, "A", 10_000, returns=FixedReal(0.0)),
            ],
            assumptions=Assumptions(life_expectancy_age=62),
        )
        scenario = Scenario("retired", retirement_dates={"A": AS_OF}, withdrawal=SpendNominal())
        projection = run(household, scenario, flat_market)
        assert projection.years[-1].balances["House"] == pytest.approx(500_000)
        assert not projection.succeeded  # house equity does not rescue the plan


class TestMarketStress:
    def test_stress_overrides_the_opening_years(self, simple_household):
        scenario = Scenario(
            "crash first",
            retirement_dates={"Alex": AS_OF},
            withdrawal=SpendNominal(),
            market_stress=({"global_equity": -0.40},),
        )
        plan = compile_plan(simple_household, scenario, UK, AS_OF)
        flat = {"global_equity": 0.0, "gov_bonds": 0.0, "inflation": 0.0}
        projection = project(plan, [flat] * plan.n_years)
        # The ISA is hit by the forced -40% in year one despite a flat path.
        assert projection.years[0].balances["Pension"] == pytest.approx(200_000 * 0.60)
        assert projection.years[1].balances["Pension"] == pytest.approx(200_000 * 0.60)
