"""Where every tax and legislation figure came from, and when to look again.

A constant in this engine is a claim about the law on a date. Without the date
it is indistinguishable from a claim about the law today, and a plan built on a
silently stale figure is wrong in a way nobody can see — which is exactly how a
2026/27 report ends up quoting a 2024/25 allowance.

So each figure carries three things: the **source** that establishes it, the
date it was last **checked** against that source, and the date it should be
**checked again**. The third is the one usually left out, and it is the one
that makes the process cheap: a recheck date derived from the figure's own
timetable turns "verify everything before every report" into "verify the four
things whose timetable has passed".

**The recheck date is not a uniform interval.** It is the earliest date the
figure could move, which depends on what moves it:

| What sets the figure | Recheck by |
|---|---|
| A rate or allowance a Budget can change | the first working day after the next Budget |
| A figure uprated each April (state pension, care limits, Class 3 NI) | 6 April |
| A change already legislated for a future date | its commencement date |
| A frozen threshold | the Budget that could unfreeze it, not the freeze's end |
| Primary legislation with no announced change | the next tax year |

A freeze is not a reason to skip a check. It binds only what it names, and a
Budget can shorten it — the nil-rate band freeze has been extended twice.

`checked_on=None` means nobody has recorded a check. That is not the same as
"unchanged since it was written", and the tooling treats it as overdue rather
than as fine.

Run `tools/check_tax_freshness.py` to see what is due; the `verify-tax-figures`
skill is the procedure for clearing it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

BUDGET_FOLLOW_UP = date(2026, 12, 1)
"""Anything a Budget can move is rechecked once the autumn Budget has been
delivered and the rate tables are published, not on the day itself."""

NEXT_TAX_YEAR = date(2027, 4, 6)
"""Uprating and every commencement date the current statute book already names
land here: pensions entering the IHT estate, and the 47% trust rate on property
and savings income."""


@dataclass(frozen=True)
class Source:
    """One authority for one group of figures.

    `covers` is written so that someone rechecking knows what to compare
    without reading the module: name the figures, not the topic.
    """

    module: str
    covers: str
    url: str
    checked_on: date | None
    recheck_by: date
    moved_by: str
    """What would change this figure — the event to watch, not a date."""

    def is_due(self, as_of: date) -> bool:
        return self.checked_on is None or as_of >= self.recheck_by


SOURCES: tuple[Source, ...] = (
    Source(
        module="retireplan.tax.uk",
        covers="personal allowance, basic rate limit, the £100k taper, additional rate start",
        url="https://www.gov.uk/government/publications/rates-and-allowances-income-tax",
        checked_on=date(2026, 8, 6),
        recheck_by=BUDGET_FOLLOW_UP,
        moved_by="a Budget; the thresholds are frozen to 2027/28 but a freeze can be "
                 "extended or cut short, and has been",
    ),
    Source(
        module="retireplan.tax.uk",
        covers="National Insurance primary threshold, main and upper rates",
        url="https://www.gov.uk/national-insurance-rates-letters",
        checked_on=date(2026, 8, 6),
        recheck_by=BUDGET_FOLLOW_UP,
        moved_by="a Budget; rates moved twice in 2024 alone",
    ),
    Source(
        module="retireplan.tax.uk",
        covers="CGT annual exempt amount and the 18%/24% rates",
        url="https://www.gov.uk/capital-gains-tax/rates",
        checked_on=date(2026, 8, 6),
        recheck_by=BUDGET_FOLLOW_UP,
        moved_by="a Budget; the rates changed mid-year on 30 October 2024, so a "
                 "tax-year-boundary assumption is not safe here",
    ),
    Source(
        module="retireplan.tax.uk",
        covers="dividend allowance and the 10.75%/35.75%/39.35% rates",
        url="https://www.gov.uk/tax-on-dividends",
        checked_on=date(2026, 8, 6),
        recheck_by=BUDGET_FOLLOW_UP,
        moved_by="a Budget; the ordinary and upper rates rose 2pp in April 2026 while "
                 "the additional rate stood still",
    ),
    Source(
        module="retireplan.tax.uk",
        covers="full new State Pension, and Class 3 voluntary NI cost",
        url="https://www.gov.uk/new-state-pension/what-youll-get",
        checked_on=date(2026, 8, 6),
        recheck_by=NEXT_TAX_YEAR,
        moved_by="the triple lock, announced at the Budget and effective each April",
    ),
    Source(
        module="retireplan.tax.uk",
        covers="annual allowance, MPAA, Lump Sum Allowance, PCLS fraction, "
               "normal minimum pension age",
        url="https://www.gov.uk/tax-on-your-private-pension",
        checked_on=date(2026, 8, 6),
        recheck_by=BUDGET_FOLLOW_UP,
        moved_by="a Budget; NMPA separately rises to 57 on 6 April 2028 by existing statute",
    ),
    Source(
        module="retireplan.tax.iht",
        covers="nil-rate band, residence nil-rate band, £2m taper threshold, 40% rate, "
               "annual gift exemption, seven-year taper",
        url="https://www.gov.uk/inheritance-tax",
        checked_on=date(2026, 8, 6),
        recheck_by=BUDGET_FOLLOW_UP,
        moved_by="a Budget; the bands are frozen to April 2031 and that freeze has "
                 "already been extended twice",
    ),
    Source(
        module="retireplan.tax.iht",
        covers="unused pension funds entering the estate from 6 April 2027, and the "
               "exemptions that survive it",
        url="https://www.gov.uk/government/publications/inheritance-tax-unused-pension-funds-and-death-benefits/inheritance-tax-unused-pension-funds-and-death-benefits",
        checked_on=date(2026, 8, 6),
        recheck_by=NEXT_TAX_YEAR,
        moved_by="commencement on 6 April 2027 — recheck the reporting mechanics and "
                 "the death-in-service and spousal carve-outs once it is live",
    ),
    Source(
        module="retireplan.tax.trusts",
        covers="which trusts are relevant property, entry/ten-year/exit charges, "
               "which settlements are outside the regime",
        url="https://www.gov.uk/guidance/trusts-and-inheritance-tax",
        checked_on=date(2026, 8, 16),
        recheck_by=NEXT_TAX_YEAR,
        moved_by="IHTA 1984 amendments; exit charge calculation changed on 6 April 2026",
    ),
    Source(
        module="retireplan.tax.trusts",
        covers="the ten-year and proportionate charge arithmetic, and the worked "
               "examples the parity test reproduces",
        url="https://www.gov.uk/hmrc-internal-manuals/inheritance-tax-manual/ihtm42087",
        checked_on=date(2026, 8, 16),
        recheck_by=NEXT_TAX_YEAR,
        moved_by="an HMRC manual restatement — if the published example changes, "
                 "tools/validate_trust_charges.py is where it shows up",
    ),
    Source(
        module="retireplan.tax.trusts",
        covers="trust rate 45%, dividend trust rate 39.35%, IIP rates, "
               "the £500 de minimis and its £100 floor",
        url="https://www.gov.uk/trusts-taxes/trusts-and-income-tax",
        checked_on=date(2026, 8, 16),
        recheck_by=NEXT_TAX_YEAR,
        moved_by="the legislated rise of the trust property and savings rates to 47% "
                 "on 6 April 2027; the dividend trust rate stays at 39.35%",
    ),
    Source(
        module="retireplan.tax.trusts",
        covers="trustee CGT rate 24%, annual exempt amount £1,500 and its division "
               "between a settlor's settlements",
        url="https://www.gov.uk/guidance/trusts-and-capital-gains-tax",
        checked_on=date(2026, 8, 16),
        recheck_by=BUDGET_FOLLOW_UP,
        moved_by="a Budget; the trustee exemption tracks half the individual one",
    ),
    Source(
        module="retireplan.tax.trusts",
        covers="the £2.5m agricultural and business relief allowance, 50% above it, "
               "and the shared allowance for settlements made from 30 October 2024",
        url="https://www.gov.uk/government/publications/reforms-to-agricultural-property-relief-and-business-property-relief/agricultural-property-relief-and-business-property-relief-reforms",
        checked_on=date(2026, 8, 16),
        recheck_by=BUDGET_FOLLOW_UP,
        moved_by="a Budget; the allowance was re-set from £1m to £2.5m before it took "
                 "effect, so the figure has already moved once without the policy changing",
    ),
    Source(
        module="retireplan.tax.trusts",
        covers="the trust property and savings rates rising to 47% on 6 April 2027, "
               "and the dividend trust rate staying at 39.35%",
        url="https://www.gov.uk/government/publications/changes-to-tax-rates-for-property-savings-and-dividend-income/change-to-tax-rates-for-property-savings-and-dividend-income-technical-note",
        checked_on=date(2026, 8, 16),
        recheck_by=NEXT_TAX_YEAR,
        moved_by="commencement on 6 April 2027 — the constant is in the module now but "
                 "unused until then, so nothing warns if it is wrong",
    ),
    Source(
        module="retireplan.tax.trusts",
        covers="Trust Registration Service: who must register, the 90-day deadline, "
               "the Schedule 3A exclusions, the £5,000 penalty",
        url="https://www.gov.uk/guidance/register-a-trust-as-a-trustee",
        checked_on=date(2026, 8, 16),
        recheck_by=NEXT_TAX_YEAR,
        moved_by="money laundering regulations, which change outside the Budget cycle",
    ),
    Source(
        module="retireplan.care",
        covers="upper and lower capital limits, tariff income step, "
               "personal expenses allowance",
        url="https://www.gov.uk/government/publications/care-act-statutory-guidance/care-and-support-statutory-guidance",
        checked_on=None,
        recheck_by=NEXT_TAX_YEAR,
        moved_by="an April uprating, and — still unimplemented — the deferred Dilnot "
                 "cap; the module's own comment says 2025/26, which is now a year old",
    ),
)


def due(as_of: date) -> tuple[Source, ...]:
    """Sources whose recheck date has passed, or which have never been checked."""
    return tuple(s for s in SOURCES if s.is_due(as_of))


def upcoming(as_of: date, within_days: int = 90) -> tuple[Source, ...]:
    """Sources falling due soon — the ones worth clearing before a report goes
    out rather than halfway through writing it."""
    return tuple(
        s
        for s in SOURCES
        if not s.is_due(as_of) and (s.recheck_by - as_of).days <= within_days
    )


def for_module(module: str) -> tuple[Source, ...]:
    return tuple(s for s in SOURCES if s.module == module)


def last_checked(module: str) -> date | None:
    """The oldest recorded check across a module's sources — the date its
    `VERIFIED_ON` should carry, since a module is only as verified as its
    least-recently-checked figure."""
    dates = [s.checked_on for s in for_module(module)]
    if not dates or any(d is None for d in dates):
        return None
    return min(d for d in dates if d is not None)
