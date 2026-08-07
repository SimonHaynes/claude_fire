"""retireplan — cashflow modelling and Monte Carlo simulation for retirement plans.

    from datetime import date
    from retireplan import Household, Scenario, run_monte_carlo

    result = run_monte_carlo(household, scenario, as_of=date.today(), seed=42)
    print(f"{result.success_probability:.1%}")

The engine works entirely in **real (today's money) terms**, so every figure in
and out is purchasing power, not future pounds.

Layout:
    model / serde       what a household is, and how it round-trips to JSON
    tax                 jurisdiction rules behind one small interface
    market              historical data, return models, the bootstrap sampler
    plan                compiles household + scenario into a fixed schedule
    cashflow            runs one path of returns through that schedule
    simulation          runs thousands, and reduces them to decisions
    strategies          withdrawal / drawdown / allocation, freely composable
    reporting           charts and the PDF report

`__version__` is part of every simulation cache key: bump it whenever a change
could alter a result, and stale cached answers invalidate themselves.
"""

__version__ = "0.9.1"

from .cashflow import Projection, YearResult, project
from .market import (
    BlockBootstrap,
    Blend,
    FixedNominal,
    FixedReal,
    HeldToMaturityCredit,
    MarketData,
    ReturnModel,
    SampledSeries,
)
from .mortality import FixedAge, LifeTable, MortalityModel
from .model import (
    Asset,
    AssetType,
    Assumptions,
    Contribution,
    Debt,
    DefinedBenefit,
    Expense,
    ExpenseCategory,
    FiscalDrag,
    Frequency,
    Goal,
    Household,
    IncomeSource,
    IncomeType,
    Maturity,
    Person,
    Phase,
)
from .plan import Plan, PlanYear, compile_plan
from .care import CareModel, CareNeed, CarePlan, ImmediateNeedsAnnuity, MeansTest
from .scenario import Gift, OneOffSpend, Scenario
from .serde import dump_household, household_from_dict, household_to_dict, load_household
from .simulation import SimulationResult, project_once, run_monte_carlo
from .strategies import (
    ByAssetTypeMix,
    CashBondLadder,
    GlidePath,
    GuytonKlinger,
    PercentOfPortfolio,
    PostAccessStepUp,
    SpendNominal,
    StandardOrder,
    StaticMix,
    TaxEfficientOrder,
    VariablePercentage,
)
from .tax.iht import UK_IHT, BequestBreakdown, IHTRules, effective_pension_death_rate
from .tax.uk import UK, UKTaxSystem
# Exported because scenario files need it: a retirement date bounded by a
# notice period has to be computed from `as_of`, not typed as a literal, or a
# plan regenerated later stays pinned to when it was first written.
from .timeline import add_months, add_years, age_on

__all__ = [
    "__version__",
    # model
    "Asset", "AssetType", "Assumptions", "Contribution", "Debt", "DefinedBenefit",
    "Expense", "ExpenseCategory", "FiscalDrag", "Frequency", "Goal", "Household",
    "IncomeSource", "IncomeType", "Maturity", "Person", "Phase",
    # market
    "BlockBootstrap", "Blend", "FixedNominal", "FixedReal", "HeldToMaturityCredit",
    "MarketData", "ReturnModel", "SampledSeries",
    # mortality
    "FixedAge", "LifeTable", "MortalityModel",
    # engine
    "Plan", "PlanYear", "compile_plan", "Projection", "YearResult", "project",
    "Scenario", "OneOffSpend", "Gift",
    # care
    "CareModel", "CareNeed", "CarePlan", "ImmediateNeedsAnnuity", "MeansTest", "SimulationResult", "run_monte_carlo", "project_once",
    # strategies
    "ByAssetTypeMix", "CashBondLadder", "GlidePath",
    "GuytonKlinger", "PercentOfPortfolio", "PostAccessStepUp", "VariablePercentage", "SpendNominal", "StandardOrder", "StaticMix", "TaxEfficientOrder",
    # tax
    "UK", "UKTaxSystem", "UK_IHT", "IHTRules", "BequestBreakdown",
    "effective_pension_death_rate",
    # serde
    "dump_household", "household_from_dict", "household_to_dict", "load_household",
    # dates
    "add_months", "add_years", "age_on",
]
