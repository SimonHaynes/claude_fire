"""What a lifetime annuity actually pays, priced from gilt yields and mortality.

The engine used to price annuities as `premium / (life_expectancy * loading)`.
That is wrong in a direction nobody notices: it ignores the discount rate
entirely, so it produced the same answer in 2021 with gilts at 1% as in 2026
with gilts at 5%, when the real market rate moved by more than half. It also
had no way to express age, a spouse, a guarantee or escalation — the four
things a client actually chooses between.

This prices from the two inputs that set a real quote:

1. **A discount curve.** Insurers back annuities with gilts and long corporate
   bonds, which is why rates follow a gilt selloff within weeks.
   `GiltCurve` reads the Bank of England series fetched by
   `tools/fetch_gilt_yields.py`.
2. **Mortality.** ONS population rates, adjusted for the two things that make
   annuitants different: they live longer than the population (people who
   expect to die soon do not buy annuities), and mortality keeps improving.

Everything else — joint life, guarantee period, escalation, enhanced
underwriting — falls out of the same annuity factor rather than being a
separate fudge, which is the point: the *relationships* between the options are
then structural, and only the overall level needs calibrating.

**Rates here are nominal, because the market quotes nominal.** The rest of this
engine works in real terms, so `AnnuityQuote.real_income` is the number that
belongs in a projection. A level annuity is not a flat income: at 3% inflation
it has lost a third of its purchasing power in fourteen years, and that is the
single most under-explained fact about the product.

**Calibrated, not predicted.** `uk_annuity_market()` carries a mortality
adjustment fitted to published best-buy rates on a stated date — see
`tools/validate_annuity_rates.py`, which reports the residual at every age
rather than only the fitted average. A quote from a whole-of-market broker is
the only real number; this is a planning estimate whose errors are visible.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Mapping, Sequence

from .mortality import ABSOLUTE_MAX_AGE, LifeTable

DATA_DIR = Path(__file__).parent / "data" / "gilts"
GILT_GLOB = "uk_gilt_yields_*.csv"
"""A subdirectory of its own, as the mortality table has, because
`MarketData.load` merges every CSV directly in `data/` by calendar year — and
these rows are keyed by month. Dropping the file alongside the return series
does not fail loudly; it corrupts the merge."""

CURVE_TERMS = (5, 10, 20)
ANNUITY_BENCHMARK_TERM = 15.0
"""The maturity the annuity market quotes against — roughly the duration of a
65-year-old's payment stream. Interpolated, since the Bank publishes 10 and 20
but not 15."""

VERIFIED_ON = date(2026, 8, 16)


@dataclass(frozen=True)
class GiltCurve:
    """Nominal yields and implied inflation at 5, 10 and 20 years.

    Percent-per-year in the source file; decimal fractions here, like every
    other rate in this engine.
    """

    month: str
    nominal: Mapping[int, float]
    implied_inflation: Mapping[int, float]

    def _interpolate(self, points: Mapping[int, float], term: float) -> float:
        """Linear between published terms, flat outside them.

        Flat rather than extrapolated on purpose: a curve extrapolated to 40
        years from a 20-year point is a guess with a slope, and for a
        90-year-old buyer the long end barely matters anyway.
        """
        terms = sorted(points)
        if term <= terms[0]:
            return points[terms[0]]
        if term >= terms[-1]:
            return points[terms[-1]]
        for lower, upper in zip(terms, terms[1:]):
            if lower <= term <= upper:
                weight = (term - lower) / (upper - lower)
                return points[lower] * (1 - weight) + points[upper] * weight
        raise AssertionError("unreachable: term is inside the published range")

    def nominal_yield(self, term: float = ANNUITY_BENCHMARK_TERM) -> float:
        return self._interpolate(self.nominal, term)

    def breakeven_inflation(self, term: float = ANNUITY_BENCHMARK_TERM) -> float:
        return self._interpolate(self.implied_inflation, term)

    def real_yield(self, term: float = ANNUITY_BENCHMARK_TERM) -> float:
        """Fisher, not subtraction.

        This is a *breakeven* real yield, so it embeds whatever inflation risk
        premium the market is charging — it is what an RPI-linked annuity is
        priced off, not a forecast of real returns.
        """
        return (1 + self.nominal_yield(term)) / (1 + self.breakeven_inflation(term)) - 1

    @classmethod
    def load(cls, path: str | Path | None = None, month: str | None = None) -> "GiltCurve":
        """The curve for `month`, or the latest available."""
        rows = _read_gilt_rows(path)
        if month is None:
            row = rows[-1]
        else:
            matching = [r for r in rows if r["month"] == month]
            if not matching:
                raise KeyError(f"no gilt curve for {month} in {len(rows)} months of data")
            row = matching[0]
        return cls._from_row(row)

    @classmethod
    def history(cls, path: str | Path | None = None) -> tuple["GiltCurve", ...]:
        """Every month, oldest first — for asking what an annuity would have
        bought at some point in the past, which is the only honest way to show
        a client how much of today's rate is the gilt market rather than them."""
        return tuple(cls._from_row(row) for row in _read_gilt_rows(path))

    @classmethod
    def _from_row(cls, row: Mapping[str, str]) -> "GiltCurve":
        return cls(
            month=row["month"],
            nominal={t: float(row[f"gilt_{t}y"]) / 100 for t in CURVE_TERMS},
            implied_inflation={t: float(row[f"inflation_{t}y"]) / 100 for t in CURVE_TERMS},
        )

    @classmethod
    def flat(cls, nominal: float, inflation: float = 0.0, month: str = "flat") -> "GiltCurve":
        """A hand-specified curve, for testing and for "what if gilts were at X"."""
        return cls(
            month=month,
            nominal={t: nominal for t in CURVE_TERMS},
            implied_inflation={t: inflation for t in CURVE_TERMS},
        )


def _read_gilt_rows(path: str | Path | None) -> list[dict[str, str]]:
    resolved = Path(path) if path else _latest_gilt_file()
    with resolved.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(line for line in fh if not line.startswith("#")))
    if not rows:
        raise ValueError(f"{resolved} has no data rows")
    return rows


def _latest_gilt_file() -> Path:
    candidates = sorted(DATA_DIR.glob(GILT_GLOB))
    if not candidates:
        raise FileNotFoundError(
            f"no {GILT_GLOB} in {DATA_DIR}. Run tools/fetch_gilt_yields.py "
            "(see DATA_SETUP.md)."
        )
    return candidates[-1]


@dataclass(frozen=True)
class AnnuitantMortality:
    """Population mortality bent towards the people who actually buy annuities.

    Two adjustments, both one-directional and both understated in a naive
    model:

    **Selection.** Annuitant mortality is materially lighter than population
    mortality — someone who expects to die soon does not exchange capital for
    an income stream, and annuity buyers skew wealthy, which is worth years by
    itself. `qx_multiplier` scales the published rates.

    **Improvement.** ONS national life tables are *period* tables: they assume
    2022-24 mortality lasts forever. It will not. Insurers price on a projected
    cohort basis, so a period table prices an annuity too cheaply — flattering
    the rate the model reports.

    `qx_multiplier` is **calibrated against market rates, not estimated from
    mortality data**, so it absorbs the insurer's expense and profit margin as
    well as genuine selection. Read `life_expectancy` from it as "what the
    published rates imply", never as a demographic finding.
    """

    table: LifeTable
    qx_multiplier: float = 1.0
    annual_improvement: float = 0.0
    male_share: float = 0.5
    """UK annuities have been unisex since December 2012, so a quote prices a
    blend rather than the buyer's own sex. Half and half unless a book's actual
    mix is known — the choice is worth about a year of life expectancy."""

    def qx(self, age: int, years_ahead: int, sex: str | None = None) -> float:
        """One-year death probability, adjusted, capped at 1."""
        if age >= ABSOLUTE_MAX_AGE:
            return 1.0
        base = self._blended(age, sex)
        improved = base * (1 - self.annual_improvement) ** years_ahead
        return min(1.0, improved * self.qx_multiplier)

    def _blended(self, age: int, sex: str | None) -> float:
        if sex in ("male", "female"):
            return self._lookup(sex, age)
        return (
            self.male_share * self._lookup("male", age)
            + (1 - self.male_share) * self._lookup("female", age)
        )

    def _lookup(self, sex: str, age: int) -> float:
        rate = self.table.qx.get((sex, age))
        return 1.0 if rate is None else rate

    def survival(self, age: float, sex: str | None = None) -> tuple[float, ...]:
        """Probability of being alive at each future whole year, starting at 1.0."""
        probabilities = [1.0]
        alive = 1.0
        start = int(age)
        for offset in range(ABSOLUTE_MAX_AGE - start):
            alive *= 1 - self.qx(start + offset, offset, sex)
            probabilities.append(alive)
            if alive < 1e-9:
                break
        return tuple(probabilities)

    def life_expectancy(self, age: float, sex: str | None = None) -> float:
        """Curtate expectation plus a half-year, so it reads like a published one."""
        return sum(self.survival(age, sex)[1:]) + 0.5


@dataclass(frozen=True)
class AnnuityOptions:
    """The four things a buyer actually chooses between, plus underwriting.

    Defaults describe the annuity the market quotes as its headline: single
    life, level, no guarantee, paid monthly in advance.
    """

    joint_life_proportion: float = 0.0
    """Fraction of the income continuing to a surviving spouse. 0 is single
    life; 0.5 and 1.0 are what providers offer."""

    spouse_age_offset: int = -3
    """Spouse's age relative to the buyer's. Negative is younger, which costs
    more — a younger spouse is likelier to outlive the annuitant and for
    longer. Three years younger is the market's own quoting convention."""

    guarantee_years: int = 0
    """Payments continue to the estate for this many years whatever happens.
    Cheap at 65 and dear at 80, because it insures the risk that is actually
    material at each age."""

    escalation: float = 0.0
    """Fixed annual increase. 0 buys a level annuity — nominally flat, and
    therefore falling in real terms every year of the contract."""

    rpi_linked: bool = False
    """Income rises with inflation, so it is priced off the *real* curve and
    holds its purchasing power. Overrides `escalation`."""

    payments_per_year: int = 12
    in_advance: bool = True

    health_uplift: float = 0.0
    """Enhanced or impaired-life underwriting, as a fraction added to the
    income. A smoker is worth roughly 7%; serious impairments reach 30% or
    more. **Only a real underwriter can price this** — the model has no
    knowledge of anyone's health, and applies whatever it is told."""

    def __post_init__(self) -> None:
        if self.rpi_linked and self.escalation:
            raise ValueError("an annuity escalates by RPI or by a fixed rate, not both")
        if not 0.0 <= self.joint_life_proportion <= 1.0:
            raise ValueError("joint_life_proportion is a fraction of the income")


@dataclass(frozen=True)
class AnnuityQuote:
    """A priced annuity, with enough working shown to argue with."""

    annual_income: float
    premium: float
    annuity_factor: float
    discount_rate: float
    life_expectancy: float
    options: AnnuityOptions
    curve_month: str

    @property
    def rate(self) -> float:
        """Income as a fraction of the premium — how the market quotes."""
        return self.annual_income / self.premium if self.premium else 0.0

    def real_income(self, year: int, inflation: float) -> float:
        """Purchasing power of year `year`'s payment, in today's money.

        Year 0 is the first payment. An RPI-linked annuity holds its value by
        construction; a level one does not, and this is the method that says so
        in pounds rather than in a warning.
        """
        if self.options.rpi_linked:
            return self.annual_income
        nominal = self.annual_income * (1 + self.options.escalation) ** year
        return nominal / (1 + inflation) ** year

    def half_life(self, inflation: float) -> float | None:
        """Years until the income has lost half its purchasing power.

        `None` where it never does — an RPI-linked annuity, or fixed escalation
        at or above inflation.
        """
        drift = (1 + self.options.escalation) / (1 + inflation) - 1
        if self.options.rpi_linked or drift >= 0:
            return None
        return math.log(0.5) / math.log(1 + drift)


@dataclass(frozen=True)
class AnnuityMarket:
    """Prices annuities from a curve and a mortality basis.

    `qx_multiplier` on the mortality is the single calibrated number. Every
    option adjustment — joint life, guarantee, escalation — is computed rather
    than assumed, so the *shape* of the market is a prediction of this model
    even though its *level* is fitted.
    """

    mortality: AnnuitantMortality
    curve: GiltCurve
    illiquidity_spread: float = 0.0
    """Yield above gilts on the assets actually backing annuities — corporate
    bonds, equity release, infrastructure. Separately identified from the
    mortality basis because the two have different age-shapes: a spread moves
    long-duration quotes most, a mortality multiplier moves short-duration
    ones."""

    inflation_risk_premium: float = 0.0
    """Subtracted from the real yield when pricing an RPI-linked annuity.

    Index-linked gilts trade richer than the nominal-minus-breakeven arithmetic
    implies, because pension funds bid for them, so a real yield derived from
    two nominal series overstates what an insurer can actually earn on
    inflation-matched assets. Without this the model prices inflation
    protection several percent too cheaply — and that is the one comparison a
    client most needs to get right."""

    verified_on: date = VERIFIED_ON

    def quote(
        self,
        premium: float,
        age: float,
        sex: str | None = None,
        options: AnnuityOptions | None = None,
    ) -> AnnuityQuote:
        options = options or AnnuityOptions()
        survival = self.mortality.survival(age, sex)
        payments = self._payment_probabilities(survival, age, sex, options)
        rate = self._discount_rate(payments, options)
        factor = self._annuity_factor(payments, rate, options)
        income = premium / factor * (1 + options.health_uplift) if factor else 0.0
        return AnnuityQuote(
            annual_income=income,
            premium=premium,
            annuity_factor=factor,
            discount_rate=rate,
            life_expectancy=self.mortality.life_expectancy(age, sex),
            options=options,
            curve_month=self.curve.month,
        )

    def _discount_rate(
        self, payments: Sequence[float], options: AnnuityOptions
    ) -> float:
        """The curve read at the payment stream's own duration.

        Reading every annuity off the 15-year point is the obvious shortcut and
        it is wrong by age: a 75-year-old's payments are concentrated inside
        ten years, so on an upward-sloping curve pricing them at fifteen
        overstates the income by several percent — and it does so only at the
        ages where the buyer is least able to change their mind.

        Duration depends on the rate and the rate depends on duration, so this
        iterates. Three passes is comfortably enough: the curve is nearly flat
        over the range the fixed point moves through.
        """
        premium = self.illiquidity_spread - (
            self.inflation_risk_premium if options.rpi_linked else 0.0
        )
        base = self.curve.real_yield if options.rpi_linked else self.curve.nominal_yield

        def source(term: float) -> float:
            return base(term) + premium

        growth = 0.0 if options.rpi_linked else options.escalation
        rate = source(ANNUITY_BENCHMARK_TERM)
        for _ in range(3):
            weights = [
                probability * (1 + growth) ** year / (1 + rate) ** year
                for year, probability in enumerate(payments)
            ]
            total = sum(weights)
            if total <= 0:
                break
            duration = sum(year * w for year, w in enumerate(weights)) / total
            rate = source(max(1.0, duration))
        return rate

    def _payment_probabilities(
        self,
        survival: Sequence[float],
        age: float,
        sex: str | None,
        options: AnnuityOptions,
    ) -> tuple[float, ...]:
        """Expected fraction of a full payment made in each future year.

        A guarantee period floors the probability at 1 for its length; a joint
        life adds the spouse's continuation weighted by the annuitant already
        having died. Both are expectations, which is exactly right for pricing
        and exactly wrong for describing an individual outcome.
        """
        spouse = (
            self.mortality.survival(age + options.spouse_age_offset, sex)
            if options.joint_life_proportion > 0 else ()
        )
        horizon = max(len(survival), len(spouse))

        probabilities = []
        for year in range(horizon):
            annuitant = survival[year] if year < len(survival) else 0.0
            paid = annuitant
            if options.joint_life_proportion > 0:
                spouse_alive = spouse[year] if year < len(spouse) else 0.0
                paid += options.joint_life_proportion * (1 - annuitant) * spouse_alive
            if year < options.guarantee_years:
                paid = max(paid, 1.0)
            probabilities.append(paid)
        return tuple(probabilities)

    def _annuity_factor(
        self, payments: Sequence[float], rate: float, options: AnnuityOptions
    ) -> float:
        """Present value of £1 a year, escalating, for as long as it is paid.

        An RPI-linked annuity is priced with a flat payment against the *real*
        curve, which is the same arithmetic as an escalating one against the
        nominal curve — and is why the two options cost about the same when
        breakeven inflation is near the escalation rate.
        """
        growth = 0.0 if options.rpi_linked else options.escalation
        factor = sum(
            probability * (1 + growth) ** year / (1 + rate) ** year
            for year, probability in enumerate(payments)
        )
        # Payments in arrears are worth a year's discount less; the frequency
        # correction is the standard (m-1)/2m of a year's payments.
        if not options.in_advance:
            factor -= 1.0
        frequency = (options.payments_per_year - 1) / (2 * options.payments_per_year)
        return max(1e-9, factor - frequency)

    def with_curve(self, curve: GiltCurve) -> "AnnuityMarket":
        return replace(self, curve=curve)


def uk_annuity_market(
    curve: GiltCurve | None = None,
    table: LifeTable | None = None,
) -> AnnuityMarket:
    """The calibrated UK market: ONS mortality, BoE curve, fitted multiplier.

    Built lazily rather than at import, because both inputs are files a fresh
    clone has not fetched yet and an import that fails on missing data would
    break every other part of the engine.
    """
    return AnnuityMarket(
        mortality=AnnuitantMortality(
            table=table or LifeTable.load(),
            qx_multiplier=CALIBRATED_QX_MULTIPLIER,
            annual_improvement=MORTALITY_IMPROVEMENT,
        ),
        curve=curve or GiltCurve.load(),
        illiquidity_spread=CALIBRATED_ILLIQUIDITY_SPREAD,
        inflation_risk_premium=CALIBRATED_INFLATION_RISK_PREMIUM,
    )


MORTALITY_IMPROVEMENT = 0.010
"""Annual reduction in each age's death rate, held fixed rather than fitted.

Roughly the long-term improvement rate the CMI's projections have settled
towards after the post-2011 slowdown. Fixing it matters: improvement and
selection are nearly degenerate against rate data alone, so fitting both would
produce two precise-looking numbers neither of which means anything."""

CALIBRATED_QX_MULTIPLIER = 0.69
"""Annuitant death rates as a fraction of the ONS population rates.

Fitted, with the spread below, to Hargreaves Lansdown's published best-buy
table of 13 August 2026 — five single-life level quotes at ages 55 to 75. The
value is in the range published annuitant tables occupy against population
mortality, but it is a calibration constant that also absorbs the insurer's
expense and profit margin, so read `life_expectancy` from it as "what today's
rates imply" rather than as a demographic estimate."""

CALIBRATED_ILLIQUIDITY_SPREAD = 0.0070
"""Yield above gilts on the assets backing annuity liabilities."""

CALIBRATED_INFLATION_RISK_PREMIUM = 0.0030
"""How much richer index-linked gilts trade than breakeven arithmetic implies.

Fitted separately, to the RPI-linked rows of the same table, and it earns its
place: without it the model prices inflation-linked annuities 2-5% too
generously at every age, which is a bias pointing straight at the level-versus-
escalating decision."""
