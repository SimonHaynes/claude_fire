"""Tax systems.

A `TaxSystem` is everything jurisdiction-specific the engine needs. Keeping it
behind one small interface is what lets the same projection code run a UK plan
this year and a different jurisdiction — or a different tax year — without the
cashflow module knowing anything about allowances or bands.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

INF = float("inf")


@dataclass(frozen=True)
class Band:
    """A marginal rate applying up to `upper` of total income."""

    upper: float  # use INF for the top band
    rate: float


@dataclass(frozen=True)
class RateSchedule:
    """A piecewise-linear marginal rate schedule on total income.

    Expressing tax as *effective marginal rates on total income* — rather than
    an allowance plus bands on taxable income — is what makes quirks like the
    UK's personal-allowance taper fall out naturally instead of needing a
    special case, and it makes the inverse (`gross_for_net`) exact rather than
    a search.
    """

    bands: tuple[Band, ...]

    def __post_init__(self) -> None:
        uppers = [b.upper for b in self.bands]
        if uppers != sorted(uppers):
            raise ValueError("bands must be in ascending order of upper bound")
        if uppers[-1] != INF:
            raise ValueError("the top band must be unbounded (upper=INF)")

    def tax(self, income: float) -> float:
        if income <= 0:
            return 0.0
        total = 0.0
        lower = 0.0
        for band in self.bands:
            if income <= lower:
                break
            total += (min(income, band.upper) - lower) * band.rate
            lower = band.upper
        return total

    def marginal_rate(self, income: float) -> float:
        for band in self.bands:
            if income < band.upper:
                return band.rate
        return self.bands[-1].rate

    def scaled(self, factor: float) -> "RateSchedule":
        """The same rates with every threshold multiplied by `factor`.

        Used to model fiscal drag. This engine works in real terms, so leaving
        thresholds alone silently assumes they rise with inflation — but the
        personal allowance, the basic-rate ceiling and the nil-rate bands are
        frozen in *nominal* terms, which means they shrink in real terms every
        year. Passing a factor below 1 restores that.
        """
        return RateSchedule(tuple(
            Band(b.upper if b.upper == INF else b.upper * factor, b.rate)
            for b in self.bands
        ))

    def gross_for_net(self, existing_income: float, target_net: float) -> float:
        """Extra gross income needed to take home `target_net` more.

        Solved exactly by walking the bands: within each one the schedule is
        linear, so £1 of gross yields £(1 - rate) of net. Returns `inf` if the
        target is unreachable (only possible with a 100% marginal band).
        """
        if target_net <= 0:
            return 0.0
        gross = 0.0
        remaining = target_net
        position = existing_income
        for band in self.bands:
            if band.upper <= position:
                continue
            width = band.upper - position
            net_rate = 1.0 - band.rate
            if net_rate <= 0:  # a confiscatory band yields no net income
                if width == INF:
                    return INF
                gross += width
                position = band.upper
                continue
            available = width * net_rate
            if remaining <= available:
                return gross + remaining / net_rate
            remaining -= available
            gross += width
            position = band.upper
        return INF

    def gross_for_net_partly_relieved(
        self, existing_income: float, relief_fraction: float,
        relief_headroom: float, target_net: float,
    ) -> float:
        """Extra gross needed to net `target_net`, where `relief_fraction` of
        every pound of gross is entirely tax-free -- up to `relief_headroom`
        tax-free pounds in total -- and the rest is taxed as ordinary income
        stacked on `existing_income`.

        This is UFPLS: 25% of each withdrawal is tax-free until the Lump Sum
        Allowance is used up, then withdrawals are fully taxable. Solved
        exactly in two phases, the same band-walking approach as
        `gross_for_net`: first while relief headroom remains (where a pound
        of gross yields `1 - taxable_fraction * rate` of net, since part of
        it was never taxable to begin with), then -- for whatever net is
        still needed -- as an ordinary fully-taxable gross-up continued from
        wherever phase one left off. Falls back to `gross_for_net` outright
        if there is no relief to give.
        """
        if target_net <= 0:
            return 0.0
        if relief_fraction <= 0 or relief_headroom <= 0:
            return self.gross_for_net(existing_income, target_net)

        taxable_fraction = 1.0 - relief_fraction
        # Relief headroom is `relief_headroom` tax-free pounds; every pound of
        # *gross* carries `relief_fraction` tax-free and `taxable_fraction`
        # taxable, so headroom runs out after this much taxable income has
        # been generated alongside it.
        phase_1_taxable_capacity = (
            relief_headroom / relief_fraction * taxable_fraction
            if taxable_fraction > 0 else INF
        )

        gross = 0.0
        remaining_net = target_net
        position = existing_income
        taxable_used = 0.0

        for band in self.bands:
            if band.upper <= position:
                continue
            width = min(band.upper - position, phase_1_taxable_capacity - taxable_used)
            if width <= 0:
                break
            # Net gained per pound of *gross* in this band: relief_fraction
            # of it was never taxable, taxable_fraction is taxed at the
            # band's rate.
            net_rate = 1.0 - taxable_fraction * band.rate
            if net_rate <= 0:  # a confiscatory band yields no net income
                if width == INF:
                    return INF
                gross += width / taxable_fraction
                position += width
                taxable_used += width
                continue
            available = width * net_rate / taxable_fraction
            if remaining_net <= available:
                return gross + remaining_net / net_rate
            remaining_net -= available
            gross += width / taxable_fraction
            position += width
            taxable_used += width

        # Relief headroom (or the bands themselves) ran out before the
        # target was reached: whatever remains is fully taxable, stacked on
        # top of wherever phase one left off.
        if remaining_net <= 0:
            return gross
        return gross + self.gross_for_net(position, remaining_net)


class TaxSystem(Protocol):
    """What the projection engine needs to know about tax."""

    name: str
    tax_year: str
    pension_access_age: int

    def income_tax(self, income: float) -> float: ...

    def national_insurance(self, employment_income: float) -> float: ...

    def gross_pension_withdrawal_for_net(self, other_taxable_income: float, target_net: float) -> float:
        """Gross drawdown needed to net `target_net` on top of existing income."""
        ...

    def ufpls_gross_for_net(
        self, other_taxable_income: float, tax_free_used: float, target_net: float
    ) -> float:
        """Gross UFPLS withdrawal needed to net `target_net`, 25% tax-free up
        to remaining Lump Sum Allowance headroom, the rest taxed on top of
        `other_taxable_income`."""
        ...

    def ufpls_split(self, gross: float, tax_free_used: float) -> tuple[float, float]:
        """Split a gross UFPLS withdrawal into (tax_free, taxable), respecting
        whatever Lump Sum Allowance headroom `tax_free_used` has left."""
        ...

    def ufpls_gross_for_taxable(self, tax_free_used: float, target_taxable: float) -> float:
        """Gross UFPLS withdrawal that produces exactly `target_taxable` of
        taxable income -- for capping at a tax-band ceiling rather than a
        net-income target."""
        ...

    def capital_gains_tax(self, gain: float, other_taxable_income: float = 0.0) -> float: ...

    def dividend_tax(self, dividends: float, other_taxable_income: float = 0.0) -> float: ...

    def gia_gross_for_net(self, other_taxable_income: float, basis_fraction: float, target_net: float) -> float:
        """Gross GIA proceeds needed to net `target_net` after CGT on the gain portion."""
        ...
