"""Checks that stop a report rendering something wrong.

Every case here corresponds to a defect that actually reached a rendered PDF
at least once -- see REVIEW.md's bug table.
"""
from __future__ import annotations

import pytest

from retireplan.reporting.checks import ReportContextError, check_report


def minimal_context(**overrides):
    context = {
        "client_name": "Pat & Robin Sample",
        "section3": {"rows": [{"name": "Base case", "net_bequest_range": "£1.1m – £3.4m"}]},
    }
    context.update(overrides)
    return context


class TestBequestMustBeNet:
    def test_net_range_passes(self):
        check_report(minimal_context())

    def test_gross_range_alone_is_rejected(self):
        context = minimal_context(
            section3={"rows": [{"name": "Base case", "bequest_range": "£2.0m – £6.1m"}]}
        )
        with pytest.raises(ReportContextError, match="net_bequest_range"):
            check_report(context)

    def test_the_message_names_the_gross_field_it_found(self):
        context = minimal_context(
            section3={"rows": [{"name": "Base case", "bequest_range": "£2.0m"}]}
        )
        with pytest.raises(ReportContextError, match="gross estate before"):
            check_report(context)

    def test_a_row_with_neither_is_still_rejected(self):
        context = minimal_context(section3={"rows": [{"name": "Base case"}]})
        with pytest.raises(ReportContextError, match="net_bequest_percentiles"):
            check_report(context)

    def test_no_results_table_is_not_an_error(self):
        # Section 3 is built late; checking a partial context should not fail.
        check_report({"client_name": "Pat Sample"})


class TestPreEscapedText:
    def test_plain_ampersand_passes(self):
        check_report(minimal_context(client_name="Pat & Robin Smith"))

    def test_pre_escaped_ampersand_is_rejected(self):
        with pytest.raises(ReportContextError, match="HTML entity"):
            check_report(minimal_context(client_name="Pat &amp; Robin Smith"))

    def test_numeric_entity_is_rejected(self):
        with pytest.raises(ReportContextError, match="HTML entity"):
            check_report(minimal_context(client_name="Pat &#38; Robin"))


class TestMarkdownEmphasis:
    def test_plain_prose_passes(self):
        check_report(minimal_context(intro="You stop working on 1 September 2028."))

    def test_bold_is_rejected(self):
        with pytest.raises(ReportContextError, match="markdown emphasis"):
            check_report(minimal_context(intro="Spending drops to **£44,400**."))

    def test_italic_is_rejected(self):
        with pytest.raises(ReportContextError, match="markdown emphasis"):
            check_report(minimal_context(intro="This is *not* a recommendation."))

    def test_it_is_found_inside_nested_structures(self):
        context = minimal_context(
            section5={"recommendations": [{"title": "Retire", "body": "Go **now**."}]}
        )
        with pytest.raises(ReportContextError, match=r"section5\.recommendations\[0\]\.body"):
            check_report(context)

    def test_svg_markup_is_not_mistaken_for_markdown(self):
        # Charts are generated and legitimately contain markup and asterisks.
        check_report(minimal_context(fanchart_svg="<svg><path d='M0 0 L*10*'/></svg>"))


class TestErrorMessage:
    def test_every_problem_is_reported_at_once(self):
        context = minimal_context(
            client_name="A &amp; B",
            intro="Spending drops to **£44,400**.",
        )
        with pytest.raises(ReportContextError) as excinfo:
            check_report(context)
        message = str(excinfo.value)
        assert "HTML entity" in message
        assert "markdown emphasis" in message
