"""Shared fixtures.

The household here is deliberately small and round-numbered so that expected
values in tests can be worked out by hand — a fixture you cannot do arithmetic
against is not much use for testing an arithmetic engine.
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
    MarketData,
    Person,
    Phase,
    SampledSeries,
)

AS_OF = date(2026, 1, 1)


@pytest.fixture
def flat_market() -> MarketData:
    """Zero real returns and zero inflation: any change in a balance is
    something the engine did, not something the market did."""
    return MarketData(
        by_year={
            y: {"global_equity": 0.0, "gov_bonds": 0.0, "inflation": 0.0, "short_corporate": 0.0}
            for y in range(2000, 2026)
        }
    )


@pytest.fixture
def growing_market() -> MarketData:
    return MarketData(
        by_year={
            y: {"global_equity": 0.10, "gov_bonds": 0.02, "inflation": 0.03, "short_corporate": 0.01}
            for y in range(2000, 2026)
        }
    )


@pytest.fixture
def simple_household() -> Household:
    """One 60-year-old, £30k salary, £20k of spending, a pension and an ISA."""
    return Household(
        people=[Person("Alex", date(1966, 1, 1))],
        incomes=[IncomeSource("Alex", IncomeType.SALARY, 30_000, Frequency.YEARLY)],
        expenses=[
            Expense("Essentials", 15_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL),
            Expense("Fun", 5_000, Frequency.YEARLY, ExpenseCategory.DISCRETIONARY),
        ],
        assets=[
            Asset("Pension", AssetType.DC_PENSION, "Alex", 200_000,
                  returns=SampledSeries("global_equity")),
            Asset("ISA", AssetType.ISA, "Alex", 100_000,
                  returns=SampledSeries("global_equity")),
        ],
        assumptions=Assumptions(life_expectancy_age=70, state_pension_age=68,
                                state_pension_annual=11_973.0),
    )


@pytest.fixture
def contributing_household() -> Household:
    """Salary sacrifice into a pension — for testing that contributions stop."""
    return Household(
        people=[Person("Sam", date(1976, 1, 1))],
        incomes=[IncomeSource("Sam", IncomeType.SALARY, 60_000, Frequency.YEARLY)],
        expenses=[
            Expense("Living", 20_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL),
        ],
        assets=[
            Asset("Pension", AssetType.DC_PENSION, "Sam", 100_000,
                  returns=FixedReal(0.0),
                  contributions=Contribution(employee_monthly=1_000, employer_monthly=500)),
            Asset("ISA", AssetType.ISA, "Sam", 500_000, returns=FixedReal(0.0)),
        ],
        assumptions=Assumptions(life_expectancy_age=56, state_pension_age=68),
    )
