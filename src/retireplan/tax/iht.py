"""UK Inheritance Tax, including pensions from April 2027.

VERIFY BEFORE USE. Figures are 2026/27 and the bands are frozen to April 2031
under current policy — but check gov.uk rather than trusting this comment.

A projection quoting a gross estate overstates what reaches the children by
around 40%, so for a plan whose goal is leaving money to them this module is
the answer rather than a refinement.

**April 2027.** Unused pension funds enter the estate for IHT on deaths from
6 April 2027 (Finance Act 2026). That inverts the old logic — spend ISAs first,
leave the pension as the IHT-efficient wrapper — and makes a large unspent
pension the most heavily taxed asset a household can die holding.

**Stacking on death after 75.** Beneficiaries then pay income tax at their own
marginal rate on what they draw from an inherited pension. It is not the naive
40%+40%: the portion of the fund equal to the IHT paid on it is exempt from
income tax, so a fund F leaves F(1-i)(1-b) — 64% effective for a higher-rate
child, 52% for a basic-rate one, against 40% on an ISA, which bears IHT alone.
That gap is the argument for moving money out of a pension during life; see
`effective_pension_death_rate`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

NIL_RATE_BAND = 325_000.0
RESIDENCE_NIL_RATE_BAND = 175_000.0
TAPER_THRESHOLD = 2_000_000.0
IHT_RATE = 0.40
PENSIONS_IN_ESTATE_FROM = date(2027, 4, 6)
ANNUAL_GIFT_EXEMPTION = 3_000.0

VERIFIED_ON = date(2026, 8, 6)
"""When these figures were last checked against gov.uk — see `tax/uk.py`, and
`tax/provenance.py` for the sources and when each is next due."""

GIFT_TAPER = ((3, 1.0), (4, 0.8), (5, 0.6), (6, 0.4), (7, 0.2))
"""Multiplier on the *tax* on a gift, by full years the donor survived it. It
reduces the tax rather than the gift, and only bites where the gift exceeded the
nil-rate band — which is why "I survived four years so it's 24%" is usually
wrong: a gift inside the band has no tax to taper."""


def gift_taper_multiplier(years_survived: float) -> float:
    """Multiplier on the 40% rate for a gift the donor survived this long."""
    for threshold, multiplier in GIFT_TAPER:
        if years_survived < threshold:
            return multiplier
    return 0.0


@dataclass
class BequestBreakdown:
    """What actually reaches the beneficiaries, and what does not."""

    gross_estate: float
    pension_included: float
    allowances: float
    iht_due: float
    beneficiary_income_tax: float
    net_to_beneficiaries: float
    gifts_made: float = 0.0
    """Value of lifetime gifts *at the point of comparison* — see
    `simulation.gift_growth_rate`.

    Comparing gifts against a terminal estate is not apples to apples. A pound
    given away in 2032 and a pound inherited in 2070 are only equivalent if
    the recipient does nothing with it for forty years. If they invest it, the
    early pound is worth far more; if they spend it on a house, it bought a
    house. Whoever reads this number needs to know which assumption produced
    it, so the caller states it explicitly rather than the model guessing."""

    gift_iht: float = 0.0
    """Tax on gifts made within seven years of death, after taper relief."""

    @property
    def total_to_family(self) -> float:
        """The number that actually answers "how much did the children get?"."""
        return self.net_to_beneficiaries + self.gifts_made - self.gift_iht

    @property
    def total_tax(self) -> float:
        return self.iht_due + self.beneficiary_income_tax

    @property
    def effective_tax_rate(self) -> float:
        return self.total_tax / self.gross_estate if self.gross_estate > 0 else 0.0


@dataclass(frozen=True)
class IHTRules:
    nil_rate_band: float = NIL_RATE_BAND
    residence_nil_rate_band: float = RESIDENCE_NIL_RATE_BAND
    taper_threshold: float = TAPER_THRESHOLD
    rate: float = IHT_RATE
    pensions_in_estate_from: date = PENSIONS_IN_ESTATE_FROM
    verified_on: date = VERIFIED_ON

    def residence_band(self, estate: float, bands: int = 1, qualifies: bool = True) -> float:
        """Residence nil-rate band after the taper.

        Withdrawn £1 for every £2 the estate exceeds £2m, so a couple's
        combined £350,000 disappears entirely by £2.7m. Any household wealthy
        enough to be worrying about a large pension has almost certainly lost
        it — which is exactly the case where people still assume they have it.
        """
        if not qualifies:
            return 0.0
        available = self.residence_nil_rate_band * bands
        excess = max(0.0, estate - self.taper_threshold)
        return max(0.0, available - excess / 2)

    def allowances(self, estate: float, bands: int = 1, home_to_descendants: bool = True) -> float:
        """Total nil-rate allowance. `bands` is 2 for a couple's second death,
        where the first death's unused bands transferred to the survivor."""
        return self.nil_rate_band * bands + self.residence_band(estate, bands, home_to_descendants)

    def pensions_count(self, on: date) -> bool:
        return on >= self.pensions_in_estate_from

    def gift_charge(
        self,
        gifts: "Sequence[tuple[date, float]]",
        death: date,
        nil_rate_band: float,
    ) -> tuple[float, float]:
        """Tax on gifts within seven years of death, and the band they consume.

        Chronological order matters: the nil-rate band is set against the
        earliest gifts first, so a later gift is the one exposed to tax. Taper
        relief then reduces that tax by how long the donor survived — but only
        where there is tax to reduce, which is why taper is far less useful
        than its reputation suggests for gifts inside the band.

        Returns `(tax, band_consumed)`; whatever band is left applies to the
        estate itself.
        """
        recent = sorted(
            ((made, amount) for made, amount in gifts
             if (death - made).days / 365.25 < 7),
            key=lambda g: g[0],
        )
        remaining_band = nil_rate_band
        tax = 0.0
        for made, amount in recent:
            covered = min(amount, remaining_band)
            remaining_band -= covered
            chargeable = amount - covered
            if chargeable > 0:
                survived = (death - made).days / 365.25
                tax += chargeable * self.rate * gift_taper_multiplier(survived)
        return tax, nil_rate_band - remaining_band

    def bequest(
        self,
        *,
        non_pension_assets: float,
        pension_assets: float,
        on: date,
        bands: int = 2,
        home_to_descendants: bool = True,
        beneficiary_marginal_rate: float = 0.40,
        death_after_75: bool = True,
        gifts: "Sequence[tuple[date, float]] | None" = None,
    ) -> BequestBreakdown:
        """Work out what beneficiaries actually receive.

        `beneficiary_marginal_rate` is the *children's* expected rate on
        inherited pension income, not the deceased's. Defaults to 40% because
        an inherited pension is drawn on top of a working-age salary and
        pushes many beneficiaries into higher rate — assuming basic rate here
        would flatter every pension-heavy plan.
        """
        pension_in_estate = pension_assets if self.pensions_count(on) else 0.0
        gross_estate = non_pension_assets + pension_in_estate
        allowances = self.allowances(gross_estate, bands, home_to_descendants)

        # Gifts inside seven years claim the nil-rate band before the estate does.
        gift_tax, band_used_by_gifts = (
            self.gift_charge(gifts, on, self.nil_rate_band * bands) if gifts else (0.0, 0.0)
        )
        allowances = max(0.0, allowances - band_used_by_gifts)
        iht = max(0.0, gross_estate - allowances) * self.rate

        # Pensions bear IHT pro-rata with the rest of the estate.
        pension_share = pension_in_estate / gross_estate if gross_estate > 0 else 0.0
        iht_on_pension = iht * pension_share
        pension_after_iht = pension_assets - iht_on_pension

        # Income tax applies only where death is after 75, and not to the
        # portion already taken as IHT.
        income_tax = pension_after_iht * beneficiary_marginal_rate if death_after_75 else 0.0

        return BequestBreakdown(
            gross_estate=non_pension_assets + pension_assets,
            pension_included=pension_in_estate,
            allowances=allowances,
            iht_due=iht,
            beneficiary_income_tax=income_tax,
            net_to_beneficiaries=non_pension_assets + pension_assets - iht - income_tax,
            gifts_made=sum(a for _, a in gifts) if gifts else 0.0,
            gift_iht=gift_tax,
        )


def effective_pension_death_rate(
    beneficiary_marginal_rate: float,
    iht_rate: float = IHT_RATE,
    death_after_75: bool = True,
) -> float:
    """Total tax on a marginal pound left unspent in a pension, above the bands.

    The decision rule this supports: **move money from pension to ISA during
    life whenever your marginal rate now is below your beneficiary's expected
    rate later.** Both wrappers suffer the same IHT once pensions are in the
    estate, so the only difference is the beneficiary's income tax on the
    pension — which you can pre-pay at your own, usually lower, rate.

    Withdraw £1 at your rate `m`, the ISA receives £(1-m) and the children
    keep £(1-m)(1-i). Leave it, and they keep £(1-i)(1-b). Move it when m < b.
    """
    if not death_after_75:
        return iht_rate
    return 1 - (1 - iht_rate) * (1 - beneficiary_marginal_rate)


UK_IHT = IHTRules()
