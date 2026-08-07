---
name: define-scenarios
description: Turn a client's goals and risk tolerance into a concrete retireplan Scenario set. Use after intake-financial-data and before run-scenario-simulation.
---

# Define scenarios

Produces `workspace/<name>/scenarios.py`: a `BASE_CASE` scenario (the literal
goal, run first and alone), a `HEADLINE` dict of the alternatives chosen once
its result is known, and a `VARIANTS` dict testing one decision each.

This skill is used **twice** per engagement, not once — see the
`retirement-planner` agent's five-step process. Phase 1 (steps 3) defines and
runs a single base case. Phase 2 (step 4) comes back to this skill only after
that result exists, to decide what alternatives are actually worth testing.
Do not collapse the two into one upfront pass: which alternatives matter is a
conclusion from the base case, not a guess made alongside it.

## What a scenario carries

`Scenario` (see `src/retireplan/scenario.py`) holds the decisions:
retirement dates, a spending multiplier, dated `one_off_spends`, a
`market_stress` prefix, and the three strategy slots — `withdrawal`,
`drawdown`, `allocation`. The household holds the facts. Anything that is a
*choice* belongs here.

## Phase 1: the base case

One scenario, not a set. It is the client's stated goal, translated as
literally as possible into a `Scenario`, bounded only by hard constraints —
not yet optimised, not yet compared against alternatives.

1. Read the household's stated goal from intake (a date, "as early as
   possible", a purchase) and any hard constraint on it.
2. **"As early as possible" is bounded by the client's notice period, not by
   guessing at what the assets can support.** If intake recorded one, the
   base case's date is `AS_OF + notice period`, computed dynamically (e.g.
   `add_months(AS_OF, n)`, never a hardcoded calendar date — a plan
   regenerated later should see this move with `AS_OF`, not stay pinned to
   when it was first written). A stated fixed date needs no such floor;
   use it as given.
3. Choose a withdrawal strategy and a drawdown order on purpose — see
   "Choosing a drawdown order" below. **Never leave `withdrawal=None`** for a
   base case that will be reported: it spends the plan regardless and lets
   shortfalls stand, which is an honest baseline for engine testing but not
   something to show a client as if it were a real plan.
4. Run it (`run-scenario-simulation`) and read the result before doing
   anything else. Do not sweep dates, do not build variants yet — that is
   phase 2, and which ones are worth building depends on what this result
   actually shows.

## Phase 2: alternatives, decided from the base case's result

Come back here once the base case has a result. What it showed determines
which alternatives are worth the compute, not habit or a fixed template of
"conservative / recommended / stretch":

- **The base case struggled or failed** — build downside alternatives tied to
  the flexibility intake captured: a later date, reduced spending, a
  different drawdown order, de-risking. **Sweep, don't guess**, for "the
  earliest date that actually works": run a range and find where success
  crosses a safe threshold, then check the neighbourhood — if the month
  before drops off a cliff, recommend a date with margin rather than the
  exact crossing point, and say why. Keep the original base case as a named
  scenario even though it fails; *why* it fails is usually the most useful
  single finding in the report.
- **The base case cleared comfortably** — the more commonly skipped half.
  **Always test alternatives that let the client have or spend more**: an
  earlier date, a higher withdrawal rule (`GuytonKlinger`,
  `PostAccessStepUp`), bringing a costed goal forward, gifting. A base case
  that already clears 98% and gets reported with no upside alternative is a
  missed finding, not a conservative choice.
- **Either way**, add variants that isolate one decision each against
  whichever scenario is now the headline, so any difference is attributable:
  - `GuytonKlinger()` vs `SpendNominal()` vs `PostAccessStepUp()`
  - `CashBondLadder()` vs `StandardOrder()` vs `TaxEfficientOrder()`
  - `StaticMix` / `ByAssetTypeMix` / `GlidePath` / `BondTent` for allocation —
    `BondTent` is the Kitces/Pfau finding that sequence risk peaks *at*
    retirement, not before or long after: de-risk into it, then re-risk
    afterward, rather than `GlidePath`'s one-way decline through it.
  - `market_stress=({"global_equity": -0.35}, ...)` for a deliberate
    sequence-of-returns test
  - Costed versions of any uncosted goal, via `OneOffSpend`
  - `care=CarePlan()` for late-life residential care, and
    `CarePlan(annuity=ImmediateNeedsAnnuity(enabled=True))` for the hedge.
    **Test this on every engagement**, not only when asked: it is off by
    default, and a report that never mentions it implies a completeness the
    plan does not have. Keep it out of the base case — it answers a
    different question from "when can we stop working".
  - `income_annuity=IncomeAnnuity(enabled=True, fraction_of_pot=...)` for a
    Bodie/Pfau floor-and-upside (safety-first) comparison: bought once from
    each accessible DC pension, converting part of it into guaranteed,
    fully-taxable income for life, so essential spending is secured before
    the rest is invested for upside. Not the same instrument as
    `ImmediateNeedsAnnuity` — that one is impaired-life, care-only, and paid
    tax-free direct to the provider; this one is an ordinary lifetime
    annuity bought at retirement, taxed like any other pension income. Worth
    testing whenever a household is anxious about running out rather than
    about the estate.
  - `death_ages={"Name": 75}` to show the survivor's position directly. The
    aggregate already includes first death, but a client asked to picture
    twenty years alone on one State Pension needs the specific number.
  - A `LifeTable` household variant against the `FixedAge` default, where
    the bequest is part of the goal — the two answer different questions and
    the gap between them is usually large.

Every alternative traces back to a goal or a flexibility intake actually
recorded — not an arbitrary variation invented at this stage. Share the
resulting `HEADLINE` set in plain language and confirm before building the
report.

## Choosing a drawdown order

`StandardOrder` (cash, then ISA, then pension) is the intuitive default and,
for any household whose estate matters, it is usually the wrong one to lead
with: since pensions entered the IHT estate (April 2027), `TaxEfficientOrder`
— pension first up to a chosen band, ISA for the rest — is normally the
better starting point, for the base case as much as any later headline
scenario. Load `uk-pension-tax-strategy` before deciding; do not reach for
`StandardOrder` by habit just because "spend the ISA first" is the familiar
rule of thumb.

**`TaxEfficientOrder`, `PensionAccess.PCLS`, and ordinary surplus investment
all work even for a person with no explicit `ISA` `Asset`** — `plan.py`
synthesises a zero-balance one automatically, the same way it already did
for a GIA, so there is nothing to check here before running anything. This
used to be a real gap (nothing would route to an ISA at all without one, and
nothing would error to say so); it no longer is. Still record the client's
*real* ISA in intake whenever they have one — the synthetic fallback opens
at zero and is a safety net for "holds none today," not a substitute for
their actual balance.

**Actively consider a variant that opens an ISA (or GIA) where the household
doesn't already lean on one.** A household sitting on pension-only wealth
approaching access age, or with meaningful pre-retirement surplus and no
ISA/GIA activity, is very often better off shifting money into a wrapper
proactively — cheaper tax now than later, and outside the IHT-exposed
pension sooner. Don't just enable the mechanism and let the engine use it
implicitly; when it looks like it would matter, cost it explicitly as a
named scenario or variant so the report can show *why* it helps, not just
that a number changed.

## Cash buffers and bucket strategies do not reduce sequence risk here — tested, not assumed

**Do not reach for `CashBondLadder` or `ThreeBucketStrategy` on the belief
that holding a cash/bond buffer protects against selling equities in a
crash.** Both were stress-tested against a same-average-allocation
rebalanced portfolio (one blended fund, no bucket mechanic) on the classic
historical worst retirement starts and a 2,000-trial Monte Carlo — full
numbers in REVIEW.md 1.15. Both bucket strategies did *worse* than the
rebalanced comparison, and the more faithfully-implemented three-bucket
version did worse than the cruder two-bucket one:

| Strategy | Success | Worst-decile ending wealth |
|---|---|---|
| `ThreeBucketStrategy` | 84.5% | £0 |
| `CashBondLadder` | 87.1% | £0 |
| All-equity, no buffer | 88.8% | £0 |
| Rebalanced, same average allocation | **92.2%** | **£112,940** |

The mechanism: both strategies top their reserve back up to its *full*
target on every qualifying year, not just enough to cover that year's
actual need — which over-extracts from equities in years that were merely
okay, not genuinely strong, and starves the growth the plan needs over a
30-year retirement.

**What is genuinely tested to help: a plain, static equity/bond ratio, no
bucket mechanic at all** — `StaticMix`/`ByAssetTypeMix` at a chosen
percentage. Same setup, success probability peaked at 60% equity (92.8%),
comfortably inside Bengen's independently-published 47–75% optimal range,
with both tails covered from 80% down to 40%. Going too conservative is its
own failure mode: 0% equity scored 48.0% success with a *median* ending
wealth of zero. If sequence-risk protection is the goal, model it as an
allocation decision, not a drawdown-order one.

This is not a blanket claim that no bucket variant could ever help — the
refill rule tested (top up to full target) is specifically what fails; a
gentler rule was not built or tested. Until it is, treat any bucket
recommendation the same way as any other: run the comparison for the actual
household, don't assume the branding.

## Cautions

- **Every reported scenario needs a withdrawal strategy chosen on purpose.**
  The default (`None`) spends the plan regardless and lets shortfalls stand —
  fine for a quick engine check, not for anything that reaches a client.
- **`GuytonKlinger` is the default needs-based rule.** A former
  `FixedFloorGuardrail` was removed: it cut only once the accounts could no
  longer fund the year, so it acted at the point of collapse, and across 2,000
  trials on a real household it cut 74 times and recovered zero times. It was
  chosen for reports because the name sounded prudent, which is the reason it
  is gone rather than merely deprecated. If a household genuinely wants flat
  spending with the shortfall risk stated openly, that is `SpendNominal`.
  Its capital-preservation cut suspends itself automatically in the final 15
  years of the household's projected retirement (`final_years`, the
  canonical Guyton-Klinger spec) — nothing to configure for this, just don't
  be surprised to see a plan stop cutting late in life even under a poor
  sequence.
- **`ByAssetTypeMix` only overrides the types you name.** Leave
  `default_growth_pct` at `None` unless you genuinely intend to re-price
  every other asset — including property and fixed-rate holdings.
- A variant that changes two things at once tells you nothing about either.
