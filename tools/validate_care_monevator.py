"""Validate `retireplan.care` — the means-test and drawdown mechanics for
late-life residential care — against a complex, real-world, publicly
published worked example: Monevator's "Social care costs: how they impact
retirement finances – case study" (monevator.com/social-care-costs/), a
first-person case study by the site's pseudonymous author ("The
Accumulator") modelling his own eventual entry into residential care.

## The household, as stated in the article

  * TA (male), enters residential care at 85, modelled for 6 years (his own
    life expectancy at that point is ~3 years; the article deliberately
    doubles it as a stress test).
  * £300,000 DC pension, drawn at a 4% rule (£12,000/yr).
  * £100,000 stocks & shares ISA, drawn at 4% (£4,000/yr).
  * Full State Pension: £9,628/yr — the 2022/23 rate, not today's.
  * Self-funded residential care: £40,780/yr, inflating at 5%/yr.
  * Local-authority rate for the same care: £29,128/yr, inflating at 3%/yr.
  * Means test thresholds used: **the October 2023 Dilnot-style reform**
    (£20,000 lower / £100,000 upper capital limits, an £86,000 lifetime
    cap on self-funded contributions, £1,295/yr Personal Expenses
    Allowance) — the article says so explicitly: "I have to assume this
    shake-up will be closer to the truth than the current bands." That
    reform was subsequently deferred indefinitely and has still not
    happened as of this engine's `care.py` (2025/26).
  * Tariff income worked example given in the article: £80,000 of banded
    capital ÷ £250 = £320/week = £16,640/year.
  * Narrative outcome: self-funder in years 1-2 (ISA "obliterated"),
    partial state support years 3-5, capital reaches the state-funded
    floor around year 5.

## What this checks

1. **The formula.** `MeansTest.tariff_income` and `.contribution`, fed the
   article's own reform-regime numbers, should reproduce the article's own
   £16,640 figure to the pound. This is the same "match a published number
   exactly" parity test REVIEW.md's Method section already relies on.

2. **Today's actual rules vs. the reform the article used.** `care.py`
   ships the *current* England thresholds (£14,250/£23,250, no £86,000
   cap) — correctly, since the reform never launched. Run the same
   household through both regimes and see how different the real answer
   is from the one a well-informed, widely-read source publishes when
   using the assumption that turned out not to come true.

3. **Whether a drawdown pension pot counts as assessable capital.**
   `care.py._assessable_capital` deliberately counts a person's remaining
   DC pension pot as their own capital once needed for care — "the
   cautious reading: a local authority can take account of a pot that
   could be drawn." The article's own £80,000/£16,640 tariff-income
   example is consistent only with counting the ISA (£100,000) alone, not
   ISA-plus-pension (£400,000) — at £400,000 the household is a full
   self-funder under *either* regime's upper limit, and the tariff-income
   band is never reached at all. Run both readings and see which the
   household's own state-support narrative actually requires.

Run: .venv/bin/python tools/validate_care_monevator.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from retireplan import (  # noqa: E402
    Asset,
    AssetType,
    Assumptions,
    CareModel,
    CareNeed,
    CarePlan,
    Expense,
    ExpenseCategory,
    FixedReal,
    Frequency,
    Household,
    MeansTest,
    Person,
    Phase,
    Scenario,
    StandardOrder,
    compile_plan,
    project,
)
from retireplan import care as care_module  # noqa: E402
from retireplan.tax.uk import UK  # noqa: E402

AS_OF = date(2026, 1, 1)
TA_DOB = date(AS_OF.year - 85, AS_OF.month, AS_OF.day)  # 85 at AS_OF: care starts immediately
MRS_TA_DOB = date(AS_OF.year - 83, AS_OF.month, AS_OF.day)

ARTICLE_STATE_PENSION = 9_628.0
ARTICLE_CARE_COST = 40_780.0
ARTICLE_CARE_YEARS = 6

REFORM_UPPER = 100_000.0
REFORM_LOWER = 20_000.0
REFORM_TARIFF_STEP = 250.0
REFORM_PEA_WEEKLY = 1_295.0 / 52.0


# 1. The formula, checked in isolation, against the article's own numbers.

def check_formula() -> None:
    print("--- 1. Formula check: MeansTest against the article's own £16,640 example ---")
    reform = MeansTest(upper_limit=REFORM_UPPER, lower_limit=REFORM_LOWER, tariff_step=REFORM_TARIFF_STEP)
    # The article's example implies capital at or above the upper limit, where
    # the banded portion maxes out at (upper - lower) = £80,000.
    tariff = reform.tariff_income(assessable_capital=REFORM_UPPER)
    print(f"  retireplan tariff_income(£100,000 capital, reform bands): £{tariff:,.0f}/yr")
    print(f"  Article's own worked figure: £16,640/yr")
    print(f"  Match: {'YES' if abs(tariff - 16_640) < 1 else 'NO'}")
    print()


# 2. Full household, run under both regimes.

def build_household(count_pension_as_capital: bool) -> Household:
    ta = Person("TA", TA_DOB, full_state_pension=True, sex="male")
    mrs_ta = Person("Mrs TA", MRS_TA_DOB, full_state_pension=True, sex="female")
    assets = [
        Asset("TA — ISA", AssetType.ISA, "TA", 100_000.0, returns=FixedReal(0.0)),
        Asset("Mrs TA — ISA", AssetType.ISA, "Mrs TA", 50_000.0, returns=FixedReal(0.0)),
    ]
    if count_pension_as_capital:
        # The realistic reading, and what retireplan actually does: a DC pot
        # in drawdown is assessable capital.
        assets.append(
            Asset("TA — DC Pension", AssetType.DC_PENSION, "TA", 300_000.0, returns=FixedReal(0.0))
        )
    # else: treat the same £12,000/yr as annuity/DB-style income the means test
    # only ever sees as income, which is the reading the article's own £16,640
    # tariff-income example is consistent with.
    return Household(
        people=[ta, mrs_ta],
        expenses=[
            Expense("TA essential spending", 19_816.0, Frequency.YEARLY,
                    ExpenseCategory.ESSENTIAL, phase=Phase.ALWAYS),
        ],
        assets=assets,
        assumptions=Assumptions(state_pension_annual=ARTICLE_STATE_PENSION, life_expectancy_age=95),
    )


def build_scenario(means_test: MeansTest, annual_cost: float) -> Scenario:
    return Scenario(
        "Care case study",
        retirement_dates={"TA": AS_OF, "Mrs TA": AS_OF},
        withdrawal=None,
        drawdown=StandardOrder(),
        care=CarePlan(
            model=CareModel(annual_cost=annual_cost, onset_age=85, max_stay_years=ARTICLE_CARE_YEARS),
            means_test=means_test,
        ),
    )


def run(regime: str, means_test: MeansTest, count_pension_as_capital: bool, pea_weekly: float | None):
    household = build_household(count_pension_as_capital)
    scenario = build_scenario(means_test, ARTICLE_CARE_COST)
    plan = compile_plan(household, scenario, UK, AS_OF)
    care_need = [CareNeed(person="TA", start_age=85, years=ARTICLE_CARE_YEARS)]

    original_pea = care_module.PERSONAL_EXPENSES_ALLOWANCE_WEEKLY
    if pea_weekly is not None:
        care_module.PERSONAL_EXPENSES_ALLOWANCE_WEEKLY = pea_weekly
    try:
        fixed = {"global_equity": 0.0, "gov_bonds": 0.0, "inflation": 0.0, "recession": 0.0}
        path = [fixed] * plan.n_years
        projection = project(plan, path, care_needs=care_need)
    finally:
        care_module.PERSONAL_EXPENSES_ALLOWANCE_WEEKLY = original_pea

    print(f"--- {regime} "
          f"(pension counted as capital: {count_pension_as_capital}) ---")
    for y in projection.years[:ARTICLE_CARE_YEARS + 1]:
        if y.care_cost or y.care_state_funded:
            ta_isa = y.balances.get("TA — ISA", 0.0)
            ta_pension = y.balances.get("TA — DC Pension", 0.0)
            print(f"  {y.year}: household pays £{y.care_cost:,.0f}  "
                  f"state pays £{y.care_state_funded:,.0f}  "
                  f"TA ISA left £{ta_isa:,.0f}  TA pension left £{ta_pension:,.0f}")
    if not any(y.care_state_funded for y in projection.years):
        print("  -> full self-funder throughout: no state contribution in any year")
    print()


def main() -> None:
    check_formula()

    current = MeansTest()  # retireplan's shipped 2025/26 defaults
    reform = MeansTest(upper_limit=REFORM_UPPER, lower_limit=REFORM_LOWER, tariff_step=REFORM_TARIFF_STEP)

    print("--- 2. Same household, today's actual rules vs. the article's assumed reform ---")
    print(f"    current: upper=£{current.upper_limit:,.0f} lower=£{current.lower_limit:,.0f}  "
          f"(retireplan's shipped 2025/26 defaults)")
    print(f"    reform:  upper=£{reform.upper_limit:,.0f} lower=£{reform.lower_limit:,.0f}  "
          f"(Oct-2023 Dilnot-style reform the article used -- since deferred indefinitely)")
    print()
    run("Today's actual rules, pension counted as capital", current, True, None)
    run("Article's reform assumptions, pension counted as capital", reform, True, REFORM_PEA_WEEKLY)
    run("Article's reform assumptions, pension NOT counted as capital (ISA only)",
        reform, False, REFORM_PEA_WEEKLY)


if __name__ == "__main__":
    main()
