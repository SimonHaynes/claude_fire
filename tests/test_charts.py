"""The hand-rolled report SVG generators — geometry, not visuals, since
there is no browser here to eyeball them with. `dataviz`-skill conformance
(one axis, thin marks, no dual-scale) is checked by construction in
`charts.py` itself; these tests guard the input contract and edge cases."""
from __future__ import annotations

import math
import re
from datetime import date

import pytest

from retireplan import Scenario, compile_plan, project
from retireplan.reporting.cashflow_chart import (
    SOURCES, KeyEvent, LifePhase, _capital_drawn, _nice_axis, _place_events,
    cashflow_chart_svg, derive_events, derive_phases,
)
from retireplan.reporting.charts import band_for, dial_svg, fan_chart_svg
from retireplan.tax.uk import UK


def _percentiles(n: int, base: float = 100_000.0) -> dict[int, list[float]]:
    """A plausible widening fan: each percentile grows at its own rate."""
    rates = {5: 0.01, 10: 0.02, 50: 0.05, 90: 0.09, 95: 0.11}
    return {p: [base * (1 + r) ** i for i in range(n)] for p, r in rates.items()}


class TestFanChartSvg:
    def test_uses_the_5_10_50_90_95_bands(self):
        """Matches the asset-mix table's percentile set exactly -- a chart
        and its table must never imply a different definition of "the
        range." Old callers passing 25/75 keys would now KeyError, which is
        the point: a silent mismatch is worse than a loud one."""
        years = list(range(2026, 2026 + 10))
        percentiles = {k: v for k, v in _percentiles(10).items()}
        svg = fan_chart_svg(years, percentiles)
        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_missing_a_required_percentile_raises(self):
        years = list(range(2026, 2031))
        incomplete = {5: [1.0] * 5, 10: [1.0] * 5, 50: [1.0] * 5, 90: [1.0] * 5}  # no 95
        with pytest.raises(KeyError):
            fan_chart_svg(years, incomplete)

    def test_defaults_to_the_full_horizon(self):
        """No horizon_years means the plotted line reaches the last year
        given -- the same year a bequest figure would be read at."""
        n = 45
        years = list(range(2026, 2026 + n))
        svg = fan_chart_svg(years, _percentiles(n))
        # The last x-axis tick label is the final year -- proof the series
        # was not silently truncated.
        assert str(years[-1]) in svg

    def test_horizon_years_truncates_when_asked(self):
        n = 45
        years = list(range(2026, 2026 + n))
        svg = fan_chart_svg(years, _percentiles(n), horizon_years=10)
        assert str(years[9]) in svg
        assert str(years[-1]) not in svg

    def test_a_single_year_does_not_divide_by_zero(self):
        svg = fan_chart_svg([2026], _percentiles(1))
        assert "<svg" in svg

    def test_a_flat_zero_series_does_not_divide_by_zero(self):
        """A real crash: an asset type (cash, say) that is zero at every
        percentile for the whole horizon -- the exact case the skill tells
        build_report.py to skip charting, but this function must not raise
        even if that check is missed somewhere."""
        years = list(range(2026, 2036))
        zero = {p: [0.0] * len(years) for p in (5, 10, 50, 90, 95)}
        svg = fan_chart_svg(years, zero, label="cash")
        assert svg.startswith("<svg")

    def test_label_appears_in_the_accessible_name(self):
        years = list(range(2026, 2031))
        svg = fan_chart_svg(years, _percentiles(5), label="Pension balance")
        assert "Pension balance" in svg

    def test_output_is_well_formed_enough_to_embed(self):
        """Not a full XML parse (WeasyPrint's HTML parser is lenient), but
        every path/circle/text tag opened must also close, and there must
        be exactly one root <svg>."""
        years = list(range(2026, 2036))
        svg = fan_chart_svg(years, _percentiles(10))
        assert svg.count("<svg") == 1
        assert svg.count("</svg>") == 1
        # Every `<path d="...">` must have a non-empty d attribute.
        for d in re.findall(r'<path d="([^"]*)"', svg):
            assert d.strip()


class TestDialSvg:
    @pytest.mark.parametrize("pct, expected_band", [(0.50, "red"), (0.92, "yellow"), (0.99, "green")])
    def test_band_matches_success_probability(self, pct, expected_band):
        assert band_for(pct * 100)[0] == expected_band

    def test_output_is_well_formed(self):
        svg = dial_svg(0.961)
        assert svg.count("<svg") == 1
        assert svg.count("</svg>") == 1

    def test_floors_rather_than_rounds_across_a_band(self):
        """94.96% must read as 94.9%, never rounded up to 95.0% and into
        the green band it has not actually reached."""
        svg = dial_svg(0.9496)
        assert "94.9" in svg
        assert "95.0" not in svg


class TestSurvivorshipMarker:
    """A wealth fan chart must show where the cohort has mostly died.

    Once mortality is sampled, a percentile band changes meaning as trials
    end: after the second death the estate is frozen, so a year in which most
    trials have ended shows a median *of frozen estates*. The symptom is a
    median that plateaus, which reads as the money running out of steam when
    households still alive are still compounding — on a real plan the chart
    flattened at £6.5m while the still-living median was £8.0m and rising.
    """

    def _series(self, n=55):
        years = list(range(2026, 2026 + n))
        bands = {k: [1_000_000 * (1 + 0.03 * i) for i in range(n)] for k in (5, 10, 50, 90, 95)}
        return years, bands

    def test_no_marker_without_alive_fraction(self):
        years, bands = self._series()
        assert "half of outcomes ended" not in fan_chart_svg(years, bands)

    def test_marker_appears_once_most_have_died(self):
        years, bands = self._series()
        alive = [1.0 if i < 30 else 0.3 for i in range(len(years))]
        svg = fan_chart_svg(years, bands, alive_fraction=alive)
        assert "half of outcomes ended by 2056" in svg

    def test_no_marker_while_everyone_is_alive(self):
        years, bands = self._series()
        svg = fan_chart_svg(years, bands, alive_fraction=[1.0] * len(years))
        assert "half of outcomes ended" not in svg

    def test_the_median_line_still_reaches_the_end(self):
        # The chart must still end where the bequest figures are read, so the
        # marker is a rule rather than a truncation.
        years, bands = self._series()
        alive = [1.0 if i < 10 else 0.1 for i in range(len(years))]
        svg = fan_chart_svg(years, bands, alive_fraction=alive)
        assert str(years[-1]) in svg


class TestCashflowChart:
    """The stacked cash-flow chart. Its one arithmetic invariant -- that the
    bands partition a year's money without double-counting -- is worth more
    than any amount of eyeballing, because two of the engine's fields are
    already contained in others (`ufpls_tax_free_taken` inside
    `dc_withdrawn_gross`, `income_annuity_income` inside
    `other_taxable_income`) and adding both would silently inflate every bar.
    """

    def _projection(self, simple_household, flat_market, **kwargs):
        scenario = Scenario(name="base", retirement_dates={"Alex": date(2029, 1, 1)})
        plan = compile_plan(simple_household, scenario, UK, date(2026, 1, 1))
        return project(plan, [flat_market.by_year[2020]] * plan.n_years, **kwargs)

    def test_bands_partition_income_plus_capital_drawn(self, simple_household, flat_market):
        projection = self._projection(simple_household, flat_market)
        for year in projection.years:
            if not year.alive:
                continue
            stacked = sum(source.amount(year) for source in SOURCES)
            expected = year.gross_income + _capital_drawn(year)
            assert stacked == pytest.approx(expected, abs=0.01), year.year

    def test_a_source_the_household_has_none_of_is_not_drawn(
        self, simple_household, flat_market
    ):
        """No dead legend entry. A band of zero for every year is not a band
        that reads as "none" -- it reads as a colour the reader hunts for."""
        svg = cashflow_chart_svg(self._projection(simple_household, flat_market))
        assert "DB pension and annuity" not in svg
        assert "Employment" in svg

    def test_the_frozen_tail_after_the_last_death_is_not_charted(
        self, simple_household, flat_market
    ):
        """`project` pads to a fixed length with zero-flow years so trials can
        be reduced on a common grid. Charting them draws empty bars for a
        decade after the household has ended."""
        projection = self._projection(simple_household, flat_market, deaths={"Alex": 4})
        assert not projection.years[-1].alive
        last_alive = max(y.year for y in projection.years if y.alive)
        svg = cashflow_chart_svg(projection)
        assert str(projection.years[-1].year) not in svg
        assert str(last_alive) in svg

    def test_a_projection_with_nobody_alive_raises(self, simple_household, flat_market):
        projection = self._projection(simple_household, flat_market)
        projection.years = [y for y in projection.years if not y.alive]
        with pytest.raises(ValueError, match="alive"):
            cashflow_chart_svg(projection)

    def test_a_height_that_leaves_no_plot_raises(self, simple_household, flat_market):
        """Rather than rendering a chart whose bars are two points tall: the
        band, axis and legend take fixed room, so a small `height` silently
        eats the data area instead of the chrome."""
        projection = self._projection(simple_household, flat_market)
        with pytest.raises(ValueError, match="plot"):
            cashflow_chart_svg(projection, height=90)

    def test_output_is_well_formed_enough_to_embed(self, simple_household, flat_market):
        svg = cashflow_chart_svg(self._projection(simple_household, flat_market))
        assert svg.count("<svg") == 1
        assert svg.count("</svg>") == 1
        for d in re.findall(r'<path d="([^"]*)"', svg):
            assert d.strip()

    def test_an_event_dated_off_the_end_of_the_plot_is_dropped(
        self, simple_household, flat_market
    ):
        """Not clamped to the first bar. A marker with nowhere to go used to
        land against the y-axis, where it reads as an event in year one."""
        projection = self._projection(simple_household, flat_market)
        after_the_end = max(y.year for y in projection.years) + 5
        svg = cashflow_chart_svg(
            projection, events=(KeyEvent(after_the_end, "Way off the end"),)
        )
        assert "Way off the end" not in svg

    def test_a_phase_dated_off_the_end_of_the_plot_is_dropped(
        self, simple_household, flat_market
    ):
        projection = self._projection(simple_household, flat_market)
        after_the_end = max(y.year for y in projection.years) + 5
        svg = cashflow_chart_svg(
            projection,
            phases=(LifePhase("Real", projection.years[0].year),
                    LifePhase("Off the end", after_the_end)),
        )
        assert "Off the end" not in svg
        assert "Real" in svg

    def test_events_and_phases_can_be_suppressed(self, simple_household, flat_market):
        projection = self._projection(simple_household, flat_market)
        svg = cashflow_chart_svg(projection, phases=(), events=())
        assert "Working" not in svg
        assert "Retire" not in svg


class TestDerivedPhasesAndEvents:
    def _projection(self, simple_household, flat_market, **kwargs):
        scenario = Scenario(name="base", retirement_dates={"Alex": date(2029, 1, 1)})
        plan = compile_plan(simple_household, scenario, UK, date(2026, 1, 1))
        return project(plan, [flat_market.by_year[2020]] * plan.n_years, **kwargs)

    def test_only_the_first_of_a_repeating_fact_is_an_event(
        self, simple_household, flat_market
    ):
        """A pension is drawn in most years of most plans. A marker on each is
        the bar chart again, not a timeline."""
        events = derive_events(self._projection(simple_household, flat_market))
        drawdowns = [e for e in events if e.label == "Pension drawdown"]
        assert len(drawdowns) <= 1

    def test_events_are_in_date_order(self, simple_household, flat_market):
        events = derive_events(self._projection(simple_household, flat_market))
        assert [e.year for e in events] == sorted(e.year for e in events)

    def test_phases_are_only_what_the_engine_knows(self, simple_household, flat_market):
        phases = derive_phases(self._projection(simple_household, flat_market))
        assert [p.label for p in phases] == ["Working", "Retired"]


class TestEventPlacement:
    def test_two_events_in_one_year_do_not_overprint(self):
        events = [KeyEvent(2030, "Retire"), KeyEvent(2030, "Tax-free cash")]
        placed = _place_events(events, lambda _year: 100.0)
        assert len({round(x, 3) for _e, x, _row in placed}) == 2

    def test_a_label_that_fits_nowhere_is_dropped_not_overprinted(self):
        """Four long labels on one year cannot be read however they are
        stacked. Dropping the surplus loses a name that Section 7's timeline
        still carries; overprinting loses all four."""
        events = [KeyEvent(2030, f"A rather long event label {i}") for i in range(4)]
        placed = _place_events(events, lambda _year: 100.0)
        assert len(placed) < len(events)

    def test_labels_use_both_rows_before_dropping_any(self):
        events = [KeyEvent(2030, "Retire"), KeyEvent(2031, "Tax-free cash")]
        placed = _place_events(events, lambda year: 100.0 + (year - 2030) * 12)
        assert {row for _e, _x, row in placed} == {0, 1}


class TestNiceAxis:
    @pytest.mark.parametrize("value", [1_234.0, 47_000.0, 124_800.0, 3_400_000.0, 1.0])
    def test_the_axis_covers_the_data_in_round_steps(self, value):
        top, intervals = _nice_axis(value)
        assert top >= value
        assert 4 <= intervals <= 6
        step = top / intervals
        mantissa = step / 10 ** math.floor(math.log10(step))
        assert round(mantissa, 6) in (1.0, 2.0, 2.5, 5.0)

    def test_an_all_zero_plan_does_not_divide_by_zero(self):
        top, intervals = _nice_axis(0.0)
        assert top > 0 and intervals > 0
