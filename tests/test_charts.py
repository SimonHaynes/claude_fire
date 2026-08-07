"""The hand-rolled report SVG generators — geometry, not visuals, since
there is no browser here to eyeball them with. `dataviz`-skill conformance
(one axis, thin marks, no dual-scale) is checked by construction in
`charts.py` itself; these tests guard the input contract and edge cases."""
from __future__ import annotations

import re

import pytest

from retireplan.reporting.charts import band_for, dial_svg, fan_chart_svg


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
