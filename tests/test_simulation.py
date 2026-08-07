"""Monte Carlo aggregation, determinism, and the result cache."""
from __future__ import annotations

from datetime import date

import pytest

from retireplan import (
    Asset,
    AssetType,
    Assumptions,
    Expense,
    ExpenseCategory,
    GuytonKlinger,
    FixedReal,
    Frequency,
    GuytonKlinger,
    Household,
    MarketData,
    PensionAccess,
    Person,
    SampledSeries,
    Scenario,
    SpendNominal,
    TaxEfficientOrder,
    run_monte_carlo,
)
from retireplan.simulation import cache_key, percentile

AS_OF = date(2026, 1, 1)


@pytest.fixture
def volatile_market() -> MarketData:
    """Alternating good and bad years, so outcomes genuinely differ by path."""
    return MarketData(by_year={
        y: {"global_equity": 0.25 if y % 2 else -0.15, "gov_bonds": 0.01,
            "inflation": 0.02, "short_corporate": 0.0}
        for y in range(2000, 2020)
    })


@pytest.fixture
def household() -> Household:
    return Household(
        people=[Person("A", date(1960, 1, 1))],
        expenses=[
            Expense("Living", 30_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL),
            Expense("Fun", 12_000, Frequency.YEARLY, ExpenseCategory.DISCRETIONARY),
        ],
        assets=[
            Asset("ISA", AssetType.ISA, "A", 250_000, returns=SampledSeries("global_equity")),
            Asset("Pension", AssetType.DC_PENSION, "A", 350_000,
                  returns=SampledSeries("global_equity")),
        ],
        assumptions=Assumptions(life_expectancy_age=85, state_pension_age=68),
    )


@pytest.fixture
def scenario() -> Scenario:
    return Scenario("retire now", retirement_dates={"A": AS_OF},
                    withdrawal=GuytonKlinger())


class TestPercentile:
    def test_endpoints_and_median(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert percentile(values, 0) == 1.0
        assert percentile(values, 100) == 5.0
        assert percentile(values, 50) == 3.0

    def test_interpolates(self):
        assert percentile([0.0, 10.0], 25) == pytest.approx(2.5)

    def test_does_not_require_sorted_input(self):
        assert percentile([5.0, 1.0, 3.0], 50) == 3.0

    def test_empty_sample_is_an_error(self):
        with pytest.raises(ValueError):
            percentile([], 50)


class TestRun:
    def test_is_deterministic_for_a_seed(self, household, scenario, volatile_market):
        a = run_monte_carlo(household, scenario, AS_OF, data=volatile_market, n_trials=50, seed=1)
        b = run_monte_carlo(household, scenario, AS_OF, data=volatile_market, n_trials=50, seed=1)
        assert a.success_probability == b.success_probability
        assert a.bequest_percentiles == b.bequest_percentiles

    def test_different_seeds_differ(self, household, scenario, volatile_market):
        a = run_monte_carlo(household, scenario, AS_OF, data=volatile_market, n_trials=50, seed=1)
        b = run_monte_carlo(household, scenario, AS_OF, data=volatile_market, n_trials=50, seed=2)
        assert a.bequest_percentiles[50] != b.bequest_percentiles[50]

    def test_success_probability_is_a_probability(self, household, scenario, volatile_market):
        result = run_monte_carlo(household, scenario, AS_OF, data=volatile_market,
                                 n_trials=40, seed=3)
        assert 0.0 <= result.success_probability <= 1.0

    def test_percentiles_are_ordered(self, household, scenario, volatile_market):
        result = run_monte_carlo(household, scenario, AS_OF, data=volatile_market,
                                 n_trials=60, seed=4)
        for year in range(result.n_years):
            assert result.wealth_percentiles[10][year] <= result.wealth_percentiles[50][year]
            assert result.wealth_percentiles[50][year] <= result.wealth_percentiles[90][year]
        assert result.bequest_percentiles[10] <= result.bequest_percentiles[90]

    def test_reports_the_sample_window_it_used(self, household, scenario, volatile_market):
        result = run_monte_carlo(household, scenario, AS_OF, data=volatile_market,
                                 n_trials=10, seed=5)
        assert result.sample_years == 20
        assert (result.sample_first_year, result.sample_last_year) == (2000, 2019)

    def test_isa_percentiles_track_the_isa_alone(self, household, scenario, volatile_market):
        result = run_monte_carlo(household, scenario, AS_OF, data=volatile_market,
                                 n_trials=20, seed=6)
        assert result.isa_percentiles[50][0] <= 250_000 * 1.30
        for year in range(result.n_years):
            assert result.isa_percentiles[50][year] <= result.wealth_percentiles[50][year] + 1e-6

    def test_a_hopeless_plan_fails_and_a_rich_one_does_not(self, volatile_market):
        broke = Household(
            people=[Person("A", date(1960, 1, 1))],
            expenses=[Expense("Living", 50_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[Asset("ISA", AssetType.ISA, "A", 20_000, returns=FixedReal(0.0))],
            assumptions=Assumptions(life_expectancy_age=80, state_pension_age=99),
        )
        rich = Household(
            people=[Person("A", date(1960, 1, 1))],
            expenses=[Expense("Living", 20_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[Asset("ISA", AssetType.ISA, "A", 5_000_000, returns=FixedReal(0.0))],
            assumptions=Assumptions(life_expectancy_age=80, state_pension_age=99),
        )
        scenario = Scenario("retired", retirement_dates={"A": AS_OF}, withdrawal=SpendNominal())
        assert run_monte_carlo(broke, scenario, AS_OF, data=volatile_market,
                               n_trials=10, seed=7).success_probability == 0.0
        assert run_monte_carlo(rich, scenario, AS_OF, data=volatile_market,
                               n_trials=10, seed=7).success_probability == 1.0

    def test_a_stateful_strategy_is_reset_between_trials(self, household, volatile_market):
        """One shared strategy object must not leak state across trials —
        otherwise a run's results depend on how many trials preceded it."""
        shared = GuytonKlinger()
        scenario = Scenario("gk", retirement_dates={"A": AS_OF}, withdrawal=shared)
        first = run_monte_carlo(household, scenario, AS_OF, data=volatile_market,
                                n_trials=25, seed=8)
        second = run_monte_carlo(household, scenario, AS_OF, data=volatile_market,
                                 n_trials=25, seed=8)
        assert first.bequest_percentiles[50] == pytest.approx(second.bequest_percentiles[50])


class TestBridge:
    """`bridge_percentiles` / `pension_access_year` — "how close did the
    bridge come to running out" needs a year to read it at and a series that
    is not just the ISA, now that a GIA can carry part of the bridge too."""

    def test_access_year_is_when_the_dc_pension_actually_unlocks(self, volatile_market):
        household = Household(
            people=[Person("A", date(1969, 6, 15))],  # turns 57 partway through 2026
            expenses=[Expense("Living", 20_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[
                Asset("ISA", AssetType.ISA, "A", 100_000, returns=SampledSeries("global_equity")),
                Asset("Pension", AssetType.DC_PENSION, "A", 300_000,
                      returns=SampledSeries("global_equity")),
            ],
            assumptions=Assumptions(life_expectancy_age=70, state_pension_age=99),
        )
        scenario = Scenario("retired", retirement_dates={"A": AS_OF}, withdrawal=SpendNominal())
        result = run_monte_carlo(household, scenario, AS_OF, data=volatile_market,
                                 n_trials=20, seed=9)
        assert result.pension_access_year == 2026

    def test_no_dc_pension_means_no_access_year(self, volatile_market):
        household = Household(
            people=[Person("A", date(1960, 1, 1))],
            expenses=[Expense("Living", 20_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[Asset("ISA", AssetType.ISA, "A", 200_000, returns=SampledSeries("global_equity"))],
            assumptions=Assumptions(life_expectancy_age=70, state_pension_age=99),
        )
        scenario = Scenario("retired", retirement_dates={"A": AS_OF}, withdrawal=SpendNominal())
        result = run_monte_carlo(household, scenario, AS_OF, data=volatile_market,
                                 n_trials=10, seed=10)
        assert result.pension_access_year is None
        assert result.bridge_at_access() is None

    def test_bridge_includes_gia_and_cash_but_excludes_pension(self, household, scenario, volatile_market):
        result = run_monte_carlo(household, scenario, AS_OF, data=volatile_market,
                                 n_trials=20, seed=11)
        for year in range(result.n_years):
            # The bridge can never exceed total investable wealth (which still
            # includes the pension), and — since this household's only
            # investable assets are the ISA and the pension — must equal the
            # ISA level exactly (there's no cash or GIA balance to add).
            assert result.bridge_percentiles[50][year] == pytest.approx(
                result.isa_percentiles[50][year], abs=1.0
            )
            assert result.bridge_percentiles[50][year] <= result.investable_percentiles[50][year] + 1e-6

    def test_bridge_at_access_returns_an_ordered_10_90_range(self, household, scenario, volatile_market):
        result = run_monte_carlo(household, scenario, AS_OF, data=volatile_market,
                                 n_trials=100, seed=12)
        low, high = result.bridge_at_access()
        assert low <= high
        assert low == pytest.approx(result.bridge_at(result.pension_access_year, 10))
        assert high == pytest.approx(result.bridge_at(result.pension_access_year, 90))

    def test_bridge_before_access_shows_the_drain_that_at_access_hides(self, flat_market):
        """A real finding, not a hypothetical: a strategy that draws pension
        aggressively once it unlocks (`TaxEfficientOrder`) can recycle
        surplus back into the ISA the *same* plan-year access begins,
        refilling a bridge that ran dry the year before -- including for a
        trial that already failed that year. `bridge_at_access()` cannot see
        the drain because it reads the year *after* the refill has already
        happened; `bridge_before_access()` must."""
        household = Household(
            people=[Person("A", date(1970, 3, 1))],  # 57 during the second plan-year
            expenses=[Expense("Living", 40_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[
                Asset("ISA", AssetType.ISA, "A", 30_000, returns=FixedReal(0.0)),
                Asset("Pension", AssetType.DC_PENSION, "A", 1_000_000, returns=FixedReal(0.0)),
            ],
            assumptions=Assumptions(life_expectancy_age=60),
        )
        scenario = Scenario("retired", retirement_dates={"A": AS_OF}, withdrawal=SpendNominal(),
                            drawdown=TaxEfficientOrder(fill_to=50_270.0))
        result = run_monte_carlo(household, scenario, AS_OF, data=flat_market, n_trials=5, seed=1)

        assert result.pension_access_year == 2027
        before_low, before_high = result.bridge_before_access()
        at_low, at_high = result.bridge_at_access()
        assert before_low == before_high == pytest.approx(0.0)   # fully drained, £40k need on a £30k ISA
        assert at_low > 0.0                                       # already refilled by the same year's recycling

    def test_bridge_before_access_is_none_with_nothing_to_bridge(self, household, scenario, volatile_market):
        """The `household`/`scenario` fixtures retire someone already 66 at
        `AS_OF` -- pension access year equals the first plan-year, so there
        is no "year before" to report."""
        result = run_monte_carlo(household, scenario, AS_OF, data=volatile_market,
                                 n_trials=10, seed=13)
        assert result.pension_access_year == result.first_year
        assert result.bridge_before_access() is None


class TestAssetTypeBreakdown:
    """`asset_type_percentiles` -- the split behind the report's asset-mix
    table, keyed by `AssetType.value`."""

    def test_includes_every_type_actually_present(self, household, scenario, volatile_market):
        result = run_monte_carlo(household, scenario, AS_OF, data=volatile_market,
                                 n_trials=20, seed=14)
        # `household` has an ISA and a DC pension; every household also gets
        # a synthetic per-person GIA and a cash reserve, present even at zero.
        assert set(result.asset_type_percentiles) == {"isa", "dc_pension", "gia", "cash"}

    def test_percentiles_are_ordered_for_every_type_and_year(self, household, scenario, volatile_market):
        result = run_monte_carlo(household, scenario, AS_OF, data=volatile_market,
                                 n_trials=40, seed=15)
        for by_percentile in result.asset_type_percentiles.values():
            for year in range(result.n_years):
                assert by_percentile[10][year] <= by_percentile[50][year] <= by_percentile[90][year]

    def test_asset_type_at_matches_direct_access(self, household, scenario, volatile_market):
        result = run_monte_carlo(household, scenario, AS_OF, data=volatile_market,
                                 n_trials=20, seed=16)
        year = result.first_year + 2
        assert result.asset_type_at("isa", year, 50) == pytest.approx(
            result.asset_type_percentiles["isa"][50][2]
        )

    def test_a_flat_property_asset_never_moves(self, volatile_market):
        household = Household(
            people=[Person("A", date(1966, 1, 1))],
            expenses=[Expense("Living", 20_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[
                Asset("House", AssetType.PROPERTY, "joint", 400_000, returns=FixedReal(0.0)),
                Asset("ISA", AssetType.ISA, "A", 500_000, returns=SampledSeries("global_equity")),
            ],
            assumptions=Assumptions(life_expectancy_age=75, state_pension_age=99),
        )
        scenario = Scenario("retired", retirement_dates={"A": AS_OF}, withdrawal=SpendNominal())
        result = run_monte_carlo(household, scenario, AS_OF, data=volatile_market,
                                 n_trials=20, seed=17)
        property_series = result.asset_type_percentiles["property"]
        for p in (5, 50, 95):
            assert all(v == pytest.approx(400_000) for v in property_series[p])

    def test_the_types_sum_no_higher_than_total_wealth(self, household, scenario, volatile_market):
        """A per-trial invariant (types sum exactly to that trial's wealth)
        does not survive taking percentiles independently -- but the median
        of each type still cannot individually exceed the median of the
        whole, since no type can be a negative share of it."""
        result = run_monte_carlo(household, scenario, AS_OF, data=volatile_market,
                                 n_trials=30, seed=18)
        for year in range(result.n_years):
            for by_percentile in result.asset_type_percentiles.values():
                assert by_percentile[50][year] <= result.wealth_percentiles[50][year] + 1e-6


class TestCaching:
    def test_cached_result_matches_the_computed_one(self, household, scenario,
                                                    volatile_market, tmp_path):
        first = run_monte_carlo(household, scenario, AS_OF, data=volatile_market,
                                n_trials=30, seed=9, cache_dir=tmp_path)
        assert list(tmp_path.glob("*.json"))
        second = run_monte_carlo(household, scenario, AS_OF, data=volatile_market,
                                 n_trials=30, seed=9, cache_dir=tmp_path)
        assert first == second

    def test_key_changes_with_the_scenario(self, household, volatile_market):
        from retireplan.tax.uk import UK

        base = Scenario("s", retirement_dates={"A": AS_OF}, withdrawal=GuytonKlinger())
        changed = Scenario("s", retirement_dates={"A": AS_OF},
                           withdrawal=GuytonKlinger(guardrail=0.30))
        args = (UK, AS_OF, 100, 5, 1, volatile_market)
        assert cache_key(household, base, *args) != cache_key(household, changed, *args)

    def test_key_changes_with_pension_access(self, household, volatile_market):
        """`pension_access` changes what `cashflow.py` actually does (a real
        lump sum leaves the pension, or every withdrawal is split 25/75) but
        was missing from the cache-key payload — two scenarios differing
        only in this flag silently shared one cached result. Caught while
        comparing PCLS on/off for a real client."""
        from retireplan.tax.uk import UK

        off = Scenario("s", retirement_dates={"A": AS_OF},
                       withdrawal=GuytonKlinger(), pension_access=PensionAccess.NONE)
        on = Scenario("s", retirement_dates={"A": AS_OF},
                      withdrawal=GuytonKlinger(), pension_access=PensionAccess.PCLS)
        args = (UK, AS_OF, 100, 5, 1, volatile_market)
        assert cache_key(household, off, *args) != cache_key(household, on, *args)

    def test_key_changes_with_income_annuity(self, household, volatile_market):
        from retireplan import IncomeAnnuity
        from retireplan.tax.uk import UK

        off = Scenario("s", retirement_dates={"A": AS_OF}, withdrawal=GuytonKlinger())
        on = Scenario("s", retirement_dates={"A": AS_OF}, withdrawal=GuytonKlinger(),
                      income_annuity=IncomeAnnuity(enabled=True, fraction_of_pot=0.3))
        args = (UK, AS_OF, 100, 5, 1, volatile_market)
        assert cache_key(household, off, *args) != cache_key(household, on, *args)

    def test_key_is_stable_across_calls(self, household, scenario, volatile_market):
        """A key that drifts between identical calls silently disables the cache."""
        from retireplan.tax.uk import UK

        args = (UK, AS_OF, 100, 5, 1, volatile_market)
        assert cache_key(household, scenario, *args) == cache_key(household, scenario, *args)

    def test_key_is_unaffected_by_accumulated_strategy_state(self, household, volatile_market):
        """Runtime state must stay out of the key — only configuration counts."""
        from retireplan.tax.uk import UK

        strategy = GuytonKlinger()
        scenario = Scenario("gk", retirement_dates={"A": AS_OF}, withdrawal=strategy)
        args = (UK, AS_OF, 100, 5, 1, volatile_market)
        before = cache_key(household, scenario, *args)
        strategy.multiplier = 0.42          # as a run would leave it
        strategy.initial_rate = 0.05
        assert cache_key(household, scenario, *args) == before

    def test_key_changes_with_the_market_data(self, household, scenario, volatile_market):
        from retireplan.tax.uk import UK

        other = MarketData(by_year={y: {"global_equity": 0.01, "gov_bonds": 0.0,
                                        "inflation": 0.0} for y in range(2000, 2020)})
        args = (UK, AS_OF, 100, 5, 1)
        assert cache_key(household, scenario, *args, volatile_market) != \
            cache_key(household, scenario, *args, other)

    def test_non_dataclass_strategy_is_rejected(self, household, volatile_market):
        """Guards the bug that once disabled this cache entirely: a plain class
        falls back to an id()-based repr, which changes every process."""
        from retireplan.strategies.withdrawal import WithdrawalStrategy
        from retireplan.tax.uk import UK

        class Sneaky(WithdrawalStrategy):       # deliberately not a dataclass
            def decide(self, ctx):
                return ctx.nominal_discretionary

        scenario = Scenario("s", retirement_dates={"A": AS_OF}, withdrawal=Sneaky())
        with pytest.raises(TypeError, match="dataclass"):
            cache_key(household, scenario, UK, AS_OF, 100, 5, 1, volatile_market)
