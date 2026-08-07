"""First death, and the survivor's position.

REVIEW.md §1.1, graded high and called "the single largest missing risk". The
model used to run both people to life expectancy and tax the estate once. Real
couples do not die together, and the survivor is materially worse off: one
personal allowance instead of two, one State Pension instead of two, a DB
pension roughly halved -- while spending barely falls.

It cuts the opposite way to almost everything else in the model: it makes
plans worse, not better.
"""
from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from retireplan import (
    Asset,
    AssetType,
    Assumptions,
    DefinedBenefit,
    Expense,
    ExpenseCategory,
    FixedReal,
    Frequency,
    Household,
    IncomeSource,
    IncomeType,
    Person,
    Scenario,
    SpendNominal,
    compile_plan,
    project,
)
from retireplan.tax.uk import UK

AS_OF = date(2026, 1, 1)
FLAT = {"global_equity": 0.0, "gov_bonds": 0.0, "inflation": 0.0}


def couple(**assumption_overrides) -> Household:
    """Two people, both retired, both on a State Pension, one with a DB pension."""
    return Household(
        people=[
            Person("Alex", date(1950, 1, 1), full_state_pension=True),
            Person("Sam", date(1950, 1, 1), full_state_pension=True),
        ],
        expenses=[
            Expense("Essentials", 20_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL),
            Expense("Fun", 10_000, Frequency.YEARLY, ExpenseCategory.DISCRETIONARY),
        ],
        assets=[
            Asset("Alex ISA", AssetType.ISA, "Alex", 100_000, returns=FixedReal(0.0)),
            Asset("Alex Pension", AssetType.DC_PENSION, "Alex", 300_000, returns=FixedReal(0.0)),
            Asset("Sam ISA", AssetType.ISA, "Sam", 50_000, returns=FixedReal(0.0)),
            Asset(
                "Alex DB", AssetType.DB_PENSION, "Alex",
                defined_benefit=DefinedBenefit(annual_amount=10_000, start_age=60),
            ),
        ],
        assumptions=Assumptions(
            life_expectancy_age=90, state_pension_age=66, **assumption_overrides
        ),
    )


def plan_for(household, death_ages=None):
    scenario = Scenario(
        "s", retirement_dates={"Alex": AS_OF, "Sam": AS_OF},
        withdrawal=SpendNominal(), death_ages=death_ages,
    )
    return compile_plan(household, scenario, UK, AS_OF)


class TestDefaultIsOldBehaviour:
    def test_nobody_dies_early_without_death_ages(self):
        plan = plan_for(couple())
        # Everyone reaches life expectancy, so every year has both alive.
        assert all(year.alive == frozenset({"Alex", "Sam"}) for year in plan.years)

    def test_a_projection_has_no_dead_years(self):
        plan = plan_for(couple())
        projection = project(plan, [FLAT] * plan.n_years)
        assert all(y.alive for y in projection.years)


class TestIncomeOnFirstDeath:
    @pytest.fixture
    def survivor_year(self):
        """A plan-year after Alex has died, with Sam alone."""
        plan = plan_for(couple())
        return plan.year_variants[frozenset({"Sam"})][10]

    @pytest.fixture
    def both_year(self):
        plan = plan_for(couple())
        return plan.year_variants[frozenset({"Alex", "Sam"})][10]

    def test_the_deceased_state_pension_stops_entirely(self, survivor_year, both_year):
        # It does not transfer. Roughly £12,000 a year simply stops.
        assert both_year.state_pension_by_person["Alex"] > 0
        assert "Alex" not in survivor_year.state_pension_by_person

    def test_the_survivor_keeps_their_own_state_pension(self, survivor_year):
        assert survivor_year.state_pension_by_person["Sam"] > 0

    def test_the_db_pension_halves(self, survivor_year, both_year):
        assert both_year.db_income_by_person["Alex"] == pytest.approx(10_000)
        assert survivor_year.db_income_by_person["Sam"] == pytest.approx(5_000)

    def test_the_db_survivor_benefit_is_taxed_in_the_survivors_name(self, survivor_year):
        # Left under the deceased's name it would draw on a personal allowance
        # and a basic-rate band that no longer exist.
        assert "Alex" not in survivor_year.db_income_by_person
        assert "Alex" not in survivor_year.taxable_income_by_person

    def test_the_survivor_fraction_is_configurable(self):
        plan = plan_for(couple(db_survivor_fraction=0.0))
        year = plan.year_variants[frozenset({"Sam"})][10]
        assert year.db_income_by_person.get("Sam", 0.0) == 0.0

    def test_household_taxable_income_falls(self, survivor_year, both_year):
        assert sum(survivor_year.taxable_income_by_person.values()) < sum(
            both_year.taxable_income_by_person.values()
        )


class TestOtherIncomeTransfersWhole:
    def test_rental_income_passes_to_the_survivor_undiminished(self):
        household = couple()
        household.incomes.append(
            IncomeSource("Alex", IncomeType.TAXABLE, 5_000, Frequency.YEARLY,
                         stops_at_retirement=False)
        )
        plan = plan_for(household)
        year = plan.year_variants[frozenset({"Sam"})][10]
        # Assets pass under the spouse exemption -- this must not be halved
        # the way a DB pension is, which is exactly the mistake a single
        # merged "other taxable" bucket would have made.
        assert year.taxable_other_by_person["Sam"] == pytest.approx(5_000)

    def test_tax_free_income_transfers_too(self):
        household = couple()
        household.incomes.append(
            IncomeSource("Alex", IncomeType.TAX_FREE, 3_000, Frequency.YEARLY,
                         stops_at_retirement=False)
        )
        plan = plan_for(household)
        both = plan.year_variants[frozenset({"Alex", "Sam"})][10]
        survivor = plan.year_variants[frozenset({"Sam"})][10]
        assert both.tax_free_income == pytest.approx(3_000)
        assert survivor.tax_free_income == pytest.approx(3_000)


class TestSpendingFallsButNotByHalf:
    def test_essentials_fall_a_little(self):
        plan = plan_for(couple())
        both = plan.year_variants[frozenset({"Alex", "Sam"})][10]
        survivor = plan.year_variants[frozenset({"Sam"})][10]
        assert survivor.essential == pytest.approx(both.essential * 0.90)

    def test_discretionary_falls_more(self):
        plan = plan_for(couple())
        both = plan.year_variants[frozenset({"Alex", "Sam"})][10]
        survivor = plan.year_variants[frozenset({"Sam"})][10]
        assert survivor.nominal_discretionary == pytest.approx(
            both.nominal_discretionary * 0.75
        )

    def test_total_spending_stays_well_above_half(self):
        # The naive assumption is that spending halves. It does not: fixed
        # costs do not care how many people live in the house.
        plan = plan_for(couple())
        both = plan.year_variants[frozenset({"Alex", "Sam"})][10]
        survivor = plan.year_variants[frozenset({"Sam"})][10]
        both_total = both.essential + both.nominal_discretionary
        survivor_total = survivor.essential + survivor.nominal_discretionary
        assert 0.80 < survivor_total / both_total < 0.90

    def test_debt_payments_do_not_fall(self):
        household = couple()
        from retireplan import Debt

        household.debts.append(Debt("Mortgage", 100_000, 1_000, 240))
        plan = plan_for(household)
        both = plan.year_variants[frozenset({"Alex", "Sam"})][5]
        survivor = plan.year_variants[frozenset({"Sam"})][5]
        assert survivor.debt_payment == pytest.approx(both.debt_payment)
        assert survivor.debt_payment > 0

    def test_the_factors_are_configurable(self):
        plan = plan_for(couple(
            survivor_essential_factor=1.0, survivor_discretionary_factor=1.0
        ))
        both = plan.year_variants[frozenset({"Alex", "Sam"})][10]
        survivor = plan.year_variants[frozenset({"Sam"})][10]
        assert survivor.essential == pytest.approx(both.essential)


class TestInheritedPotsAreRekeyed:
    def test_the_deceased_pension_moves_to_the_survivor(self):
        plan = plan_for(couple())
        slots = plan.slots_by_variant[frozenset({"Sam"})]
        # This is the regression test that matters most. Left keyed under
        # "Alex", every drawdown strategy would keep drawing that pot and
        # stacking it against a dead person's personal allowance and
        # basic-rate band -- every year, forever, invisibly.
        assert "Alex" not in slots.dc_slots_by_person
        assert slots.dc_slots_by_person["Sam"]

    def test_the_deceased_isa_moves_too(self):
        plan = plan_for(couple())
        slots = plan.slots_by_variant[frozenset({"Sam"})]
        assert "Alex" not in slots.isa_slots_by_person
        # Sam's own ISA plus Alex's.
        assert len(slots.isa_slots_by_person["Sam"]) == 2

    def test_an_inherited_pension_is_accessible_regardless_of_age(self):
        plan = plan_for(couple())
        slots = plan.slots_by_variant[frozenset({"Sam"})]
        # A beneficiary can draw an inherited pension at any age; without the
        # override the survivor would inherit the deceased's access age.
        assert "Sam" in slots.dc_accessible_override

    def test_nothing_is_rekeyed_while_both_are_alive(self):
        plan = plan_for(couple())
        slots = plan.slots_by_variant[frozenset({"Alex", "Sam"})]
        assert set(slots.dc_slots_by_person) == {"Alex", "Sam"}
        assert not slots.dc_accessible_override


class TestProjectionWithADeath:
    def test_forcing_a_death_produces_survivor_years(self):
        plan = plan_for(couple(), death_ages={"Alex": 80})
        projection = project(plan, [FLAT] * plan.n_years)
        alive_sets = {y.alive for y in projection.years}
        assert frozenset({"Alex", "Sam"}) in alive_sets
        assert frozenset({"Sam"}) in alive_sets

    def test_an_early_death_leaves_the_household_worse_off(self):
        # The whole point: the survivor loses income faster than spending.
        base = plan_for(couple())
        widowed = plan_for(couple(), death_ages={"Alex": 70})
        base_final = project(base, [FLAT] * base.n_years).years[-1].total_wealth
        widowed_final = project(widowed, [FLAT] * widowed.n_years).years[-1].total_wealth
        assert widowed_final < base_final

    def test_dead_years_record_no_shortfall(self):
        # A household that no longer exists cannot fail to fund itself, so
        # "success" means "never failed while someone was alive".
        plan = plan_for(couple(), death_ages={"Alex": 70, "Sam": 75})
        projection = project(plan, [FLAT] * plan.n_years)
        dead = [y for y in projection.years if not y.alive]
        assert dead, "expected years after the second death"
        assert all(y.unmet_shortfall == 0.0 for y in dead)

    def test_dead_years_spend_nothing_and_freeze_the_estate(self):
        plan = plan_for(couple(), death_ages={"Alex": 70, "Sam": 75})
        projection = project(plan, [FLAT] * plan.n_years)
        dead = [y for y in projection.years if not y.alive]
        assert all(y.total_spending == 0.0 for y in dead)
        assert len({round(y.total_wealth, 6) for y in dead}) == 1

    def test_every_trial_still_has_the_same_number_of_years(self):
        # Fixed-length results are what let the simulation reduce percentile
        # bands across trials that ended at different times.
        plan = plan_for(couple(), death_ages={"Alex": 70, "Sam": 75})
        projection = project(plan, [FLAT] * plan.n_years)
        assert len(projection.years) == plan.n_years

    def test_deaths_can_be_overridden_per_call(self):
        plan = plan_for(couple())
        projection = project(
            plan, [FLAT] * plan.n_years, deaths={"Alex": 5, "Sam": 10}
        )
        assert projection.years[6].alive == frozenset({"Sam"})
        assert projection.years[11].alive == frozenset()


class TestSinglePersonHouseholdIsUntouched:
    def test_no_survivor_adjustment_applies(self):
        household = Household(
            people=[Person("Alex", date(1950, 1, 1))],
            expenses=[
                Expense("Essentials", 20_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)
            ],
            assets=[Asset("ISA", AssetType.ISA, "Alex", 500_000, returns=FixedReal(0.0))],
            assumptions=Assumptions(life_expectancy_age=90),
        )
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal())
        plan = compile_plan(household, scenario, UK, AS_OF)
        projection = project(plan, [FLAT] * plan.n_years)
        assert all(y.alive == frozenset({"Alex"}) for y in projection.years)


class TestCacheKey:
    def test_death_ages_change_the_cache_key(self):
        from retireplan.market import MarketData
        from retireplan.simulation import cache_key

        household = couple()
        data = MarketData.load()
        base = Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal())
        widowed = dataclasses.replace(base, death_ages={"Alex": 70})
        args = (household,)
        rest = (UK, AS_OF, 100, 5, 42, data)
        assert cache_key(*args, base, *rest) != cache_key(*args, widowed, *rest)
