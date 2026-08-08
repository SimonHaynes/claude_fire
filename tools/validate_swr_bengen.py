"""Validate retireplan's cashflow/withdrawal/allocation mechanics against the
two most-cited published safe-withdrawal-rate studies.

**Bengen (1994), "Determining Withdrawal Rates Using Historical Data"**:
rolling 30+ year retirements starting every year from the 1920s on, a 50/50
(his tested range was 50-75%) US stock/intermediate-government-bond
portfolio, rebalanced annually, withdrawing a fixed *initial* percentage of
the portfolio and then that same real (CPI-adjusted) dollar amount every
year after. He found a "SAFEMAX" of 4.15%: the highest rate that survived
every historical 30-year start year in his data, with the worst case being a
retiree starting in the mid-to-late 1960s, protected only by the 1973-74
crash landing early enough in the sequence to matter and not so early it was
catastrophic.

**The Trinity Study (Cooley, Hubbard & Walz, 1998)**: the same rolling-window
method against Ibbotson data 1925-1995, publishing success rates (percentage
of historical start years in which the portfolio was not exhausted) across a
grid of withdrawal rates, stock/bond mixes and 15/20/25/30-year horizons. The
widely-cited headline: a 30-year, 50/50 portfolio at a 4% real withdrawal
rate succeeds in roughly 95-100% of historical starts (the exact figure
varies slightly by data vintage between re-publications of the study).

## Why this is a real test of the engine, not a new one

Both studies are: (a) a *deterministic* walk of every actual historical
start year -- not a bootstrap -- (b) a portfolio that earns a blended
stock/bond return every year, (c) a withdrawal that is spent regardless of
whether it can be afforded, with "ran out of money" as the only failure mode,
and (d) no tax. Every one of those is already a first-class feature of this
engine:

  * (a) is `project()` fed an explicit historical path instead of
    `BlockBootstrap` -- the engine was already built to take either.
  * (b) is `StaticMix`, unmodified.
  * (c) is `withdrawal=None` ("spends the plan regardless and lets a
    shortfall stand" -- see `strategies/withdrawal.py`), and failure is
    `Projection.succeeded`.
  * (d) falls out for free: an ISA with no other income has nothing to tax.

So this script isn't a bespoke simulation written to match the papers -- it
drives the same `compile_plan`/`project` pair every real scenario uses, with
a household simple enough to read by eye.

## Expected divergence, stated up front

retireplan's data is NYU Stern/Damodaran S&P 500 + 10-year Treasury,
1928-2024 (see `data/us_long_1928_2024.csv`), not Bengen/Trinity's Ibbotson
SBBI 1925/1926-. Same instruments, same real-terms convention, different
vintage of the same underlying market history -- close enough that the
*shape* of the result (SAFEMAX in the low 4%s, the worst cohort landing in
the mid-to-late 1960s) is a real check, not close enough to expect the
figures to the second decimal place.

Run: .venv/bin/python tools/validate_swr_bengen.py
"""
from __future__ import annotations

import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from retireplan import (  # noqa: E402
    Asset,
    AssetType,
    Assumptions,
    Expense,
    ExpenseCategory,
    Frequency,
    Household,
    Person,
    Phase,
    SampledSeries,
    Scenario,
    StaticMix,
    compile_plan,
    project,
)
from retireplan.market import MarketData  # noqa: E402
from retireplan.tax.uk import UK  # noqa: E402

AS_OF = date(2026, 1, 1)
RETIREE_DOB = date(AS_OF.year - 65, AS_OF.month, AS_OF.day)  # age 65 at AS_OF
HORIZON_YEARS = 30  # Assumptions.life_expectancy_age default (95) - 65
PORTFOLIO = 1_000_000.0
EQUITY_PCT = 0.50


def build_plan(rate: float):
    """A single ISA, no income, no tax -- fixed real withdrawal, 50/50 mix."""
    household = Household(
        people=[Person("Retiree", RETIREE_DOB)],
        expenses=[
            Expense(
                "Fixed real withdrawal", PORTFOLIO * rate, Frequency.YEARLY,
                ExpenseCategory.ESSENTIAL, phase=Phase.RETIREMENT,
            ),
        ],
        assets=[
            Asset(
                "Portfolio (ISA)", AssetType.ISA, "Retiree", PORTFOLIO,
                returns=SampledSeries("global_equity"),
            ),
        ],
        assumptions=Assumptions(),
    )
    scenario = Scenario(
        f"SWR {rate:.3%}",
        retirement_dates={"Retiree": AS_OF},
        withdrawal=None,  # spend the plan regardless; a shortfall is the failure signal
        allocation=StaticMix(growth_pct=EQUITY_PCT),
    )
    return compile_plan(household, scenario, UK, AS_OF)


def historical_windows(data: MarketData, horizon: int) -> list[tuple[int, ...]]:
    """Every real (non-bootstrapped) contiguous `horizon`-year window the data covers."""
    window = data.window(["global_equity", "gov_bonds"])
    years = sorted(window)
    out = []
    for i in range(len(years) - horizon + 1):
        span = years[i:i + horizon]
        if span[-1] - span[0] == horizon - 1:  # contiguous, no gap
            out.append(span)
    return out


def run_cohort(plan, data: MarketData, start_years: tuple[int, ...]) -> bool:
    path = [data.by_year[y] for y in start_years]
    return project(plan, path).succeeded


def success_rate(rate: float, data: MarketData, windows: list[tuple[int, ...]]) -> tuple[float, list[int]]:
    plan = build_plan(rate)
    failures = []
    for span in windows:
        if not run_cohort(plan, data, span):
            failures.append(span[0])
    return 1 - len(failures) / len(windows), failures


def find_safemax(data: MarketData, windows: list[tuple[int, ...]], lo=0.02, hi=0.08, tol=0.0005) -> float:
    """Highest rate at which every historical cohort in `windows` survives."""
    # lo must succeed everywhere, hi must fail somewhere, else bisection is meaningless.
    assert success_rate(lo, data, windows)[0] == 1.0, "lo bound already fails somewhere"
    assert success_rate(hi, data, windows)[0] < 1.0, "hi bound doesn't fail anywhere"
    while hi - lo > tol:
        mid = (lo + hi) / 2
        rate, _ = success_rate(mid, data, windows)
        if rate == 1.0:
            lo = mid
        else:
            hi = mid
    return lo


def main() -> None:
    data = MarketData.load()
    windows = historical_windows(data, HORIZON_YEARS)
    first_years = [w[0] for w in windows]
    print(f"Data: global_equity + gov_bonds real returns, {data.window(['global_equity','gov_bonds'])[0]}"
          f"-{data.window(['global_equity','gov_bonds'])[-1]} ({len(data.window(['global_equity','gov_bonds']))} years)")
    print(f"{len(windows)} contiguous {HORIZON_YEARS}-year historical starts: "
          f"{first_years[0]}-{first_years[-1]}")
    print()

    print("--- Trinity-style check: fixed 4% withdrawal, 50/50, 30-year horizon ---")
    rate, failures = success_rate(0.04, data, windows)
    print(f"retireplan success rate: {rate:.1%}  ({len(windows) - len(failures)}/{len(windows)} cohorts)")
    print(f"Published (Trinity, various re-runs): ~95-100%")
    if failures:
        print(f"Failing start years: {failures}")
    print()

    print("--- Bengen-style check: SAFEMAX at 50/50 ---")
    safemax = find_safemax(data, windows)
    print(f"retireplan SAFEMAX (bisected to 0.05%): {safemax:.2%}")
    print(f"Published (Bengen 1994): 4.15%")
    rate_at_safemax, _ = success_rate(safemax, data, windows)
    _, failures_above = success_rate(safemax + 0.0005, data, windows)
    print(f"Binding (worst) cohort just above SAFEMAX starts: {sorted(failures_above)}")
    print(f"Published worst cohort: mid-to-late 1960s")
    print()

    print("--- Sensitivity: success rate by rate, 50/50, 30-year ---")
    for pct in [0.030, 0.035, 0.040, 0.0415, 0.045, 0.050, 0.055]:
        rate, failures = success_rate(pct, data, windows)
        marker = f"  worst starts: {sorted(failures)[:5]}{'...' if len(failures) > 5 else ''}" if failures else ""
        print(f"  {pct:.2%}: {rate:.1%}{marker}")


if __name__ == "__main__":
    main()
