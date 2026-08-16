"""UK trust taxation: the relevant property regime, trust income tax, trustee CGT.

VERIFY BEFORE USE. Figures are 2026/27 England & Wales. The nil-rate band is
frozen to April 2031, but nothing else here is: the trust rate on property and
savings income rises to 47% in April 2027, and the APR/BPR allowance was
re-set from £1m to £2.5m before it ever took effect.

A settlement is a **separate taxpayer from the person who created it**, and
that is the whole reason this module is not part of `tax/iht.py`. It has its
own nil-rate band, its own decennial charge, a CGT exemption at half an
individual's and an income tax rate at the top of the scale from the first
pound. A projection that treats trust assets as simply "outside the estate"
overstates what a trust saves, often by more than the 40% it was set up to
avoid.

The regime charges roughly a generation's worth of IHT in instalments: 6% every
ten years is about 40% over the ~200 years HMRC's 3/10 factor is derived from.
So the question a trust answers is not "is this cheaper than 40%" — over a long
enough horizon it is not — but "what does control, protection or a deferral buy
that is worth the running cost".

Rates here are *charge rates on the whole fund*, never marginal rates: a 6%
ten-year charge is 6% of everything, not 6% of the excess over the nil-rate
band. The nil-rate band enters through the effective-rate calculation instead,
which is why a fund at twice the band pays about 3%, not 6% of half of it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from .iht import NIL_RATE_BAND

VERIFIED_ON = date(2026, 8, 16)
"""When these figures were last checked against gov.uk. The sources, and the
date each is due to be checked again, are in `tax/provenance.py`; this is the
oldest of them, and `tests/test_provenance.py` keeps the two in step."""

LIFETIME_RATE = 0.20
"""IHT on a chargeable lifetime transfer: half the death rate, because the
settlor may yet survive seven years. If the *settlor* pays it rather than the
trustees, the payment is itself a transfer of value and the charge grosses up
to 25% of the net gift."""

SETTLOR_PAYS_RATE = 0.25

DECENNIAL_FRACTION = 0.30
"""The 3/10 in every relevant property charge. It converts a lifetime rate into
a decennial one and is the reason the maximum charge is 6%, not 20%."""

MAX_TEN_YEAR_RATE = LIFETIME_RATE * DECENNIAL_FRACTION
QUARTERS_PER_CYCLE = 40

EXCEPTED_SETTLEMENT_FRACTION = 0.80
"""A ten-year anniversary needs no IHT100 if the notional transfer is within
80% of the nil-rate band. Below that line the charge is nil anyway; the value
of the threshold is that it also removes the filing."""

APR_BPR_ALLOWANCE = 2_500_000.0
"""100% agricultural and business relief is capped from 6 April 2026, with 50%
relief above. A settlement has its own allowance refreshing every ten years —
but every settlement one settlor made **on or after 30 October 2024** shares a
single allowance, allocated to the earliest first, so creating more trusts no
longer multiplies it."""

APR_BPR_RATE_ABOVE_ALLOWANCE = 0.50
APR_BPR_ALLOWANCE_SHARED_FROM = date(2024, 10, 30)

TRUST_RATE = 0.45
DIVIDEND_TRUST_RATE = 0.3935
TRUST_PROPERTY_AND_SAVINGS_RATE_2027_28 = 0.47
"""Property and savings income leaves the 45% trust rate in April 2027; the
dividend trust rate stays at 39.35%."""

IIP_RATE = 0.20
IIP_DIVIDEND_RATE = 0.1075

DE_MINIMIS = 500.0
DE_MINIMIS_FLOOR = 100.0
"""Income within the de minimis is untaxed — which is not the same as the
£1,000 standard rate band it replaced in April 2024, because no tax is paid and
so nothing enters the tax pool. Divided between a settlor's settlements, floored
at £100 once there are five or more."""

TRUSTEE_CGT_RATE = 0.24
TRUSTEE_ANNUAL_EXEMPT_AMOUNT = 1_500.0
VULNERABLE_BENEFICIARY_ANNUAL_EXEMPT_AMOUNT = 3_000.0
TRUSTEE_AEA_FLOOR = 300.0

BENEFICIARY_TAX_CREDIT_RATE = 0.45
"""A discretionary distribution reaches the beneficiary net of 45% whatever the
trustees actually paid. On dividend income they paid 39.35%, so every pound
distributed drains the tax pool faster than it filled it — see
`tax_pool_shortfall`."""


def charge_rate(fraction: float) -> float:
    """A charge rate rounded as HMRC states it: three decimal places as a
    percentage, i.e. five as a fraction.

    Worth doing exactly rather than approximately, because the rounding is
    applied to the effective rate *and* again after the 3/10, and a plan that
    quotes a figure HMRC will not recognise invites the wrong argument.
    """
    return math.floor(fraction * 1e5 + 0.5) / 1e5


def complete_quarters(start: date, end: date) -> int:
    """Complete quarters between two dates, capped at a full ten-year cycle.

    Exit charges are reduced by `quarters/40`, so property leaving within three
    months of the settlement or of an anniversary carries no charge at all —
    the single most reliable piece of timing in the regime.
    """
    if end <= start:
        return 0
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return min(QUARTERS_PER_CYCLE, max(0, months // 3))


@dataclass(frozen=True)
class Charge:
    """A relevant property charge and the arithmetic that produced it.

    `settlement_rate` is the rate *before* any time apportionment — the figure
    a ten-year anniversary charges, and the one carried forward to rate the
    exits of the following decade.
    """

    notional_transfer: float
    available_nil_rate_band: float
    chargeable: float
    notional_tax: float
    effective_rate: float
    settlement_rate: float
    quarters: int
    rate: float
    chargeable_value: float
    tax: float


@dataclass(frozen=True)
class RelevantPropertyRules:
    """The IHT charges on a settlement that is not one of the privileged types.

    Privileged settlements — a bare trust, a disabled person's trust, an IPDI,
    a bereaved minor's trust, a pre-22-March-2006 interest in possession — are
    outside this regime entirely. They pay nothing here and instead sit in a
    beneficiary's own estate at 40%, which for a fund growing faster than the
    frozen nil-rate band is usually the more expensive answer.
    """

    nil_rate_band: float = NIL_RATE_BAND
    lifetime_rate: float = LIFETIME_RATE
    decennial_fraction: float = DECENNIAL_FRACTION
    verified_on: date = VERIFIED_ON

    def available_nil_rate_band(self, cumulative_total: float) -> float:
        """The settlement's band after the settlor's own history.

        `cumulative_total` is the settlor's chargeable transfers in the seven
        years **before** the settlement began, plus related settlements and
        same-day additions. It is fixed for the settlement's life and never
        refreshes, which is why the order a settlor creates trusts in matters:
        the first one gets the band.
        """
        return max(0.0, self.nil_rate_band - cumulative_total)

    def entry_charge(
        self,
        value: float,
        cumulative_total: float = 0.0,
        settlor_pays: bool = True,
    ) -> float:
        """IHT on creating the settlement, above the available band.

        Defaults to the settlor paying, which is what happens unless the trust
        deed says otherwise — and costs 25% of the excess rather than 20%,
        because paying someone else's tax is itself a gift.
        """
        chargeable = max(0.0, value - self.available_nil_rate_band(cumulative_total))
        rate = SETTLOR_PAYS_RATE if settlor_pays else self.lifetime_rate
        return chargeable * rate

    def _rate(self, notional_transfer: float, cumulative_total: float) -> tuple[float, float, float, float, float]:
        band = self.available_nil_rate_band(cumulative_total)
        chargeable = max(0.0, notional_transfer - band)
        notional_tax = chargeable * self.lifetime_rate
        effective = charge_rate(notional_tax / notional_transfer) if notional_transfer > 0 else 0.0
        return band, chargeable, notional_tax, effective, charge_rate(effective * self.decennial_fraction)

    def ten_year_charge(
        self,
        relevant_property: float,
        cumulative_total: float = 0.0,
    ) -> Charge:
        """The charge on a ten-year anniversary.

        Valued the day before the anniversary, on the whole fund, at up to 6%.
        The band bites once and the excess is charged at a flat 6%, so a fund at
        the band pays nothing, one at twice the band pays 3%, and the marginal
        pound above the band always costs 6p.
        """
        band, chargeable, notional_tax, effective, settlement = self._rate(
            relevant_property, cumulative_total
        )
        return Charge(
            notional_transfer=relevant_property,
            available_nil_rate_band=band,
            chargeable=chargeable,
            notional_tax=notional_tax,
            effective_rate=effective,
            settlement_rate=settlement,
            quarters=QUARTERS_PER_CYCLE,
            rate=settlement,
            chargeable_value=relevant_property,
            tax=relevant_property * settlement,
        )

    def exit_before_first_anniversary(
        self,
        distribution: float,
        notional_transfer: float,
        cumulative_total: float,
        quarters: int,
    ) -> Charge:
        """An exit in the first decade, rated on the settlement's *opening* value.

        `notional_transfer` is what the settlement held when it commenced, not
        what it holds now — so a fund that has grown pays on the smaller,
        historic figure, and a distribution in year nine of a boom is charged as
        if the boom had not happened.

        Pass the full notional transfer where related settlements or same-day
        additions apply (IHTM42114 components A to F); this function does not
        attribute them, because getting that wrong is worse than being asked.
        """
        band, chargeable, notional_tax, effective, settlement = self._rate(
            notional_transfer, cumulative_total
        )
        rate = charge_rate(settlement * quarters / QUARTERS_PER_CYCLE)
        return Charge(
            notional_transfer=notional_transfer,
            available_nil_rate_band=band,
            chargeable=chargeable,
            notional_tax=notional_tax,
            effective_rate=effective,
            settlement_rate=settlement,
            quarters=quarters,
            rate=rate,
            chargeable_value=distribution,
            tax=distribution * rate,
        )

    def exit_after_anniversary(
        self,
        distribution: float,
        settlement_rate_at_last_anniversary: float,
        quarters: int,
    ) -> Charge:
        """An exit between anniversaries, rated on the last anniversary's rate.

        No revaluation and no fresh effective-rate sum: the rate is simply
        `quarters/40` of what the fund was charged at its last anniversary. The
        planning consequence is that an exit is cheapest immediately after an
        anniversary, when both the rate is freshly known and the fraction is
        near zero.
        """
        rate = charge_rate(settlement_rate_at_last_anniversary * quarters / QUARTERS_PER_CYCLE)
        return Charge(
            notional_transfer=0.0,
            available_nil_rate_band=0.0,
            chargeable=0.0,
            notional_tax=0.0,
            effective_rate=0.0,
            settlement_rate=settlement_rate_at_last_anniversary,
            quarters=quarters,
            rate=rate,
            chargeable_value=distribution,
            tax=distribution * rate,
        )

    def needs_iht100(self, notional_transfer: float, cumulative_total: float = 0.0) -> bool:
        """Whether an anniversary must be reported even though no tax is due."""
        return notional_transfer > EXCEPTED_SETTLEMENT_FRACTION * self.available_nil_rate_band(
            cumulative_total
        )


@dataclass(frozen=True)
class TrustIncomeTax:
    """Income tax on trustees, and what a distribution costs on top.

    Discretionary and accumulation trustees pay the top rate on the first
    pound: there is no personal allowance, no basic rate band and — since April
    2024 — no standard rate band either, only a £500 de minimis that is exempt
    rather than taxed. An interest in possession trust instead pays basic rate
    and the beneficiary settles the rest at their own rate, which is why an IIP
    is cheaper for income and a discretionary trust is bought for control.
    """

    trust_rate: float = TRUST_RATE
    dividend_trust_rate: float = DIVIDEND_TRUST_RATE
    iip_rate: float = IIP_RATE
    iip_dividend_rate: float = IIP_DIVIDEND_RATE
    de_minimis: float = DE_MINIMIS
    verified_on: date = VERIFIED_ON

    def de_minimis_for(self, settlements_by_settlor: int = 1) -> float:
        return max(DE_MINIMIS_FLOOR, self.de_minimis / max(1, settlements_by_settlor))

    def discretionary_tax(
        self,
        *,
        non_dividend: float = 0.0,
        dividends: float = 0.0,
        settlements_by_settlor: int = 1,
    ) -> float:
        """Trustees' liability on accumulated or discretionary income.

        The de minimis covers non-dividend income first, which is the ordering
        that leaves the smaller bill given the higher rate applies there.
        """
        exempt = self.de_minimis_for(settlements_by_settlor)
        taxed_non_dividend = max(0.0, non_dividend - exempt)
        taxed_dividends = max(0.0, dividends - max(0.0, exempt - non_dividend))
        return taxed_non_dividend * self.trust_rate + taxed_dividends * self.dividend_trust_rate

    def interest_in_possession_tax(
        self, *, non_dividend: float = 0.0, dividends: float = 0.0
    ) -> float:
        """Trustees' liability where a life tenant is entitled to the income.

        The beneficiary is then taxable on the gross income at their own rates
        with credit for this, so a basic-rate life tenant pays nothing more and
        a non-taxpayer reclaims it.
        """
        return non_dividend * self.iip_rate + dividends * self.iip_dividend_rate

    def gross_up_distribution(self, net_paid: float) -> float:
        """The gross a beneficiary is treated as receiving for a net payment."""
        return net_paid / (1 - BENEFICIARY_TAX_CREDIT_RATE)

    def tax_pool_shortfall(self, net_paid: float, tax_pool: float) -> float:
        """Extra tax the trustees owe because the pool cannot fund the credit.

        Every discretionary distribution carries a 45% credit whatever the
        trustees actually paid, and the pool is only what they did pay. Two
        things drain it faster than it fills: dividends taxed at 39.35% against
        a credit given at 45%, and the £500 de minimis, which pays no tax and
        therefore contributes nothing. A trust living on dividend income and
        distributing all of it runs a structural deficit.
        """
        credit = self.gross_up_distribution(net_paid) * BENEFICIARY_TAX_CREDIT_RATE
        return max(0.0, credit - tax_pool)

    def beneficiary_reclaim(self, net_paid: float, beneficiary_marginal_rate: float) -> float:
        """What the beneficiary gets back from HMRC on a discretionary payment.

        Negative would mean they owe more, which only an additional-rate
        beneficiary can, and then only zero — the credit is already 45%. This is
        the mechanism that makes a discretionary trust efficient for a
        non-taxpaying beneficiary and pointless for a top-rate one.
        """
        gross = self.gross_up_distribution(net_paid)
        return max(0.0, gross * (BENEFICIARY_TAX_CREDIT_RATE - beneficiary_marginal_rate))


def trustee_annual_exempt_amount(
    settlements_by_settlor: int = 1, vulnerable_beneficiary: bool = False
) -> float:
    """A settlement's CGT exemption: half an individual's, split further between
    the settlor's settlements and floored at a fifth."""
    full = (
        VULNERABLE_BENEFICIARY_ANNUAL_EXEMPT_AMOUNT
        if vulnerable_beneficiary
        else TRUSTEE_ANNUAL_EXEMPT_AMOUNT
    )
    floor = TRUSTEE_AEA_FLOOR * (2 if vulnerable_beneficiary else 1)
    return max(floor, full / max(1, settlements_by_settlor))


def trustee_cgt(
    gain: float, settlements_by_settlor: int = 1, vulnerable_beneficiary: bool = False
) -> float:
    """CGT on trustees: one flat rate, no basic-rate band to fall into.

    Trustees also get no uplift on a beneficiary's death — except where a
    qualifying interest in possession ends — so a settlement holding an asset
    for decades accrues a gain that an individual's estate would have wiped.
    Weigh that against the 40% it avoided before calling the trust the cheaper
    holding.
    """
    taxable = max(
        0.0, gain - trustee_annual_exempt_amount(settlements_by_settlor, vulnerable_beneficiary)
    )
    return taxable * TRUSTEE_CGT_RATE


def agricultural_or_business_relief(value: float, allowance_used: float = 0.0) -> float:
    """Relievable value after the 6 April 2026 cap: 100% to the allowance, 50%
    above. `allowance_used` is what earlier exits in this ten-year cycle, or
    settlements the same settlor made on or after 30 October 2024, already
    claimed."""
    headroom = max(0.0, APR_BPR_ALLOWANCE - allowance_used)
    full = min(value, headroom)
    return full + (value - full) * APR_BPR_RATE_ABOVE_ALLOWANCE


@dataclass(frozen=True)
class SettlementProjection:
    """What a settlement leaves the family, against the same assets held
    personally until death.

    Both arms start from the same `settlor_outlay` and run the same returns, so
    every difference between them is tax. That outlay is what the settlement
    costs the family on day one: the fund plus the entry charge where the
    settlor pays it, the fund alone where the trustees do — which is the only
    way to compare a 25% grossed-up charge with a 20% one honestly.
    """

    settlor_outlay: float
    final_value: float
    entry_charge: float
    ten_year_charges: tuple[float, ...]
    exit_charge: float
    trustee_income_tax: float
    net_to_beneficiaries: float
    personal_net_to_beneficiaries: float
    personal_income_tax: float

    @property
    def total_trust_tax(self) -> float:
        return (
            self.entry_charge
            + sum(self.ten_year_charges)
            + self.exit_charge
            + self.trustee_income_tax
        )

    @property
    def advantage(self) -> float:
        """Positive means the settlement beat holding the assets personally."""
        return self.net_to_beneficiaries - self.personal_net_to_beneficiaries


def project_settlement(
    *,
    initial_value: float,
    years: int,
    real_growth_rate: float,
    yield_rate: float = 0.0,
    dividend_share: float = 1.0,
    cumulative_total: float = 0.0,
    settlor_pays_entry_charge: bool = True,
    settlements_by_settlor: int = 1,
    settlor_survives_seven_years: bool = True,
    settlor_income_tax_rate: float = 0.40,
    settlor_dividend_tax_rate: float = 0.3575,
    estate_iht_rate: float = 0.40,
    nil_rate_band_at_death: float = 0.0,
    rules: RelevantPropertyRules | None = None,
    income_tax: TrustIncomeTax | None = None,
) -> SettlementProjection:
    """Run a discretionary settlement forward and compare it with doing nothing.

    Real terms throughout, matching the rest of the engine. The nil-rate band
    is frozen in *nominal* terms to 2031, so a real-terms projection that holds
    it constant is already flattering the trust; pass a `real_growth_rate` net
    of that erosion, or read the answer as a floor on the charges.

    Income is accumulated, not distributed, so `trustee_income_tax` is the full
    trust-rate bill with no beneficiary reclaim against it. A trust paying
    income out to non-taxpayers recovers most of that — model it separately,
    because whether the beneficiaries are non-taxpayers is a fact about the
    family rather than about the structure.

    `nil_rate_band_at_death` defaults to nothing: a household considering a
    trust has usually spent its bands elsewhere, and assuming otherwise makes
    the personal arm look better than it will be.
    """
    rules = rules or RelevantPropertyRules()
    income_tax = income_tax or TrustIncomeTax()

    band = rules.available_nil_rate_band(cumulative_total)
    entry = rules.entry_charge(initial_value, cumulative_total, settlor_pays_entry_charge)
    if not settlor_survives_seven_years:
        # Death inside seven years recharges the transfer at the death rate,
        # crediting the lifetime tax already paid.
        entry = max(entry, max(0.0, initial_value - band) * estate_iht_rate)

    value = initial_value if settlor_pays_entry_charge else initial_value - entry
    outlay = initial_value + entry if settlor_pays_entry_charge else initial_value
    opening_fund = value
    personal_value = outlay
    trustee_tax = 0.0
    personal_tax = 0.0
    ten_year_charges: list[float] = []
    last_settlement_rate = 0.0
    quarters_since_anniversary = 0

    for year in range(1, years + 1):
        income = value * yield_rate
        dividends = income * dividend_share
        year_tax = income_tax.discretionary_tax(
            non_dividend=income - dividends,
            dividends=dividends,
            settlements_by_settlor=settlements_by_settlor,
        )
        trustee_tax += year_tax
        value = value * (1 + real_growth_rate) - year_tax

        personal_income = personal_value * yield_rate
        personal_dividends = personal_income * dividend_share
        personal_year_tax = (
            (personal_income - personal_dividends) * settlor_income_tax_rate
            + personal_dividends * settlor_dividend_tax_rate
        )
        personal_tax += personal_year_tax
        personal_value = personal_value * (1 + real_growth_rate) - personal_year_tax

        quarters_since_anniversary += 4
        if year % 10 == 0:
            charge = rules.ten_year_charge(value, cumulative_total)
            ten_year_charges.append(charge.tax)
            value -= charge.tax
            last_settlement_rate = charge.settlement_rate
            quarters_since_anniversary = 0

    if ten_year_charges:
        exit_charge = rules.exit_after_anniversary(
            value, last_settlement_rate, quarters_since_anniversary
        ).tax
    else:
        exit_charge = rules.exit_before_first_anniversary(
            value, opening_fund, cumulative_total, min(QUARTERS_PER_CYCLE, years * 4)
        ).tax

    personal_net = personal_value - max(0.0, personal_value - nil_rate_band_at_death) * estate_iht_rate

    return SettlementProjection(
        settlor_outlay=outlay,
        final_value=value,
        entry_charge=entry,
        ten_year_charges=tuple(ten_year_charges),
        exit_charge=exit_charge,
        trustee_income_tax=trustee_tax,
        net_to_beneficiaries=value - exit_charge,
        personal_net_to_beneficiaries=personal_net,
        personal_income_tax=personal_tax,
    )


UK_RELEVANT_PROPERTY = RelevantPropertyRules()
UK_TRUST_INCOME_TAX = TrustIncomeTax()
