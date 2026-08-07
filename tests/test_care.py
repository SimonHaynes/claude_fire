"""Late-life care: incidence, length, the means test, and the state floor.

REVIEW.md §1.4. Care is the largest single spending risk a retired household
faces. What decides its effect on an estate is not the headline cost but the
means test -- assessed on each person's own capital, with the home disregarded
while a spouse still lives there.
"""
from __future__ import annotations

import random
import statistics
from datetime import date

import pytest

from retireplan import (
    Asset,
    AssetType,
    Assumptions,
    CareModel,
    CarePlan,
    CashBondLadder,
    Expense,
    ExpenseCategory,
    GuytonKlinger,
    FixedReal,
    Frequency,
    Household,
    ImmediateNeedsAnnuity,
    MeansTest,
    Person,
    Scenario,
    SpendNominal,
    compile_plan,
    project,
)
from retireplan.care import LOWER_CAPITAL_LIMIT, UPPER_CAPITAL_LIMIT, CareNeed
from retireplan.tax.uk import UK

AS_OF = date(2026, 1, 1)
FLAT = {"global_equity": 0.0, "gov_bonds": 0.0, "inflation": 0.0}


def couple(wealth: float = 2_000_000.0) -> Household:
    return Household(
        people=[
            Person("Alex", date(1950, 1, 1), sex="male"),
            Person("Sam", date(1952, 1, 1), sex="female"),
        ],
        expenses=[
            Expense("Essentials", 20_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL),
            Expense("Fun", 10_000, Frequency.YEARLY, ExpenseCategory.DISCRETIONARY),
        ],
        assets=[
            Asset("Alex ISA", AssetType.ISA, "Alex", wealth / 2, returns=FixedReal(0.0)),
            Asset("Sam ISA", AssetType.ISA, "Sam", wealth / 2, returns=FixedReal(0.0)),
            Asset("House", AssetType.PROPERTY, "joint", 750_000, returns=FixedReal(0.0)),
        ],
        assumptions=Assumptions(life_expectancy_age=95, state_pension_age=66),
    )


def run(household, care=None, needs=None, drawdown=None):
    extra = {"drawdown": drawdown} if drawdown is not None else {}
    scenario = Scenario(
        "s", retirement_dates={"Alex": AS_OF, "Sam": AS_OF},
        withdrawal=SpendNominal(), care=care, **extra,
    )
    plan = compile_plan(household, scenario, UK, AS_OF)
    return plan, project(plan, [FLAT] * plan.n_years, care_needs=needs)


class TestIncidence:
    def test_not_everyone_needs_care(self):
        model, rng = CareModel(), random.Random(1)
        got = [model.sample("X", "female", rng) for _ in range(5_000)]
        share = sum(1 for g in got if g) / len(got)
        assert 0.1 < share < 0.5, "assuming everyone needs care overstates the risk"

    def test_women_are_more_likely_to_need_it(self):
        model, rng = CareModel(), random.Random(2)
        f = sum(1 for _ in range(5_000) if model.sample("X", "female", rng))
        m = sum(1 for _ in range(5_000) if model.sample("X", "male", rng))
        assert f > m

    def test_incidence_matches_the_published_figure(self):
        model, rng = CareModel(), random.Random(3)
        got = [model.sample("X", "female", rng) for _ in range(20_000)]
        assert sum(1 for g in got if g) / len(got) == pytest.approx(0.30, abs=0.02)

    def test_it_can_be_switched_off(self):
        model = CareModel(probability={"male": 0.0, "female": 0.0, None: 0.0})
        rng = random.Random(4)
        assert all(model.sample("X", "female", rng) is None for _ in range(200))


class TestLengthOfStay:
    def test_the_distribution_is_right_skewed(self):
        # The mean is dragged up by a long tail, which is exactly why an
        # average is a poor planning number.
        model, rng = CareModel(), random.Random(5)
        years = [n.years for n in (model.sample("X", "female", rng) for _ in range(20_000)) if n]
        assert statistics.median(years) < statistics.mean(years)

    def test_the_mean_matches_the_published_figure(self):
        model, rng = CareModel(), random.Random(6)
        years = [n.years for n in (model.sample("X", "female", rng) for _ in range(20_000)) if n]
        assert statistics.mean(years) == pytest.approx(2.5, abs=0.3)

    def test_no_implausibly_long_stay(self):
        model, rng = CareModel(max_stay_years=8.0), random.Random(7)
        years = [n.years for n in (model.sample("X", "female", rng) for _ in range(5_000)) if n]
        assert max(years) <= 8.0


class TestMeansTestIsPerPerson:
    def test_above_the_upper_limit_you_pay_everything(self):
        household, state = MeansTest().contribution(60_000, 500_000, 20_000)
        assert household == 60_000 and state == 0.0

    def test_below_the_limit_the_state_meets_the_balance(self):
        household, state = MeansTest().contribution(60_000, 10_000, 20_000)
        assert state > 0
        assert household + state == pytest.approx(60_000)

    def test_the_resident_keeps_a_personal_expenses_allowance(self):
        household, _ = MeansTest().contribution(60_000, 0.0, 20_000)
        assert household < 20_000, "income is not taken in full"

    def test_tariff_income_applies_between_the_limits(self):
        mt = MeansTest()
        assert mt.tariff_income(LOWER_CAPITAL_LIMIT) == 0.0
        assert mt.tariff_income(UPPER_CAPITAL_LIMIT) > 0.0
        assert mt.tariff_income(1_000_000) == mt.tariff_income(UPPER_CAPITAL_LIMIT)

    def test_the_limits_are_the_published_england_figures(self):
        assert (UPPER_CAPITAL_LIMIT, LOWER_CAPITAL_LIMIT) == (23_250.0, 14_250.0)


class TestTheStateIsAFloor:
    def test_a_poor_household_does_not_fail_because_of_care(self):
        # Nobody in England is left without essential care for lack of money.
        # Running out is a fallback to the state, not a plan failure.
        needs = [CareNeed("Alex", start_age=80, years=5.0)]
        _, projection = run(couple(wealth=50_000), care=CarePlan(), needs=needs)
        funded = [y for y in projection.years if y.care_state_funded > 0]
        assert funded, "expected the local authority to step in"

    def test_a_wealthy_household_gets_no_state_help(self):
        needs = [CareNeed("Alex", start_age=80, years=5.0)]
        _, projection = run(couple(wealth=4_000_000), care=CarePlan(), needs=needs)
        assert all(y.care_state_funded == 0 for y in projection.years)

    def test_state_funded_care_is_reported_not_hidden(self):
        needs = [CareNeed("Alex", start_age=80, years=5.0)]
        _, projection = run(couple(wealth=50_000), care=CarePlan(), needs=needs)
        assert any(y.care_state_funded > 0 for y in projection.years)


class TestTheHomeIsDisregarded:
    def test_a_house_does_not_make_someone_self_funding(self):
        # The home is disregarded while a spouse still lives there. A
        # household with a £750k house and almost no other capital should
        # still qualify for help.
        needs = [CareNeed("Alex", start_age=80, years=4.0)]
        _, projection = run(couple(wealth=40_000), care=CarePlan(), needs=needs)
        assert any(y.care_state_funded > 0 for y in projection.years)


class TestCareCostsMoney:
    def test_care_reduces_the_estate(self):
        needs = [CareNeed("Alex", start_age=80, years=4.0)]
        _, without = run(couple(), care=None, needs=needs)
        _, with_care = run(couple(), care=CarePlan(), needs=needs)
        assert with_care.years[-1].total_wealth < without.years[-1].total_wealth

    def test_only_the_person_in_care_is_charged(self):
        one = [CareNeed("Alex", start_age=80, years=3.0)]
        both = [CareNeed("Alex", start_age=80, years=3.0),
                CareNeed("Sam", start_age=80, years=3.0)]
        _, a = run(couple(), care=CarePlan(), needs=one)
        _, b = run(couple(), care=CarePlan(), needs=both)
        assert sum(y.care_cost for y in b.years) > sum(y.care_cost for y in a.years)

    def test_a_dead_person_incurs_no_care(self):
        needs = [CareNeed("Alex", start_age=120, years=3.0)]
        _, projection = run(couple(), care=CarePlan(), needs=needs)
        assert all(y.care_cost == 0 for y in projection.years)


class TestCareIsUncuttable:
    def test_a_guardrail_cannot_cut_care(self):
        needs = [CareNeed("Alex", start_age=80, years=3.0)]
        scenario = Scenario(
            "s", retirement_dates={"Alex": AS_OF, "Sam": AS_OF},
            withdrawal=GuytonKlinger(), care=CarePlan(),
        )
        plan = compile_plan(couple(), scenario, UK, AS_OF)
        projection = project(plan, [FLAT] * plan.n_years, care_needs=needs)
        charged = [y for y in projection.years if y.care_cost > 0]
        assert charged and all(y.care_cost > 0 for y in charged)

    def test_the_ladder_does_not_size_itself_against_care(self):
        # `CashBondLadder` sizes its bucket from `essential`. Care can treble
        # what a household spends, and a ladder reading that would pull years
        # of care fees into a low-return bucket in exactly the worst years --
        # so care must land in `one_off`, inside `fixed_spend` (uncuttable)
        # but outside `essential` (what the ladder reads).
        needs = [CareNeed("Alex", start_age=80, years=3.0)]
        _, plain = run(couple(), care=None, needs=needs, drawdown=CashBondLadder())
        _, cared = run(couple(), care=CarePlan(), needs=needs, drawdown=CashBondLadder())
        charged = [y for y in cared.years if y.care_cost > 0]
        assert charged, "expected some care to be charged"

        # Care is uncuttable: it is charged in full as a one-off.
        assert all(y.one_off_spending >= y.care_cost for y in charged)

        # But the ladder's target must not have grown with it.
        by_year = {y.year: y for y in plain.years}
        for y in charged:
            assert y.balances["__ladder_reserve"] <= (
                by_year[y.year].balances["__ladder_reserve"] + 1.0
            ), "the cash ladder sized itself against care costs"


class TestImmediateNeedsAnnuity:
    def test_a_premium_is_charged_once(self):
        needs = [CareNeed("Alex", start_age=80, years=5.0)]
        care = CarePlan(annuity=ImmediateNeedsAnnuity(enabled=True))
        _, projection = run(couple(), care=care, needs=needs)
        spikes = [y for y in projection.years if y.one_off_spending > 0]
        assert len(spikes) == 1, "bought once, at the point of entering care"

    def test_it_caps_the_care_liability(self):
        # The whole point: however long the stay, the estate is exposed only
        # to the premium.
        short = [CareNeed("Alex", start_age=80, years=1.0)]
        long = [CareNeed("Alex", start_age=80, years=10.0)]
        care = CarePlan(annuity=ImmediateNeedsAnnuity(enabled=True))
        _, a = run(couple(), care=care, needs=short)
        _, b = run(couple(), care=care, needs=long)
        assert a.years[-1].total_wealth == pytest.approx(b.years[-1].total_wealth, rel=1e-6)

    def test_self_funding_a_long_stay_costs_more_than_the_annuity(self):
        long = [CareNeed("Alex", start_age=80, years=10.0)]
        _, self_funded = run(couple(), care=CarePlan(), needs=long)
        _, insured = run(
            couple(), care=CarePlan(annuity=ImmediateNeedsAnnuity(enabled=True)), needs=long
        )
        assert insured.years[-1].total_wealth > self_funded.years[-1].total_wealth

    def test_the_premium_scales_with_the_benefit(self):
        ina = ImmediateNeedsAnnuity()
        assert ina.premium(60_000) == pytest.approx(2 * ina.premium(30_000))

    def test_it_is_off_by_default(self):
        assert ImmediateNeedsAnnuity().enabled is False


class TestOffByDefault:
    def test_no_care_plan_means_no_care(self):
        needs = [CareNeed("Alex", start_age=80, years=5.0)]
        _, projection = run(couple(), care=None, needs=needs)
        assert all(y.care_cost == 0 and y.care_state_funded == 0 for y in projection.years)

    def test_a_scenario_has_no_care_unless_asked(self):
        assert Scenario("s").care is None
