"""Scenarios for the fabricated sample household.

**Not a real client.** See `household.py`.

This is the worked example the `define-scenarios` skill points to. It is
deliberately small — three headline scenarios and four variants — because its
job is to show the *shape* of a scenario set, not to explore every option the
engine has.

## The two phases, and why the order matters

`BASE_CASE` is defined and run **alone**, first. It is the household's stated
goal translated as literally as possible, bounded only by a hard constraint
(here, Pat's three-month notice period), and it is not optimised.

`HEADLINE` and `VARIANTS` exist only because `BASE_CASE`'s result told us what
was worth testing. Writing them at the same time as the base case would be
guessing at the answer and then confirming it. The comment above each records
what in the base case's result prompted it — if you change the base case, those
comments are the first thing to re-check.

## Dates are computed, not typed

`STRETCH` is `AS_OF` plus the notice period, not a hardcoded date. A plan
regenerated in six months should see the earliest possible retirement date move
with it, rather than staying pinned to when the file was first written.
"""
from __future__ import annotations

from datetime import date

from retireplan import (
    ByAssetTypeMix,
    CashBondLadder,
    GuytonKlinger,
    SpendNominal,
    OneOffSpend,
    PostAccessStepUp,
    Scenario,
    StandardOrder,
    TaxEfficientOrder,
    add_months,
)

from .household import AS_OF

#: Pat's notice period. A real floor on "as early as possible" -- it is not a
#: financial constraint, so nothing in the model knows about it unless it is
#: written here.
NOTICE_PERIOD_MONTHS = 3

#: The earliest date the notice period actually permits.
STRETCH = add_months(AS_OF, NOTICE_PERIOD_MONTHS)

#: Where a quarterly sweep clears 95%, plus one quarter of margin.
#:
#: The base case does not clear (49.4%), so the question became "when does
#: this actually work?" -- swept quarterly from 2029 to 2031 under all three
#: withdrawal rules, because `GuytonKlinger` alone is not trustworthy for this
#: (REVIEW.md 1.12, and see `define-scenarios`). Success on the worst of the
#: three is what the date is chosen on:
#:
#:              GK   SpendNominal  PostAccessStepUp    worst
#:     2029-10  95.5%    92.8%          92.8%          92.8%
#:     2030-01  96.5%    94.0%          93.9%          93.9%
#:     2030-04  96.2%    95.0%          94.9%          94.9%
#:     2030-07  97.0%    95.5%          95.2%          95.2%   <- crossing
#:     2030-10  97.6%    96.4%          96.2%          96.2%   <- RECOMMENDED
#:     2031-01  97.8%    96.9%          96.8%          96.8%
#:
#: Note what taking GK on its own would have done: it clears 95% a full three
#: quarters earlier, at 2029-10. That is the trap the sweep exists to avoid.
#:
#: July 2030 is the crossing point on the worst column. The curve either side
#: is a smooth ~1.3 points/quarter slope rather than a cliff, so one quarter of
#: margin is enough; on a cliff it would need more. Recommending the crossing
#: point itself would leave a plan that fails on any small revision to the
#: inputs.
RECOMMENDED = date(2030, 10, 1)

#: A further year, to show what waiting actually buys (98.1% on the worst rule
#: — about two points for twelve months, which is usually less than clients
#: expect).
CONSERVATIVE = date(2031, 10, 1)


def _retire_both(when: date) -> dict[str, date]:
    """Pat and Robin stop together, which is what the notes describe."""
    return {"Pat": when, "Robin": when}


# ---------------------------------------------------------------------------
# Phase 1: the base case. Run this alone, and read it, before going further.
# ---------------------------------------------------------------------------

BASE_CASE = Scenario(
    "Base case — retire as soon as notice allows",
    retirement_dates=_retire_both(STRETCH),
    withdrawal=GuytonKlinger(),
    drawdown=TaxEfficientOrder(),
)
"""The stated goal, taken literally.

`TaxEfficientOrder` rather than `StandardOrder` even here: since pensions
entered the IHT estate in April 2027, "spend the ISA first" is no longer the
neutral default it reads as, so leading with it would bias the base case. See
the `uk-pension-tax-strategy` skill.

`withdrawal` is set deliberately. Leaving it `None` spends the plan regardless
and lets shortfalls stand, which is an honest baseline for engine testing but
not something to show a client as if it were a plan.
"""


# ---------------------------------------------------------------------------
# Phase 2: decided *from* the base case's result, not alongside it.
# ---------------------------------------------------------------------------

HEADLINE = {
    # The base case did not clear, so it stays in the set: why it fails is
    # more useful to the reader than quietly replacing it with one that works.
    "stretch": BASE_CASE,

    # Found by sweeping, not guessing -- see RECOMMENDED's comment for the
    # swept range and why this is a quarter past the crossing point.
    "recommended": Scenario(
        f"Retire {RECOMMENDED:%B %Y}",
        retirement_dates=_retire_both(RECOMMENDED),
        withdrawal=GuytonKlinger(),
        drawdown=TaxEfficientOrder(),
    ),

    # What another year of working actually buys. Worth showing even when the
    # recommendation is earlier: a client asked to wait deserves to see the
    # size of the gain, which here is about two percentage points.
    "conservative": Scenario(
        f"Retire {CONSERVATIVE:%B %Y}",
        retirement_dates=_retire_both(CONSERVATIVE),
        withdrawal=GuytonKlinger(),
        drawdown=TaxEfficientOrder(),
    ),
}

#: Each variant changes exactly one decision against `recommended`, so any
#: difference is attributable to that decision. A variant that changes two
#: things at once tells you nothing about either.
VARIANTS = {
    "withdrawal_spend_nominal": Scenario(
        "Spend the plan regardless, and let a shortfall stand",
        retirement_dates=_retire_both(RECOMMENDED),
        withdrawal=SpendNominal(),
        drawdown=TaxEfficientOrder(),
    ),
    "withdrawal_step_up": Scenario(
        "Spend more once the pensions unlock",
        retirement_dates=_retire_both(RECOMMENDED),
        withdrawal=PostAccessStepUp(),
        drawdown=TaxEfficientOrder(),
    ),
    "drawdown_standard_order": Scenario(
        "ISA first, pension last (the pre-2027 rule)",
        retirement_dates=_retire_both(RECOMMENDED),
        withdrawal=GuytonKlinger(),
        drawdown=StandardOrder(),
    ),
    "drawdown_cash_ladder": Scenario(
        "A pre-funded cash and bond ladder",
        retirement_dates=_retire_both(RECOMMENDED),
        withdrawal=GuytonKlinger(),
        drawdown=CashBondLadder(),
    ),
    "allocation_by_asset_type": Scenario(
        "De-risk the bridge, leave the pensions in equities",
        retirement_dates=_retire_both(RECOMMENDED),
        withdrawal=GuytonKlinger(),
        drawdown=TaxEfficientOrder(),
        # Only the types named are overridden. Leaving `default_growth_pct` at
        # None is deliberate: setting it re-prices *every* other asset,
        # including the house, which once overstated an estate by two thirds.
        allocation=ByAssetTypeMix({"isa": 0.4}),
    ),
    "stress_crash_at_retirement": Scenario(
        "A 35% crash in the first two years",
        retirement_dates=_retire_both(RECOMMENDED),
        withdrawal=GuytonKlinger(),
        drawdown=TaxEfficientOrder(),
        market_stress=({"global_equity": -0.35}, {"global_equity": -0.10}),
    ),
    "goal_costed_kitchen": Scenario(
        "With the kitchen the notes mention but never cost",
        retirement_dates=_retire_both(RECOMMENDED),
        withdrawal=GuytonKlinger(),
        drawdown=TaxEfficientOrder(),
        one_off_spends=(OneOffSpend(date(2030, 6, 1), 25_000, "New kitchen"),),
    ),
}
