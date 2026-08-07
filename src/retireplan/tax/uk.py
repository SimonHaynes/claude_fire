"""UK income tax, National Insurance, and pension access rules.

VERIFY BEFORE USE. The income tax, NI, CGT and dividend thresholds below were
first entered for 2025/26 and are frozen under current policy through
2027/28, so they are still the correct 2026/27 figures (`tax_year` reflects
that) — but a freeze is a policy choice, not a law of nature: do not take it
on trust from this comment, re-check gov.uk each tax year, and always before
showing output to anyone. `FULL_STATE_PENSION_ANNUAL` is *not* frozen — it
rises each April under the triple lock — and has not been re-verified past
its original 2025/26 value; treat any report figure derived from it as a
lower bound, not a current one, until it is checked.

Scope: income tax, Class 1 employee NI, State Pension, and the Normal Minimum
Pension Age. Dividend tax, Capital Gains Tax and Inheritance Tax are not
modelled — General Investment Accounts and estate planning will be wrong until
they are.
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

# The effective marginal rates a UK taxpayer actually faces on total income.
#
# The 60% band between £100,000 and £125,140 is not a legislated rate: it is
# the personal allowance being withdrawn at £1 for every £2 earned, so each
# extra £1 is taxed at 40p and drags a further 50p of previously-untaxed
# allowance into the 40% band (40p + 20p = 60p). Expressing it directly is
# both simpler and more accurate than reconstructing it from a tapered
# allowance — an earlier version of this engine did the latter and got the
# basic-rate band width wrong for anyone inside the taper.
UK_INCOME_TAX_2025_26 = RateSchedule((
    Band(PERSONAL_ALLOWANCE, 0.00),
    Band(BASIC_RATE_LIMIT, 0.20),
    Band(TAPER_START, 0.40),
    Band(ADDITIONAL_RATE_START, 0.60),
    Band(INF, 0.45),
))

# Class 1 employee NI. Self-employed Class 2/4 are not modelled.
UK_NATIONAL_INSURANCE_2025_26 = RateSchedule((
    Band(PERSONAL_ALLOWANCE, 0.00),   # primary threshold, currently aligned with the PA
    Band(BASIC_RATE_LIMIT, 0.08),     # upper earnings limit
    Band(INF, 0.02),
))

FULL_STATE_PENSION_ANNUAL = 11_973.0

# Normal Minimum Pension Age. The rise from 55 to 57 is already legislated for
# 6 April 2028, so this engine uses 57 even for earlier modelled dates: any
# plan being written today will be lived under the new rule, and assuming 55
# would quietly manufacture a bridge that will not exist.
PENSION_ACCESS_AGE = 57

# Pension Commencement Lump Sum: 25% of the pot may be taken tax-free, but
# capped by the Lump Sum Allowance, which is 25% of the old Lifetime Allowance
# and did not rise with it. Anyone with a pot above ~£1.073m is capped, so the
# "25% tax-free" rule of thumb quietly stops being true exactly for the people
# most likely to rely on it.
PCLS_FRACTION = 0.25
LUMP_SUM_ALLOWANCE = 268_275.0

# Capital Gains Tax on a General Investment Account. Since the 30 Oct 2024
# Budget, shares carry the same two rates as residential property -- the
# separate, lower "shares" rate no longer exists. There is no third
# (additional-rate) CGT band: only whether the taxpayer's *other* income
# already fills the basic-rate band decides which of the two rates applies.
CGT_ANNUAL_EXEMPT_AMOUNT = 3_000.0
CGT_BASIC_RATE = 0.18
CGT_HIGHER_RATE = 0.24

# Dividend tax, for the assumed distribution yield on a GIA. Three bands,
# mirroring income tax's, on top of a flat allowance that -- like the CGT
# exempt amount -- is not stacked with the income personal allowance.
DIVIDEND_ALLOWANCE = 500.0
DIVIDEND_BASIC_RATE = 0.0875
DIVIDEND_HIGHER_RATE = 0.3375
DIVIDEND_ADDITIONAL_RATE = 0.3935

# Assumed annual distribution yield on a GIA invested in a global tracker,
# taxed as dividend income each year (and reinvested, which raises cost basis
# by the same amount) even though nothing left the account. A total-return
# index's quoted return already includes this; splitting it out is what makes
# the dividend tax visible without changing the assumed total return. This is
# a modelling assumption, not a client-stated fact -- roughly the long-run
# average for a global equity index, but a real fund's actual distribution
# varies by year and by which index is held.
GIA_DIVIDEND_YIELD = 0.02

#: When these figures were last checked against gov.uk. This is a date, not a
#: comment, because "verify the rates" written in prose is a rule everyone
#: agrees with and nobody executes -- `simulation.run_monte_carlo` warns when
#: this goes stale, so skipping the check has to be a decision rather than an
#: oversight. Move it only when you have actually re-checked, and say so.
VERIFIED_ON = date(2026, 8, 6)


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

    def _stacked_tax(self, amount: float, other_taxable_income: float,
                      allowance: float, bands: tuple[tuple[float, float], ...]) -> float:
        """Tax `amount` (a dividend or a gain) stacked on top of income tax's
        bands, but with its own flat allowance rather than the income
        personal allowance. `bands` is `((upper, rate), ...)`, `upper` in
        INF-terminated ascending order, positions measured against total
        income (existing + this amount) exactly like `RateSchedule.tax`."""
        taxable = max(0.0, amount - allowance)
        if taxable <= 0:
            return 0.0
        total = 0.0
        lower = other_taxable_income
        remaining = taxable
        for upper, rate in bands:
            if remaining <= 0:
                break
            width = upper - lower
            if width <= 0:
                continue
            taken = min(remaining, width)
            total += taken * rate
            remaining -= taken
            lower += taken
        return total

    def capital_gains_tax(self, gain: float, other_taxable_income: float = 0.0) -> float:
        """CGT on `gain`, given `other_taxable_income` already occupies the
        income tax bands (only the *rate* on the gain depends on that; the
        annual exempt amount is a flat allowance on the gain itself)."""
        return self._stacked_tax(
            gain, other_taxable_income, self.cgt_annual_exempt_amount,
            ((self.income_tax_schedule.bands[1].upper, self.cgt_basic_rate), (INF, self.cgt_higher_rate)),
        )

    def dividend_tax(self, dividends: float, other_taxable_income: float = 0.0) -> float:
        """Dividend tax on `dividends`, stacked the same way as `capital_gains_tax`."""
        basic_upper = self.income_tax_schedule.bands[1].upper
        additional_upper = self.income_tax_schedule.bands[3].upper
        return self._stacked_tax(
            dividends, other_taxable_income, self.dividend_allowance,
            (
                (basic_upper, self.dividend_basic_rate),
                (additional_upper, self.dividend_higher_rate),
                (INF, self.dividend_additional_rate),
            ),
        )

    def gia_gross_for_net(self, other_taxable_income: float, basis_fraction: float, target_net: float) -> float:
        """Gross GIA proceeds needed to net `target_net` after CGT.

        Only the gain portion of what's sold (`1 - basis_fraction`) is a
        taxable gain; the rest is a tax-free return of capital.
        `basis_fraction` is the fraction of the slot's current value that is
        cost basis, assumed constant across a pro-rata sale (the fraction
        does not change as more of the *same* holding is sold).
        """
        if target_net <= 0:
            return 0.0
        gain_fraction = max(0.0, 1.0 - basis_fraction)
        if gain_fraction <= 0:
            return target_net  # no gain at all: £1 sold nets £1

        basic_upper = self.income_tax_schedule.bands[1].upper
        exempt = self.cgt_annual_exempt_amount
        breakpoints = (
            (exempt, 0.0),
            (exempt + max(0.0, basic_upper - other_taxable_income), self.cgt_basic_rate),
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
