---
name: define-scenarios
description: Turn a client's goals and risk tolerance into a concrete retireplan Scenario set. Use after intake-financial-data and before run-scenario-simulation.
---

# Define scenarios

Produces `workspace/<name>/scenarios.py`: a `BASE_CASE` (the literal goal, run
first and alone), a `HEADLINE` dict of alternatives chosen once its result is
known, and a `VARIANTS` dict testing one decision each.

**Used twice per engagement.** Phase 1 defines and runs the base case; phase 2
returns here only once that result exists. Which alternatives matter is a
conclusion from the base case, not a guess made alongside it.

`Scenario` (`src/retireplan/scenario.py`) holds the *decisions* — retirement
dates, spending multiplier, dated `one_off_spends`, a `market_stress` prefix,
and the `withdrawal` / `drawdown` / `allocation` slots. The household holds the
facts.

## Phase 1: the base case

One scenario, not a set: the client's stated goal translated as literally as
possible, bounded only by hard constraints.

1. Read the stated goal from intake (a date, "as early as possible", a
   purchase) and any hard constraint on it.
2. **"As early as possible" is bounded by the notice period**, not by guessing
   what the assets support. Compute it dynamically — `add_months(AS_OF, n)`,
   never a hardcoded date, so a regenerated plan moves with `AS_OF`. A stated
   fixed date needs no floor.
3. Choose a withdrawal strategy and drawdown order on purpose (below). **Never
   leave `withdrawal=None`** for anything reported: it spends the plan
   regardless and lets shortfalls stand — an honest engine baseline, not a plan.
4. Run it and read the result before anything else. No date sweeps, no variants.

## Phase 2: alternatives, decided from the result

- **Base case struggled or failed** — build downside alternatives tied to the
  flexibility intake recorded: later date, reduced spending, different drawdown
  order, de-risking. **Sweep, don't guess** for "the earliest date that works":
  run a range, find where success crosses a safe threshold, then check the
  neighbourhood — if the month before falls off a cliff, recommend a date with
  margin and say why. Keep the failing base case as a named scenario; *why* it
  fails is usually the most useful finding in the report.
- **Base case cleared comfortably** — the commonly skipped half. **Always test
  alternatives that let the client have or spend more**: an earlier date, a
  higher withdrawal rule (`GuytonKlinger`, `PostAccessStepUp`), bringing a
  costed goal forward, gifting. A 98% base case reported with no upside
  alternative is a missed finding, not conservatism.
- **Either way**, add variants isolating one decision each against the current
  headline, so any difference is attributable:

| Variant | What it tests |
|---|---|
| `GuytonKlinger` / `SpendNominal` / `PostAccessStepUp` | the spending rule |
| `CashBondLadder` / `StandardOrder` / `TaxEfficientOrder` | the draw order |
| `StaticMix` / `ByAssetTypeMix` / `GlidePath` / `BondTent` | allocation |
| `market_stress=({"global_equity": -0.35}, ...)` | sequence-of-returns |
| `OneOffSpend` | any uncosted goal |
| `care=CarePlan()`, and with `ImmediateNeedsAnnuity(enabled=True)` | care and its hedge |
| `income_annuity=IncomeAnnuity(enabled=True, fraction_of_pot=...)` | a safety-first floor |
| `death_ages={"Name": 75}` | the survivor's position |
| a `LifeTable` household against the `FixedAge` default | mortality |

- `BondTent` is the Kitces/Pfau finding that sequence risk peaks *at*
  retirement: de-risk into it and re-risk after, rather than `GlidePath`'s
  one-way decline through it.
- **Test care on every engagement**, not only when asked — it is off by default,
  and a report that never mentions it implies a completeness the plan lacks.
  Keep it out of the base case: it answers a different question from "when can
  we stop working".
- `IncomeAnnuity` is bought once from each accessible DC pension, securing
  essential spending as fully-taxable income for life before the rest is
  invested for upside. Not `ImmediateNeedsAnnuity`, which is impaired-life,
  care-only and paid tax-free direct to the provider. Test it whenever a
  household is anxious about running out rather than about the estate.
- `death_ages` is worth running even though the aggregate already includes first
  death: a client asked to picture twenty years alone on one State Pension needs
  the specific number.
- `FixedAge` vs `LifeTable` answer different questions and the gap is usually
  large — run both where the bequest is part of the goal.

Every alternative traces to a goal or flexibility intake actually recorded.
Share the `HEADLINE` set in plain language and confirm before reporting.

## Choosing a drawdown order

`StandardOrder` (cash, ISA, pension) is intuitive and usually the wrong lead for
any household whose estate matters: since pensions entered the IHT estate in
April 2027, `TaxEfficientOrder` — pension first up to a chosen band, ISA for the
rest — is normally the better starting point, base case included. Load
`uk-pension-tax-strategy` before deciding rather than reaching for the familiar
rule of thumb.

`TaxEfficientOrder`, `PensionAccess.PCLS` and surplus investment all work for a
person with no explicit ISA `Asset` — `plan.py` synthesises a zero-balance one,
as it already did for a GIA. Still record a client's real ISA in intake: the
fallback is a safety net for "holds none today", not a substitute for a balance.

**Actively consider a variant that opens an ISA or GIA where the household does
not already lean on one.** Pension-only wealth approaching access age, or
meaningful pre-retirement surplus with no ISA/GIA activity, is very often better
off shifting into a wrapper proactively — cheaper tax now, and out of the
IHT-exposed pension sooner. Cost it as a named scenario so the report can show
*why* it helps, rather than letting the engine use it implicitly.

## Bucket strategies do not reduce sequence risk here — tested, not assumed

**Do not reach for `CashBondLadder` or `ThreeBucketStrategy` believing a
cash/bond buffer protects against selling equities in a crash.** Both were
stress-tested against a same-average-allocation rebalanced portfolio on the
classic historical worst starts and a 2,000-trial Monte Carlo (REVIEW.md 1.15).
Both did *worse*, and the more faithful three-bucket version did worse than the
cruder two-bucket one:

| Strategy | Success | Worst-decile ending wealth |
|---|---|---|
| `ThreeBucketStrategy` | 84.5% | £0 |
| `CashBondLadder` | 87.1% | £0 |
| All-equity, no buffer | 88.8% | £0 |
| Rebalanced, same average allocation | **92.2%** | **£112,940** |

The mechanism: both top the reserve back to its *full* target every qualifying
year rather than covering that year's actual need, over-extracting from equities
in merely-okay years and starving 30 years of growth.

**What is tested to help is a plain static equity/bond ratio with no bucket
mechanic** — `StaticMix`/`ByAssetTypeMix`. Success peaked at 60% equity (92.8%),
inside Bengen's independently published 47–75% range, with both tails covered
from 80% down to 40%. Too conservative is its own failure mode: 0% equity scored
48.0% with a *median* ending wealth of zero. Model sequence-risk protection as
an allocation decision, not a drawdown-order one.

This is not a claim that no bucket variant could help — the refill-to-full rule
is specifically what fails, and a gentler rule was never built. Until it is, run
the comparison for the actual household rather than trusting the branding.

## Cautions

- **Every reported scenario needs a withdrawal strategy chosen on purpose.**
- **`GuytonKlinger` is the default needs-based rule.** `FixedFloorGuardrail` was
  removed, not deprecated: it cut only at the point of collapse — 74 cuts, zero
  recoveries across 2,000 trials — and got chosen because the name sounded
  prudent. For flat spending with the risk stated openly, use `SpendNominal`.
  GK's capital-preservation cut suspends itself in the final 15 years
  (`final_years`, per the canonical spec), so a plan that stops cutting late in
  life under a poor sequence is behaving correctly.
- **`ByAssetTypeMix` only overrides the types you name.** Leave
  `default_growth_pct` at `None` unless you intend to re-price every other
  asset, property and fixed-rate holdings included.
- A variant that changes two things at once tells you nothing about either.
