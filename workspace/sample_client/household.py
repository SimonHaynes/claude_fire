"""A fabricated household, transcribed from `notes.txt`.

**Not a real client.** Pat, Robin and Robbie do not exist; every figure below
was invented to be plausible and easy to hand-check, not sourced from an
actual person's finances. This is the fixture used by the integration tests
in `tests/test_integration_sample_client.py`, and the worked example the
`intake-financial-data` skill points to.

It exists because real client data must never be committed to this repo (see
`.gitignore` — everything under `workspace/` other than this directory is
ignored) but the test suite still needs a household stable enough, and public
enough, to pin exact numbers against.

## Assumptions made where the notes were silent

Deliberately kept simple, since the point of this household is to be read
and hand-verified, not to explore every feature the engine has:

  * Salaries are flat in real terms, and pension contributions (both read as
    salary sacrifice, per the "SS" in the notes) stop the instant the salary
    does.
  * "Everything Else (food, holidays, cars)" is pre-retirement-only: retirement
    has its own, separately stated, essential and discretionary figures, so
    treating the catch-all as a permanent commitment would be inventing a fact
    the notes do not state.
  * Council tax/utilities is quoted at the same figure before and after
    retirement, so it is modelled as one continuous `Phase.ALWAYS` expense.
  * The house is assumed flat in real terms (0% real growth) — the least
    flattering default.
  * State pension age (68) and life expectancy (95) are the engine's
    defaults, not stated by the notes.
  * Pat has a full 35-year NI record; Robin is short six years, a fabricated
    figure chosen so the fixture exercises the pro-rating and gives the
    voluntary-NI comparison something to bite on. A real intake reads both
    numbers off a gov.uk forecast.
"""
from __future__ import annotations

from datetime import date

from retireplan import (
    Asset,
    AssetType,
    Assumptions,
    Contribution,
    Debt,
    DefinedBenefit,
    Expense,
    ExpenseCategory,
    FixedReal,
    Frequency,
    Goal,
    Household,
    IncomeSource,
    IncomeType,
    Person,
    Phase,
    SampledSeries,
)

AS_OF = date(2026, 1, 1)

PAT_DOB = date(1969, 4, 12)
ROBIN_DOB = date(1971, 8, 25)

SAMPLE_CLIENT = Household(
    people=[
        Person("Pat", PAT_DOB, state_pension_qualifying_years=35),
        Person("Robin", ROBIN_DOB, state_pension_qualifying_years=29),
    ],
    incomes=[
        IncomeSource("Pat", IncomeType.SALARY, 78_000, Frequency.YEARLY),
        IncomeSource("Robin", IncomeType.SALARY, 46_000, Frequency.YEARLY),
    ],
    expenses=[
        Expense("Council tax, utilities etc.", 450, Frequency.MONTHLY,
                ExpenseCategory.ESSENTIAL, phase=Phase.ALWAYS),
        Expense("Everything else (food, holidays, cars)", 2_200, Frequency.MONTHLY,
                ExpenseCategory.ESSENTIAL, phase=Phase.PRE_RETIREMENT),
        Expense("Essential spending", 1_600, Frequency.MONTHLY,
                ExpenseCategory.ESSENTIAL, phase=Phase.RETIREMENT),
        Expense("Discretionary spending", 700, Frequency.MONTHLY,
                ExpenseCategory.DISCRETIONARY, phase=Phase.RETIREMENT),
        Expense("House repairs, car replacement etc.", 6_000, Frequency.YEARLY,
                ExpenseCategory.DISCRETIONARY, phase=Phase.RETIREMENT),
    ],
    debts=[
        Debt("Mortgage", 145_000, 950, 150),
    ],
    assets=[
        Asset("House", AssetType.PROPERTY, "joint", 480_000, returns=FixedReal(0.0)),
        Asset(
            "Pat — DC Pension (Global Tracker)", AssetType.DC_PENSION, "Pat", 310_000,
            returns=SampledSeries("global_equity"),
            contributions=Contribution(employee_monthly=650, employer_monthly=260),
        ),
        Asset(
            "Pat — ISA (Global Tracker)", AssetType.ISA, "Pat", 52_000,
            returns=SampledSeries("global_equity"),
        ),
        Asset(
            "Robin — DC Pension (Global Tracker)", AssetType.DC_PENSION, "Robin", 95_000,
            returns=SampledSeries("global_equity"),
            contributions=Contribution(employee_monthly=350, employer_monthly=180),
        ),
        Asset(
            "Robin — DB Pension (workplace scheme)", AssetType.DB_PENSION, "Robin",
            defined_benefit=DefinedBenefit(annual_amount=3_800, start_age=65, lump_sum=6_500),
        ),
        Asset(
            "Robin — ISA (Global Tracker)", AssetType.ISA, "Robin", 21_000,
            returns=SampledSeries("global_equity"),
        ),
    ],
    goals=[
        Goal("Retire as early as comfortably possible.", priority=1),
        Goal("Keep a comfortable cushion for the unexpected.", priority=1),
        Goal("Leave whatever's left to each other, then to Robbie.", priority=2),
    ],
    assumptions=Assumptions(risk_tolerance="medium"),
)
