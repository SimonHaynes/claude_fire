"""Validate `retireplan.tax.trusts` against HMRC's own published worked examples.

The relevant property regime is the part of UK tax where a plausible-looking
answer is most likely to be wrong: the charge is on the whole fund rather than
the excess, the rate is fixed at a moment years before the money moves, and it
is rounded twice. So this checks the arithmetic against numbers HMRC published
with the workings, not against a second opinion.

## The examples

**IHTM42087, example 1 — ten-year anniversary.** A settlement created in 2010
with £300,000; the settlor had made £50,000 of chargeable transfers in the
seven years before, leaving £275,000 of nil-rate band. The fund is £450,000 at
the anniversary.

    A  notional transfer        £450,000
    B  less nil-rate band       £275,000
    C  difference               £175,000
    D  x 20%                     £35,000
    E  D / A                       7.777%   (see the rounding note below)
    F  E x 3/10                    2.333%
       tax                     £10,498.50

**IHTM42114 — exit before the first ten-year anniversary.** A notional transfer
of £440,000 built from three components (the settlement's own £290,000, a
£50,000 same-day addition, and £100,000 in the settlement that addition was
made to) against a cumulative total of £190,000. £350,000 is distributed after
12 complete quarters.

    notional transfer          £440,000
    less nil-rate band         £135,000
    difference                 £305,000
    x 20%                       £61,000
    effective rate               13.864%
    x 3/10                        4.159%
    x 12/40                       1.248%
    tax                          £4,368

This one is fed the notional transfer and cumulative total directly. The module
deliberately does not attribute same-day additions and related settlements
itself — the attribution is where practitioners disagree, and a wrong split is
worse than an explicit input.

**IHTM42115 — exit after an anniversary.** A rate of 3.3% at the last
anniversary, 10 complete quarters later: 3.3% x 10/40 = 0.825%. No revaluation
and no fresh effective-rate sum.

## The rounding note

HMRC states rates to three decimal places as a percentage, and its two examples
are not consistent about the direction. 35,000/450,000 is 7.7777...%, which
HMRC's ten-year example shows as 7.777% (rounded down); 61,000/440,000 is
13.8636...%, which its exit example shows as 13.864% (rounded up). The module
rounds. That reproduces every *tax* figure HMRC publishes, including the one in
the example whose intermediate rate it disagrees with by 0.001pp, because the
disagreement washes out at the next rounding. This script reports the gap
rather than hiding it.

Run: .venv/bin/python tools/validate_trust_charges.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from retireplan.tax.trusts import RelevantPropertyRules  # noqa: E402

RULES = RelevantPropertyRules(nil_rate_band=325_000.0)
TOLERANCE = 0.01


def check(label: str, got: float, expected: float, unit: str = "£") -> bool:
    ok = abs(got - expected) <= TOLERANCE
    mark = "PASS" if ok else "FAIL"
    if unit == "%":
        print(f"  [{mark}] {label}: {got:.3f}% vs HMRC {expected:.3f}%")
    else:
        print(f"  [{mark}] {label}: £{got:,.2f} vs HMRC £{expected:,.2f}")
    return ok


def ten_year_anniversary() -> bool:
    print("IHTM42087 example 1 — ten-year anniversary")
    charge = RULES.ten_year_charge(relevant_property=450_000, cumulative_total=50_000)
    ok = [
        check("available nil-rate band", charge.available_nil_rate_band, 275_000),
        check("chargeable", charge.chargeable, 175_000),
        check("notional tax at 20%", charge.notional_tax, 35_000),
        check("actual rate (F)", charge.settlement_rate * 100, 2.333, "%"),
        check("tax", charge.tax, 10_498.50),
    ]
    hmrc_effective = 7.777
    ours = charge.effective_rate * 100
    if abs(ours - hmrc_effective) > 0.0005:
        print(
            f"  [note] effective rate (E): {ours:.3f}% vs HMRC {hmrc_effective:.3f}% — "
            "HMRC rounds this one down; both give the same F and the same tax"
        )
    return all(ok)


def exit_before_first_anniversary() -> bool:
    print("IHTM42114 — exit before the first ten-year anniversary")
    charge = RULES.exit_before_first_anniversary(
        distribution=350_000,
        notional_transfer=440_000,
        cumulative_total=190_000,
        quarters=12,
    )
    ok = [
        check("available nil-rate band", charge.available_nil_rate_band, 135_000),
        check("chargeable", charge.chargeable, 305_000),
        check("notional tax at 20%", charge.notional_tax, 61_000),
        check("effective rate", charge.effective_rate * 100, 13.864, "%"),
        check("settlement rate (x 3/10)", charge.settlement_rate * 100, 4.159, "%"),
        check("actual rate (x 12/40)", charge.rate * 100, 1.248, "%"),
        check("tax", charge.tax, 4_368.00),
    ]
    return all(ok)


def exit_after_anniversary() -> bool:
    print("IHTM42115 — exit after a ten-year anniversary")
    charge = RULES.exit_after_anniversary(
        distribution=100_000,
        settlement_rate_at_last_anniversary=0.033,
        quarters=10,
    )
    ok = [
        check("actual rate", charge.rate * 100, 0.825, "%"),
        check("tax on a £100,000 distribution", charge.tax, 825.00),
    ]
    return all(ok)


def the_three_month_rule() -> bool:
    """Not an HMRC example: the boundary the examples imply and clients rely on."""
    print("Boundary — property leaving inside three months")
    charge = RULES.exit_before_first_anniversary(
        distribution=1_000_000, notional_transfer=1_000_000, cumulative_total=0, quarters=0
    )
    return all([check("tax with 0 complete quarters", charge.tax, 0.00)])


def the_charge_is_on_the_whole_fund() -> bool:
    """The misreading that costs the most: 6% of the excess, not of the fund."""
    print("Boundary — a fund at twice the nil-rate band")
    charge = RULES.ten_year_charge(relevant_property=650_000, cumulative_total=0)
    return all([
        check("actual rate", charge.settlement_rate * 100, 3.000, "%"),
        check("tax", charge.tax, 19_500.00),
    ])


def main() -> int:
    checks = (
        ten_year_anniversary,
        exit_before_first_anniversary,
        exit_after_anniversary,
        the_three_month_rule,
        the_charge_is_on_the_whole_fund,
    )
    results = []
    for fn in checks:
        results.append(fn())
        print()
    if all(results):
        print("All checks match HMRC's published workings.")
        return 0
    print("Some checks did not match — the module is wrong, or HMRC has restated.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
