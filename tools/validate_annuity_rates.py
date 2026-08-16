"""Check `retireplan.annuity` against published best-buy annuity rates.

    .venv/bin/python tools/validate_annuity_rates.py

An annuity model can be wrong by 20% and still look entirely reasonable — the
number it produces has no natural scale a reader can check against. So this
compares it with a whole-of-market best-buy table that anyone can look up, and
prints the residual on **every** cell rather than an average that hides the
worst one.

## The benchmark

Hargreaves Lansdown's published best-buy table, **13 August 2026**. Its stated
assumptions, which the model is set up to match:

  * £100,000 purchase, average postcode, paid **monthly in advance**
  * joint-life quotes assume the spouse is **three years younger**
  * "smoker" is an enhanced quote, not a standard one

Cross-checked against Which?'s table of 10 August 2026, whose best single-life
rate at 65 (£7,956 from Canada Life) and at 70 (£8,800 from Scottish Widows)
sit within a percent of HL's — so the benchmark is the market, not one broker.

## What is fitted and what is not

Ten of the thirty cells were used for calibration:

  * the five **single life, level, no guarantee** rows fixed the mortality
    multiplier and the illiquidity spread
  * the five **RPI-linked** rows fixed the inflation risk premium

The other twenty — guarantee periods, fixed escalation, joint life, and joint
life combined with escalation — are **predictions**. They come out of the same
annuity factor with no further adjustment, which is the only real evidence that
the model has the mechanism right rather than a curve fitted through five
points. Watch those rows, not the fitted ones.

## What this cannot check

That the model is right *tomorrow*. The gilt curve moves daily and the
published table is a snapshot; a residual growing over time means the curve
data is stale (re-run `tools/fetch_gilt_yields.py`) or the market has repriced
mortality, not that the arithmetic broke. Re-benchmark against a fresh table
after a large move in gilts, and record it in `tax/provenance.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from retireplan.annuity import AnnuityOptions, uk_annuity_market  # noqa: E402

BENCHMARK_DATE = "13 August 2026"
SOURCE = "https://www.hl.co.uk/retirement/annuities/best-buy-rates"
PREMIUM = 100_000.0
AGES = (55, 60, 65, 70, 75)

TOLERANCE = 0.03
"""Three percent. A real quote varies by more than this between providers on
the same day — Which?'s own table spans 16% between best and worst at 65 — so a
tighter tolerance would be pretending the market has one price."""

# (label, options, income per £100,000 at ages 55/60/65/70/75, fitted?)
BENCHMARK = (
    ("single life, level, no guarantee",
     {}, (6820, 7209, 7968, 8709, 9969), True),
    ("single life, level, 5-year guarantee",
     {"guarantee_years": 5}, (6808, 7195, 7906, 8598, 9714), False),
    ("single life, RPI-linked, 5-year guarantee",
     {"guarantee_years": 5, "rpi_linked": True}, (4337, 4771, 5585, 6234, 7565), True),
    ("single life, 3% escalation, 5-year guarantee",
     {"guarantee_years": 5, "escalation": 0.03}, (4737, 5168, 5895, 6634, 7830), False),
    ("joint life 50%, level, no guarantee",
     {"joint_life_proportion": 0.5}, (6465, 6874, 7406, 8030, 8819), False),
    ("joint life 50%, 3% escalation, no guarantee",
     {"joint_life_proportion": 0.5, "escalation": 0.03}, (4362, 4778, 5349, 6093, 6998), False),
)

SMOKER_AT_65 = (8554, 0.074)
"""HL's smoker quote at 65, and the uplift it implies over the standard rate.
The model cannot derive this — it has no knowledge of anyone's health — so this
records the market's own figure as the sanity check on what
`AnnuityOptions.health_uplift` should be handed for a mild enhancement."""


def main() -> int:
    market = uk_annuity_market()
    print(f"Benchmark: HL best-buy table, {BENCHMARK_DATE}")
    print(f"           {SOURCE}")
    print(f"Curve:     Bank of England, {market.curve.month} "
          f"(15-year nominal {market.curve.nominal_yield():.2%}, "
          f"real {market.curve.real_yield():.2%})")
    print(f"Mortality: ONS x {market.mortality.qx_multiplier:.2f}, "
          f"improving {market.mortality.annual_improvement:.1%}/yr "
          f"-> e(65) = {market.mortality.life_expectancy(65):.1f} years")
    print()

    header = "  ".join(f"{age:>13}" for age in AGES)
    print(f"{'':<52}{header}")

    residuals: list[float] = []
    unfitted: list[float] = []
    failures = 0

    for label, options, published, fitted in BENCHMARK:
        cells = []
        for age, target in zip(AGES, published):
            quote = market.quote(PREMIUM, age, options=AnnuityOptions(**options))
            error = quote.annual_income / target - 1
            residuals.append(error)
            if not fitted:
                unfitted.append(error)
            if abs(error) > TOLERANCE:
                failures += 1
            cells.append(f"{quote.annual_income:>7,.0f}{error * 100:>+6.1f}%")
        mark = "fitted " if fitted else "PREDICT"
        print(f"  [{mark}] {label[:41]:<41}" + "  ".join(cells))

    print()
    print(f"  {'published (level, no guarantee)':<51}" + "  ".join(
        f"{value:>7,.0f}{'':>6}" for value in BENCHMARK[0][2]))
    print()

    def summarise(name: str, values: list[float]) -> None:
        rms = (sum(v * v for v in values) / len(values)) ** 0.5
        worst = max(values, key=abs)
        print(f"  {name:<28} rms {rms * 100:5.2f}%   worst {worst * 100:+.1f}%   "
              f"n = {len(values)}")

    summarise("all cells", residuals)
    summarise("unfitted predictions only", unfitted)
    print()

    standard = market.quote(PREMIUM, 65).annual_income
    print(f"  Enhanced underwriting: HL quotes £{SMOKER_AT_65[0]:,} for a smoker at 65 "
          f"against £{standard:,.0f} standard")
    print(f"  -> health_uplift = {SMOKER_AT_65[1]:.3f} for a smoker. The model applies "
          "whatever it is told; only an underwriter can price a real life.")
    print()

    if failures:
        print(f"{failures} cell(s) outside {TOLERANCE:.0%}. Either the gilt data is "
              "stale (re-run tools/fetch_gilt_yields.py) or the market has repriced "
              "and the calibration needs redoing against a fresh table.")
        return 1
    print(f"Every cell within {TOLERANCE:.0%} of the published table.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
