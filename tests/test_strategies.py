"""The three strategy axes, and that they compose."""
from __future__ import annotations

from datetime import date

import pytest

from retireplan import (
    Asset,
    AssetType,
    Assumptions,
    VPW,
    BondTent,
    BridgeGuardrail,
    BridgeLadder,
    ByAssetTypeMix,
    CashBondLadder,
    EndowmentSmoothing,
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
    Ratchet,
    SampledSeries,
    Scenario,
    SpendNominal,
    StandardOrder,
    StaticMix,
    ThreeBucketStrategy,
    VanguardDynamicSpending,
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
        years_remaining=30,
        bridge_value=1_000_000.0,
        years_to_access=0,
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

    def test_guyton_klinger_suspends_the_cut_in_the_final_years(self):
        """The canonical rule: capital-preservation cuts stop in the last 15
        years of the plan, since a cut this late defends an estate the
        retiree will not live to need."""
        strategy = GuytonKlinger()
        strategy.reset()
        strategy.decide(context(portfolio_value=1_000_000, years_remaining=30))
        strategy.decide(context(portfolio_value=300_000, years_remaining=10))
        assert strategy.multiplier == pytest.approx(1.0)

    def test_guyton_klinger_still_cuts_just_outside_the_final_years(self):
        strategy = GuytonKlinger()
        strategy.reset()
        strategy.decide(context(portfolio_value=1_000_000, years_remaining=30))
        strategy.decide(context(portfolio_value=300_000, years_remaining=16))
        assert strategy.multiplier < 1.0

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

    def test_bond_tent_de_risks_into_retirement_then_re_risks(self):
        """The Kitces/Pfau V-shape: lowest equity *at* retirement (year 10
        here), not before or long after."""
        market = {"global_equity": 0.10, "gov_bonds": 0.0}
        tent = BondTent(start_pct=0.9, low_pct=0.4, end_pct=0.7,
                        years_to_low=10, years_to_recover=10)
        assert tent.real_return(self._asset(), market, 0) == pytest.approx(0.09)
        assert tent.real_return(self._asset(), market, 10) == pytest.approx(0.04)   # the low point
        assert tent.real_return(self._asset(), market, 20) == pytest.approx(0.07)
        assert tent.real_return(self._asset(), market, 50) == pytest.approx(0.07)   # holds after recovering


class TestRatchet:
    def test_it_raises_once_the_portfolio_has_grown_far_enough(self):
        strategy = Ratchet(trigger=1.5, step=0.10, min_years_between=3)
        strategy.reset()
        strategy.decide(context(year_index=0, portfolio_value=1_000_000))  # sets the baseline
        assert strategy.decide(context(year_index=3, portfolio_value=1_600_000)) \
            == pytest.approx(11_000.0)

    def test_the_cadence_holds_it_back(self):
        strategy = Ratchet(trigger=1.5, min_years_between=3)
        strategy.reset()
        strategy.decide(context(year_index=0, portfolio_value=1_000_000))
        assert strategy.decide(context(year_index=2, portfolio_value=2_000_000)) \
            == pytest.approx(10_000.0)

    def test_it_never_cuts(self):
        strategy = Ratchet()
        strategy.reset()
        strategy.decide(context(year_index=0, portfolio_value=1_000_000))
        assert strategy.decide(context(year_index=5, portfolio_value=100_000)) \
            == pytest.approx(10_000.0)

    def test_the_baseline_does_not_reset_so_raises_repeat(self):
        """Kitces' published rule keys off the value at retirement throughout,
        so a portfolio parked above the trigger earns a raise every cadence."""
        strategy = Ratchet(trigger=1.5, step=0.10, min_years_between=3)
        strategy.reset()
        strategy.decide(context(year_index=0, portfolio_value=1_000_000))
        strategy.decide(context(year_index=3, portfolio_value=1_600_000))
        assert strategy.decide(context(year_index=6, portfolio_value=1_600_000)) \
            == pytest.approx(12_100.0)


class TestVPW:
    def test_the_rate_rises_as_the_horizon_shortens(self):
        strategy = VPW(expected_real_return=0.03, ceiling=10.0)
        early = strategy.decide(context(portfolio_value=1_000_000, years_remaining=40))
        late = strategy.decide(context(portfolio_value=1_000_000, years_remaining=10))
        assert late > early

    def test_zero_expected_return_is_the_one_over_n_rule(self):
        """PMT at 0% is 1/N — the RMD-style rule, and the arithmetic is
        checkable by hand: 1/20 of £1m, plus £5,000 income, less £20,000 fixed."""
        strategy = VPW(expected_real_return=0.0, ceiling=10.0)
        spend = strategy.decide(context(portfolio_value=1_000_000, years_remaining=20))
        assert spend == pytest.approx(50_000.0 + 5_000.0 - 20_000.0)

    def test_it_does_nothing_before_retirement(self):
        assert VPW().decide(context(is_retired=False)) == pytest.approx(10_000.0)


class TestSmoothedRules:
    def test_vanguard_clips_the_rise_to_the_ceiling(self):
        strategy = VanguardDynamicSpending(rate=0.04, ceiling_rise=0.05)
        strategy.reset()
        first = strategy.decide(context(portfolio_value=1_000_000))
        assert first == pytest.approx(40_000.0 + 5_000.0 - 20_000.0)
        assert strategy.decide(context(portfolio_value=10_000_000)) \
            == pytest.approx(first * 1.05)

    def test_vanguard_clips_the_cut_to_the_floor(self):
        strategy = VanguardDynamicSpending(rate=0.04, floor_drop=0.025)
        strategy.reset()
        first = strategy.decide(context(portfolio_value=1_000_000))
        assert strategy.decide(context(portfolio_value=100_000)) \
            == pytest.approx(first * 0.975)

    def test_vanguard_anchors_on_what_was_actually_spent(self):
        """A year the portfolio forced a cut restarts the band from the lower
        figure, not from the number the rule asked for."""
        strategy = VanguardDynamicSpending(rate=0.04)
        strategy.reset()
        strategy.decide(context(portfolio_value=1_000_000, affordable_up_to=8_000))
        # Just under: the affordability search only ever returns a point it
        # has verified, so it converges on the limit from below.
        assert 7_900.0 < strategy.prior_spend <= 8_000.0

    def test_endowment_moves_a_fifth_of_the_way(self):
        strategy = EndowmentSmoothing(rate=0.04, weight_on_prior=0.8)
        strategy.reset()
        first = strategy.decide(context(portfolio_value=1_000_000))
        target = 0.04 * 500_000 + 5_000 - 20_000
        assert strategy.decide(context(portfolio_value=500_000)) \
            == pytest.approx(0.8 * first + 0.2 * target)

    def test_endowment_cuts_harder_than_vanguard_after_a_crash(self):
        """The blend is unbounded, so it beats Vanguard's 2.5% floor to the
        cut — the more responsive rule despite feeling like the gentler one."""
        crash = dict(portfolio_value=1_000_000), dict(portfolio_value=400_000)
        yale, vanguard = EndowmentSmoothing(), VanguardDynamicSpending()
        for rule in (yale, vanguard):
            rule.reset()
            rule.decide(context(**crash[0]))
        assert yale.decide(context(**crash[1])) < vanguard.decide(context(**crash[1]))


class TestBridgeGuardrail:
    def _bridging(self, **overrides):
        defaults = dict(years_to_access=4, dc_accessible=False, bridge_value=100_000.0)
        defaults.update(overrides)
        return context(**defaults)

    def test_it_cuts_when_the_bridge_will_not_reach_access(self):
        strategy = BridgeGuardrail(adjustment=0.10)
        strategy.reset()
        # £40,000 of accessible money against four years needing £25,000 each.
        strategy.decide(self._bridging(bridge_value=40_000))
        assert strategy.multiplier == pytest.approx(0.9)

    def test_it_leaves_a_comfortable_bridge_alone(self):
        strategy = BridgeGuardrail()
        strategy.reset()
        strategy.decide(self._bridging(bridge_value=105_000))
        assert strategy.multiplier == pytest.approx(1.0)

    def test_it_restores_but_never_above_the_plan(self):
        strategy = BridgeGuardrail(adjustment=0.10)
        strategy.reset()
        strategy.decide(self._bridging(bridge_value=40_000))       # cut to 0.9
        strategy.decide(self._bridging(bridge_value=1_000_000))    # far ahead
        assert strategy.multiplier == pytest.approx(0.99)
        strategy.decide(self._bridging(bridge_value=1_000_000))
        assert strategy.multiplier == pytest.approx(1.0)

    def test_it_does_not_restore_into_a_falling_market(self):
        strategy = BridgeGuardrail(adjustment=0.10)
        strategy.reset()
        strategy.decide(self._bridging(bridge_value=40_000))
        strategy.decide(self._bridging(bridge_value=1_000_000, growth_return=-0.2))
        assert strategy.multiplier == pytest.approx(0.9)

    def test_the_whole_portfolio_rule_misses_what_this_one_catches(self):
        """The point of the strategy: a bridge running dry beside a large
        locked pension moves no whole-portfolio withdrawal rate at all."""
        failing_bridge = self._bridging(bridge_value=40_000, portfolio_value=1_000_000)
        klinger = GuytonKlinger()
        klinger.reset()
        klinger.decide(failing_bridge)
        klinger.decide(failing_bridge)
        assert klinger.multiplier == pytest.approx(1.0)

        bridge = BridgeGuardrail()
        bridge.reset()
        bridge.decide(failing_bridge)
        assert bridge.multiplier < 1.0

    def test_access_hands_over_to_the_inner_rule_and_drops_the_cut(self):
        strategy = BridgeGuardrail(after=PostAccessStepUp(step_up=1.25, surplus_years=1.0))
        strategy.reset()
        strategy.decide(self._bridging(bridge_value=40_000))
        assert strategy.decide(context(years_to_access=0, dc_accessible=True)) \
            == pytest.approx(12_500.0)

    def test_reset_clears_the_inner_rule_too(self):
        inner = PostAccessStepUp(surplus_years=1.0)
        strategy = BridgeGuardrail(after=inner)
        strategy.decide(self._bridging(bridge_value=40_000))
        strategy.decide(context(years_to_access=0))
        strategy.reset()
        assert strategy.multiplier == 1.0
        assert inner.stepped_up is False


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


class TestBridgeLadder:
    """A household that stops at 50 with the pension locked until 57."""

    FLAT = {"global_equity": 0.0, "gov_bonds": 0.0, "inflation": 0.0}

    def _run(self, strategy, born=date(1976, 1, 1), market=None):
        household = Household(
            people=[Person("A", born)],
            expenses=[Expense("Living", 30_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[
                Asset("ISA", AssetType.ISA, "A", 400_000, returns=SampledSeries("global_equity")),
                Asset("Pension", AssetType.DC_PENSION, "A", 300_000,
                      returns=SampledSeries("global_equity")),
            ],
            assumptions=Assumptions(life_expectancy_age=70, state_pension_age=99),
        )
        scenario = Scenario("retired", retirement_dates={"A": AS_OF},
                            withdrawal=SpendNominal(), drawdown=strategy)
        plan = compile_plan(household, scenario, UK, AS_OF)
        return project(plan, [market or self.FLAT] * plan.n_years)

    def _ladder(self, projection):
        return [y.balances["__ladder_reserve"] for y in projection.years]

    def test_it_carves_out_the_bridge_years_that_remain(self):
        """Seeded at the end of year 1 of retirement, six bridge years left,
        £30,000 of essential spending each."""
        ladder = self._ladder(self._run(BridgeLadder(cover=1.0)))
        assert ladder[0] == pytest.approx(6 * 30_000, rel=0.02)

    def test_it_is_never_refilled(self):
        """The liability shrinks every year, so the pot only ever falls."""
        ladder = self._ladder(self._run(BridgeLadder(cover=1.0)))
        assert all(b <= ladder[0] + 1 for b in ladder)

    def test_it_is_all_but_spent_down_by_pension_access(self):
        """Sized on years × spending, so the `real_return` it earns on top is
        pure overshoot — a few per cent left over, spent first afterwards."""
        ladder = self._ladder(self._run(BridgeLadder(cover=1.0)))
        assert 0 <= ladder[6] < 0.05 * ladder[0]

    def test_a_crash_is_not_paid_for_by_selling_equities(self):
        crash = {"global_equity": -0.30, "gov_bonds": 0.0, "inflation": 0.0}
        carved = self._run(BridgeLadder(cover=1.0), market=crash)
        plain = self._run(StandardOrder(), market=crash)
        assert carved.years[3].isa_withdrawn < plain.years[3].isa_withdrawn

    def test_nothing_is_carved_out_when_there_is_no_bridge(self):
        """Retiring at 60, past the access age, leaves no liability to match."""
        ladder = self._ladder(self._run(BridgeLadder(), born=date(1966, 1, 1)))
        assert ladder == [pytest.approx(0.0)] * len(ladder)


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
            is_retired=True, years_to_access=0, essential_spend=0.0,
            growth_return=0.0, bond_return=0.0,
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


class TestSharedCGTExemption:
    """The £3,000 annual exempt amount is per person per *year*, but two
    mechanisms realise gains for the same person in one year -- GIA drawdown
    inside a strategy, and the end-of-year Bed-and-ISA sweep in `cashflow.py`.
    Each once claimed a fresh exemption, so a household running both got two.
    """

    def test_two_disposals_in_one_year_share_one_exemption(self):
        from retireplan.strategies.drawdown import charge_cgt
        from retireplan.tax.uk import UK

        used: dict[str, float] = {}
        first = charge_cgt(10_000, "A", 30_000, UK, used)
        second = charge_cgt(10_000, "A", 30_000, UK, used)
        assert first + second == pytest.approx(UK.capital_gains_tax(20_000, 30_000))

    def test_the_exemption_is_still_per_person(self):
        from retireplan.strategies.drawdown import charge_cgt
        from retireplan.tax.uk import UK

        used: dict[str, float] = {}
        charge_cgt(10_000, "A", 30_000, UK, used)
        assert charge_cgt(10_000, "B", 30_000, UK, used) == pytest.approx(
            UK.capital_gains_tax(10_000, 30_000)
        )

    def test_a_gain_smaller_than_the_exemption_only_spends_what_it_uses(self):
        from retireplan.strategies.drawdown import charge_cgt
        from retireplan.tax.uk import UK

        used: dict[str, float] = {}
        assert charge_cgt(1_000, "A", 30_000, UK, used) == 0.0
        assert used["A"] == pytest.approx(1_000)
        assert charge_cgt(5_000, "A", 30_000, UK, used) == pytest.approx(3_000 * 0.18)

    def test_a_dry_run_probe_does_not_spend_it(self):
        from retireplan.strategies.drawdown import charge_cgt
        from retireplan.tax.uk import UK

        ctx = TestShortfallTolerance()._ctx(UK, cgt_exempt_used={})
        charge_cgt(10_000, "A", 30_000, UK, ctx.for_dry_run().cgt_exempt_used)
        assert ctx.cgt_exempt_used == {}
