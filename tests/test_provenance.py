"""The tax figure register: sources, check dates and recheck dates.

`test_tax_verification.py` pins the staleness *warning*. This pins the thing
the warning is about — that every hardcoded figure names an authority and a
date, and that the dates in the register and the dates in the modules cannot
drift apart silently.
"""
from __future__ import annotations

import importlib
from datetime import date, timedelta

import pytest

from retireplan.tax import provenance

MODULES_WITH_RULES = {
    "retireplan.tax.uk": "UK",
    "retireplan.tax.iht": "UK_IHT",
    "retireplan.tax.trusts": "UK_RELEVANT_PROPERTY",
}


class TestEverySourceIsUsable:
    @pytest.mark.parametrize("source", provenance.SOURCES, ids=lambda s: s.covers[:40])
    def test_it_names_an_authority_over_https(self, source):
        assert source.url.startswith("https://")

    @pytest.mark.parametrize("source", provenance.SOURCES, ids=lambda s: s.covers[:40])
    def test_it_says_what_would_move_the_figure(self, source):
        # A recheck date without a reason gets rolled forward mechanically.
        assert len(source.moved_by) > 20

    @pytest.mark.parametrize("source", provenance.SOURCES, ids=lambda s: s.covers[:40])
    def test_the_recheck_date_follows_the_check(self, source):
        if source.checked_on is not None:
            assert source.recheck_by > source.checked_on

    @pytest.mark.parametrize("source", provenance.SOURCES, ids=lambda s: s.covers[:40])
    def test_it_names_the_figures_not_just_the_topic(self, source):
        assert len(source.covers) > 25

    def test_no_figure_is_registered_twice(self):
        keys = [(s.module, s.covers) for s in provenance.SOURCES]
        assert len(keys) == len(set(keys))


class TestDue:
    def test_an_unchecked_source_is_due_however_recent_its_recheck_date(self):
        never = provenance.Source(
            module="x", covers="c" * 30, url="https://example.invalid",
            checked_on=None, recheck_by=date(2099, 1, 1), moved_by="m" * 30,
        )
        assert never.is_due(date(2026, 1, 1))

    def test_a_source_is_due_on_its_recheck_date_not_after_it(self):
        source = provenance.SOURCES[0]
        assert source.is_due(source.recheck_by)
        assert not source.is_due(source.recheck_by - timedelta(days=1))

    def test_upcoming_excludes_what_is_already_due(self):
        as_of = date(2027, 6, 1)
        assert not set(provenance.upcoming(as_of, 3650)) & set(provenance.due(as_of))


class TestTheRegisterAgreesWithTheModules:
    """A module claiming a verification date the register cannot support is the
    failure this whole scheme exists to prevent."""

    @pytest.mark.parametrize("module_name,attribute", MODULES_WITH_RULES.items())
    def test_verified_on_matches_the_oldest_recorded_check(self, module_name, attribute):
        rules = getattr(importlib.import_module(module_name), attribute)
        assert rules.verified_on == provenance.last_checked(module_name)

    @pytest.mark.parametrize("module_name", MODULES_WITH_RULES)
    def test_every_module_with_rules_has_sources(self, module_name):
        assert provenance.for_module(module_name)

    def test_a_module_with_an_unchecked_source_reports_no_check_date(self):
        assert provenance.last_checked("retireplan.care") is None
