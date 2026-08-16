"""Cost a UK discretionary settlement over its life, against holding the assets.

The question a household actually asks is "should we put this in trust?", and
the honest answer needs both arms costed. A trust is usually presented with its
IHT saving stated and its running cost left implicit: an entry charge on the
excess over the nil-rate band, up to 6% every ten years, trust-rate income tax
from the first pound, a halved CGT exemption and no uplift on death. This
prints all of it beside the do-nothing case, so the trade is visible rather
than asserted.

What it does **not** do is decide. Most trusts are bought for control,
protection from a divorce or a remarriage, or a vulnerable beneficiary — none
of which this can score. A settlement that costs money and is still right is a
normal outcome; use the number to say what the protection costs, not to say no.

Real terms, like the rest of the engine: figures are today's purchasing power.
The nil-rate band is frozen in nominal terms to April 2031, so its real value
falls — pass `--band-erosion` to model that, and read the un-eroded run as the
most favourable case the trust can have rather than the expected one.

Examples:

    # £600,000 settled, run 30 years, 4% real growth, 2% dividend yield
    .venv/bin/python tools/trust_charges.py --value 600000 --years 30 \
        --growth 0.04 --yield 0.02

    # The same, after a £200,000 gift five years ago used part of the band
    .venv/bin/python tools/trust_charges.py --value 600000 --years 30 \
        --growth 0.04 --yield 0.02 --cumulative 200000

    # Just the charge on one anniversary
    .venv/bin/python tools/trust_charges.py --anniversary 1200000
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from retireplan.tax.trusts import (  # noqa: E402
    MAX_TEN_YEAR_RATE,
    RelevantPropertyRules,
    TrustIncomeTax,
    project_settlement,
    trustee_annual_exempt_amount,
    trustee_cgt,
)


def money(x: float) -> str:
    return f"£{x:,.0f}"


def print_anniversary(rules: RelevantPropertyRules, value: float, cumulative: float) -> None:
    charge = rules.ten_year_charge(value, cumulative)
    print(f"Ten-year anniversary charge on {money(value)}")
    print(f"  available nil-rate band   {money(charge.available_nil_rate_band)}")
    print(f"  chargeable                {money(charge.chargeable)}")
    print(f"  notional tax at 20%       {money(charge.notional_tax)}")
    print(f"  effective rate            {charge.effective_rate:.3%}")
    print(f"  charge rate (x 3/10)      {charge.settlement_rate:.3%}"
          f"  (maximum {MAX_TEN_YEAR_RATE:.0%})")
    print(f"  tax                       {money(charge.tax)}")
    if rules.needs_iht100(value, cumulative):
        print("  reporting                 IHT100 due within 6 months of the anniversary")
    else:
        print("  reporting                 excepted settlement — no IHT100")
    print()
    print("  Exits during the next ten years are rated on this charge rate:")
    for years in (1, 3, 5, 10):
        quarters = min(40, years * 4)
        exit_charge = rules.exit_after_anniversary(100_000, charge.settlement_rate, quarters)
        print(f"    after {years:>2} year(s): {exit_charge.rate:.3%}"
              f"  ({money(exit_charge.tax)} per £100,000 distributed)")


def print_lifecycle(args: argparse.Namespace) -> None:
    rules = RelevantPropertyRules(nil_rate_band=args.nil_rate_band)
    growth = args.growth - args.band_erosion
    projection = project_settlement(
        initial_value=args.value,
        years=args.years,
        real_growth_rate=growth,
        yield_rate=args.yield_rate,
        dividend_share=args.dividend_share,
        cumulative_total=args.cumulative,
        settlor_pays_entry_charge=not args.trustees_pay_entry_charge,
        settlements_by_settlor=args.settlements,
        settlor_survives_seven_years=not args.settlor_dies_within_seven_years,
        settlor_income_tax_rate=args.settlor_rate,
        estate_iht_rate=args.estate_iht_rate,
        nil_rate_band_at_death=args.nil_rate_band_at_death,
        rules=rules,
    )

    label = "{:<30}"
    print(f"Settlement of {money(args.value)}, run {args.years} years at "
          f"{growth:.2%} real growth and a {args.yield_rate:.2%} yield")
    if args.band_erosion:
        print(f"  (growth stated net of {args.band_erosion:.2%} nil-rate band erosion)")
    print(f"  costing the settlor {money(projection.settlor_outlay)} on day one, "
          "which is what the do-nothing arm keeps")
    print()
    print("Charges on the settlement")
    print("  " + label.format("entry charge") + money(projection.entry_charge))
    for i, charge in enumerate(projection.ten_year_charges, start=1):
        print("  " + label.format(f"anniversary at {i * 10} years") + money(charge))
    print("  " + label.format("exit charge") + money(projection.exit_charge))
    if projection.exit_charge == 0 and projection.ten_year_charges:
        print("  " + label.format("") + "nil: the fund leaves in the same quarter as an "
              "anniversary")
    print("  " + label.format("trustees' income tax") + money(projection.trustee_income_tax))
    print("  " + label.format("total") + money(projection.total_trust_tax))
    print()
    print("What reaches the beneficiaries")
    print("  " + label.format("in trust") + money(projection.net_to_beneficiaries))
    print("  " + label.format(f"held personally, IHT at {args.estate_iht_rate:.0%}")
          + money(projection.personal_net_to_beneficiaries))
    verdict = "trust ahead by" if projection.advantage >= 0 else "trust behind by"
    print("  " + label.format(verdict) + money(abs(projection.advantage)))
    print()
    print("Also true, and not in the numbers above")
    exemption = trustee_annual_exempt_amount(args.settlements)
    print("  " + label.format("CGT exemption")
          + f"{money(exemption)} against an individual's £3,000")
    print("  " + label.format("CGT on a £50,000 gain")
          + f"{money(trustee_cgt(50_000, args.settlements))} at a flat 24%, "
            "with no basic-rate band")
    print("  " + label.format("no CGT uplift on death")
          + "a long-held gain survives into the beneficiaries' hands")
    print("  " + label.format("income tax de minimis")
          + f"{money(TrustIncomeTax().de_minimis_for(args.settlements))}, then 45% "
            "(39.35% on dividends) from the next pound")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--anniversary", type=float,
                        help="just price one ten-year anniversary at this fund value")
    parser.add_argument("--value", type=float, default=600_000.0,
                        help="value settled (default 600000)")
    parser.add_argument("--years", type=int, default=30,
                        help="horizon in years (default 30)")
    parser.add_argument("--growth", type=float, default=0.04,
                        help="real capital growth, decimal fraction (default 0.04)")
    parser.add_argument("--band-erosion", type=float, default=0.0,
                        help="real annual decline in the frozen nil-rate band, "
                             "subtracted from growth (try 0.025)")
    parser.add_argument("--yield", dest="yield_rate", type=float, default=0.02,
                        help="income yield, decimal fraction (default 0.02)")
    parser.add_argument("--dividend-share", type=float, default=1.0,
                        help="share of that yield taxed as dividends (default 1.0)")
    parser.add_argument("--cumulative", type=float, default=0.0,
                        help="settlor's chargeable transfers in the 7 years before "
                             "the settlement, plus related settlements")
    parser.add_argument("--settlements", type=int, default=1,
                        help="settlements this settlor has made — splits the CGT "
                             "exemption and the income de minimis")
    parser.add_argument("--settlor-rate", type=float, default=0.40,
                        help="settlor's own income tax rate, for the do-nothing arm")
    parser.add_argument("--nil-rate-band", type=float, default=325_000.0)
    parser.add_argument("--estate-iht-rate", type=float, default=0.40,
                        help="IHT rate on the do-nothing arm (0.36 where 10%% of "
                             "the estate goes to charity)")
    parser.add_argument("--nil-rate-band-at-death", type=float, default=0.0,
                        help="band left for the estate in the do-nothing arm "
                             "(default 0: assume it is spent elsewhere)")
    parser.add_argument("--trustees-pay-entry-charge", action="store_true",
                        help="20%% rather than the 25%% grossed-up charge")
    parser.add_argument("--settlor-dies-within-seven-years", action="store_true")
    args = parser.parse_args(argv)

    if args.anniversary is not None:
        print_anniversary(
            RelevantPropertyRules(nil_rate_band=args.nil_rate_band),
            args.anniversary,
            args.cumulative,
        )
    else:
        print_lifecycle(args)

    print()
    print("A modelling tool, not legal or tax advice. Every structure here needs a "
          "STEP-qualified solicitor before anyone acts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
