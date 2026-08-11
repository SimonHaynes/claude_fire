"""UK income tax, NI, CGT, dividend tax and pension access rules. IHT lives in
`tax/iht.py`; self-employed Class 2/4 NI is not modelled.

VERIFY BEFORE USE. The income tax, NI and CGT *thresholds* are frozen under
current policy through 2027/28, so a 2025/26 figure is still the right 2026/27
one — but a freeze binds only what it names. It says nothing about rates, and
nothing about a figure with its own uprating mechanism: the dividend rates rose
2pp in April 2026 and the state pension rises every April under the triple lock,
both while the thresholds around them stood still. Check each constant against
its own timetable, not against the freeze.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date

from . import INF, Band, RateSchedule

PERSONAL_ALLOWANCE = 12_570.0
BASIC_RATE_LIMIT = 50_270.0
TAPER_START = 100_000.0
ADDITIONAL_RATE_START = 125_140.0

# Effective marginal rates, not legislated ones: the 60% band above £100,000 is
# the personal allowance withdrawing at £1 per £2 earned (40p + 20p). Stating it
# directly beats reconstructing it from a tapered allowance, which an earlier
# version did — and got the basic-rate band width wrong inside the taper.
UK_INCOME_TAX_2025_26 = RateSchedule((
    Band(PERSONAL_ALLOWANCE, 0.00),
    Band(BASIC_RATE_LIMIT, 0.20),
    Band(TAPER_START, 0.40),
    Band(ADDITIONAL_RATE_START, 0.60),
    Band(INF, 0.45),
))

UK_NATIONAL_INSURANCE_2025_26 = RateSchedule((
    Band(PERSONAL_ALLOWANCE, 0.00),   # primary threshold, currently aligned with the PA
    Band(BASIC_RATE_LIMIT, 0.08),     # upper earnings limit
    Band(INF, 0.02),
))

# 2026/27: £241.30 a week, the 2025/26 figure uprated 4.8% by the triple lock.
FULL_STATE_PENSION_ANNUAL = 12_547.60

# Normal Minimum Pension Age. 57 even for earlier modelled dates: the rise from
# 55 is legislated for 6 April 2028, and any plan written today will be lived
# under it, so assuming 55 would manufacture a bridge that will not exist.
PENSION_ACCESS_AGE = 57

# The PCLS is 25% of the pot, capped by a Lump Sum Allowance that did not rise
# with the old Lifetime Allowance: above a pot of ~£1.073m the "25% tax-free"
# rule of thumb stops being true, exactly for those most likely to rely on it.
PCLS_FRACTION = 0.25
LUMP_SUM_ALLOWANCE = 268_275.0

# Since the 30 Oct 2024 Budget shares carry the same two rates as residential
# property. There is no additional-rate CGT band: which of the two applies turns
# only on whether the taxpayer's other income already fills the basic-rate band.
CGT_ANNUAL_EXEMPT_AMOUNT = 3_000.0
CGT_BASIC_RATE = 0.18
CGT_HIGHER_RATE = 0.24

# The ordinary and upper rates rose 2pp on 6 April 2026; the additional rate did
# not. Unlike the CGT exempt amount the dividend allowance is a nil-rate *band*,
# not a deduction: it is charged at 0% but still occupies band space, so it can
# push later dividends up a band rather than removing £500 from tax outright.
DIVIDEND_ALLOWANCE = 500.0
DIVIDEND_BASIC_RATE = 0.1075
DIVIDEND_HIGHER_RATE = 0.3575
DIVIDEND_ADDITIONAL_RATE = 0.3935

# Assumed distribution yield on a global tracker held in a GIA, taxed yearly as
# dividend income and reinvested (which raises cost basis) though nothing leaves
# the account. A total-return index already includes it; splitting it out makes
# the tax visible without changing the assumed total return. A modelling
# assumption, not a client fact — a real fund's distribution varies by year.
GIA_DIVIDEND_YIELD = 0.02

VERIFIED_ON = date(2026, 8, 6)
"""When these figures were last checked against gov.uk. A date rather than a
prose reminder, because `simulation.run_monte_carlo` warns when it goes stale —
which makes skipping the check a decision rather than an oversight. Move it only
after actually re-checking."""


@dataclass(frozen=True)
class UKTaxSystem:
    name: str = "United Kingdom"
    tax_year: str = "2026/27"
    pension_access_age: int = PENSION_ACCESS_AGE
    income_tax_schedule: RateSchedule = field(default=UK_INCOME_TAX_2025_26)
    ni_schedule: RateSchedule = field(default=UK_NATIONAL_INSURANCE_2025_26)
    full_state_pension_annual: float = FULL_STATE_PENSION_ANNUAL
    pcls_fraction: float = PCLS_FRACTION
    lump_sum_allowance: float = LUMP_SUM_ALLOWANCE
    isa_annual_allowance: float = 20_000.0
    cgt_annual_exempt_amount: float = CGT_ANNUAL_EXEMPT_AMOUNT
    cgt_basic_rate: float = CGT_BASIC_RATE
    cgt_higher_rate: float = CGT_HIGHER_RATE
    dividend_allowance: float = DIVIDEND_ALLOWANCE
    dividend_basic_rate: float = DIVIDEND_BASIC_RATE
    dividend_higher_rate: float = DIVIDEND_HIGHER_RATE
    dividend_additional_rate: float = DIVIDEND_ADDITIONAL_RATE
    gia_dividend_yield: float = GIA_DIVIDEND_YIELD
    verified_on: date = VERIFIED_ON

    def with_thresholds_scaled(
        self, income_factor: float, allowance_factor: float | None = None
    ) -> "UKTaxSystem":
        """This system with every threshold multiplied by a factor below 1.

        Two factors because they run on different clocks. `income_factor`
        covers income tax and NI, frozen by announced policy to a stated date.
        `allowance_factor` covers the flat allowances with no uprating
        mechanism at all -- the Lump Sum Allowance, the ISA subscription
        limit, the CGT exempt amount, the dividend allowance -- which can
        keep eroding after the announced freezes end. Defaults to
        `income_factor` when not given.

        Note the ISA limit eroding progressively weakens `TaxEfficientOrder`'s
        recycling: less can be moved out of a pension each year in real terms.
        That is a real consequence the engine used to miss entirely, not an
        artefact of this method.

        Rates are untouched -- only the positions of the band edges move.
        `full_state_pension_annual` is untouched too: it is triple-locked and
        rises in real terms, so dragging it down would be wrong.
        """
        if allowance_factor is None:
            allowance_factor = income_factor
        return dataclasses.replace(
            self,
            income_tax_schedule=self.income_tax_schedule.scaled(income_factor),
            ni_schedule=self.ni_schedule.scaled(income_factor),
            lump_sum_allowance=self.lump_sum_allowance * allowance_factor,
            isa_annual_allowance=self.isa_annual_allowance * allowance_factor,
            cgt_annual_exempt_amount=self.cgt_annual_exempt_amount * allowance_factor,
            dividend_allowance=self.dividend_allowance * allowance_factor,
        )

    def income_tax(self, income: float) -> float:
        return self.income_tax_schedule.tax(income)

    def national_insurance(self, employment_income: float) -> float:
        return self.ni_schedule.tax(employment_income)

    def gross_pension_withdrawal_for_net(self, other_taxable_income: float, target_net: float) -> float:
        """Pension drawdown is subject to income tax but not NI."""
        return self.income_tax_schedule.gross_for_net(other_taxable_income, target_net)

    def _tax_stacked_on(self, amount: float, position: float,
                        bands: tuple[tuple[float, float], ...]) -> float:
        """Tax `amount` occupying the range `position` to `position + amount`.
        `bands` is `((upper, rate), ...)`, INF-terminated ascending, positions
        measured against total income exactly like `RateSchedule.tax`."""
        total = 0.0
        remaining = amount
        for upper, rate in bands:
            if remaining <= 0:
                break
            width = upper - position
            if width <= 0:
                continue
            taken = min(remaining, width)
            total += taken * rate
            remaining -= taken
            position += taken
        return total

    def cgt_basic_rate_room(self, other_taxable_income: float) -> float:
        """How much gain is charged at the basic rate before the higher one.

        Gains stack on *taxable* income -- income after the personal
        allowance -- so income below the allowance uses none of the basic-rate
        band. The allowance itself is not available against gains, but nor
        does leaving it unused shrink the band, which is why this floors the
        income at the allowance rather than subtracting it.
        """
        personal_allowance = self.income_tax_schedule.bands[0].upper
        basic_upper = self.income_tax_schedule.bands[1].upper
        return max(0.0, basic_upper - max(other_taxable_income, personal_allowance))

    def capital_gains_tax(self, gain: float, other_taxable_income: float = 0.0,
                          exempt_used: float = 0.0) -> float:
        """CGT on `gain`, given `other_taxable_income` already occupies the
        income tax bands and `exempt_used` of this year's annual exempt amount
        has already been consumed by an earlier disposal.

        The exempt amount is a deduction from the gain, not a nil-rate band:
        unlike the dividend allowance it does not occupy basic-rate space.
        """
        exempt = max(0.0, self.cgt_annual_exempt_amount - exempt_used)
        taxable = max(0.0, gain - exempt)
        if taxable <= 0:
            return 0.0
        at_basic = min(taxable, self.cgt_basic_rate_room(other_taxable_income))
        return at_basic * self.cgt_basic_rate + (taxable - at_basic) * self.cgt_higher_rate

    def dividend_tax(self, dividends: float, other_taxable_income: float = 0.0) -> float:
        """Dividend tax on `dividends` as the top slice of income.

        Dividends *are* income, so whatever personal allowance
        `other_taxable_income` has not used covers them first -- a retiree
        living on less than the allowance pays nothing on them. The dividend
        allowance then sits directly above at 0%, occupying band space rather
        than being deducted, so it can push later dividends up a band.

        Dividends do not taper the personal allowance here, though in reality
        they count towards adjusted net income: above £100,000 this
        understates the charge.
        """
        if dividends <= 0:
            return 0.0
        schedule = self.income_tax_schedule
        allowance_left = max(0.0, schedule.bands[0].upper - other_taxable_income)
        relieved = min(dividends, allowance_left + self.dividend_allowance)
        return self._tax_stacked_on(
            dividends - relieved, other_taxable_income + relieved,
            (
                (schedule.bands[1].upper, self.dividend_basic_rate),
                (schedule.bands[3].upper, self.dividend_higher_rate),
                (INF, self.dividend_additional_rate),
            ),
        )

    def gia_gross_for_net(self, other_taxable_income: float, basis_fraction: float,
                          target_net: float, exempt_used: float = 0.0) -> float:
        """Gross GIA proceeds needed to net `target_net` after CGT.

        Only the gain portion of what's sold (`1 - basis_fraction`) is a
        taxable gain; the rest is a tax-free return of capital.
        `basis_fraction` is the fraction of the slot's current value that is
        cost basis, assumed constant across a pro-rata sale (the fraction
        does not change as more of the *same* holding is sold).
        `exempt_used` is this year's annual exempt amount already spent by an
        earlier disposal, so the inverse of `capital_gains_tax` stays its
        inverse when a person sells twice in one year.
        """
        if target_net <= 0:
            return 0.0
        gain_fraction = max(0.0, 1.0 - basis_fraction)
        if gain_fraction <= 0:
            return target_net  # no gain at all: £1 sold nets £1

        exempt = max(0.0, self.cgt_annual_exempt_amount - exempt_used)
        breakpoints = (
            (exempt, 0.0),
            (exempt + self.cgt_basic_rate_room(other_taxable_income), self.cgt_basic_rate),
            (INF, self.cgt_higher_rate),
        )
        gross = 0.0
        remaining = target_net
        gain_position = 0.0
        for gain_upper, rate in breakpoints:
            gain_width = gain_upper - gain_position
            if gain_width <= 0:
                continue
            net_rate = 1.0 - gain_fraction * rate
            if gain_width == INF:
                return gross + (remaining / net_rate if net_rate > 0 else INF)
            gross_width = gain_width / gain_fraction
            available_net = gross_width * net_rate
            if remaining <= available_net:
                return gross + (remaining / net_rate if net_rate > 0 else INF)
            remaining -= available_net
            gross += gross_width
            gain_position = gain_upper
        return INF

    def pcls_available(self, pension_value: float, already_taken: float = 0.0) -> float:
        """Tax-free lump sum available from a pot of `pension_value`.

        The binding constraint is usually the allowance, not the 25%.
        """
        headroom = max(0.0, self.lump_sum_allowance - already_taken)
        return max(0.0, min(pension_value * self.pcls_fraction, headroom))

    def ufpls_gross_for_net(
        self, other_taxable_income: float, tax_free_used: float, target_net: float
    ) -> float:
        """Gross UFPLS withdrawal needed to net `target_net`.

        25% of it is tax-free, up to whatever Lump Sum Allowance headroom
        `tax_free_used` has left; the rest is taxed as ordinary income on
        top of `other_taxable_income`. Once the allowance is exhausted this
        degrades to `gross_pension_withdrawal_for_net` automatically -- see
        `RateSchedule.gross_for_net_partly_relieved`.
        """
        headroom = max(0.0, self.lump_sum_allowance - tax_free_used)
        return self.income_tax_schedule.gross_for_net_partly_relieved(
            other_taxable_income, self.pcls_fraction, headroom, target_net,
        )

    def ufpls_gross_for_taxable(self, tax_free_used: float, target_taxable: float) -> float:
        """Gross UFPLS withdrawal that produces exactly `target_taxable` of
        taxable income, given `tax_free_used` of the Lump Sum Allowance
        already used.

        For capping a withdrawal at a taxable-income ceiling -- a tax band
        to fill up to, in `TaxEfficientOrder` -- rather than a net-income
        target. Closed form, not a band-walk: taxable income is a simple
        piecewise-linear function of gross here (25% relief until the
        allowance runs out, then none), so no search is needed.
        """
        if target_taxable <= 0:
            return 0.0
        headroom = max(0.0, self.lump_sum_allowance - tax_free_used)
        taxable_fraction = 1.0 - self.pcls_fraction
        phase_1_taxable_capacity = (
            headroom / self.pcls_fraction * taxable_fraction if self.pcls_fraction > 0 else 0.0
        )
        if target_taxable <= phase_1_taxable_capacity:
            return target_taxable / taxable_fraction if taxable_fraction > 0 else INF
        phase_1_gross = (
            phase_1_taxable_capacity / taxable_fraction if taxable_fraction > 0 else 0.0
        )
        return phase_1_gross + (target_taxable - phase_1_taxable_capacity)

    def ufpls_split(self, gross: float, tax_free_used: float) -> tuple[float, float]:
        """Split a gross UFPLS withdrawal into (tax_free, taxable).

        Call this on whatever gross amount was *actually* drawn (after
        capping to what the pot holds) -- `ufpls_gross_for_net`'s result is
        only a target to aim for, not the guaranteed real split, since the
        pot might not hold enough to reach it.
        """
        headroom = max(0.0, self.lump_sum_allowance - tax_free_used)
        tax_free = max(0.0, min(gross * self.pcls_fraction, headroom))
        return tax_free, gross - tax_free

    def state_pension(self, full_record: bool = True) -> float:
        if not full_record:
            raise NotImplementedError(
                "partial NI records are not pro-rated yet — set the amount explicitly "
                "on Assumptions.state_pension_annual instead of guessing"
            )
        return self.full_state_pension_annual


UK = UKTaxSystem()
