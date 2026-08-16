"""Annuity pricing: the curve, the mortality basis, and the option adjustments.

The market parity cases live in `tools/validate_annuity_rates.py`. The ones
repeated here are the relationships that must hold whatever the calibration is
— a refactor that breaks them has broken the mechanism, not the fit.

Every test that needs data uses `GiltCurve.flat`, so the suite runs on a clone
that has not fetched anything. The parity check that does need real data is
skipped rather than failed when the file is absent.
"""
from __future__ import annotations

import pytest

from retireplan.annuity import (
    AnnuitantMortality,
    AnnuityMarket,
    AnnuityOptions,
    GiltCurve,
    uk_annuity_market,
)
from retireplan.mortality import LifeTable

pytestmark = pytest.mark.filterwarnings("ignore")


@pytest.fixture(scope="module")
def table():
    try:
        return LifeTable.load()
    except FileNotFoundError:
        pytest.skip("mortality table not fetched — see DATA_SETUP.md")


@pytest.fixture(scope="module")
def market(table):
    return AnnuityMarket(
        mortality=AnnuitantMortality(table, qx_multiplier=0.69, annual_improvement=0.01),
        curve=GiltCurve.flat(0.05, 0.03),
        illiquidity_spread=0.007,
        inflation_risk_premium=0.003,
    )


class TestTheCurve:
    def test_it_interpolates_between_published_terms(self):
        curve = GiltCurve("test", {5: 0.04, 10: 0.05, 20: 0.06}, {5: 0.03, 10: 0.03, 20: 0.03})
        assert curve.nominal_yield(15) == pytest.approx(0.055)
        assert curve.nominal_yield(7.5) == pytest.approx(0.045)

    def test_it_stays_flat_outside_them_rather_than_extrapolating(self):
        curve = GiltCurve("test", {5: 0.04, 10: 0.05, 20: 0.06}, {5: 0.03, 10: 0.03, 20: 0.03})
        assert curve.nominal_yield(40) == pytest.approx(0.06)
        assert curve.nominal_yield(1) == pytest.approx(0.04)

    def test_the_real_yield_is_fisher_not_subtraction(self):
        curve = GiltCurve.flat(0.05, 0.03)
        assert curve.real_yield() == pytest.approx(1.05 / 1.03 - 1)
        assert curve.real_yield() < 0.02  # subtraction would say exactly 2%


class TestMortality:
    def test_a_multiplier_below_one_lengthens_life(self, table):
        heavy = AnnuitantMortality(table, qx_multiplier=1.0)
        light = AnnuitantMortality(table, qx_multiplier=0.69)
        assert light.life_expectancy(65) > heavy.life_expectancy(65)

    def test_improvement_lengthens_it_further(self, table):
        flat = AnnuitantMortality(table, 0.69, annual_improvement=0.0)
        improving = AnnuitantMortality(table, 0.69, annual_improvement=0.01)
        assert improving.life_expectancy(65) > flat.life_expectancy(65)

    def test_improvement_helps_a_younger_buyer_more(self, table):
        """It compounds over the projection, so it barely touches an 85-year-old."""
        flat = AnnuitantMortality(table, 0.69, annual_improvement=0.0)
        improving = AnnuitantMortality(table, 0.69, annual_improvement=0.01)
        young = improving.life_expectancy(55) - flat.life_expectancy(55)
        old = improving.life_expectancy(85) - flat.life_expectancy(85)
        assert young > old

    def test_the_unisex_blend_sits_between_the_sexes(self, table):
        basis = AnnuitantMortality(table, 0.69)
        blended = basis.life_expectancy(65)
        assert basis.life_expectancy(65, "male") < blended < basis.life_expectancy(65, "female")

    def test_survival_starts_at_one_and_never_rises(self, table):
        probabilities = AnnuitantMortality(table, 0.69).survival(65)
        assert probabilities[0] == 1.0
        assert all(a >= b for a, b in zip(probabilities, probabilities[1:]))


class TestRateRisesWithAge:
    def test_an_older_buyer_gets_more_income(self, market):
        rates = [market.quote(100_000, age).rate for age in (55, 60, 65, 70, 75, 80)]
        assert all(a < b for a, b in zip(rates, rates[1:]))

    def test_because_the_premium_buys_fewer_expected_years(self, market):
        assert market.quote(100_000, 75).annuity_factor < market.quote(100_000, 55).annuity_factor


class TestOptionsCostWhatTheyShould:
    def test_a_joint_life_annuity_pays_less_than_a_single_one(self, market):
        single = market.quote(100_000, 65).annual_income
        half = market.quote(100_000, 65, options=AnnuityOptions(joint_life_proportion=0.5))
        full = market.quote(100_000, 65, options=AnnuityOptions(joint_life_proportion=1.0))
        assert full.annual_income < half.annual_income < single

    def test_a_younger_spouse_costs_more(self, market):
        near = AnnuityOptions(joint_life_proportion=1.0, spouse_age_offset=0)
        far = AnnuityOptions(joint_life_proportion=1.0, spouse_age_offset=-10)
        assert market.quote(100_000, 65, options=far).annual_income < \
            market.quote(100_000, 65, options=near).annual_income

    def test_a_guarantee_costs_little_at_65_and_more_at_85(self, market):
        def cost(age: int) -> float:
            plain = market.quote(100_000, age).annual_income
            guaranteed = market.quote(
                100_000, age, options=AnnuityOptions(guarantee_years=10)
            ).annual_income
            return 1 - guaranteed / plain

        assert cost(85) > cost(65)
        assert cost(65) < 0.05

    def test_escalation_buys_a_much_lower_starting_income(self, market):
        level = market.quote(100_000, 65).annual_income
        rising = market.quote(100_000, 65, options=AnnuityOptions(escalation=0.03))
        assert 0.6 < rising.annual_income / level < 0.85

    def test_rpi_linking_costs_more_than_fixed_escalation_at_the_same_rate(self, market):
        """Because it is priced off the real curve, which carries an inflation
        risk premium the fixed rate does not."""
        curve = GiltCurve.flat(0.05, 0.03)
        priced = market.with_curve(curve)
        fixed = priced.quote(100_000, 65, options=AnnuityOptions(escalation=0.03))
        linked = priced.quote(100_000, 65, options=AnnuityOptions(rpi_linked=True))
        assert linked.annual_income < fixed.annual_income

    def test_health_uplift_is_applied_as_given(self, market):
        plain = market.quote(100_000, 65).annual_income
        enhanced = market.quote(
            100_000, 65, options=AnnuityOptions(health_uplift=0.20)
        ).annual_income
        assert enhanced == pytest.approx(plain * 1.20)

    def test_rpi_and_fixed_escalation_are_mutually_exclusive(self):
        with pytest.raises(ValueError, match="not both"):
            AnnuityOptions(rpi_linked=True, escalation=0.03)


class TestTheDiscountRateMatters:
    """The bug this module was written to fix: the old pricing ignored yields
    entirely and gave the same answer at 1% gilts as at 5%."""

    def test_higher_yields_buy_more_income(self, table):
        basis = AnnuitantMortality(table, 0.69, 0.01)
        cheap = AnnuityMarket(basis, GiltCurve.flat(0.01, 0.02))
        dear = AnnuityMarket(basis, GiltCurve.flat(0.05, 0.02))
        assert dear.quote(100_000, 65).annual_income > \
            cheap.quote(100_000, 65).annual_income * 1.3

    def test_an_older_buyer_is_priced_off_a_shorter_point_on_the_curve(self, table):
        rising = GiltCurve("test", {5: 0.03, 10: 0.05, 20: 0.07}, {5: 0.02, 10: 0.02, 20: 0.02})
        market = AnnuityMarket(AnnuitantMortality(table, 0.69, 0.01), rising)
        assert market.quote(100_000, 80).discount_rate < market.quote(100_000, 55).discount_rate


class TestRealIncome:
    def test_a_level_annuity_loses_purchasing_power(self, market):
        quote = market.quote(100_000, 65)
        assert quote.real_income(20, 0.03) < quote.annual_income * 0.6

    def test_an_rpi_annuity_does_not(self, market):
        quote = market.quote(100_000, 65, options=AnnuityOptions(rpi_linked=True))
        assert quote.real_income(30, 0.03) == pytest.approx(quote.annual_income)
        assert quote.half_life(0.03) is None

    def test_escalation_below_inflation_only_slows_the_decay(self, market):
        quote = market.quote(100_000, 65, options=AnnuityOptions(escalation=0.03))
        level = market.quote(100_000, 65)
        assert quote.half_life(0.05) > level.half_life(0.05)

    def test_escalation_above_inflation_never_halves(self, market):
        quote = market.quote(100_000, 65, options=AnnuityOptions(escalation=0.03))
        assert quote.half_life(0.02) is None


class TestAgainstTheMarket:
    """One published figure, so a broken calibration fails the suite rather
    than waiting for someone to run the validator."""

    def test_a_65_year_old_gets_roughly_the_published_best_buy_rate(self):
        try:
            market = uk_annuity_market()
        except FileNotFoundError:
            pytest.skip("gilt or mortality data not fetched — see DATA_SETUP.md")
        income = market.quote(100_000, 65).annual_income
        # HL best buy, single life level no guarantee, 13 August 2026: £7,968.
        assert income == pytest.approx(7_968, rel=0.03)
