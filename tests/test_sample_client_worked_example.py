"""The `sample_client` scenario set and report builder stay usable.

Three of the four workflow skills point at `workspace/sample_client/` as their
worked example. An example that has quietly stopped working teaches the wrong
thing more effectively than no example at all, so the structure is pinned here.

Deliberately does *not* run the Monte Carlo: that belongs in
`test_integration_sample_client.py`, and a test that needs 2,000 trials per
scenario to tell you an import broke is a test nobody runs.
"""
from __future__ import annotations

from datetime import date

from workspace.sample_client.household import AS_OF
from workspace.sample_client.scenarios import (
    BASE_CASE,
    CONSERVATIVE,
    HEADLINE,
    NOTICE_PERIOD_MONTHS,
    RECOMMENDED,
    STRETCH,
    VARIANTS,
)
from retireplan import add_months


class TestScenarioSet:
    def test_base_case_is_the_stretch_scenario(self):
        # Phase 1 defines exactly one scenario, and phase 2 keeps it in the
        # set even though it fails -- why it fails is the useful finding.
        assert HEADLINE["stretch"] is BASE_CASE

    def test_stretch_date_is_computed_from_as_of_not_hardcoded(self):
        # A plan regenerated later must see this move with AS_OF, rather than
        # staying pinned to when the file was written.
        assert STRETCH == add_months(AS_OF, NOTICE_PERIOD_MONTHS)

    def test_headline_dates_are_ordered(self):
        assert STRETCH < RECOMMENDED < CONSERVATIVE

    def test_every_reported_scenario_chooses_a_withdrawal_rule(self):
        # `withdrawal=None` spends the plan regardless and lets shortfalls
        # stand: an honest baseline for engine testing, not a client plan.
        for name, scenario in {**HEADLINE, **VARIANTS}.items():
            assert scenario.withdrawal is not None, f"{name} has no withdrawal rule"

    def test_every_scenario_retires_both_people(self):
        for name, scenario in {**HEADLINE, **VARIANTS}.items():
            assert set(scenario.retirement_dates) == {"Pat", "Robin"}, name

    def test_variants_all_run_against_the_recommended_date(self):
        # A variant that changes two things at once tells you nothing about
        # either, so every variant must hold the date fixed.
        for name, scenario in VARIANTS.items():
            assert set(scenario.retirement_dates.values()) == {RECOMMENDED}, name

    def test_by_asset_type_mix_does_not_reprice_everything(self):
        # Setting `default_growth_pct` re-prices every unnamed asset including
        # the house, which once overstated an estate by two thirds.
        allocation = VARIANTS["allocation_by_asset_type"].allocation
        assert allocation.default_growth_pct is None

    def test_scenario_names_are_distinct(self):
        names = [s.name for s in {**HEADLINE, **VARIANTS}.values()]
        assert len(names) == len(set(names))


class TestReportBuilderImports:
    def test_module_imports_and_helpers_behave(self):
        from workspace.sample_client import build_report

        # Percentages are floored, never rounded, so prose can never disagree
        # with the dial beside it.
        assert build_report.pct(0.9496) == "94.9%"
        assert build_report.pct(0.9999) == "99.9%"
        assert build_report.money(1234.6) == "£1,235"
        assert build_report.millions(2_450_000) == "£2.5m"
        assert build_report.millions(950_000) == "£950,000"

    def test_asset_type_labels_are_plain_english(self):
        from workspace.sample_client.build_report import TYPE_LABELS

        # A client should never have to read "dc_pension".
        assert TYPE_LABELS["dc_pension"] == "Pension"
        assert all(not label.islower() for label in TYPE_LABELS.values())


class TestSweptDatesStillDescribeReality:
    def test_recommended_is_later_than_the_documented_crossing_point(self):
        # RECOMMENDED's docstring records a sweep crossing 95% in April 2030
        # and adds a quarter of margin. If the engine's numbers move, that
        # comment is the first thing that goes stale.
        assert RECOMMENDED > date(2030, 4, 1)
