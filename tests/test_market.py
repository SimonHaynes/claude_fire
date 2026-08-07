"""Market data, return models, and the bootstrap sampler.

Includes checks on the packaged CSVs themselves: a data file with a wrong sign
or a misparsed column produces plausible-looking output and is nearly
impossible to spot downstream.
"""
from __future__ import annotations

import random

import pytest

from retireplan import Blend, FixedNominal, FixedReal, MarketData, SampledSeries
from retireplan.market import BlockBootstrap


class TestReturnModels:
    def test_sampled_series_reads_its_key(self):
        assert SampledSeries("global_equity").real_return({"global_equity": 0.07}) == 0.07

    def test_fixed_real_ignores_the_market(self):
        assert FixedReal(0.03).real_return({"inflation": 0.50}) == 0.03

    def test_fixed_nominal_is_deflated(self):
        real = FixedNominal(0.08).real_return({"inflation": 0.03})
        assert real == pytest.approx(1.08 / 1.03 - 1)

    def test_fixed_nominal_goes_negative_when_inflation_bites(self):
        assert FixedNominal(0.06).real_return({"inflation": 0.12}) < 0

    def test_fixed_nominal_equals_its_rate_at_zero_inflation(self):
        assert FixedNominal(0.06).real_return({"inflation": 0.0}) == pytest.approx(0.06)

    def test_blend_weights_its_parts(self):
        blend = Blend.of(global_equity=0.6, gov_bonds=0.4)
        got = blend.real_return({"global_equity": 0.10, "gov_bonds": 0.0})
        assert got == pytest.approx(0.06)

    def test_series_keys_drive_the_sample_window(self):
        assert SampledSeries("x").series_keys() == frozenset({"x"})
        assert FixedReal(0.1).series_keys() == frozenset()
        assert FixedNominal(0.1).series_keys() == frozenset({"inflation"})
        assert Blend.of(a=0.5, b=0.5).series_keys() == frozenset({"a", "b"})


class TestMarketData:
    def test_window_is_the_intersection_of_the_requested_series(self):
        data = MarketData(by_year={
            2000: {"a": 0.1, "b": 0.2},
            2001: {"a": 0.1},
            2002: {"a": 0.1, "b": 0.2},
        })
        assert data.window(["a"]) == (2000, 2001, 2002)
        assert data.window(["a", "b"]) == (2000, 2002)

    def test_window_is_empty_for_an_unknown_series(self):
        data = MarketData(by_year={2000: {"a": 0.1}})
        assert data.window(["nope"]) == ()

    def test_packaged_data_loads(self):
        data = MarketData.load()
        assert len(data.sources) >= 2

    def test_long_series_spans_a_century(self):
        data = MarketData.load()
        window = data.window(["global_equity", "gov_bonds", "inflation"])
        assert window[0] == 1928
        assert len(window) >= 95

    def test_corporate_series_narrows_the_window(self):
        """Adding a short series must shrink the sample, visibly, not silently."""
        data = MarketData.load()
        long_window = data.window(["global_equity", "inflation"])
        with_corp = data.window(["global_equity", "inflation", "short_corporate"])
        assert len(with_corp) < len(long_window)
        assert with_corp[0] == 2008

    def test_known_historical_values_are_intact(self):
        """Spot-check landmark years against the sourced data.

        Tolerances are loose, not exact: `tools/fetch_market_data.py` rebuilds
        these CSVs from live sources on every clone, and CPI revisions plus
        upstream data changes mean two fetches a year apart will not agree
        to five decimal places. What must hold is the shape of the crash --
        get the sign or the rough magnitude wrong and something upstream has
        actually broken.
        """
        data = MarketData.load()
        assert data.by_year[2008]["global_equity"] == pytest.approx(-0.39, abs=0.01)
        assert data.by_year[1974]["global_equity"] == pytest.approx(-0.33, abs=0.01)
        assert data.by_year[2022]["short_corporate"] == pytest.approx(-0.126, abs=0.005)

    def test_returns_are_decimals_not_percentages(self):
        """A units slip here would inflate every projection by 100x."""
        data = MarketData.load()
        for year, row in data.by_year.items():
            for key, value in row.items():
                assert -1.0 < value < 2.0, f"{key} in {year} looks like a percentage: {value}"

    def test_inflation_is_present_for_every_long_year(self):
        """Every year the equity series covers must also carry inflation.

        Bounded by the data's own window, not a hardcoded range: the exact
        end year shifts with each `tools/fetch_market_data.py` run (CPI
        publication lags the current year), so pinning a literal upper bound
        here would fail on a perfectly good fresh fetch.
        """
        data = MarketData.load()
        window = data.window(["global_equity"])
        for year in window:
            assert "inflation" in data.by_year[year]


class TestBlockBootstrap:
    def _data(self):
        return MarketData(by_year={y: {"x": float(y)} for y in range(2000, 2010)})

    def test_path_has_the_requested_length(self):
        path = BlockBootstrap(5).path(self._data(), ["x"], 23, random.Random(1))
        assert len(path) == 23

    def test_is_reproducible_for_a_given_seed(self):
        a = BlockBootstrap(5).path(self._data(), ["x"], 30, random.Random(7))
        b = BlockBootstrap(5).path(self._data(), ["x"], 30, random.Random(7))
        assert a == b

    def test_different_seeds_give_different_paths(self):
        a = BlockBootstrap(5).path(self._data(), ["x"], 30, random.Random(1))
        b = BlockBootstrap(5).path(self._data(), ["x"], 30, random.Random(2))
        assert a != b

    def test_blocks_are_contiguous_and_wrap(self):
        """Consecutive years within a block is the whole point — it is what
        preserves sequence-of-returns risk."""
        path = BlockBootstrap(5).path(self._data(), ["x"], 5, random.Random(3))
        years = [int(row["x"]) for row in path]
        for earlier, later in zip(years, years[1:]):
            assert later == earlier + 1 or (earlier == 2009 and later == 2000)

    def test_block_of_one_is_iid_sampling(self):
        path = BlockBootstrap(1).path(self._data(), ["x"], 200, random.Random(4))
        assert len({int(r["x"]) for r in path}) > 5

    def test_raises_when_no_year_covers_every_series(self):
        with pytest.raises(ValueError, match="no historical years"):
            BlockBootstrap().path(self._data(), ["missing"], 10, random.Random(1))
