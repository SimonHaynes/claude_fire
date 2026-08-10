"""Historical market data, return models, and the block-bootstrap sampler.

Everything in this package works in **real (inflation-adjusted) terms**. The
CSVs in `retireplan/data/` hold real annual returns per series, plus an
`inflation` series used to convert fixed *nominal* yields into real ones.

Two ideas do most of the work here:

`ReturnModel` — how one asset earns its return. A global tracker samples a
historical equity series (`SampledSeries`); a bond slice bought at a fixed
quoted yield does not (`FixedNominal`) — its nominal rate is contractual and
it is *inflation* that decides what it is really worth. Modelling the second
as if it were the first is the single most flattering mistake available in
retirement planning, so it is deliberately hard to express here by accident.

`MarketData.window` — different series cover different periods. Equity data
runs from 1928; short-dated corporate bond data only from 2008. Rather than
pad or extrapolate, the sampler restricts itself to years where every series
a scenario actually needs is present, and reports that window so the
narrowing is visible instead of silent.
"""
from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Protocol, runtime_checkable

DATA_DIR = Path(__file__).parent / "data"

#: One year's real returns, keyed by series name (plus "inflation").
YearReturns = Mapping[str, float]


@runtime_checkable
class ReturnModel(Protocol):
    """How a single asset converts a year of market data into a real return.

    `rng` is supplied during simulation and omitted for a single deterministic
    projection. Models that carry idiosyncratic risk — a small number of
    individual bonds, say — should use it when present and fall back to their
    expected outcome when it is None, so a deterministic run stays readable.
    """

    def real_return(self, market: YearReturns, rng: random.Random | None = None) -> float: ...

    def series_keys(self) -> frozenset[str]:
        """Market series this model needs. Drives the sample-window intersection."""
        ...


@dataclass(frozen=True)
class SampledSeries:
    """Track a historical series directly (e.g. a global equity tracker)."""

    key: str

    def real_return(self, market: YearReturns, rng: random.Random | None = None) -> float:
        return market[self.key]

    def series_keys(self) -> frozenset[str]:
        return frozenset({self.key})


@dataclass(frozen=True)
class FixedReal:
    """A constant real return. Use for assets you deliberately want inert."""

    rate: float

    def real_return(self, market: YearReturns, rng: random.Random | None = None) -> float:
        return self.rate

    def series_keys(self) -> frozenset[str]:
        return frozenset()


@dataclass(frozen=True)
class ParametricNormal:
    """A real return drawn each year from a Normal(mean, stdev) distribution,
    independently -- the standard alternative to bootstrapping a historical
    series, not a replacement for it.

    Every year is an independent draw. That is a real, documented limitation
    relative to `BlockBootstrap`-sampled history, not a simplification this
    class hides: no autocorrelation, no mean reversion, no fat tails, no
    sequence that ever actually happened. Wade Pfau's comparison of the two
    families ("Monte Carlo Simulations Versus Historical Simulations")
    is explicit that this is the standing critique of parametric Monte
    Carlo -- markets exhibit mean reversion after crashes that an IID normal
    draw cannot reproduce, so this model tends to understate how much a bad
    early sequence and a subsequent recovery correlate. Kitces' finding runs
    the other way for the tails specifically: because a real 30-year
    historical window is drawn from a finite, already-survived sample,
    Monte Carlo -- sampling a wider distribution than history happened to
    realise -- can show a *worse* tail than any actual historical period did.
    Neither family dominates; which matters for a given question is the
    reason both exist here rather than one replacing the other.

    Deliberately does **not** attempt to correct `SampledSeries`-style
    historical data for known biases (survivorship, single-country
    coverage, and so on) by adjusting its mean or shape -- that is not
    standard practice anywhere in this space; FIRECalc and cFIREsim both
    use their historical series exactly as recorded and document the bias
    as a caveat rather than editing the data (see REVIEW.md sec.6). Use
    this class instead, with parameters taken from a source that already
    accounts for the bias you care about -- a published capital market
    assumption, or (see `tools/fetch_global_market_data.py`) the DMS/UBS
    Global Investment Returns Yearbook's own headline figures -- rather
    than asking a historical series to be two things at once.

    Needs no historical series (`series_keys()` is empty), which has one
    side effect worth knowing before reading a result: a household using
    this for every asset still reports `sample_years`/`sample_first_year`/
    `sample_last_year` from whatever other CSVs happen to be loaded (an
    empty requirement is satisfied by every year in the data), even though
    none of those years' actual returns fed the simulation at all. Not new
    to this class -- `FixedReal`-only households already do this -- but
    easy to misread as "97 years of history" when the real answer is zero.
    """

    mean: float
    stdev: float

    def real_return(self, market: YearReturns, rng: random.Random | None = None) -> float:
        return self.mean if rng is None else rng.gauss(self.mean, self.stdev)

    def series_keys(self) -> frozenset[str]:
        return frozenset()


@dataclass(frozen=True)
class FixedNominal:
    """A fixed *nominal* yield — a bond slice, a fixed-rate savings product.

    The real return is whatever inflation leaves behind, so a quoted 8% is
    worth ~5.4% real at 2.5% inflation and *negative* in a 1970s-style decade.
    Prefer this over `FixedReal` for anything quoted as a headline rate.
    """

    nominal_rate: float

    def real_return(self, market: YearReturns, rng: random.Random | None = None) -> float:
        return (1.0 + self.nominal_rate) / (1.0 + market["inflation"]) - 1.0

    def series_keys(self) -> frozenset[str]:
        return frozenset({"inflation"})


@dataclass(frozen=True)
class HeldToMaturityCredit:
    """Short-dated corporate bonds bought at a fixed yield and held to maturity.

    This is a different instrument from a bond *fund*, and modelling it as one
    gets the risk backwards. Holding to maturity removes mark-to-market risk
    entirely: rates can move and the bond still redeems at par. What remains is
    the risk that the issuer does not pay — so this model earns the coupon and
    loses capital only to defaults, net of recovery.

    Two features matter more than the headline numbers:

    **Defaults cluster with crashes.** Default incidence keys off the sampled
    year's equity return, so a bad credit year lands in the same year equities
    fall and the portfolio is being sold to fund spending. Treating defaults as
    independent would put the losses in the wrong years and badly understate
    the damage — the correlation *is* the risk.

    **Recoveries fall exactly when defaults rise.** Moody's data shows the two
    are negatively correlated (senior unsecured recovered 53.3% in 2007 and
    33.8% in 2008), so a stressed year applies both a higher default rate and
    a worse recovery.

    Defaults for `n_holdings` up to a few dozen are drawn from a binomial when
    an rng is available, because a concentrated ladder does not lose its
    long-run average every year — it loses nothing for years and then loses a
    lot at once. Set `n_holdings=0` for a diversified fund (expected loss).

    The stress signal is the `recession` series — the fraction of the year the
    economy was in an NBER-dated recession — not the equity return, so the
    credit cycle is driven by measured history rather than inferred from
    prices, and it covers the full 1928-2025 window.

    Defaults here are calibration, not measurement: pass parameters that suit
    the actual holdings. The shipped values reproduce Moody's long-run
    speculative-grade statistics — a 3.4% base rate at the 3x recession
    multiple gives a through-the-cycle average of ~4.5% and a full-recession
    year of ~10%, against Moody's reported long-run average of 4.48% and 2001
    peak of 9.98%. Investment-grade paper defaults an order of magnitude less
    often; set `default_rate` accordingly.
    """

    nominal_yield: float
    default_rate: float = 0.034
    """Annual issuer default rate outside recession. The default value is
    calibrated so the through-the-cycle average lands at Moody's long-run
    speculative-grade figure once recession years are weighted in."""

    recovery_rate: float = 0.60
    """Fraction of principal recovered on default. ~60% suits senior secured;
    senior unsecured has historically averaged nearer 40%."""

    stress_default_multiple: float = 3.0
    stress_recovery_rate: float = 0.40
    """Recoveries fall as defaults rise — the two are negatively correlated,
    so a recession applies both a higher default rate and a worse recovery."""

    n_holdings: int = 0
    """0 treats the holding as diversified and applies the expected loss.
    A positive value draws actual defaults from a binomial, so a concentrated
    ladder loses nothing for years and then loses a lot at once — which is how
    holding a dozen individual issuers actually behaves."""

    def _cycle(self, market: YearReturns) -> tuple[float, float]:
        """Default rate and recovery for this year, scaled by recession intensity."""
        intensity = market.get("recession", 0.0)
        rate = self.default_rate * (1 + (self.stress_default_multiple - 1) * intensity)
        recovery = self.recovery_rate + (self.stress_recovery_rate - self.recovery_rate) * intensity
        return min(1.0, rate), recovery

    def real_return(self, market: YearReturns, rng: random.Random | None = None) -> float:
        rate, recovery = self._cycle(market)

        if self.n_holdings > 0 and rng is not None:
            defaulted = sum(1 for _ in range(self.n_holdings) if rng.random() < rate)
            fraction = defaulted / self.n_holdings
        else:
            fraction = rate

        # Survivors pay their coupon and redeem at par; defaults return `recovery`.
        nominal = (1 - fraction) * (1 + self.nominal_yield) + fraction * recovery - 1
        return (1 + nominal) / (1 + market["inflation"]) - 1

    def series_keys(self) -> frozenset[str]:
        return frozenset({"inflation", "recession"})


@dataclass(frozen=True)
class Blend:
    """A fixed-weight mix of other return models, rebalanced annually.

    Weights are used as given and are not normalised — passing weights that
    do not sum to 1 is a leveraged or partly-uninvested position, which is a
    thing you may legitimately want to model.
    """

    parts: tuple[tuple[ReturnModel, float], ...]

    @classmethod
    def of(cls, **weighted_keys: float) -> "Blend":
        """Blend.of(global_equity=0.6, gov_bonds=0.4) — the common case."""
        return cls(tuple((SampledSeries(k), w) for k, w in weighted_keys.items()))

    def real_return(self, market: YearReturns, rng: random.Random | None = None) -> float:
        return sum(model.real_return(market, rng) * weight for model, weight in self.parts)

    def series_keys(self) -> frozenset[str]:
        return frozenset().union(*(m.series_keys() for m, _ in self.parts)) if self.parts else frozenset()


@dataclass(frozen=True)
class MarketData:
    """Real annual returns by year and series, loaded from the data CSVs."""

    by_year: Mapping[int, Mapping[str, float]]
    sources: tuple[str, ...] = ()

    @classmethod
    def load(cls, directory: Path | str | None = None) -> "MarketData":
        """Load and merge every CSV in `directory` (default: packaged data).

        Files may cover different year ranges and different series; rows are
        merged by year. Lines beginning with '#' are provenance headers — read
        them before trusting any number that comes out of this package.
        """
        directory = Path(directory) if directory is not None else DATA_DIR
        merged: dict[int, dict[str, float]] = {}
        names: list[str] = []
        for path in sorted(directory.glob("*.csv")):
            names.append(path.name)
            with path.open(newline="") as fh:
                rows = list(csv.DictReader(line for line in fh if not line.startswith("#")))
            if not rows:
                raise ValueError(f"{path} contains no data rows")
            for row in rows:
                year = int(row["year"])
                target = merged.setdefault(year, {})
                for key, raw in row.items():
                    if key != "year" and raw not in ("", None):
                        target[key] = float(raw)
        if not merged:
            raise ValueError(f"no market data CSVs found in {directory}")
        return cls(by_year=merged, sources=tuple(names))

    def window(self, keys: Iterable[str]) -> tuple[int, ...]:
        """Years for which *every* requested series has a value, ascending.

        This is what stops a short series silently contaminating a long one:
        ask for equities alone and you get ~a century; add short-dated
        corporate bonds and the usable window collapses to the years both
        cover. Callers should surface the length of what they get back.
        """
        required = frozenset(keys)
        return tuple(sorted(y for y, row in self.by_year.items() if required <= row.keys()))

    def series(self, key: str) -> dict[int, float]:
        return {y: row[key] for y, row in sorted(self.by_year.items()) if key in row}


@dataclass(frozen=True)
class BlockBootstrap:
    """Circular block bootstrap over historical years.

    Sampling contiguous blocks rather than independent years preserves the
    autocorrelation that makes sequence-of-returns risk real: a run of bad
    years early in retirement, while you are selling to eat, does far more
    damage than the same years scattered across three decades. "Circular"
    means a block that runs off the end wraps to the start, so every year is
    equally likely to be drawn.
    """

    block_years: int = 5

    def path(
        self,
        data: MarketData,
        keys: Iterable[str],
        n_years: int,
        rng: random.Random,
    ) -> list[YearReturns]:
        window = data.window(keys)
        if not window:
            raise ValueError(f"no historical years cover all of: {sorted(set(keys))}")
        out: list[YearReturns] = []
        n = len(window)
        while len(out) < n_years:
            start = rng.randrange(n)
            for offset in range(self.block_years):
                out.append(data.by_year[window[(start + offset) % n]])
                if len(out) >= n_years:
                    break
        return out
