"""Allocation strategies: overriding what an asset earns.

By default each asset earns whatever its own `ReturnModel` says. An
`AllocationStrategy` can override that per asset per year, which is how you
express glide paths and equity/bond splits without editing the household's
asset definitions.

Overriding *per asset* rather than globally matters more than it sounds. An
ISA bridging the years before a pension unlocks and the pension itself may
both be global trackers, but they are doing completely different jobs on
completely different horizons — de-risking them together is usually the wrong
answer to whichever problem you were trying to solve.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..market import SampledSeries, YearReturns
from ..model import Asset, AssetType


class AllocationStrategy(ABC):
    def reset(self) -> None:
        """Clear per-run state. Called once at the start of every trial."""

    def series_keys(self) -> frozenset[str]:
        """Market series this strategy needs, for the sample-window intersection."""
        return frozenset()

    @abstractmethod
    def real_return(self, asset: Asset, market: YearReturns, year_index: int) -> float | None:
        """Return for this asset this year, or None to use the asset's own model."""


def _blend(market: YearReturns, growth_key: str, safe_key: str, growth_pct: float) -> float:
    return growth_pct * market[growth_key] + (1 - growth_pct) * market[safe_key]


@dataclass
class StaticMix(AllocationStrategy):
    """One fixed growth/safe split applied to every matching asset, rebalanced annually.

    Rebalancing is frictionless here: no transaction costs, no spreads, and no
    capital gains tax (which is real for a GIA, though not for the ISAs and
    pensions this is usually pointed at).
    """

    growth_pct: float
    growth_key: str = "global_equity"
    safe_key: str = "gov_bonds"
    applies_to: frozenset[AssetType] | None = None
    """None means "every asset that tracks `growth_key`" — the usual intent.
    Name asset types explicitly to target a subset."""

    def series_keys(self) -> frozenset[str]:
        return frozenset({self.growth_key, self.safe_key})

    def _applies(self, asset: Asset) -> bool:
        if self.applies_to is not None:
            return asset.type in self.applies_to
        return isinstance(asset.returns, SampledSeries) and asset.returns.key == self.growth_key

    def real_return(self, asset, market, year_index):
        if not self._applies(asset):
            return None
        return _blend(market, self.growth_key, self.safe_key, self.growth_pct)


@dataclass
class ByAssetTypeMix(AllocationStrategy):
    """A different growth/safe split per asset type.

    The targeted alternative to `StaticMix`: hold pensions at full growth
    while de-risking only the money that has to survive a short bridge — or
    discover, by running it, that the bridge needed the growth more than it
    needed the protection.
    """

    growth_pct_by_type: dict[AssetType, float]
    default_growth_pct: float | None = None
    """What to do with asset types not named above. None — the default —
    leaves them entirely alone, on their own return models.

    Setting this to a number overrides *every* other asset, which is almost
    never what you want: it will happily re-price a house or a fixed-rate
    bond as though it were an equity fund. An earlier version defaulted to
    1.0 and did exactly that, inflating a projected estate by two thirds."""

    growth_key: str = "global_equity"
    safe_key: str = "gov_bonds"

    def series_keys(self) -> frozenset[str]:
        return frozenset({self.growth_key, self.safe_key})

    def real_return(self, asset, market, year_index):
        pct = self.growth_pct_by_type.get(asset.type, self.default_growth_pct)
        if pct is None:
            return None
        return _blend(market, self.growth_key, self.safe_key, pct)


@dataclass
class GlidePath(AllocationStrategy):
    """De-risk linearly from `start_pct` to `end_pct` over `years`, then hold.

    Measured in plan years from the as-of date rather than years to
    retirement, matching how most target-date funds actually behave.
    """

    start_pct: float
    end_pct: float
    years: int
    growth_key: str = "global_equity"
    safe_key: str = "gov_bonds"
    applies_to: frozenset[AssetType] | None = None

    def series_keys(self) -> frozenset[str]:
        return frozenset({self.growth_key, self.safe_key})

    def _applies(self, asset: Asset) -> bool:
        if self.applies_to is not None:
            return asset.type in self.applies_to
        return isinstance(asset.returns, SampledSeries) and asset.returns.key == self.growth_key

    def real_return(self, asset, market, year_index):
        if not self._applies(asset):
            return None
        t = min(1.0, year_index / self.years) if self.years > 0 else 1.0
        pct = self.start_pct + (self.end_pct - self.start_pct) * t
        return _blend(market, self.growth_key, self.safe_key, pct)


@dataclass
class BondTent(AllocationStrategy):
    """De-risk toward retirement, then re-risk afterward -- a V-shape, not a
    one-way decline.

    The Kitces/Pfau finding behind this: sequence-of-returns risk peaks *at*
    retirement, not years before it and not long after -- the portfolio is at
    its largest right when withdrawals begin, so a bad early sequence does
    the most damage exactly there. The classic "reduce equities as you age"
    glide path (`GlidePath`) keeps de-risking through retirement, which is
    the wrong side of the peak: once past the first several years, more
    growth improves outcomes rather than threatening them, because there is
    less remaining horizon for a crash to compound against and more horizon
    for a recovery to pay off.

    Three points, linear between them, in years from the as-of date (the
    same convention `GlidePath` uses) -- pick `years_to_low` to land on your
    own retirement date:

        start_pct (year 0) -> low_pct (years_to_low) -> end_pct (years_to_low + years_to_recover)

    `years_to_low` is therefore doing double duty as "years until
    retirement" -- there is no separate retirement-date parameter, by
    design, so this composes the same way every other allocation strategy
    does rather than needing the scenario's retirement date threaded through
    a new channel.
    """

    start_pct: float
    low_pct: float
    end_pct: float
    years_to_low: int
    years_to_recover: int
    growth_key: str = "global_equity"
    safe_key: str = "gov_bonds"
    applies_to: frozenset[AssetType] | None = None

    def series_keys(self) -> frozenset[str]:
        return frozenset({self.growth_key, self.safe_key})

    def _applies(self, asset: Asset) -> bool:
        if self.applies_to is not None:
            return asset.type in self.applies_to
        return isinstance(asset.returns, SampledSeries) and asset.returns.key == self.growth_key

    def real_return(self, asset, market, year_index):
        if not self._applies(asset):
            return None
        if year_index <= self.years_to_low:
            t = year_index / self.years_to_low if self.years_to_low > 0 else 1.0
            pct = self.start_pct + (self.low_pct - self.start_pct) * t
        else:
            elapsed = year_index - self.years_to_low
            t = min(1.0, elapsed / self.years_to_recover) if self.years_to_recover > 0 else 1.0
            pct = self.low_pct + (self.end_pct - self.low_pct) * t
        return _blend(market, self.growth_key, self.safe_key, pct)
