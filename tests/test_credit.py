"""The hold-to-maturity corporate credit model.

Held to maturity, a bond has no mark-to-market risk — it redeems at par. The
risk is that the issuer does not pay, and that this happens in recessions,
alongside falling equities and a retiree selling to fund spending.
"""
from __future__ import annotations

import random
import statistics

import pytest

from retireplan import MarketData
from retireplan.market import HeldToMaturityCredit

CLEAN = {"inflation": 0.02, "recession": 0.0}
RECESSION = {"inflation": 0.02, "recession": 1.0}


class TestMechanics:
    def test_a_clean_year_earns_the_coupon_less_expected_losses(self):
        credit = HeldToMaturityCredit(nominal_yield=0.07, default_rate=0.0)
        assert credit.real_return({"inflation": 0.0, "recession": 0.0}) == pytest.approx(0.07)

    def test_inflation_erodes_the_coupon(self):
        credit = HeldToMaturityCredit(nominal_yield=0.07, default_rate=0.0)
        assert credit.real_return({"inflation": 0.07, "recession": 0.0}) == pytest.approx(0.0)
        assert credit.real_return({"inflation": 0.12, "recession": 0.0}) < 0

    def test_defaults_reduce_the_return_by_the_loss_given_default(self):
        credit = HeldToMaturityCredit(nominal_yield=0.07, default_rate=0.10,
                                      recovery_rate=0.60)
        # 90% redeem at 1.07, 10% return 0.60
        expected_nominal = 0.9 * 1.07 + 0.1 * 0.60 - 1
        assert credit.real_return({"inflation": 0.0, "recession": 0.0}) == pytest.approx(expected_nominal)

    def test_full_recovery_means_default_costs_only_the_coupon(self):
        credit = HeldToMaturityCredit(nominal_yield=0.07, default_rate=0.5, recovery_rate=1.0)
        got = credit.real_return({"inflation": 0.0, "recession": 0.0})
        assert got == pytest.approx(0.5 * 0.07)


class TestTheCreditCycle:
    def test_recessions_raise_defaults_and_cut_recoveries(self):
        credit = HeldToMaturityCredit(nominal_yield=0.07)
        clean_rate, clean_recovery = credit._cycle(CLEAN)
        stress_rate, stress_recovery = credit._cycle(RECESSION)
        assert stress_rate > clean_rate
        assert stress_recovery < clean_recovery

    def test_a_recession_year_returns_less(self):
        credit = HeldToMaturityCredit(nominal_yield=0.07)
        assert credit.real_return(RECESSION) < credit.real_return(CLEAN)

    def test_partial_years_scale_smoothly(self):
        credit = HeldToMaturityCredit(nominal_yield=0.07)
        half = credit.real_return({"inflation": 0.02, "recession": 0.5})
        assert credit.real_return(RECESSION) < half < credit.real_return(CLEAN)

    def test_default_rate_cannot_exceed_certainty(self):
        credit = HeldToMaturityCredit(nominal_yield=0.07, default_rate=0.5,
                                      stress_default_multiple=10)
        assert credit._cycle(RECESSION)[0] == 1.0


class TestCalibration:
    """The shipped defaults should reproduce published long-run statistics."""

    def test_through_the_cycle_rate_matches_moodys_long_run_average(self):
        data = MarketData.load()
        credit = HeldToMaturityCredit(nominal_yield=0.07)
        years = data.window(["recession"])
        mean = statistics.mean(credit._cycle(data.by_year[y])[0] for y in years)
        assert mean == pytest.approx(0.0448, abs=0.004)  # Moody's: 4.48%

    def test_a_full_recession_year_matches_the_2001_peak(self):
        credit = HeldToMaturityCredit(nominal_yield=0.07)
        assert credit._cycle(RECESSION)[0] == pytest.approx(0.0998, abs=0.01)  # Moody's: 9.98%

    def test_investment_grade_can_be_configured_far_lower(self):
        ig = HeldToMaturityCredit(nominal_yield=0.04, default_rate=0.002)
        assert ig._cycle(CLEAN)[0] == pytest.approx(0.002)


class TestConcentration:
    def test_a_diversified_holding_takes_the_expected_loss(self):
        credit = HeldToMaturityCredit(nominal_yield=0.07, n_holdings=0)
        rng = random.Random(1)
        assert credit.real_return(CLEAN, rng) == credit.real_return(CLEAN, None)

    def test_a_concentrated_ladder_is_lumpy(self):
        """Twelve issuers do not lose their long-run average every year: they
        lose nothing for years and then lose a lot at once."""
        credit = HeldToMaturityCredit(nominal_yield=0.07, n_holdings=12)
        rng = random.Random(7)
        draws = [credit.real_return(RECESSION, rng) for _ in range(200)]
        assert len(set(draws)) > 3
        assert statistics.pstdev(draws) > 0.02

    def test_concentration_averages_out_to_the_diversified_case(self):
        credit = HeldToMaturityCredit(nominal_yield=0.07, n_holdings=20)
        rng = random.Random(3)
        draws = [credit.real_return(CLEAN, rng) for _ in range(4000)]
        diversified = HeldToMaturityCredit(nominal_yield=0.07).real_return(CLEAN)
        assert statistics.mean(draws) == pytest.approx(diversified, abs=0.004)

    def test_without_an_rng_it_stays_deterministic(self):
        credit = HeldToMaturityCredit(nominal_yield=0.07, n_holdings=5)
        assert credit.real_return(CLEAN) == credit.real_return(CLEAN)


class TestAgainstHistory:
    def test_the_worst_year_is_a_stagflation_year_not_a_crash_year(self):
        """1974 beats 2008 for damage: a recession's defaults on top of 11%
        inflation destroys more of a fixed coupon than defaults alone."""
        data = MarketData.load()
        credit = HeldToMaturityCredit(nominal_yield=0.07)
        years = data.window(["inflation", "recession"])
        by_year = {y: credit.real_return(data.by_year[y]) for y in years}
        worst = min(by_year, key=by_year.__getitem__)
        assert worst in (1974, 1980, 1979, 1946, 1947)
        assert by_year[worst] < -0.05
        assert by_year[1974] < by_year[2008]

    def test_deflation_makes_a_fixed_coupon_valuable(self):
        data = MarketData.load()
        credit = HeldToMaturityCredit(nominal_yield=0.07)
        assert credit.real_return(data.by_year[1932]) > 0.08  # CPI fell ~10%

    def test_it_needs_inflation_and_recession_only(self):
        """Keeping off the corporate return series is what preserves the
        full 98-year sampling window."""
        assert HeldToMaturityCredit(0.07).series_keys() == frozenset({"inflation", "recession"})
