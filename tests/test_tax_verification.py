"""The staleness warning on tax figures.

REVIEW.md called verification "advisory, not structural" -- it sat in prose
where it was agreed with and skipped. These tests pin the structural version.
"""
from __future__ import annotations

import dataclasses
import warnings
from contextlib import contextmanager
from datetime import date

import pytest

from retireplan.simulation import StaleTaxRulesWarning, warn_if_tax_rules_stale
from retireplan.tax.iht import UK_IHT
from retireplan.tax.uk import UK


@contextmanager
def no_staleness_warning():
    with warnings.catch_warnings(record=True) as log:
        warnings.simplefilter("always")
        yield
    stale = [r for r in log if issubclass(r.category, StaleTaxRulesWarning)]
    assert not stale, f"unexpected staleness warning: {[str(r.message) for r in stale]}"


class TestStaleTaxRules:
    def test_freshly_verified_rules_are_silent(self):
        tax = dataclasses.replace(UK, verified_on=date(2026, 1, 1))
        iht = dataclasses.replace(UK_IHT, verified_on=date(2026, 1, 1))
        with no_staleness_warning():
            warn_if_tax_rules_stale(tax, iht, as_of=date(2026, 8, 6))

    def test_rules_older_than_a_tax_year_warn(self):
        tax = dataclasses.replace(UK, verified_on=date(2023, 1, 1))
        with pytest.warns(StaleTaxRulesWarning, match="tax rules were last verified"):
            warn_if_tax_rules_stale(tax, UK_IHT, as_of=date(2026, 8, 6))

    def test_iht_is_checked_independently_of_income_tax(self):
        iht = dataclasses.replace(UK_IHT, verified_on=date(2020, 1, 1))
        with pytest.warns(StaleTaxRulesWarning, match="iht rules were last verified"):
            warn_if_tax_rules_stale(UK, iht, as_of=date(2026, 8, 6))

    def test_the_warning_says_what_to_do(self):
        tax = dataclasses.replace(UK, verified_on=date(2020, 1, 1))
        with pytest.warns(StaleTaxRulesWarning, match="gov.uk"):
            warn_if_tax_rules_stale(tax, UK_IHT, as_of=date(2026, 8, 6))

    def test_exactly_one_year_stale_does_not_warn(self):
        tax = dataclasses.replace(UK, verified_on=date(2025, 8, 6))
        with no_staleness_warning():
            warn_if_tax_rules_stale(tax, UK_IHT, as_of=date(2026, 8, 6))

    def test_a_tax_system_without_the_field_is_tolerated(self):
        # `TaxSystem` is a Protocol; a third-party jurisdiction need not carry
        # a verification date, and must not crash the engine for lacking one.
        class Bare:
            name = "Nowhere"

        with no_staleness_warning():
            warn_if_tax_rules_stale(Bare(), Bare(), as_of=date(2026, 8, 6))

    def test_shipped_defaults_are_current_enough_to_be_silent(self):
        # If this fails, the shipped figures need re-checking against gov.uk --
        # that is the point of the test, not a reason to move the date.
        with no_staleness_warning():
            warn_if_tax_rules_stale(UK, UK_IHT, as_of=UK.verified_on)
