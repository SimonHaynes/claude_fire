"""Price a lifetime annuity, and show what it is really worth over time.

    .venv/bin/python tools/annuity_quote.py --premium 200000 --age 65
    .venv/bin/python tools/annuity_quote.py --premium 200000 --age 66 --joint 0.5 \
        --spouse-age 63 --guarantee 5
    .venv/bin/python tools/annuity_quote.py --age 65 --compare
    .venv/bin/python tools/annuity_quote.py --age 65 --history

`--compare` prices every option combination side by side, with the real income
each still buys after twenty years. That second column is the point: a level
annuity wins every headline comparison and loses most twenty-year ones, and no
client makes that trade properly without seeing both.

`--history` shows what the same annuity would have paid in every month since
2000. Most of what a client thinks of as "my annuity rate" is the gilt market
on the day they happened to buy, and the range is far wider than anyone
expects.

Rates are a planning estimate calibrated to published best-buy tables (see
`tools/validate_annuity_rates.py`), not a quote. A real quote is underwritten,
postcode-rated and varies by more between providers than this model's error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from retireplan.annuity import AnnuityOptions, GiltCurve, uk_annuity_market  # noqa: E402


def money(x: float) -> str:
    return f"£{x:,.0f}"


def describe(options: AnnuityOptions) -> str:
    parts = ["joint life" if options.joint_life_proportion else "single life"]
    if options.joint_life_proportion:
        parts[0] = f"joint life {options.joint_life_proportion:.0%}"
    if options.rpi_linked:
        parts.append("RPI-linked")
    elif options.escalation:
        parts.append(f"{options.escalation:.0%} escalation")
    else:
        parts.append("level")
    parts.append(f"{options.guarantee_years}yr guarantee" if options.guarantee_years
                 else "no guarantee")
    if options.health_uplift:
        parts.append(f"enhanced +{options.health_uplift:.0%}")
    return ", ".join(parts)


def print_quote(args, market, options: AnnuityOptions) -> None:
    quote = market.quote(args.premium, args.age, args.sex, options)
    print(f"{money(args.premium)} at age {args.age} — {describe(options)}")
    print()
    print(f"  annual income            {money(quote.annual_income)}  "
          f"({quote.rate:.2%} of the premium)")
    print(f"  monthly                  {money(quote.annual_income / 12)}")
    print()
    print(f"  priced off               {quote.curve_month} gilts at "
          f"{quote.discount_rate:.2%}")
    print(f"  annuity factor           {quote.annuity_factor:.2f} "
          f"(years of income the premium buys, discounted)")
    print(f"  life expectancy used     {quote.life_expectancy:.1f} years, "
          f"to age {args.age + quote.life_expectancy:.0f}")
    print(f"  total paid if you live   {money(quote.annual_income * quote.life_expectancy)} "
          "to that expectancy, undiscounted")
    print()
    print(f"  What it buys, at {args.inflation:.1%} inflation:")
    for year in (0, 10, 20, 30):
        print(f"    year {year:>2}                {money(quote.real_income(year, args.inflation))}"
              " in today's money")
    half_life = quote.half_life(args.inflation)
    if half_life is None:
        print("    purchasing power         holds — the income rises with prices")
    else:
        print(f"    half its value by        year {half_life:.0f}"
              f" (age {args.age + half_life:.0f})")


def print_comparison(args, market) -> None:
    variants = (
        AnnuityOptions(),
        AnnuityOptions(guarantee_years=5),
        AnnuityOptions(guarantee_years=10),
        AnnuityOptions(escalation=0.03),
        AnnuityOptions(rpi_linked=True),
        AnnuityOptions(joint_life_proportion=0.5),
        AnnuityOptions(joint_life_proportion=1.0),
        AnnuityOptions(joint_life_proportion=0.5, rpi_linked=True),
    )
    base = market.quote(args.premium, args.age, args.sex, AnnuityOptions()).annual_income
    print(f"{money(args.premium)} at age {args.age}, "
          f"{args.inflation:.1%} inflation assumed\n")
    print(f"  {'option':<44}{'income':>10}{'vs level':>10}"
          f"{'real yr20':>12}{'lifetime real':>15}")
    for options in variants:
        quote = market.quote(args.premium, args.age, args.sex, options)
        lifetime = sum(
            quote.real_income(year, args.inflation)
            for year in range(int(quote.life_expectancy))
        )
        print(f"  {describe(options):<44}{money(quote.annual_income):>10}"
              f"{quote.annual_income / base - 1:>+9.1%}"
              f"{money(quote.real_income(20, args.inflation)):>12}"
              f"{money(lifetime):>15}")
    print()
    print("  'lifetime real' totals the real payments to life expectancy — the "
          "column that reverses the headline ranking.")


def print_history(args, market) -> None:
    history = GiltCurve.history()
    options = AnnuityOptions()
    quotes = [
        (curve.month, market.with_curve(curve).quote(
            args.premium, args.age, args.sex, options).annual_income)
        for curve in history
    ]
    incomes = [income for _, income in quotes]
    best = max(quotes, key=lambda q: q[1])
    worst = min(quotes, key=lambda q: q[1])
    latest = quotes[-1]

    print(f"{money(args.premium)} at age {args.age}, single life level, "
          f"priced on each month's gilt curve\n")
    print(f"  best        {best[0]}   {money(best[1])}")
    print(f"  worst       {worst[0]}   {money(worst[1])}")
    print(f"  latest      {latest[0]}   {money(latest[1])}")
    print(f"  average     {' ' * 7}   {money(sum(incomes) / len(incomes))}")
    print()
    print(f"  Best to worst is a {best[1] / worst[1] - 1:.0%} difference on the same "
          "premium at the same age.")
    print("  Today's mortality basis is held fixed throughout, so this isolates the")
    print("  gilt market. Longevity did improve over the period, which would have made")
    print("  the early rates better still — the spread is a floor, not an overstatement.")
    print()
    step = max(1, len(quotes) // 24)
    for month, income in quotes[::step]:
        bar = "#" * int((income - worst[1]) / (best[1] - worst[1]) * 40)
        print(f"  {month}  {money(income):>8}  {bar}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--premium", type=float, default=100_000.0)
    parser.add_argument("--age", type=float, default=65)
    parser.add_argument("--sex", choices=("male", "female"), default=None,
                        help="UK annuities are unisex, so this changes nothing "
                             "unless you are asking what one life expects")
    parser.add_argument("--joint", dest="joint_life_proportion", type=float, default=0.0,
                        help="fraction of income continuing to a spouse (0.5, 1.0)")
    parser.add_argument("--spouse-age", type=float, default=None,
                        help="spouse's age (default: three years younger)")
    parser.add_argument("--guarantee", dest="guarantee_years", type=int, default=0)
    parser.add_argument("--escalation", type=float, default=0.0,
                        help="fixed annual increase, e.g. 0.03")
    parser.add_argument("--rpi", dest="rpi_linked", action="store_true",
                        help="income rises with inflation")
    parser.add_argument("--health-uplift", type=float, default=0.0,
                        help="enhanced underwriting, e.g. 0.07 for a smoker")
    parser.add_argument("--inflation", type=float, default=0.03,
                        help="assumed inflation for the real-income columns")
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args(argv)

    try:
        market = uk_annuity_market()
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.compare:
        print_comparison(args, market)
    elif args.history:
        print_history(args, market)
    else:
        offset = (
            int(args.spouse_age - args.age) if args.spouse_age is not None else -3
        )
        print_quote(args, market, AnnuityOptions(
            joint_life_proportion=args.joint_life_proportion,
            spouse_age_offset=offset,
            guarantee_years=args.guarantee_years,
            escalation=args.escalation,
            rpi_linked=args.rpi_linked,
            health_uplift=args.health_uplift,
        ))

    print()
    print("A planning estimate calibrated to published best-buy tables, not a quote. "
          "Real rates are underwritten and vary by more between providers than this "
          "model's own error.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
