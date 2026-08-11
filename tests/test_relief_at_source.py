"""Contributions paid from taxed money, and the State Pension record.

Both exist for the same reason: the allowances a household is entitled to
belong to a *person*, so the planning question is whose name money goes into,
not just how much. A non-earning partner still gets basic-rate relief, and a
partner short of NI years can buy them back.
"""
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
    FixedReal,
    Frequency,
    Household,
    IncomeSource,
    IncomeType,
    Person,
    ReliefAtSource,
    Scenario,
    SpendNominal,
    compile_plan,
)
from retireplan.model import FiscalDrag
from retireplan.serde import household_from_dict, household_to_dict
from retireplan.tax.uk import UK

AS_OF = date(2026, 1, 1)
EARNER_DOB = date(1976, 1, 1)
PARTNER_DOB = date(1978, 1, 1)


def couple(
    *, net_annual=2_880.0, partner_salary=0.0, partner_dob=PARTNER_DOB,
    contribution_end=None, fiscal_drag=None,
) -> Household:
    """One earner funding a pension for a partner who may or may not work."""
    incomes = [IncomeSource("Alex", IncomeType.SALARY, 60_000, Frequency.YEARLY)]
    if partner_salary:
        incomes.append(
            IncomeSource("Jo", IncomeType.SALARY, partner_salary, Frequency.YEARLY)
        )
    return Household(
        people=[Person("Alex", EARNER_DOB), Person("Jo", partner_dob)],
        incomes=incomes,
        expenses=[Expense("Living", 30_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
        assets=[
            Asset("Jo — Pension", AssetType.DC_PENSION, "Jo", 50_000, returns=FixedReal(0.0),
                  contributions=ReliefAtSource(net_annual=net_annual, end=contribution_end)),
            Asset("Alex — ISA", AssetType.ISA, "Alex", 200_000, returns=FixedReal(0.0)),
        ],
        assumptions=Assumptions(
            life_expectancy_age=95, state_pension_age=68,
            fiscal_drag=fiscal_drag or FiscalDrag(allowance_inflation=0.0),
        ),
    )


def plan_for(household: Household, retire=date(2041, 1, 1)):
    scenario = Scenario(
        "plan",
        retirement_dates={"Alex": retire, "Jo": retire},
        withdrawal=SpendNominal(),
    )
    return compile_plan(household, scenario, UK, AS_OF)


def paid_into(year, plan, asset_name: str) -> float:
    slot = plan.slot(asset_name)
    return sum(a for _owner, s, a in year.contributions if s == slot)


class TestTheNonEarnerGrossUp:
    def test_2880_of_cash_buys_3600_of_pot(self):
        plan = plan_for(couple())
        assert paid_into(plan.years[0], plan, "Jo — Pension") == pytest.approx(3_600.0)

    def test_only_the_net_payment_leaves_the_household(self):
        plan = plan_for(couple())
        assert plan.years[0].relief_at_source_net_by_person["Jo"] == pytest.approx(2_880.0)

    def test_the_cash_is_spending_a_withdrawal_rule_cannot_cut(self):
        """It is a saving decision, not discretion: the rule may not fund it by
        skipping it, any more than it may skip a gift."""
        plan = plan_for(couple())
        no_contribution = plan_for(couple(net_annual=0.0))
        assert plan.years[0].fixed_spend - no_contribution.years[0].fixed_spend == (
            pytest.approx(2_880.0)
        )

    def test_it_carries_on_after_the_household_retires(self):
        """Unlike payroll contributions: relief needs no earnings behind it."""
        plan = plan_for(couple(), retire=date(2027, 1, 1))
        retired = plan.years[5]
        assert retired.is_retired
        assert paid_into(retired, plan, "Jo — Pension") == pytest.approx(3_600.0)


class TestTheRelievableCeiling:
    def test_the_ceiling_falls_to_the_flat_limit_when_the_earnings_stop(self):
        """A contribution sized against a salary is trimmed once the salary
        goes: the member's relevant earnings, not the household's, set it."""
        household = couple(net_annual=16_000.0, partner_salary=25_000.0)
        plan = plan_for(household, retire=date(2028, 1, 1))
        retired = plan.years[5]
        assert retired.is_retired
        assert paid_into(retired, plan, "Jo — Pension") == pytest.approx(3_600.0)
        assert retired.relief_at_source_net_by_person["Jo"] == pytest.approx(2_880.0)

    def test_an_earner_may_pay_up_to_their_own_earnings(self):
        household = couple(net_annual=16_000.0, partner_salary=25_000.0)
        plan = plan_for(household)
        assert paid_into(plan.years[0], plan, "Jo — Pension") == pytest.approx(20_000.0)

    def test_relevant_earnings_are_employment_income_only(self):
        household = couple()
        household.incomes.append(
            IncomeSource("Jo", IncomeType.TAXABLE, 40_000, Frequency.YEARLY)
        )
        assert household.relevant_earnings("Jo") == 0.0

    def test_the_flat_limit_erodes_in_real_terms(self):
        """Fixed in cash terms since 2001, so the trick shrinks every year."""
        plan = plan_for(couple(fiscal_drag=FiscalDrag(allowance_inflation=0.02)))
        assert paid_into(plan.years[20], plan, "Jo — Pension") < 3_600.0

    def test_relief_stops_at_75(self):
        plan = plan_for(couple(partner_dob=date(1960, 1, 1)))
        turns_75 = next(y for y in plan.years if y.ages["Jo"] >= 75)
        assert paid_into(turns_75, plan, "Jo — Pension") == 0.0

    def test_an_overstated_contribution_is_refused_at_outset(self):
        household = couple(net_annual=2_880.0)
        household.assets[0] = Asset(
            "Jo — Pension", AssetType.DC_PENSION, "Jo", 50_000, returns=FixedReal(0.0),
            contributions=ReliefAtSource(net_annual=8_000.0),
        )
        with pytest.raises(ValueError, match="above the £3,600 they can claim relief on"):
            household.validate()


class TestNobodyFundsADeadPersonsPension:
    def test_the_contribution_stops_when_the_member_dies(self):
        plan = plan_for(couple())
        survivors = plan.year_variants[frozenset({"Alex"})][0]
        assert paid_into(survivors, plan, "Jo — Pension") == 0.0
        assert survivors.relief_at_source_net_by_person == {}

    def test_a_payroll_contribution_stops_too(self):
        """Not specific to relief at source: a dead person's salary has
        stopped, so the sacrifice funding their pot has stopped with it."""
        household = couple()
        household.assets.append(
            Asset("Alex — Pension", AssetType.DC_PENSION, "Alex", 100_000,
                  returns=FixedReal(0.0),
                  contributions=Contribution(employee_monthly=500, employer_monthly=200))
        )
        plan = plan_for(household)
        assert paid_into(plan.years[0], plan, "Alex — Pension") == pytest.approx(8_400.0)
        survivors = plan.year_variants[frozenset({"Jo"})][0]
        assert paid_into(survivors, plan, "Alex — Pension") == 0.0


class TestStatePensionRecord:
    def test_a_full_record_pays_the_full_rate(self):
        plan = plan_for(couple())
        at_68 = next(y for y in plan.years if y.state_pension_by_person.get("Alex"))
        assert at_68.state_pension_by_person["Alex"] == pytest.approx(
            UK.full_state_pension_annual, rel=1e-3
        )

    def test_a_short_record_is_pro_rated(self):
        household = couple()
        household.people[1] = Person("Jo", PARTNER_DOB, state_pension_qualifying_years=28)
        plan = plan_for(household)
        paid = max(y.state_pension_by_person.get("Jo", 0.0) for y in plan.years)
        assert paid == pytest.approx(UK.full_state_pension_annual * 28 / 35, rel=1e-3)

    def test_below_ten_years_nothing_is_payable(self):
        household = couple()
        household.people[1] = Person("Jo", PARTNER_DOB, state_pension_qualifying_years=9)
        plan = plan_for(household)
        assert all("Jo" not in y.state_pension_by_person for y in plan.years)

    def test_an_impossible_record_is_refused(self):
        household = couple()
        household.people[1] = Person("Jo", PARTNER_DOB, state_pension_qualifying_years=60)
        with pytest.raises(ValueError, match="not a possible NI record"):
            household.validate()

    def test_buying_a_year_back_repays_inside_three_years(self):
        """The comparison that makes voluntary NI worth raising with every
        client who has a gap — nothing else guaranteed comes close."""
        assert UK.class_3_payback_years() < 3.0


class TestRoundTrip:
    def test_relief_at_source_survives_serialisation(self):
        original = couple()
        restored = household_from_dict(household_to_dict(original))
        assert restored.assets[0].contributions == ReliefAtSource(net_annual=2_880.0)

    def test_a_payroll_contribution_is_not_confused_for_a_net_one(self):
        original = couple()
        original.assets[0] = Asset(
            "Jo — Pension", AssetType.DC_PENSION, "Jo", 50_000, returns=FixedReal(0.0),
            contributions=Contribution(employee_monthly=100.0, employer_monthly=50.0),
        )
        restored = household_from_dict(household_to_dict(original))
        assert restored.assets[0].contributions == Contribution(
            employee_monthly=100.0, employer_monthly=50.0
        )

    def test_the_qualifying_years_survive(self):
        original = couple()
        original.people[1] = Person("Jo", PARTNER_DOB, state_pension_qualifying_years=28)
        restored = household_from_dict(household_to_dict(original))
        assert restored.people[1].state_pension_qualifying_years == 28
