"""The three strategy axes, and that they compose."""
from __future__ import annotations

from datetime import date

import pytest

from retireplan import (
    Asset,
    AssetType,
    Assumptions,
    ByAssetTypeMix,
    CashBondLadder,
    Expense,
    ExpenseCategory,
    FixedReal,
    Frequency,
    GlidePath,
    GuytonKlinger,
    Household,
    MarketData,
    Person,
    PostAccessStepUp,
    SampledSeries,
    Scenario,
    SpendNominal,
    StandardOrder,
    StaticMix,
    ThreeBucketStrategy,
    compile_plan,
    project,
)
from retireplan.strategies.withdrawal import WithdrawalContext
from retireplan.tax.uk import UK

AS_OF = date(2026, 1, 1)


def context(**overrides) -> WithdrawalContext:
    """A withdrawal context whose affordability rule is stated by the test."""
    affordable_up_to = overrides.pop("affordable_up_to", float("inf"))
    defaults = dict(
        year_index=0,
        is_retired=True,
        dc_accessible=True,
        nominal_discretionary=10_000.0,
        fixed_spend=20_000.0,
        net_income=5_000.0,
        portfolio_value=1_000_000.0,
        growth_return=0.05,
        oldest_age=65,
        shortfall_for=lambda amount: max(0.0, amount - affordable_up_to),
    )
    defaults.update(overrides)
    return WithdrawalContext(**defaults)


class TestWithdrawalStrategies:
    def test_spend_nominal_ignores_affordability(self):
        assert SpendNominal().decide(context(affordable_up_to=0)) == 10_000.0

    def test_guyton_klinger_cuts_when_the_withdrawal_rate_climbs(self):
        strategy = GuytonKlinger()
        strategy.reset()
        strategy.decide(context(portfolio_value=1_000_000))   # sets the baseline rate
        before = strategy.multiplier
        strategy.decide(context(portfolio_value=300_000))     # same spend, far smaller pot
        assert strategy.multiplier < before

    def test_guyton_klinger_raises_after_a_good_run(self):
        strategy = GuytonKlinger()
        strategy.reset()
        strategy.decide(context(portfolio_value=1_000_000))
        strategy.decide(context(portfolio_value=5_000_000, growth_return=0.20))
        assert strategy.multiplier > 1.0

    def test_guyton_klinger_does_not_raise_into_a_falling_market(self):
        strategy = GuytonKlinger()
        strategy.reset()
        strategy.decide(context(portfolio_value=1_000_000))
        strategy.decide(context(portfolio_value=5_000_000, growth_return=-0.20))
        assert strategy.multiplier == pytest.approx(1.0)

    def test_guyton_klinger_adjustments_persist(self):
        strategy = GuytonKlinger()
        strategy.reset()
        strategy.decide(context(portfolio_value=1_000_000))
        strategy.decide(context(portfolio_value=300_000))
        cut = strategy.multiplier
        strategy.decide(context(portfolio_value=1_000_000))
        assert strategy.multiplier <= cut * 1.11  # carried forward, not reset

    def test_reset_clears_state_between_trials(self):
        strategy = GuytonKlinger()
        strategy.decide(context(portfolio_value=1_000_000))
        strategy.decide(context(portfolio_value=200_000))
        strategy.reset()
        assert strategy.multiplier == 1.0
        assert strategy.initial_rate is None

    def test_step_up_waits_for_pension_access(self):
        strategy = PostAccessStepUp(step_up=1.5, surplus_years=1.0)
        strategy.reset()
        locked = strategy.decide(context(dc_accessible=False))
        assert locked == pytest.approx(10_000.0)
        unlocked = strategy.decide(context(dc_accessible=True))
        assert unlocked == pytest.approx(15_000.0)

    def test_step_up_waits_for_a_genuine_surplus(self):
        strategy = PostAccessStepUp(step_up=1.5, surplus_years=25.0)
        strategy.reset()
        # A £100k pot against £30k of annual need is nowhere near 25 years.
        assert strategy.decide(context(portfolio_value=100_000)) == pytest.approx(10_000.0)

    def test_step_up_is_permanent(self):
        strategy = PostAccessStepUp(step_up=1.5, surplus_years=1.0)
        strategy.reset()
        strategy.decide(context())
        assert strategy.stepped_up
        strategy.decide(context(portfolio_value=1.0))  # surplus gone
        assert strategy.stepped_up

    def test_no_strategy_cuts_essential_spending(self):
        """Every strategy flexes only the discretionary figure it is handed."""
        for strategy in (SpendNominal(), GuytonKlinger(), PostAccessStepUp()):
            strategy.reset()
            spend = strategy.decide(context(affordable_up_to=0))
            assert spend <= 10_000.0  # never exceeds nominal discretionary
            assert spend >= 0.0


class TestAllocationStrategies:
    def _asset(self, key="global_equity", type_=AssetType.ISA):
        return Asset("X", type_, "A", 100.0, returns=SampledSeries(key))

    def test_static_mix_blends_growth_and_safe(self):
        market = {"global_equity": 0.10, "gov_bonds": 0.02}
        blended = StaticMix(0.6).real_return(self._asset(), market, 0)
        assert blended == pytest.approx(0.6 * 0.10 + 0.4 * 0.02)

    def test_static_mix_at_full_growth_is_a_passthrough(self):
        market = {"global_equity": 0.10, "gov_bonds": 0.02}
        assert StaticMix(1.0).real_return(self._asset(), market, 0) == pytest.approx(0.10)

    def test_static_mix_ignores_assets_it_does_not_track(self):
        asset = Asset("Bond", AssetType.ISA, "A", 100.0, returns=FixedReal(0.03))
        assert StaticMix(0.6).real_return(asset, {"global_equity": 0.1, "gov_bonds": 0.0}, 0) is None

    def test_by_asset_type_targets_only_the_named_type(self):
        market = {"global_equity": 0.10, "gov_bonds": 0.0}
        strategy = ByAssetTypeMix({AssetType.ISA: 0.0})
        isa = strategy.real_return(self._asset(type_=AssetType.ISA), market, 0)
        pension = strategy.real_return(self._asset(type_=AssetType.DC_PENSION), market, 0)
        assert isa == pytest.approx(0.0)  # de-risked
        assert pension is None            # left on its own return model

    def test_by_asset_type_leaves_unnamed_assets_alone_by_default(self):
        """Regression: defaulting to 1.0 silently re-priced a house and a
        fixed-rate bond as equities, inflating a projected estate by ~two thirds."""
        market = {"global_equity": 0.10, "gov_bonds": 0.0}
        strategy = ByAssetTypeMix({AssetType.ISA: 0.0})
        house = Asset("House", AssetType.PROPERTY, "A", 750_000, returns=FixedReal(0.02))
        assert strategy.real_return(house, market, 0) is None

    def test_by_asset_type_can_still_override_everything_explicitly(self):
        market = {"global_equity": 0.10, "gov_bonds": 0.0}
        strategy = ByAssetTypeMix({AssetType.ISA: 0.0}, default_growth_pct=1.0)
        house = Asset("House", AssetType.PROPERTY, "A", 750_000, returns=FixedReal(0.02))
        assert strategy.real_return(house, market, 0) == pytest.approx(0.10)

    def test_glide_path_de_risks_over_time(self):
        market = {"global_equity": 0.10, "gov_bonds": 0.0}
        strategy = GlidePath(start_pct=1.0, end_pct=0.0, years=10)
        assert strategy.real_return(self._asset(), market, 0) == pytest.approx(0.10)
        assert strategy.real_return(self._asset(), market, 5) == pytest.approx(0.05)
        assert strategy.real_return(self._asset(), market, 10) == pytest.approx(0.0)
        assert strategy.real_return(self._asset(), market, 50) == pytest.approx(0.0)


class TestDrawdownStrategies:
    def _household(self):
        return Household(
            people=[Person("A", date(1960, 1, 1))],
            expenses=[Expense("Living", 30_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[
                Asset("ISA", AssetType.ISA, "A", 200_000, returns=SampledSeries("global_equity")),
                Asset("Pension", AssetType.DC_PENSION, "A", 300_000,
                      returns=SampledSeries("global_equity")),
            ],
            assumptions=Assumptions(life_expectancy_age=68, state_pension_age=99),
        )

    def _run(self, strategy, market_row, years=8):
        household = self._household()
        scenario = Scenario("retired", retirement_dates={"A": AS_OF},
                            withdrawal=SpendNominal(), drawdown=strategy)
        plan = compile_plan(household, scenario, UK, AS_OF)
        return project(plan, [market_row] * plan.n_years)

    def test_standard_order_spends_the_isa_before_the_pension(self):
        flat = {"global_equity": 0.0, "gov_bonds": 0.0, "inflation": 0.0}
        projection = self._run(StandardOrder(), flat)
        assert projection.years[0].isa_withdrawn > 0
        assert projection.years[0].dc_withdrawn_gross == 0.0

    def test_cash_ladder_seeds_itself_from_the_isa(self):
        flat = {"global_equity": 0.0, "gov_bonds": 0.0, "inflation": 0.0}
        projection = self._run(CashBondLadder(target_years=3.0), flat)
        ladder = projection.years[0].balances["__ladder_reserve"]
        assert ladder > 0
        assert ladder <= 3 * 30_000

    def test_cash_ladder_is_drawn_before_the_isa(self):
        crash = {"global_equity": -0.30, "gov_bonds": 0.0, "inflation": 0.0}
        projection = self._run(CashBondLadder(target_years=3.0), crash)
        # Year 1 seeds the ladder; year 2 should draw it rather than sell equities.
        assert projection.years[1].balances["__ladder_reserve"] < \
            projection.years[0].balances["__ladder_reserve"]

    def test_ladder_reset_clears_the_seeded_flag(self):
        ladder = CashBondLadder()
        ladder.seeded = True
        ladder.reset()
        assert ladder.seeded is False


class TestThreeBucketStrategy:
    def _household(self):
        return Household(
            people=[Person("A", date(1960, 1, 1))],
            expenses=[Expense("Living", 30_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[Asset("ISA", AssetType.ISA, "A", 1_000_000, returns=SampledSeries("global_equity"))],
            assumptions=Assumptions(life_expectancy_age=68, state_pension_age=99),
        )

    def _run(self, market_rows, cash_years=2.0, bond_years=5.0):
        household = self._household()
        scenario = Scenario("retired", retirement_dates={"A": AS_OF}, withdrawal=SpendNominal(),
                            drawdown=ThreeBucketStrategy(cash_years=cash_years, bond_years=bond_years))
        plan = compile_plan(household, scenario, UK, AS_OF)
        path = market_rows if len(market_rows) >= plan.n_years else market_rows + [market_rows[-1]] * (plan.n_years - len(market_rows))
        return project(plan, path)

    def test_seeds_both_buckets_from_the_isa_at_retirement(self):
        flat = [{"global_equity": 0.0, "gov_bonds": 0.0, "inflation": 0.0}] * 3
        first = self._run(flat).years[0]
        assert first.balances["__cash_reserve"] == pytest.approx(2 * 30_000)
        assert first.balances["__bond_reserve"] == pytest.approx(5 * 30_000)

    def test_bond_bucket_refills_cash_every_year_regardless_of_equities(self):
        """The defining difference from CashBondLadder: cash is topped up
        from bonds unconditionally, not gated on the market being up."""
        crash = [{"global_equity": 0.0, "gov_bonds": 0.0, "inflation": 0.0},
                 {"global_equity": -0.30, "gov_bonds": 0.0, "inflation": 0.0},
                 {"global_equity": -0.30, "gov_bonds": 0.0, "inflation": 0.0}]
        years = self._run(crash).years
        # Cash stays topped up to target even through two equity-crash years.
        assert years[1].balances["__cash_reserve"] == pytest.approx(2 * 30_000, abs=1.0)
        assert years[2].balances["__cash_reserve"] == pytest.approx(2 * 30_000, abs=1.0)
        # ...funded by the bond bucket actually shrinking to pay for it.
        assert years[2].balances["__bond_reserve"] < years[0].balances["__bond_reserve"]

    def test_bond_bucket_only_refills_from_equity_when_equity_is_up(self):
        down_then_up = [{"global_equity": 0.0, "gov_bonds": 0.0, "inflation": 0.0},
                        {"global_equity": -0.20, "gov_bonds": 0.0, "inflation": 0.0},
                        {"global_equity": 0.20, "gov_bonds": 0.0, "inflation": 0.0}]
        years = self._run(down_then_up).years
        target = 5 * 30_000
        # After the down year, the bond bucket is not topped back up...
        assert years[1].balances["__bond_reserve"] < target
        # ...but it is, the moment equities recover.
        assert years[2].balances["__bond_reserve"] == pytest.approx(target, abs=1.0)

    def test_series_keys_declares_gov_bonds(self):
        assert ThreeBucketStrategy().series_keys() == frozenset({"gov_bonds"})


class TestComposition:
    def test_all_three_axes_can_be_combined(self):
        """The point of separating them: any combination must run."""
        household = Household(
            people=[Person("A", date(1960, 1, 1))],
            expenses=[Expense("Living", 25_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL),
                      Expense("Fun", 10_000, Frequency.YEARLY, ExpenseCategory.DISCRETIONARY)],
            assets=[
                Asset("ISA", AssetType.ISA, "A", 300_000, returns=SampledSeries("global_equity")),
                Asset("Pension", AssetType.DC_PENSION, "A", 400_000,
                      returns=SampledSeries("global_equity")),
            ],
            assumptions=Assumptions(life_expectancy_age=70, state_pension_age=99),
        )
        scenario = Scenario(
            "everything at once",
            retirement_dates={"A": AS_OF},
            withdrawal=GuytonKlinger(),
            drawdown=CashBondLadder(target_years=2.0),
            allocation=ByAssetTypeMix({AssetType.ISA: 0.3}, default_growth_pct=1.0),
        )
        plan = compile_plan(household, scenario, UK, AS_OF)
        projection = project(plan, [{"global_equity": 0.05, "gov_bonds": 0.02,
                                     "inflation": 0.02}] * plan.n_years)
        assert len(projection.years) == plan.n_years
        assert all(y.total_wealth >= 0 for y in projection.years)


class TestShortfallTolerance:
    """A sub-penny arithmetic residue is not a plan failure.

    `need` is chased down through a pension gross-up, a CGT gross-up and a
    bisection on the withdrawal rule, each leaving floating-point dust. A
    residue of 3.6e-12 once marked a year unfunded for a household holding
    £2.5m, because `Projection.succeeded` tests `unmet > 0`.

    It hid while tax thresholds were round numbers and the inversions landed
    exactly; scaling them for fiscal drag exposed it, and made success rates
    chaotic rather than merely wrong — 2% inflation scored 65% where 1% scored
    92%, both reproducible.
    """

    def _ctx(self, tax, **kw):
        from retireplan.strategies.drawdown import DrawdownContext

        defaults = dict(
            tax=tax, isa_slots=(0,), isa_slots_by_person={"A": (0,)},
            dc_slots_by_person={}, gia_slots_by_person={},
            cash_slot=1, ladder_slot=2, bond_slot=3, dc_accessible_by_person={},
            is_retired=True, essential_spend=0.0, growth_return=0.0, bond_return=0.0,
            isa_headroom_used={},
        )
        defaults.update(kw)
        return DrawdownContext(**defaults)

    def test_a_sub_penny_residue_reports_as_fully_funded(self):
        from retireplan.portfolio import Portfolio
        from retireplan.strategies.drawdown import DrawResult, _draw_isa_gia_then_pensions
        from retireplan.tax.uk import UK

        portfolio = Portfolio([1_000.0, 0.0, 0.0])
        # Ask for a hair more than the ISA holds.
        unmet = _draw_isa_gia_then_pensions(
            1_000.0 + 3.6e-12, portfolio, {}, self._ctx(UK), DrawResult()
        )
        assert unmet == 0.0

    def test_a_real_gap_is_still_reported(self):
        from retireplan.portfolio import Portfolio
        from retireplan.strategies.drawdown import DrawResult, _draw_isa_gia_then_pensions
        from retireplan.tax.uk import UK

        portfolio = Portfolio([1_000.0, 0.0, 0.0])
        unmet = _draw_isa_gia_then_pensions(
            1_500.0, portfolio, {}, self._ctx(UK), DrawResult()
        )
        assert unmet == pytest.approx(500.0)

    def test_the_tolerance_is_economically_negligible(self):
        from retireplan.strategies.drawdown import SHORTFALL_TOLERANCE

        assert 0 < SHORTFALL_TOLERANCE <= 0.01
