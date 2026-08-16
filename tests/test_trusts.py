"""The relevant property regime, trust income tax and trustee CGT.

The HMRC parity cases live in `tools/validate_trust_charges.py` and are
repeated here so a refactor that breaks them fails the suite rather than
waiting for someone to run the script.
"""
from __future__ import annotations

from datetime import date

import pytest

from retireplan.tax.trusts import (
    MAX_TEN_YEAR_RATE,
    RelevantPropertyRules,
    TrustIncomeTax,
    charge_rate,
    complete_quarters,
    project_settlement,
    trustee_annual_exempt_amount,
    trustee_cgt,
)

RULES = RelevantPropertyRules(nil_rate_band=325_000.0)


class TestHMRCWorkedExamples:
    def test_ten_year_anniversary(self):
        charge = RULES.ten_year_charge(450_000, cumulative_total=50_000)
        assert charge.available_nil_rate_band == pytest.approx(275_000)
        assert charge.notional_tax == pytest.approx(35_000)
        assert charge.settlement_rate == pytest.approx(0.02333)
        assert charge.tax == pytest.approx(10_498.50)

    def test_exit_before_the_first_anniversary(self):
        charge = RULES.exit_before_first_anniversary(
            distribution=350_000,
            notional_transfer=440_000,
            cumulative_total=190_000,
            quarters=12,
        )
        assert charge.effective_rate == pytest.approx(0.13864)
        assert charge.settlement_rate == pytest.approx(0.04159)
        assert charge.rate == pytest.approx(0.01248)
        assert charge.tax == pytest.approx(4_368.00)

    def test_exit_after_an_anniversary(self):
        charge = RULES.exit_after_anniversary(100_000, 0.033, quarters=10)
        assert charge.rate == pytest.approx(0.00825)
        assert charge.tax == pytest.approx(825.00)


class TestTheChargeIsOnTheWholeFund:
    """The misreading that costs the most: 6% of the excess over the band, not
    6% of the fund."""

    def test_a_fund_inside_the_band_pays_nothing(self):
        assert RULES.ten_year_charge(325_000).tax == 0.0

    def test_a_fund_at_twice_the_band_pays_three_percent(self):
        charge = RULES.ten_year_charge(650_000)
        assert charge.settlement_rate == pytest.approx(0.03)
        assert charge.tax == pytest.approx(19_500)

    def test_the_rate_approaches_but_never_reaches_six_percent(self):
        assert RULES.ten_year_charge(100_000_000).settlement_rate < MAX_TEN_YEAR_RATE
        assert RULES.ten_year_charge(100_000_000).settlement_rate > 0.0598

    def test_the_marginal_pound_above_the_band_always_costs_six_pence(self):
        small = RULES.ten_year_charge(1_000_000).tax
        large = RULES.ten_year_charge(1_100_000).tax
        # Not exactly 6%: the rate is rounded to three decimal places as a
        # percentage before it meets the fund, so it lands within £5 per £1m.
        assert large - small == pytest.approx(6_000, abs=10)


class TestTheNilRateBandIsFixedForLife:
    def test_the_settlors_earlier_gifts_shrink_it(self):
        with_history = RULES.ten_year_charge(650_000, cumulative_total=200_000)
        without = RULES.ten_year_charge(650_000)
        assert with_history.tax > without.tax

    def test_a_settlor_who_used_the_whole_band_gets_none(self):
        assert RULES.available_nil_rate_band(400_000) == 0.0
        assert RULES.ten_year_charge(650_000, 400_000).settlement_rate == pytest.approx(0.06)


class TestEntryCharge:
    def test_the_settlor_paying_grosses_the_charge_up_to_25_percent(self):
        assert RULES.entry_charge(825_000, settlor_pays=True) == pytest.approx(125_000)
        assert RULES.entry_charge(825_000, settlor_pays=False) == pytest.approx(100_000)

    def test_a_settlement_inside_the_band_costs_nothing_to_create(self):
        assert RULES.entry_charge(325_000) == 0.0


class TestQuarters:
    def test_inside_three_months_is_no_quarters_and_no_charge(self):
        assert complete_quarters(date(2026, 1, 1), date(2026, 3, 31)) == 0
        charge = RULES.exit_before_first_anniversary(1_000_000, 1_000_000, 0, quarters=0)
        assert charge.tax == 0.0

    def test_a_quarter_needs_the_full_three_months(self):
        assert complete_quarters(date(2026, 1, 15), date(2026, 4, 14)) == 0
        assert complete_quarters(date(2026, 1, 15), date(2026, 4, 15)) == 1

    def test_a_cycle_is_capped_at_forty(self):
        assert complete_quarters(date(2000, 1, 1), date(2040, 1, 1)) == 40


class TestChargeRateRounding:
    def test_rates_are_stated_to_three_decimal_places_as_a_percentage(self):
        assert charge_rate(0.138636363) == pytest.approx(0.13864)
        assert charge_rate(0.0777777) == pytest.approx(0.07778)


class TestTrustIncomeTax:
    TAX = TrustIncomeTax()

    def test_the_top_rate_applies_from_the_first_pound_above_the_de_minimis(self):
        assert self.TAX.discretionary_tax(non_dividend=500) == 0.0
        assert self.TAX.discretionary_tax(non_dividend=1_500) == pytest.approx(450)

    def test_the_de_minimis_covers_non_dividend_income_first(self):
        # 45p saved is worth more than 39.35p.
        both = self.TAX.discretionary_tax(non_dividend=400, dividends=400)
        assert both == pytest.approx(300 * 0.3935)

    def test_multiple_settlements_divide_it_to_a_floor_of_one_hundred(self):
        assert self.TAX.de_minimis_for(2) == pytest.approx(250)
        assert self.TAX.de_minimis_for(5) == pytest.approx(100)
        assert self.TAX.de_minimis_for(20) == pytest.approx(100)

    def test_an_interest_in_possession_pays_basic_rate_not_trust_rate(self):
        assert self.TAX.interest_in_possession_tax(non_dividend=10_000) == pytest.approx(2_000)
        assert self.TAX.discretionary_tax(non_dividend=10_000) == pytest.approx(4_275)

    def test_a_non_taxpaying_beneficiary_reclaims_the_whole_credit(self):
        assert self.TAX.beneficiary_reclaim(5_500, 0.0) == pytest.approx(4_500)

    def test_an_additional_rate_beneficiary_reclaims_nothing(self):
        assert self.TAX.beneficiary_reclaim(5_500, 0.45) == 0.0

    def test_dividend_income_leaves_the_tax_pool_short(self):
        # 39.35% paid in, 45% credited out: distributing everything cannot work.
        pool = self.TAX.discretionary_tax(dividends=10_000)
        shortfall = self.TAX.tax_pool_shortfall(net_paid=10_000 - pool, tax_pool=pool)
        assert shortfall > 0


class TestTrusteeCGT:
    def test_the_exemption_is_half_an_individuals(self):
        assert trustee_annual_exempt_amount() == 1_500.0

    def test_it_divides_between_settlements_to_a_floor_of_a_fifth(self):
        assert trustee_annual_exempt_amount(3) == pytest.approx(500)
        assert trustee_annual_exempt_amount(5) == pytest.approx(300)
        assert trustee_annual_exempt_amount(50) == pytest.approx(300)

    def test_a_vulnerable_beneficiary_trust_keeps_the_full_amount(self):
        assert trustee_annual_exempt_amount(vulnerable_beneficiary=True) == 3_000.0

    def test_one_flat_rate_with_no_basic_rate_band(self):
        assert trustee_cgt(101_500) == pytest.approx(100_000 * 0.24)


class TestSettlementProjection:
    def test_both_arms_start_from_the_same_outlay(self):
        p = project_settlement(
            initial_value=600_000, years=10, real_growth_rate=0.0, yield_rate=0.0
        )
        assert p.settlor_outlay == pytest.approx(600_000 + p.entry_charge)

    def test_trustees_paying_the_entry_charge_shrinks_the_fund_instead(self):
        p = project_settlement(
            initial_value=600_000, years=10, real_growth_rate=0.0, yield_rate=0.0,
            settlor_pays_entry_charge=False,
        )
        assert p.settlor_outlay == pytest.approx(600_000)
        assert p.entry_charge == pytest.approx(275_000 * 0.20)

    def test_a_settlement_inside_the_band_that_never_grows_costs_nothing(self):
        p = project_settlement(
            initial_value=300_000, years=30, real_growth_rate=0.0, yield_rate=0.0
        )
        assert p.total_trust_tax == 0.0

    def test_dying_within_seven_years_charges_the_death_rate(self):
        survived = project_settlement(
            initial_value=825_000, years=10, real_growth_rate=0.0, yield_rate=0.0
        )
        died = project_settlement(
            initial_value=825_000, years=10, real_growth_rate=0.0, yield_rate=0.0,
            settlor_survives_seven_years=False,
        )
        assert died.entry_charge == pytest.approx(500_000 * 0.40)
        assert died.entry_charge > survived.entry_charge

    def test_growth_above_a_frozen_band_drives_the_charges_up_each_decade(self):
        p = project_settlement(
            initial_value=600_000, years=30, real_growth_rate=0.04, yield_rate=0.0
        )
        assert len(p.ten_year_charges) == 3
        assert p.ten_year_charges[0] < p.ten_year_charges[1] < p.ten_year_charges[2]

    def test_an_exit_in_the_same_quarter_as_an_anniversary_is_free(self):
        p = project_settlement(
            initial_value=600_000, years=20, real_growth_rate=0.04, yield_rate=0.0
        )
        assert p.exit_charge == 0.0

    def test_leaving_it_one_more_year_is_not(self):
        p = project_settlement(
            initial_value=600_000, years=21, real_growth_rate=0.04, yield_rate=0.0
        )
        assert p.exit_charge > 0.0
