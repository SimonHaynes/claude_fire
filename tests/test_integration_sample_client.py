"""End-to-end checks against the fabricated sample_client household.

`workspace/sample_client` is not a real client — real client data is gitignored
(see `.gitignore`) so it can never be the thing CI or a fresh checkout
depends on. This fixture exists so the whole chain (intake -> salary
sacrifice -> tax -> NI -> Monte Carlo) still has a hand-checkable, publicly
committable household to run against. The first-year figures below are
worked out by hand from `workspace/sample_client/notes.txt` in the module
docstring's arithmetic, the same way a real client's household was for the
fixture this replaced.
"""
from __future__ import annotations

from datetime import date

import pytest

from workspace.sample_client.household import AS_OF, PAT_DOB, ROBIN_DOB, SAMPLE_CLIENT
from retireplan import GuytonKlinger, Scenario, compile_plan, run_monte_carlo
from retireplan.tax.uk import UK

COMFORTABLE = date(2033, 1, 1)


@pytest.fixture(scope="module")
def plan():
    scenario = Scenario("comfortable", retirement_dates={"Pat": COMFORTABLE, "Robin": COMFORTABLE},
                        withdrawal=GuytonKlinger())
    return compile_plan(SAMPLE_CLIENT, scenario, UK, AS_OF)


class TestHouseholdIsWellFormed:
    def test_validates(self):
        SAMPLE_CLIENT.validate()

    def test_horizon_reaches_life_expectancy(self, plan):
        assert plan.years[-1].ages["Pat"] >= SAMPLE_CLIENT.assumptions.life_expectancy_age


class TestFirstYearArithmetic:
    """Hand-computed from `notes.txt`; see the module docstring.

    Pat: £78,000 salary less £650 x 12 sacrificed = £70,200 taxable/NI-able.
    Robin: £46,000 salary less £350 x 12 sacrificed = £41,800.

    Income tax (PA £12,570, 20% to £50,270, 40% above):
      Pat:   (50,270-12,570)*0.20 + (70,200-50,270)*0.40 = 7,540 + 7,972 = 15,512
      Robin: (41,800-12,570)*0.20                        = 5,846

    NI (0% to £12,570, 8% to £50,270, 2% above):
      Pat:   (50,270-12,570)*0.08 + (70,200-50,270)*0.02 = 3,016 + 398.60 = 3,414.60
      Robin: (41,800-12,570)*0.08                        = 2,338.40
    """

    def test_salary_sacrifice_reduces_taxable_pay(self, plan):
        year = plan.years[0]
        assert year.employment_income_by_person["Pat"] == pytest.approx(70_200)
        assert year.employment_income_by_person["Robin"] == pytest.approx(41_800)
        assert year.salary_gross_by_person["Pat"] == pytest.approx(78_000)
        assert year.salary_gross_by_person["Robin"] == pytest.approx(46_000)

    def test_income_tax(self, plan):
        taxable = plan.years[0].taxable_income_by_person
        assert UK.income_tax(taxable["Pat"]) == pytest.approx(15_512)
        assert UK.income_tax(taxable["Robin"]) == pytest.approx(5_846)
        assert sum(UK.income_tax(v) for v in taxable.values()) == pytest.approx(21_358)

    def test_national_insurance(self, plan):
        employment = plan.years[0].employment_income_by_person
        assert sum(UK.national_insurance(v) for v in employment.values()) == pytest.approx(5_753.0)

    def test_pension_contributions(self, plan):
        """Employee sacrifice plus employer top-up, both while still working."""
        by_slot = dict(plan.years[0].contributions)
        pat = by_slot[plan.slot("Pat — DC Pension (Global Tracker)")]
        robin = by_slot[plan.slot("Robin — DC Pension (Global Tracker)")]
        assert pat == pytest.approx(650 * 12 + 260 * 12)
        assert robin == pytest.approx(350 * 12 + 180 * 12)


class TestStructuralFacts:
    def test_contributions_stop_at_retirement(self, plan):
        retired = [y for y in plan.years if y.is_retired]
        assert retired, "the scenario should reach retirement"
        assert all(y.contributions == () for y in retired)

    def test_pats_pension_unlocks_within_the_birthday_year_not_the_next_one(self, plan):
        """Pat turns 57 (the Normal Minimum Pension Age) on 12 April 2026 --
        inside the first plan-year (2026-01-01 to 2027-01-01), not on a plan-
        year boundary. This is the case the plan.py date-rounding fix (see
        `dc_accessible_by_person`) exists for: access must open in the plan
        year the birthday falls in, not be pushed out to the next one."""
        pat_57th = date(PAT_DOB.year + 57, PAT_DOB.month, PAT_DOB.day)
        assert plan.years[0].start <= pat_57th < plan.years[0].end
        assert plan.years[0].dc_accessible_by_person["Pat"] is True

    def test_robins_db_pension_and_lump_sum_start_at_65(self, plan):
        robin_65th = date(ROBIN_DOB.year + 65, ROBIN_DOB.month, ROBIN_DOB.day)
        with_lump = [y for y in plan.years if y.lump_sums_by_person.get("Robin", 0.0) > 0]
        assert len(with_lump) == 1
        year = with_lump[0]
        assert year.start <= robin_65th < year.end
        assert year.lump_sums_by_person["Robin"] == pytest.approx(6_500)


class TestSimulationRegression:
    """Locks the headline results at three clearly-separated retirement dates.

    Not tuned client advice -- just enough spread (a fabricated household that
    plainly cannot retire immediately, plainly can retire in 2033, and sits
    in between in 2029) to catch an engine change that silently degenerates
    every scenario to the same answer, which is exactly the kind of bug this
    project has hit before (see REVIEW.md's bug table)."""

    @pytest.mark.parametrize("retire, low, high", [
        # Bounds re-derived when the headline rule became GuytonKlinger:
        # it adjusts spending early and reversibly, so the mid date scores
        # materially better than it did under a rule that only cut at the
        # point of collapse. The spread is what matters, not the levels.
        (AS_OF,               0.25, 0.55),   # immediate: the bridge isn't there yet
        (date(2029, 1, 1),    0.82, 0.97),   # mid
        (COMFORTABLE,         0.97, 1.00),   # comfortable
    ])
    def test_success_probabilities_are_stable(self, retire, low, high):
        scenario = Scenario(str(retire), retirement_dates={"Pat": retire, "Robin": retire},
                            withdrawal=GuytonKlinger())
        result = run_monte_carlo(SAMPLE_CLIENT, scenario, AS_OF, n_trials=500, seed=42)
        assert low <= result.success_probability <= high
