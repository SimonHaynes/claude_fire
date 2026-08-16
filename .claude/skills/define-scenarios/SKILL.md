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
  order, de-risking. **Sweep, don't guess** for "the earliest date that works"
  (below). Keep the failing base case as a named scenario; *why* it fails is
  usually the most useful finding in the report.
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
| `market_stress=({"global_equity": -0.35}, ...)` | sequence-of-returns — forces the first N *plan* years from `as_of`, so for a household retiring later it lands **before** they stop, not after. Name the scenario accordingly |
| `OneOffSpend` | any uncosted goal |
| `care=CarePlan()`, and with `ImmediateNeedsAnnuity(enabled=True)` | care and its hedge |
| `income_annuity=IncomeAnnuity(enabled=True, fraction_of_pot=...)` | a safety-first floor |
| `death_ages={"Name": 75}` | the survivor's position |
| a `LifeTable` household against the `FixedAge` default | mortality |
| `ReliefAtSource` on the lower earner's pension | funding a partner's pension — see `uk-tax-relief-and-allowances` for when it pays |
| raised `state_pension_qualifying_years` + a matching `OneOffSpend` | buying back NI years |

- `BondTent` is the Kitces/Pfau finding that sequence risk peaks *at*
  retirement: de-risk into it and re-risk after, rather than `GlidePath`'s
  one-way decline through it.
- **Test care on every engagement**, not only when asked — it is off by default,
  and a report that never mentions it implies a completeness the plan lacks.
  Keep it out of the base case: it answers a different question from "when can
  we stop working".
- `IncomeAnnuity` is bought once from each accessible DC pension, securing
  essential spending as fully-taxable income for life before the rest is
  invested for upside. Priced at the buyer's real age off the gilt curve, with
  `joint_life_proportion`, `guarantee_years`, `escalation` and `rpi_linked` —
  see `uk-annuities`, and note the default is **level**, which decays in real
  terms. Not `ImmediateNeedsAnnuity`, which is impaired-life, care-only and paid
  tax-free direct to the provider. Test it whenever a household is anxious about
  running out rather than about the estate.
- `death_ages` is worth running even though the aggregate already includes first
  death: a client asked to picture twenty years alone on one State Pension needs
  the specific number.
- `FixedAge` vs `LifeTable` answer different questions and the gap is usually
  large — run both where the bequest is part of the goal.

Every alternative traces to a goal or flexibility intake actually recorded.
Share the `HEADLINE` set in plain language and confirm before reporting.

## Sweeping for a retirement date

**Never pick a date on one withdrawal rule's number.** `GuytonKlinger` anchors
its withdrawal rate on the first year of retirement, so for any household
bridging to pension access that anchor is set abnormally high, the guardrail
never engages, and success stops being monotonic in the date — a month can
score six points better than its neighbour for reasons unrelated to the
household's finances (REVIEW.md 1.12, seen twice on real engagements).

Sweep `GuytonKlinger`, `SpendNominal` and `PostAccessStepUp` together and
**recommend on the worst of the three**, which does slope smoothly. Quote that
figure in the report beside the headline one.

**The tell that you are in this trap: median spend identical across dates, and
at or above the full unreduced plan.** That is the guardrail never firing.

```python
scenarios = {(when, name): Scenario(f"{name} {when}", retirement_dates=..., withdrawal=rule())
             for when in dates for name, rule in RULES.items()}
results = run_many(household, scenarios, as_of, seed=42, cache_dir=...)   # see run-scenario-simulation
```

Sweep coarsely first, then monthly around the crossing, and read the shape: a
smooth slope needs a month or two of margin past the threshold, a cliff needs
much more. Recommend the knee — where the curve flattens — not the crossing
point itself, and say which you did.

## When the bridge is what binds

A household stopping before pension access funds everything from non-pension
assets until it unlocks. The tells: failures cluster before access, a low
`bridge_before_access()` p10, and success climbing steeply with each month of
work. The bridge — not the portfolio — is then the constraint, and these are
the levers. Effects are from one engagement with a four-year bridge, worst of
three rules, at the earliest date notice allowed; treat them as calibration for
which lever to reach for first, not as figures to quote.

| Lever | How | Effect, in points of success |
|---|---|---|
| Defer discretionary spending to access | `Expense(phase=RETIREMENT, start=access_date)` | +23.8 for two items, +25.5 for all: bought a full year earlier |
| De-risk the bridge's growth assets, re-risk at access | `ByAssetTypeMix`, or an `AllocationStrategy` targeting one wrapper | +1, or +8 against a crash — but **−16 at the earliest date** |
| Redirect contributions from pension to ISA | `Contribution(employee_monthly=0)` | −0.2: relief beats liquidity unless the bridge runs dry |
| Sell fixed income into the tracker | replace the asset's `returns` | −1.8 success, +£1.3m estate |

- **Deferral is the large lever, and it is a spending decision, not an
  investment one.** Nothing done to the asset mix moved more than a point or
  two. Quote the worst-5% spend beside it: a pre-committed cut consumes the
  headroom an adjusting rule needs, so the bad tail lands on the essential floor
  with nothing left to flex. That trade — a certainty of planned cuts instead of
  a risk of forced ones — is the client's to make, and belongs in the report.
- **Protection has to be in place before they stop.** The crash variant lands in
  the run-up to retirement, which is where sequence risk peaks, so an allocation
  change dated from the retirement date answers a question nobody asked.
- **Never de-risk a bridge permanently, and never assume the sign.** After
  access, recycled pension money makes the same accounts long-horizon money
  again. The de-risking worth a point at the recommended date cost 16 at a date
  twelve months earlier, where the bridge must grow through a larger draw rather
  than merely survive it. Run it at every date under consideration.
- `PostAccessStepUp` expresses "lean now, more later" as a withdrawal rule
  rather than an expense edit. Test both; they are not equivalent.
- Debts are fixed schedules — `Debt.interest_rate` is recorded for the report
  and never used — so clearing one early is pure cost here and cannot be tested.
  Say that rather than reporting the loss as a finding.

## Screen first, then choose what to run

`diagnose(compile_plan(...))` reports, from the schedule alone and with no
simulation, everything that decides which rules are worth testing:

```python
d = diagnose(compile_plan(household, base_scenario, UK, as_of))
d.bridge_years, d.bridge_coverage, d.essential_bridge_coverage, d.initial_draw_rate
```

**C** = accessible money ÷ what the bridge must draw. **E** = the same against
essential spending. Both zero-return, so they are the pessimistic reading; a
60/40 mix over seven years multiplies them by roughly 1.3.

**Read E first — it is a ceiling, not a preference.** Best success achievable
by *any* rule, measured over a 105-run grid (REVIEW.md 1.19):

| E | Ceiling | What to do |
|---|---|---|
| < 0.8 | **2.6%** | Stop. No spending rule fixes this. Test the retirement date, deferred spending, or moving money into a reachable wrapper. |
| 0.8–1.0 | ~43% | Rules matter but cannot rescue it. Say so in the report before quoting any probability. |
| 1.0–1.2 | ~70% | Worth the full comparison. |
| ≥ 1.2 | 89–97% | The bridge is not the binding constraint. |

**Then C, for whether a bridge rule is worth a run:**

| C | `BridgeGuardrail` gain | Test it? |
|---|---|---|
| < 0.6 | +7.3 | Only after checking E — usually beyond rescue |
| 0.6–0.8 | **+31.4** | Yes, at `floor=0.5` and `floor=0` |
| 0.8–1.0 | +12.9 | Yes |
| 1.0–1.2 | +2.9 | Marginal; only if E is also near 1 |
| ≥ 1.2, or `bridge_years == 0` | **+0.0** | No — inert to within 0.1 points in every cell |

- **Screen, don't decide.** These bands pick which candidates get a run. The
  winner is still whatever the simulation says for the household in front of
  you — quote measured numbers, never the band.
- **The grid varies accessible share and spending only** — always a 7-year
  bridge, 60% equity, one person. Treat the bands as ratios that should
  travel, not as facts that have been checked at other shapes.

## Choosing a withdrawal rule

Measured in REVIEW.md 1.18 (`tools/compare_withdrawal_rules.py`): three
households, same £800,000 and £40,000/yr, differing only in how much is
reachable before pension access. Points are against `SpendNominal`.

| Rule | Wide bridge | Thin bridge | No bridge | Reach for it when |
|---|---|---|---|---|
| `SpendNominal` | 47.9% | 6.3% | 79.3% | always, as the honest baseline |
| `BridgeGuardrail` → inner rule | +13.8 | **+27.1** | 0.0 | a bridge binds — the only rule that reads it |
| `GuytonKlinger` | +10.7 | **+0.2** | +7.7 | no bridge, and the client will accept cuts |
| `PercentOfPortfolio` | +30.6 | **−3.3** | +14.9 | never for a bridge; good after access |
| `EndowmentSmoothing` (Yale) | +48.1 | +23.1 | +20.2 | stability matters more than the plan's level |
| `VanguardDynamicSpending` | +38.6 | +29.2 | +17.3 | as above, when a hard cap on cuts is wanted |
| `Ratchet` (Kitces) | +2.4 | +1.5 | +0.2 | capturing upside without ever cutting |
| `VPW` | −7.7 | −6.3 | −34.5 | only at a defensible assumed return; 0% (= 1/N) is far safer |

- **A whole-portfolio rule cannot see a bridge.** Across the grid it gains
  +27.3 points where there is *no* bridge problem and **+0.4** where the bridge
  is tightest — the opposite of a protection profile. It rations early because
  4% of the *total* is below the plan, which helps everywhere and is luck
  rather than protection. Sharpest cell: £34,000 spending against £160,000
  accessible — baseline 11.8%, `BridgeGuardrail` 56.1%, `PercentOfPortfolio`
  **2.0%**, Yale **1.9%**. Both worse than doing nothing, exactly where reading
  the constraint matters most.
- **`GuytonKlinger` will not cut during a failing bridge** — its denominator
  includes the locked pension. Compose it: `BridgeGuardrail(after=GuytonKlinger())`.
- **Read the spend columns.** Vanguard scored 35.5% on the thin bridge with a
  *median* spend of £26,000 — the essential floor, permanently — and a median
  bequest larger than the starting portfolio. Success bought by starvation.
- **"A percentage rule cannot run out" is false here.** Every one has a `floor`,
  and the floor is what reintroduces failure. Say so rather than quoting the
  textbook claim.
- **The largest single lever is how far the client will cut**, not which rule.
  `BridgeGuardrail` gained 10.6 further points on the thin bridge by moving
  `floor` from 0.5 to 0 (essentials only). That is the client's decision and
  belongs in the report as one.

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

**The refill rule was never the problem.** `BridgeLadder` is the strongest form
of the counter-argument — sized to the actual bridge liability, shrinking a year
every year, *never* refilled — and it still cost 9.8 points against holding no
reserve at all, funded none of the six worst starts, and delayed the earliest
failure by not one year (REVIEW.md 1.18). A reserve moves money from a
60%-equity mix into a 1% real asset for years; where the bridge binds, that
growth is exactly what was needed. Offer `BridgeLadder` when a household wants
the certainty and price it as the ~10-point cost it is, not as a safeguard.

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
