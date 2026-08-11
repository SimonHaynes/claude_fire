"""UK tax rules.

The gross-up inverse and the personal-allowance taper are where an error is
both easy to make and invisible in the output, so they get the most attention.
"""
from __future__ import annotations

import pytest

from retireplan.tax import INF, Band, RateSchedule
from retireplan.tax.uk import UK


class TestIncomeTax:
    @pytest.mark.parametrize(
        "income, expected",
        [
            (0, 0.0),
            (12_570, 0.0),                     # exactly the personal allowance
            (20_000, (20_000 - 12_570) * 0.20),
            (50_270, 37_700 * 0.20),           # top of basic rate
            (60_000, 7_540 + 9_730 * 0.40),
        ],
    )
    def test_bands(self, income, expected):
        assert UK.income_tax(income) == pytest.approx(expected)

    def test_taper_zone_is_an_effective_60_percent(self):
        """Each extra £1 above £100k costs 40p, plus 20p of withdrawn allowance."""
        base = UK.income_tax(100_000)
        assert UK.income_tax(101_000) - base == pytest.approx(600.0)

    def test_allowance_is_fully_gone_at_the_additional_rate_threshold(self):
        # 0 + 37,700@20% + 49,730@40% + 25,140@60%
        assert UK.income_tax(125_140) == pytest.approx(7_540 + 19_892 + 15_084)

    def test_additional_rate_applies_above_the_threshold(self):
        assert UK.income_tax(150_000) == pytest.approx(
            7_540 + 19_892 + 15_084 + 24_860 * 0.45
        )

    def test_marginal_rate_never_exceeds_60_percent(self):
        """A regression guard: an earlier engine mis-sized the basic-rate band
        inside the taper, which inflated the marginal rate above 60%."""
        for income in range(0, 200_000, 500):
            marginal = UK.income_tax(income + 1) - UK.income_tax(income)
            assert 0.0 <= marginal <= 0.60 + 1e-9

    def test_tax_is_monotonic(self):
        previous = -1.0
        for income in range(0, 300_000, 1_000):
            current = UK.income_tax(income)
            assert current >= previous
            previous = current


class TestNationalInsurance:
    def test_below_primary_threshold_is_free(self):
        assert UK.national_insurance(12_570) == 0.0

    def test_main_and_upper_rates(self):
        assert UK.national_insurance(50_270) == pytest.approx(37_700 * 0.08)
        assert UK.national_insurance(60_000) == pytest.approx(37_700 * 0.08 + 9_730 * 0.02)


class TestGrossUp:
    @pytest.mark.parametrize("existing", [0, 10_000, 30_000, 95_000, 120_000, 200_000])
    @pytest.mark.parametrize("target_net", [1_000, 25_000, 60_000])
    def test_round_trips_exactly(self, existing, target_net):
        """Gross up, then tax it: the net gained must be what was asked for."""
        gross = UK.gross_pension_withdrawal_for_net(existing, target_net)
        net = gross - (UK.income_tax(existing + gross) - UK.income_tax(existing))
        assert net == pytest.approx(target_net, rel=1e-9)

    def test_spanning_the_taper_costs_more_gross(self):
        """Crossing the 60% zone needs more gross for the same net."""
        below = UK.gross_pension_withdrawal_for_net(50_000, 10_000)
        across = UK.gross_pension_withdrawal_for_net(98_000, 10_000)
        assert across > below

    def test_zero_and_negative_targets(self):
        assert UK.gross_pension_withdrawal_for_net(20_000, 0) == 0.0
        assert UK.gross_pension_withdrawal_for_net(20_000, -5) == 0.0

    def test_matches_a_brute_force_search(self):
        """The analytic inverse must agree with the bisection it replaced."""
        existing, target = 40_000.0, 30_000.0
        lo, hi = 0.0, 500_000.0
        for _ in range(200):
            mid = (lo + hi) / 2
            net = mid - (UK.income_tax(existing + mid) - UK.income_tax(existing))
            if net < target:
                lo = mid
            else:
                hi = mid
        assert UK.gross_pension_withdrawal_for_net(existing, target) == pytest.approx(hi, rel=1e-6)


class TestRateSchedule:
    def test_rejects_unsorted_bands(self):
        with pytest.raises(ValueError, match="ascending"):
            RateSchedule((Band(100, 0.1), Band(50, 0.2), Band(INF, 0.3)))

    def test_rejects_a_bounded_top_band(self):
        with pytest.raises(ValueError, match="unbounded"):
            RateSchedule((Band(100, 0.1), Band(200, 0.2)))

    def test_confiscatory_band_is_unreachable(self):
        schedule = RateSchedule((Band(1_000, 0.0), Band(INF, 1.0)))
        assert schedule.gross_for_net(0, 500) == pytest.approx(500)
        assert schedule.gross_for_net(0, 5_000) == INF


def test_pension_access_age_reflects_the_2028_rise():
    """Legislated, not proposed: assuming 55 invents a bridge that will not exist."""
    assert UK.pension_access_age == 57


class TestCapitalGainsTax:
    def test_matches_the_govuk_worked_example(self):
        """gov.uk/capital-gains-tax/rates: taxable income £20,000 and gains of
        £12,600. Less the £3,000 exemption, £9,600 added to £20,000 is £29,600,
        inside the £37,700 basic-rate band, so all of it is charged at 18%."""
        assert UK.capital_gains_tax(12_600, 20_000 + 12_570) == pytest.approx(1_728.0)

    def test_annual_exempt_amount_is_flat_not_stacked_with_the_personal_allowance(self):
        """The £3,000 CGT exemption applies to the gain itself -- someone with
        £80,000 of other income still gets it in full."""
        assert UK.capital_gains_tax(3_000, 80_000) == 0.0

    def test_basic_and_higher_rate(self):
        # No other income: gain sits entirely in the basic-rate band.
        assert UK.capital_gains_tax(10_000, 0) == pytest.approx((10_000 - 3_000) * 0.18)
        # Other income already past the basic-rate ceiling: all at 24%.
        assert UK.capital_gains_tax(10_000, 60_000) == pytest.approx((10_000 - 3_000) * 0.24)

    def test_a_gain_straddling_the_bands(self):
        other, gain = 45_000, 10_000
        taxable = gain - 3_000
        at_basic = min(taxable, 50_270 - other)
        at_higher = taxable - at_basic
        assert UK.capital_gains_tax(gain, other) == pytest.approx(at_basic * 0.18 + at_higher * 0.24)

    def test_income_below_the_personal_allowance_leaves_the_band_intact_not_wider(self):
        """The personal allowance is not available against gains, but leaving
        it unused does not shrink the basic-rate band either: a retiree with no
        income gets £37,700 of 18% room, not £50,270 of it."""
        taxable = 60_000 - 3_000
        expected = 37_700 * 0.18 + (taxable - 37_700) * 0.24
        assert UK.capital_gains_tax(60_000, 0) == pytest.approx(expected)
        assert UK.capital_gains_tax(60_000, 5_000) == pytest.approx(expected)
        # Once income covers the allowance, every extra pound of it does eat
        # into the band.
        assert UK.capital_gains_tax(60_000, 22_570) == pytest.approx(
            27_700 * 0.18 + (taxable - 27_700) * 0.24
        )

    def test_a_second_disposal_does_not_get_a_second_exemption(self):
        assert UK.capital_gains_tax(10_000, 30_000, exempt_used=3_000) == pytest.approx(
            10_000 * 0.18
        )
        split = UK.capital_gains_tax(10_000, 30_000) + UK.capital_gains_tax(
            10_000, 30_000, exempt_used=3_000
        )
        assert split == pytest.approx(UK.capital_gains_tax(20_000, 30_000))

    def test_no_gain_no_tax(self):
        assert UK.capital_gains_tax(0, 50_000) == 0.0


class TestDividendTax:
    def test_matches_the_govuk_worked_example(self):
        """gov.uk/tax-on-dividends: £29,570 of wages and £3,000 of dividends --
        no tax on £500 of it, 10.75% on the remaining £2,500."""
        assert UK.dividend_tax(3_000, 29_570) == pytest.approx(2_500 * 0.1075)

    def test_allowance_is_flat(self):
        assert UK.dividend_tax(500, 80_000) == 0.0

    def test_three_bands(self):
        assert UK.dividend_tax(5_000, 60_000) == pytest.approx((5_000 - 500) * 0.3575)
        assert UK.dividend_tax(5_000, 130_000) == pytest.approx((5_000 - 500) * 0.3935)

    def test_unused_personal_allowance_covers_dividends(self):
        """Dividends are income: a retiree living on less than the personal
        allowance pays nothing on them, and the allowance is not wasted."""
        assert UK.dividend_tax(5_000, 0) == 0.0
        assert UK.dividend_tax(12_570, 0) == 0.0
        # £5,000 of other income leaves £7,570 of allowance, then £500 at 0%.
        assert UK.dividend_tax(10_000, 5_000) == pytest.approx(
            (10_000 - 7_570 - 500) * 0.1075
        )

    def test_the_allowance_occupies_band_space_rather_than_being_deducted(self):
        """Unlike the CGT exemption the £500 is charged at 0% but still uses up
        basic-rate room, so it can push later dividends into the higher rate
        instead of taking £500 out of charge."""
        other = 48_000
        at_basic = 50_270 - other - 500
        assert UK.dividend_tax(3_000, other) == pytest.approx(
            at_basic * 0.1075 + (3_000 - 500 - at_basic) * 0.3575
        )


class TestGiaGrossForNet:
    @pytest.mark.parametrize("other", [0, 40_000, 48_000])
    @pytest.mark.parametrize("basis_fraction", [0.0, 0.2, 0.5, 0.9, 1.0])
    @pytest.mark.parametrize("target_net", [0, 2_000, 60_000, 500_000])
    def test_round_trips_exactly(self, other, basis_fraction, target_net):
        """Sell that much, pay CGT on the gain portion, and the net proceeds
        must be exactly what was asked for."""
        gross = UK.gia_gross_for_net(other, basis_fraction, target_net)
        gain = gross * (1 - basis_fraction)
        net = gross - UK.capital_gains_tax(gain, other)
        assert net == pytest.approx(target_net, rel=1e-6, abs=1e-6)

    def test_no_gain_is_a_pound_for_pound_sale(self):
        assert UK.gia_gross_for_net(0, 1.0, 12_345) == pytest.approx(12_345)

    def test_more_gain_needs_more_gross_for_the_same_net(self):
        """A holding with a bigger embedded gain costs more to realise the
        same net amount from, because more of each pound sold is taxable."""
        low_gain = UK.gia_gross_for_net(0, basis_fraction=0.9, target_net=10_000)
        high_gain = UK.gia_gross_for_net(0, basis_fraction=0.1, target_net=10_000)
        assert high_gain > low_gain
