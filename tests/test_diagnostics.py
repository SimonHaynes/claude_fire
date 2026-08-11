"""Screening numbers read off a compiled plan, before any market is run."""
from __future__ import annotations

from datetime import date

import pytest

from retireplan import (
    Asset,
    AssetType,
    Assumptions,
    Contribution,
    Expense,
    ExpenseCategory,
    Frequency,
    Household,
    IncomeSource,
    IncomeType,
    Person,
    SampledSeries,
    Scenario,
    SpendNominal,
    compile_plan,
    diagnose,
)
from retireplan.tax.uk import UK

AS_OF = date(2026, 1, 1)


def build(
    *, born=date(1976, 1, 1), isa=240_000.0, pension=560_000.0,
    essential=26_000.0, discretionary=14_000.0, incomes=(), isa_contributions=None,
    retire=AS_OF, state_pension_age=99,
):
    household = Household(
        people=[Person("A", born)],
        expenses=[
            Expense("Essentials", essential, Frequency.YEARLY, ExpenseCategory.ESSENTIAL),
            Expense("Discretionary", discretionary, Frequency.YEARLY,
                    ExpenseCategory.DISCRETIONARY),
        ],
        assets=[
            Asset("ISA", AssetType.ISA, "A", isa, returns=SampledSeries("global_equity"),
                  contributions=isa_contributions),
            Asset("Pension", AssetType.DC_PENSION, "A", pension,
                  returns=SampledSeries("global_equity")),
        ],
        incomes=list(incomes),
        assumptions=Assumptions(state_pension_age=state_pension_age),
    )
    scenario = Scenario("plan", retirement_dates={"A": retire}, withdrawal=SpendNominal())
    return diagnose(compile_plan(household, scenario, UK, AS_OF))


class TestBridgeLength:
    def test_it_counts_the_years_the_pension_is_locked(self):
        """Retiring at 50 with the Normal Minimum Pension Age at 57."""
        assert build().bridge_years == 7

    def test_there_is_no_bridge_past_the_access_age(self):
        assert build(born=date(1966, 1, 1)).bridge_years == 0

    def test_a_plan_with_no_retirement_has_nothing_to_diagnose(self):
        assert build(retire=date(2090, 1, 1)) is None

    def test_a_couple_bridges_only_to_the_first_unlock(self):
        """One accessible pension funds the household, so the younger
        partner's own lock is a tax question, not a liquidity one."""
        household = Household(
            people=[Person("Older", date(1974, 1, 1)), Person("Younger", date(1980, 1, 1))],
            expenses=[Expense("Living", 40_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[
                Asset("ISA", AssetType.ISA, "Older", 240_000,
                      returns=SampledSeries("global_equity")),
                Asset("Her pension", AssetType.DC_PENSION, "Older", 280_000,
                      returns=SampledSeries("global_equity")),
                Asset("His pension", AssetType.DC_PENSION, "Younger", 280_000,
                      returns=SampledSeries("global_equity")),
            ],
            assumptions=Assumptions(state_pension_age=99),
        )
        scenario = Scenario("both retire now",
                            retirement_dates={"Older": AS_OF, "Younger": AS_OF},
                            withdrawal=SpendNominal())
        # Older is 52 and unlocks at 57; Younger is 46 and unlocks at 57.
        assert diagnose(compile_plan(household, scenario, UK, AS_OF)).bridge_years == 5


class TestCoverage:
    def test_it_divides_reachable_money_by_what_the_bridge_costs(self):
        """£240,000 against seven years of £40,000, no growth assumed."""
        assert build().bridge_coverage == pytest.approx(240_000 / (7 * 40_000))

    def test_essential_coverage_ignores_discretionary_spending(self):
        assert build().essential_bridge_coverage == pytest.approx(240_000 / (7 * 26_000))

    def test_income_during_the_bridge_reduces_what_must_be_drawn(self):
        """A £15,000 pension in payment leaves only £25,000 a year to find."""
        with_income = build(incomes=[
            IncomeSource("A", IncomeType.TAXABLE, 15_000, Frequency.YEARLY,
                         stops_at_retirement=False),
        ])
        assert with_income.bridge_coverage > build().bridge_coverage

    def test_nothing_to_cover_reads_as_infinite_rather_than_large(self):
        no_bridge = build(born=date(1966, 1, 1))
        assert no_bridge.bridge_coverage == float("inf")
        assert no_bridge.essential_bridge_coverage == float("inf")


class TestBalancesAtRetirement:
    def test_the_pension_is_not_accessible_money(self):
        assert build().accessible_at_retirement == pytest.approx(240_000)
        assert build().portfolio_at_retirement == pytest.approx(800_000)

    def test_contributions_before_retirement_count(self):
        """Retiring in five years, paying £500 a month into the ISA until then."""
        later = date(AS_OF.year + 5, 1, 1)
        topped_up = build(
            retire=later,
            incomes=[IncomeSource("A", IncomeType.SALARY, 60_000, Frequency.YEARLY)],
            isa_contributions=Contribution(employee_monthly=500.0),
        )
        assert topped_up.accessible_at_retirement == pytest.approx(240_000 + 5 * 6_000)


class TestDrawRate:
    def test_it_is_the_first_retired_year_over_the_whole_portfolio(self):
        assert build().initial_draw_rate == pytest.approx(40_000 / 800_000)

    def test_income_lowers_it(self):
        funded = build(incomes=[
            IncomeSource("A", IncomeType.TAXABLE, 40_000, Frequency.YEARLY,
                         stops_at_retirement=False),
        ])
        assert funded.initial_draw_rate < 40_000 / 800_000
