"""Inheritance tax, and the pension/ISA decision it drives."""
from __future__ import annotations

from datetime import date

import pytest

from retireplan.tax.iht import UK_IHT, IHTRules, effective_pension_death_rate

BEFORE = date(2027, 4, 5)
AFTER = date(2027, 4, 6)


class TestNilRateBands:
    def test_single_estate_below_the_bands_pays_nothing(self):
        result = UK_IHT.bequest(non_pension_assets=400_000, pension_assets=0,
                                on=AFTER, bands=1)
        assert result.iht_due == 0.0

    def test_couple_gets_transferable_bands(self):
        single = UK_IHT.allowances(600_000, bands=1)
        couple = UK_IHT.allowances(600_000, bands=2)
        assert single == pytest.approx(500_000)    # 325k + 175k
        assert couple == pytest.approx(1_000_000)  # both bands transferred

    def test_residence_band_tapers_above_two_million(self):
        assert UK_IHT.residence_band(2_000_000, bands=1) == pytest.approx(175_000)
        assert UK_IHT.residence_band(2_100_000, bands=1) == pytest.approx(125_000)
        assert UK_IHT.residence_band(2_350_000, bands=1) == 0.0

    def test_couple_residence_band_is_gone_by_2_7_million(self):
        """The case that catches people: a large pension pushes the estate
        past the taper and the residence band vanishes entirely."""
        assert UK_IHT.residence_band(2_000_000, bands=2) == pytest.approx(350_000)
        assert UK_IHT.residence_band(2_700_000, bands=2) == 0.0
        assert UK_IHT.allowances(5_000_000, bands=2) == pytest.approx(650_000)

    def test_no_residence_band_without_a_home_to_descendants(self):
        assert UK_IHT.residence_band(1_000_000, bands=2, qualifies=False) == 0.0


class TestPensionsInTheEstate:
    def test_pensions_are_outside_the_estate_before_april_2027(self):
        result = UK_IHT.bequest(non_pension_assets=500_000, pension_assets=1_000_000,
                                on=BEFORE, bands=2)
        assert result.pension_included == 0.0
        assert result.iht_due == 0.0  # 500k of assets sits inside the bands

    def test_pensions_are_inside_from_april_2027(self):
        result = UK_IHT.bequest(non_pension_assets=500_000, pension_assets=1_000_000,
                                on=AFTER, bands=2)
        assert result.pension_included == pytest.approx(1_000_000)
        assert result.iht_due > 0

    def test_the_change_is_worth_real_money(self):
        before = UK_IHT.bequest(non_pension_assets=800_000, pension_assets=1_200_000,
                                on=BEFORE, bands=2)
        after = UK_IHT.bequest(non_pension_assets=800_000, pension_assets=1_200_000,
                               on=AFTER, bands=2)
        assert after.net_to_beneficiaries < before.net_to_beneficiaries


class TestBeneficiaryIncomeTax:
    def test_death_after_75_stacks_income_tax_on_the_pension(self):
        after_75 = UK_IHT.bequest(non_pension_assets=0, pension_assets=1_000_000,
                                  on=AFTER, bands=2, death_after_75=True)
        before_75 = UK_IHT.bequest(non_pension_assets=0, pension_assets=1_000_000,
                                   on=AFTER, bands=2, death_after_75=False)
        assert after_75.beneficiary_income_tax > 0
        assert before_75.beneficiary_income_tax == 0.0
        assert after_75.net_to_beneficiaries < before_75.net_to_beneficiaries

    def test_income_tax_is_not_charged_on_the_slice_taken_as_iht(self):
        """The rules relieve the portion equal to the IHT paid, so the
        stack is 1-(1-i)(1-b), not the 80% people often quote."""
        result = UK_IHT.bequest(non_pension_assets=0, pension_assets=2_000_000,
                                on=AFTER, bands=2, beneficiary_marginal_rate=0.40)
        pension_after_iht = 2_000_000 - result.iht_due
        assert result.beneficiary_income_tax == pytest.approx(pension_after_iht * 0.40)

    @pytest.mark.parametrize("rate, expected", [(0.20, 0.52), (0.40, 0.64), (0.45, 0.67)])
    def test_effective_rate_on_an_unspent_pension(self, rate, expected):
        assert effective_pension_death_rate(rate) == pytest.approx(expected, abs=0.005)

    def test_an_isa_is_taxed_less_than_a_pension_after_2027(self):
        """The whole basis of moving money out during life."""
        assert effective_pension_death_rate(0.40) > 0.40


class TestTheDecisionRule:
    def test_moving_to_an_isa_wins_when_your_rate_is_below_the_beneficiary_s(self):
        """Withdraw at m, the ISA keeps (1-m); leave it and heirs keep (1-b).
        Move when m < b."""
        fund, iht_rate = 100_000.0, 0.40
        my_rate, their_rate = 0.20, 0.40

        moved = fund * (1 - my_rate) * (1 - iht_rate)
        left = fund * (1 - iht_rate) * (1 - their_rate)
        assert moved > left

    def test_and_loses_when_your_rate_is_higher(self):
        fund, iht_rate = 100_000.0, 0.40
        moved = fund * (1 - 0.45) * (1 - iht_rate)
        left = fund * (1 - iht_rate) * (1 - 0.20)
        assert moved < left


class TestBreakdown:
    def test_components_reconcile(self):
        result = UK_IHT.bequest(non_pension_assets=1_000_000, pension_assets=2_000_000,
                                on=AFTER, bands=2)
        assert result.gross_estate == pytest.approx(3_000_000)
        assert result.net_to_beneficiaries == pytest.approx(
            result.gross_estate - result.iht_due - result.beneficiary_income_tax
        )
        assert result.effective_tax_rate == pytest.approx(
            result.total_tax / result.gross_estate
        )

    def test_a_pension_heavy_estate_loses_most_of_itself(self):
        result = UK_IHT.bequest(non_pension_assets=750_000, pension_assets=5_000_000,
                                on=AFTER, bands=2, beneficiary_marginal_rate=0.40)
        assert result.effective_tax_rate > 0.55

    def test_rules_are_configurable(self):
        """Bands are frozen only until they are not."""
        generous = IHTRules(nil_rate_band=1_000_000)
        assert generous.bequest(non_pension_assets=1_500_000, pension_assets=0,
                                on=AFTER, bands=2).iht_due == 0.0


class TestGifts:
    """Lifetime gifting: the seven-year rule and taper relief."""

    def test_taper_multipliers(self):
        from retireplan.tax.iht import gift_taper_multiplier
        assert gift_taper_multiplier(1) == 1.0      # full 40%
        assert gift_taper_multiplier(3.5) == 0.8    # 32%
        assert gift_taper_multiplier(4.5) == 0.6    # 24%
        assert gift_taper_multiplier(5.5) == 0.4    # 16%
        assert gift_taper_multiplier(6.5) == 0.2    # 8%
        assert gift_taper_multiplier(7.5) == 0.0    # out of the estate

    def test_a_gift_older_than_seven_years_is_ignored(self):
        old = UK_IHT.bequest(non_pension_assets=1_000_000, pension_assets=0, on=date(2070, 1, 1),
                             gifts=[(date(2050, 1, 1), 500_000)])
        assert old.gift_iht == 0.0
        assert old.allowances == UK_IHT.allowances(1_000_000, bands=2)

    def test_a_recent_gift_consumes_the_nil_rate_band(self):
        recent = UK_IHT.bequest(non_pension_assets=1_000_000, pension_assets=0,
                                on=date(2070, 1, 1), gifts=[(date(2068, 1, 1), 200_000)])
        no_gift = UK_IHT.bequest(non_pension_assets=1_000_000, pension_assets=0,
                                 on=date(2070, 1, 1))
        assert recent.allowances < no_gift.allowances

    def test_taper_only_bites_above_the_nil_rate_band(self):
        """A gift inside the band has no tax to taper — the common
        misunderstanding of the seven-year rule."""
        small = UK_IHT.bequest(non_pension_assets=500_000, pension_assets=0,
                               on=date(2070, 1, 1), gifts=[(date(2066, 1, 1), 100_000)])
        assert small.gift_iht == 0.0

    def test_a_large_recent_gift_is_taxed_with_taper(self):
        big = UK_IHT.bequest(non_pension_assets=500_000, pension_assets=0,
                             on=date(2070, 1, 1), gifts=[(date(2066, 1, 1), 1_000_000)])
        chargeable = 1_000_000 - 650_000          # two nil-rate bands
        assert big.gift_iht == pytest.approx(chargeable * 0.40 * 0.6)  # ~4 years survived

    def test_earlier_gifts_claim_the_band_first(self):
        gifts = [(date(2065, 1, 1), 650_000), (date(2068, 1, 1), 100_000)]
        result = UK_IHT.bequest(non_pension_assets=500_000, pension_assets=0,
                                on=date(2070, 1, 1), gifts=gifts)
        # The band is exhausted by the first gift, so the second is fully charged.
        assert result.gift_iht == pytest.approx(100_000 * 0.40)

    def test_gifting_early_beats_gifting_late(self):
        early = UK_IHT.bequest(non_pension_assets=600_000, pension_assets=2_000_000,
                               on=date(2070, 1, 1), gifts=[(date(2040, 1, 1), 400_000)])
        late = UK_IHT.bequest(non_pension_assets=600_000, pension_assets=2_000_000,
                              on=date(2070, 1, 1), gifts=[(date(2068, 1, 1), 400_000)])
        assert early.total_to_family > late.total_to_family

    def test_total_to_family_counts_gifts_already_received(self):
        result = UK_IHT.bequest(non_pension_assets=500_000, pension_assets=0,
                                on=date(2070, 1, 1), gifts=[(date(2040, 1, 1), 300_000)])
        assert result.total_to_family == pytest.approx(
            result.net_to_beneficiaries + 300_000 - result.gift_iht
        )
