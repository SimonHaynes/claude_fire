"""Compare every withdrawal rule the engine implements, across households that
differ in how much of their money they can actually reach, so the choice of
rule is made from measurements rather than from how sensible each rule sounds.

Three fabricated single-person households, each holding £800,000 and spending
£40,000 a year (£26,000 of it essential), with the State Pension at 67:

  * **Bridge** — 50, £240,000 ISA / £560,000 pension. The pension is locked
    for seven more years, and 7 × £40,000 = £280,000 has to come out of a
    £240,000 ISA, so the bridge binds rather than being a formality.
  * **Thin bridge** — 50, £180,000 ISA / £620,000 pension. Same total, same
    spending, but the accessible share is now smaller than seven years of
    even *essential* spending (£182,000). This household exists to separate
    rules that protect a bridge on purpose from rules that happen to ration
    early for unrelated reasons: any rule keyed off the whole portfolio sees
    an identical £800,000 in both households and cannot tell them apart.
  * **No bridge** — 60, £240,000 ISA / £560,000 pension. Past the Normal
    Minimum Pension Age, so everything is reachable from day one.

£40,000 on £800,000 is a 5% initial draw, tight enough that rules can be told
apart — rules that only differ where nobody fails are not worth choosing
between. The households are not directly comparable to each other (the older
one also has a shorter horizon) but the *ranking of rules within each* is the
question.

Everything is measured against the same 60% equity `StaticMix`, the allocation
REVIEW.md 1.15 found optimal for this kind of household, so allocation is held
constant and only the rule varies.

Read the spend columns beside the success column, always. A rule that spends
a portfolio fraction cannot fail by construction; its failure mode is arriving
at a number the household cannot live on, which shows up as worst-5% spend and
nowhere else.

Run: .venv/bin/python tools/compare_withdrawal_rules.py [n_trials]
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from retireplan import (  # noqa: E402
    VPW,
    Asset,
    AssetType,
    Assumptions,
    BridgeGuardrail,
    BridgeLadder,
    CashBondLadder,
    EndowmentSmoothing,
    Expense,
    ExpenseCategory,
    Frequency,
    GuytonKlinger,
    Household,
    MarketData,
    PercentOfPortfolio,
    Person,
    PostAccessStepUp,
    Ratchet,
    SampledSeries,
    Scenario,
    SpendNominal,
    StandardOrder,
    StaticMix,
    ThreeBucketStrategy,
    VanguardDynamicSpending,
    VariablePercentage,
    compile_plan,
    project,
    run_monte_carlo,
)
from retireplan.tax.uk import UK  # noqa: E402

AS_OF = date(2026, 1, 1)
CACHE = Path(__file__).parent.parent / ".cache" / "withdrawal_rules"
EQUITY_PCT = 0.60

WEALTH = 800_000.0
ISA = 240_000.0
THIN_ISA = 180_000.0
ESSENTIAL = 26_000.0
DISCRETIONARY = 14_000.0

# The six starts every safe-withdrawal-rate study reports on: the crashes and
# the inflation that produced the worst outcomes in the historical record.
WORST_STARTS = (1929, 1937, 1966, 1973, 2000, 2007)


def household(
    age_at_retirement: int, isa: float = ISA,
    essential: float = ESSENTIAL, discretionary: float = DISCRETIONARY,
) -> Household:
    return Household(
        people=[Person("Client", date(AS_OF.year - age_at_retirement, 1, 1))],
        expenses=[
            Expense("Essentials", essential, Frequency.YEARLY, ExpenseCategory.ESSENTIAL),
            Expense("Discretionary", discretionary, Frequency.YEARLY,
                    ExpenseCategory.DISCRETIONARY),
        ],
        assets=[
            Asset("ISA", AssetType.ISA, "Client", isa, returns=SampledSeries("global_equity")),
            Asset("Pension", AssetType.DC_PENSION, "Client", WEALTH - isa,
                  returns=SampledSeries("global_equity")),
        ],
        assumptions=Assumptions(),
    )


def scenario(name: str, withdrawal=None, drawdown=None) -> Scenario:
    return Scenario(
        name,
        retirement_dates={"Client": AS_OF},
        withdrawal=withdrawal,
        drawdown=drawdown or StandardOrder(),
        allocation=StaticMix(growth_pct=EQUITY_PCT),
    )


WITHDRAWAL_RULES = {
    "SpendNominal (4%-rule baseline)": lambda: SpendNominal(),
    "Ratchet (Kitces)": lambda: Ratchet(),
    "PostAccessStepUp": lambda: PostAccessStepUp(),
    "GuytonKlinger": lambda: GuytonKlinger(),
    "PercentOfPortfolio 4%": lambda: PercentOfPortfolio(rate=0.04),
    "VariablePercentage": lambda: VariablePercentage(),
    "VPW (3.5% assumed)": lambda: VPW(),
    "VPW 0% (= 1/N, RMD)": lambda: VPW(expected_real_return=0.0),
    "VanguardDynamicSpending": lambda: VanguardDynamicSpending(),
    "EndowmentSmoothing (Yale)": lambda: EndowmentSmoothing(),
    "BridgeGuardrail → SpendNominal": lambda: BridgeGuardrail(),
    "BridgeGuardrail → GuytonKlinger": lambda: BridgeGuardrail(after=GuytonKlinger()),
    "BridgeGuardrail, cut to essentials": lambda: BridgeGuardrail(floor=0.0),
}

RESERVE_STRATEGIES = {
    "StandardOrder (no reserve)": lambda: StandardOrder(),
    "BridgeLadder (matched, never refilled)": lambda: BridgeLadder(),
    "BridgeLadder covering discretionary too": lambda: BridgeLadder(
        cover=(ESSENTIAL + DISCRETIONARY) / ESSENTIAL
    ),
    "CashBondLadder 3y (refills to full)": lambda: CashBondLadder(target_years=3.0),
    "ThreeBucketStrategy (2y + 5y)": lambda: ThreeBucketStrategy(),
}


def row(label: str, result) -> str:
    bridge = result.bridge_before_access()
    bridge_p10 = f"£{bridge[0]:>10,.0f}" if bridge else " " * 11
    return (
        f"{label:<40} {result.success_probability:>7.1%} "
        f"£{result.median_annual_spend:>8,.0f} "
        f"£{result.worst_case_5pct_min_spend:>8,.0f} "
        f"{bridge_p10} "
        f"£{result.net_bequest_percentiles[50]:>10,.0f}"
    )


HEADER = (
    f"{'':<40} {'success':>7} {'med spend':>9} {'worst 5%':>9} "
    f"{'bridge p10':>11} {'net bequest':>11}"
)


def monte_carlo(label: str, hh: Household, sc: Scenario, n_trials: int) -> None:
    print(row(label, run_monte_carlo(hh, sc, AS_OF, n_trials=n_trials, seed=42,
                                     cache_dir=CACHE)))


def historical_starts(hh: Household, make_rule, data: MarketData, *, reserve=False) -> str:
    """Deterministic walk of each classic worst start year: did the plan fund
    every year, and what was the leanest year's spending?"""
    covered = data.window(["global_equity", "gov_bonds"])
    outcomes = []
    for start in WORST_STARTS:
        sc = (scenario("worst start", SpendNominal(), make_rule()) if reserve
              else scenario("worst start", make_rule()))
        plan = compile_plan(hh, sc, UK, AS_OF)
        years = [y for y in covered if y >= start][:plan.n_years]
        # Recent starts run off the end of the record; hold the last year.
        years += [covered[-1]] * (plan.n_years - len(years))
        projection = project(plan, [data.by_year[y] for y in years])
        living = [y.total_spending for y in projection.years if y.alive]
        failed = projection.first_shortfall_year
        outcomes.append((start, failed, min(living) if living else 0.0))
    survived = sum(1 for _, failed, _ in outcomes if failed is None)
    # How long the money lasted matters when everything fails: a plan that
    # broke in year 8 and one that broke in year 25 are not the same plan.
    lasted = [failed - AS_OF.year for _, failed, _ in outcomes if failed is not None]
    endurance = f"earliest failure yr {min(lasted)}" if lasted else "no failures"
    leanest = min(spend for _, _, spend in outcomes)
    return (f"{survived}/{len(WORST_STARTS)} funded, {endurance:<21} "
            f"leanest year £{leanest:>8,.0f}")


def main() -> None:
    n_trials = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    data = MarketData.load()
    bridging = household(50)
    thin = household(50, isa=THIN_ISA)
    unbridged = household(60)

    print(f"{n_trials} trials, {EQUITY_PCT:.0%} equity, £{WEALTH:,.0f} "
          f"against £{ESSENTIAL + DISCRETIONARY:,.0f}/yr\n")

    for label, hh in ((f"BRIDGE household (50, £{ISA:,.0f} accessible of £{WEALTH:,.0f})", bridging),
                      (f"THIN BRIDGE household (50, £{THIN_ISA:,.0f} accessible)", thin),
                      ("NO-BRIDGE household (60, everything reachable)", unbridged)):
        print(f"--- Withdrawal rules: {label} ---")
        print(HEADER)
        for name, make in WITHDRAWAL_RULES.items():
            monte_carlo(name, hh, scenario(name, make()), n_trials)
        print()

    print("--- Reserve strategies, bridge household, SpendNominal throughout ---")
    print(HEADER)
    for name, make in RESERVE_STRATEGIES.items():
        monte_carlo(name, bridging, scenario(name, SpendNominal(), make()), n_trials)
    print()

    print("--- Bridge household, six classic worst historical starts ---")
    for name, make in WITHDRAWAL_RULES.items():
        print(f"{name:<40} {historical_starts(bridging, make, data)}")
    print()

    # The scenario a cash buffer exists for: if a reserve never earns its
    # keep here, it has no case left to make.
    print("--- Reserve strategies, same six starts, SpendNominal throughout ---")
    for name, make in RESERVE_STRATEGIES.items():
        print(f"{name:<40} {historical_starts(bridging, make, data, reserve=True)}")


if __name__ == "__main__":
    main()
