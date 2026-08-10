"""Tax thresholds frozen in nominal terms, eroding in real ones.

REVIEW.md §1.3, graded high: the engine works in today's money, so leaving a
threshold constant silently assumes it rises with inflation. Most UK
thresholds are frozen instead, which drags income into higher bands and estate
above the nil-rate band every year. The omission flatters every projection.
"""
from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from retireplan import Assumptions, FiscalDrag, Scenario, compile_plan
from retireplan.plan import real_terms_factor
from retireplan.simulation import _iht_at
from retireplan.tax.iht import UK_IHT
from retireplan.tax.uk import UK

AS_OF = date(2026, 1, 1)


def plan_with(inflation: float, household, **drag_kwargs):
    household = dataclasses.replace(
        household,
        assumptions=dataclasses.replace(
            household.assumptions,
            fiscal_drag=FiscalDrag(inflation=inflation, **drag_kwargs),
        ),
    )
    scenario = Scenario("t", retirement_dates={})
    return compile_plan(household, scenario, UK, AS_OF)


@pytest.fixture
def household():
    from workspace.sample_client.household import SAMPLE_CLIENT

    return SAMPLE_CLIENT


class TestRealTermsFactor:
    def test_no_inflation_is_no_erosion(self):
        assert real_terms_factor(0.0, 20) == 1.0

    def test_year_zero_is_no_erosion(self):
        # Today's £12,570 *is* today's real value by definition.
        assert real_terms_factor(0.02, 0) == 1.0

    def test_erosion_compounds(self):
        assert real_terms_factor(0.02, 20) == pytest.approx(1 / 1.02**20)


class TestDefaultIsOldBehaviour:
    def test_drag_on_announced_freezes_is_opt_in(self):
        # Income tax, NI and the IHT bands have published freeze end dates, so
        # eroding them stays opt-in and attributable.
        assert Assumptions().fiscal_drag.inflation == 0.0

    def test_never_uprated_allowances_erode_by_default(self):
        """The Lump Sum Allowance and friends have no uprating provision at
        all, so holding them constant in real terms would assume an indexation
        that does not exist -- not a neutral default."""
        assert Assumptions().fiscal_drag.allowance_inflation == 0.02

    def test_switching_both_off_reuses_one_tax_system(self, household):
        plan = plan_with(0.0, household, allowance_inflation=0.0)
        assert all(y.tax is UK for y in plan.years)

    def test_the_lump_sum_allowance_erodes_with_no_inflation_set(self, household):
        plan = plan_with(0.0, household)
        assert plan.years[20].tax.lump_sum_allowance == pytest.approx(
            UK.lump_sum_allowance / 1.02**20
        )
        # ...while the announced freezes are left alone.
        assert plan.years[20].tax.income_tax_schedule.bands[0].upper == pytest.approx(
            UK.income_tax_schedule.bands[0].upper
        )


class TestIncomeThresholdsErode:
    def test_personal_allowance_shrinks_in_real_terms(self, household):
        plan = plan_with(0.02, household)
        year_zero = plan.years[0].tax.income_tax_schedule.bands[0].upper
        year_two = plan.years[2].tax.income_tax_schedule.bands[0].upper
        assert year_zero == pytest.approx(12_570)
        assert year_two == pytest.approx(12_570 / 1.02**2)

    def test_basic_rate_ceiling_shrinks_too(self, household):
        plan = plan_with(0.02, household)
        assert plan.years[2].tax.income_tax_schedule.bands[1].upper == pytest.approx(
            50_270 / 1.02**2
        )

    def test_rates_are_untouched(self, household):
        plan = plan_with(0.02, household)
        rates = [b.rate for b in plan.years[10].tax.income_tax_schedule.bands]
        assert rates == [b.rate for b in UK.income_tax_schedule.bands]

    def test_more_tax_is_due_on_the_same_real_income(self, household):
        plan = plan_with(0.02, household)
        early = plan.years[0].tax.income_tax(40_000)
        late = plan.years[10].tax.income_tax(40_000)
        assert late > early, "fiscal drag must raise tax on a constant real income"

    def test_erosion_stops_when_the_announced_freeze_ends(self, household):
        plan = plan_with(0.02, household, income_freeze_until=date(2028, 4, 6))
        # Roughly 2.3 years of freeze from AS_OF, then uprating resumes.
        frozen = plan.years[5].tax.income_tax_schedule.bands[0].upper
        later = plan.years[20].tax.income_tax_schedule.bands[0].upper
        assert frozen == pytest.approx(later)
        assert frozen < 12_570


class TestNeverUpratedAllowancesKeepEroding:
    def test_isa_allowance_erodes_past_the_income_freeze(self, household):
        plan = plan_with(0.02, household)
        # The ISA limit has no uprating mechanism and has not moved since 2017.
        assert plan.years[20].tax.isa_annual_allowance < plan.years[5].tax.isa_annual_allowance

    def test_lump_sum_allowance_erodes(self, household):
        plan = plan_with(0.02, household)
        assert plan.years[20].tax.lump_sum_allowance == pytest.approx(
            UK.lump_sum_allowance / 1.02**20
        )

    def test_they_can_be_made_to_track_the_income_freeze_instead(self, household):
        plan = plan_with(0.02, household, never_uprated_freeze_forever=False)
        # Both well past the income freeze end, so erosion has stopped for good.
        assert plan.years[20].tax.isa_annual_allowance == pytest.approx(
            plan.years[10].tax.isa_annual_allowance
        )
        assert plan.years[10].tax.isa_annual_allowance < UK.isa_annual_allowance


class TestTheTwoClocksDiverge:
    """Income thresholds resume uprating when the freeze ends; the allowances
    with no uprating mechanism never do. That asymmetry is what makes delaying
    a PCLS lose value while the bands it is drawn against hold theirs."""

    def test_income_thresholds_stop_eroding_but_the_lump_sum_allowance_does_not(self, household):
        plan = plan_with(0.02, household)
        late, later = plan.years[20].tax, plan.years[30].tax
        assert late.income_tax_schedule.bands[0].upper == pytest.approx(
            later.income_tax_schedule.bands[0].upper
        )
        assert later.lump_sum_allowance < late.lump_sum_allowance

    def test_the_lump_sum_allowance_loses_far_more_than_the_personal_allowance(self, household):
        plan = plan_with(0.02, household)
        end = plan.years[30].tax
        kept_allowance = end.income_tax_schedule.bands[0].upper / UK.income_tax_schedule.bands[0].upper
        kept_lsa = end.lump_sum_allowance / UK.lump_sum_allowance
        assert kept_allowance > 0.85          # capped by the announced freeze end
        assert kept_lsa < 0.60                # frozen in cash terms indefinitely


class TestStatePensionIsNotDragged:
    def test_state_pension_holds_its_real_value(self, household):
        # Triple-locked: it rises in real terms. Dragging it down would be
        # wrong, and wrong in the expensive direction.
        plan = plan_with(0.02, household)
        assert plan.years[20].tax.full_state_pension_annual == UK.full_state_pension_annual


class TestIHTBandsErodeOnTheirOwnHorizon:
    def test_zero_inflation_returns_the_rules_unchanged(self):
        assert _iht_at(UK_IHT, FiscalDrag(inflation=0.0), AS_OF, date(2070, 1, 1)) is UK_IHT

    def test_nil_rate_band_shrinks(self):
        drag = FiscalDrag(inflation=0.02, iht_freeze_until=date(2031, 4, 6))
        eroded = _iht_at(drag=drag, iht=UK_IHT, as_of=AS_OF, on=date(2070, 1, 1))
        assert eroded.nil_rate_band < UK_IHT.nil_rate_band

    def test_erosion_stops_at_the_iht_freeze_end(self):
        drag = FiscalDrag(inflation=0.02, iht_freeze_until=date(2031, 4, 6))
        at_2040 = _iht_at(UK_IHT, drag, AS_OF, date(2040, 1, 1))
        at_2070 = _iht_at(UK_IHT, drag, AS_OF, date(2070, 1, 1))
        assert at_2040.nil_rate_band == pytest.approx(at_2070.nil_rate_band)

    def test_the_iht_horizon_is_tracked_separately_from_the_income_one(self):
        """The two clocks have repeatedly moved on different timetables, so
        neither may borrow the other's factor -- tested by setting them apart
        rather than by asserting today's announced dates happen to differ,
        which they no longer do."""
        drag = FiscalDrag(
            inflation=0.02,
            income_freeze_until=date(2028, 4, 6),
            iht_freeze_until=date(2040, 4, 6),
        )
        iht = _iht_at(UK_IHT, drag, AS_OF, date(2070, 1, 1))
        income_factor = real_terms_factor(0.02, (date(2028, 4, 6) - AS_OF).days / 365.25)
        assert iht.nil_rate_band / UK_IHT.nil_rate_band < income_factor

    def test_taper_threshold_moves_with_the_bands(self):
        # A shrinking residence band tested against a fixed £2m threshold
        # would taper out at the wrong estate size.
        drag = FiscalDrag(inflation=0.02)
        eroded = _iht_at(UK_IHT, drag, AS_OF, date(2070, 1, 1))
        ratio_band = eroded.residence_nil_rate_band / UK_IHT.residence_nil_rate_band
        ratio_taper = eroded.taper_threshold / UK_IHT.taper_threshold
        assert ratio_band == pytest.approx(ratio_taper)


class TestSerdeRoundTrip:
    def test_non_default_fiscal_drag_survives(self):
        # Deliberately non-default: a round-trip test using defaults passes
        # even if the whole block is dropped.
        from retireplan.serde import household_from_dict, household_to_dict
        from workspace.sample_client.household import SAMPLE_CLIENT

        drag = FiscalDrag(
            inflation=0.031,
            income_freeze_until=date(2029, 4, 6),
            iht_freeze_until=date(2033, 4, 6),
            never_uprated_freeze_forever=False,
        )
        household = dataclasses.replace(
            SAMPLE_CLIENT,
            assumptions=dataclasses.replace(SAMPLE_CLIENT.assumptions, fiscal_drag=drag),
        )
        restored = household_from_dict(household_to_dict(household))
        assert restored.assumptions.fiscal_drag == drag

    def test_it_comes_back_as_a_dataclass_not_a_dict(self):
        # The old `Assumptions(**raw)` splat would hand back a plain dict here
        # and raise nothing until much later, or never.
        from retireplan.serde import household_from_dict, household_to_dict
        from workspace.sample_client.household import SAMPLE_CLIENT

        restored = household_from_dict(household_to_dict(SAMPLE_CLIENT))
        assert isinstance(restored.assumptions.fiscal_drag, FiscalDrag)

    def test_a_legacy_household_without_the_block_still_loads(self):
        from retireplan.serde import household_from_dict, household_to_dict
        from workspace.sample_client.household import SAMPLE_CLIENT

        raw = household_to_dict(SAMPLE_CLIENT)
        del raw["assumptions"]["fiscal_drag"]
        restored = household_from_dict(raw)
        assert restored.assumptions.fiscal_drag == FiscalDrag()
