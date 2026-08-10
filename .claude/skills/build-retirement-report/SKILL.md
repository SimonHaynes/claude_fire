---
name: build-retirement-report
description: Write and render the eight-section client PDF — position, scenarios, results, detailed analysis of the recommended scenario, recommendations, structuring, timeline, notes — from retireplan simulation results. Covers what to explain, how to reason, and how to handle speculative advice. Use as the final step after simulations have been run and checked.
---

# Build retirement report

```bash
.venv/bin/python3 -m workspace.<name>.build_report [out.pdf]
```

`workspace/<name>/build_report.py` builds a context dict; charts, template and
rendering live in `retireplan.reporting`.

The reader is an intelligent non-specialist deciding when to stop working. A
number without a mechanism has not done the job.

## Non-negotiables

- **Every figure comes from a `SimulationResult`.** Interpolate; never type a
  number into prose.
- **Every derived figure — a change, a difference, a rate — is computed in
  Python**, never worked out by hand while writing.
- **A "typical year" figure comes from the household's expenses, not from a
  projection's maximum or median.** The largest projected year picks up whatever
  time-limited items overlap — university support, the first five years of
  holidays — and describes a year that happens five times out of forty. Sum the
  expenses that have no `end` and no `years_from_retirement`, and give the
  time-limited ones their own row.
- **Say which calendar date a plan-year label means.** `pension_access_year` is
  the plan year *containing* the birthday, and plan years start on `as_of`'s
  month — so a 57th birthday in March 2032 reports as 2031. Quote the
  birthday to the client and the plan year only where the table needs it;
  printing both unexplained reads as a contradiction.
- **Quote net, not gross**: `net_bequest_percentiles`, never
  `bequest_percentiles`. `reporting.check_report()` enforces this; do not work
  around it. `uk-pension-tax-strategy` explains the size of the gap.
- **Say what is not modelled**, especially where the omission flatters the
  plan. Load `challenge-the-model` and name the limits bearing on *this*
  household.
- **Percentages are floored, not rounded** — 94.96% is "94.9%", so prose can
  never disagree with the dial beside it.

## Explaining a scenario: mechanics, not labels

"Retire September 2028 with a fixed-floor guardrail" tells the reader nothing.
Each scenario needs operating instructions — what happens, in order, in pounds:

> You stop working on 1 September 2028. From then until March 2032 the
> pensions are locked, so the ISAs fund everything: about £52,000 a year, drawn
> first from the cash reserve and then from the Vanguard tracker. That takes
> roughly £180,000 out of the ISAs, leaving about £138,000 when Ada turns 57.
>
> From March 2032 Ada's pension unlocks. Each year you draw from it up to
> the top of the basic-rate band — around £50,270 of taxable income — pay 20%,
> and take the rest from the ISAs so you never pay 40%. Surplus goes back into
> an ISA, up to £20,000 each per year.
>
> If markets fall, discretionary spending is cut first — never essentials — by
> up to 40%, taking spending from £52,000 to £43,000 until markets recover. In
> the worst 5% of outcomes, that is where you end up.

**No markup of any kind in a context string.** The template autoescapes, has no
markdown filter, and the only `|safe` fields are the SVGs — so `**bold**`
renders as asterisks and `<strong>` renders as a visible tag. Both have shipped.
For emphasis, restructure: a heading, a list, an em dash, or a separate
paragraph. Grep the built module for `<` before rendering.

Rules of thumb:

- Order of operations, not just components.
- Numbers — "about £180,000 over the bridge", not "a portion".
- Trigger and response for every conditional: *if this, do that, until this*.
- Real account names, not asset classes.
- What the household would notice — spending, not portfolio mechanics.

**Give the spending rule as an if-this/then-this table** (`section2.spending_rules`),
in the order the model evaluates: the normal year split essential/discretionary;
any time-limited addition; what happens when the full amount is affordable; what
triggers a cut, what may be cut, how deep; the floor and what happens below it;
what restores full spending. Prose around it stays short — the table is the
explanation.

**Then say what the rule does not do**, where readers are most often misled:

- **Check any cut-and-recover rule actually recovers for this household**
  before describing recovery. `FixedFloorGuardrail` was removed for failing
  this: 74 cuts and zero recoveries across 2,000 trials, while the report
  described the recovery mechanism in detail. A bridge is the honest exception
  — an unlocking pension really does refill the accounts.
- `GuytonKlinger` **is** an early-warning rule: it watches the withdrawal rate
  against year one's, trims ~10% when that drifts a fifth above, and raises it
  on the same test in good years. On one bad path it cut nine years before
  failing, and failed a year later than the fixed floor.
- Neither watches "the market". Nothing keys off an index level, an all-time
  high or a drawdown percentage — a reasonable reader assumption that is wrong.

Read the class, then measure the two things no results table holds:

- **Years of warning** — trace a deliberately bad `project_once` path; take the
  gap between first cut and first failure.
- **Recovery rate** — how often a cut is followed by a return to full spending.
  A rule that cuts and never recovers is a step down, not a guardrail.

**State the draw order as an explicit named fact**, one sentence near the top of
each scenario's mechanics: which wrapper is spent first, second, last, and why
this plan follows the pre- or post-April-2027 rule (see
`uk-pension-tax-strategy`). "Pension first, up to £50,270 of taxable income
each per year, ISA for the rest, surplus recycled into the ISA" is actionable;
"tax-efficient drawdown" is a label.

Strategy docstrings in `retireplan/strategies/` say what each rule does;
`withdrawal.py`'s module docstring covers the two families and the trade.

## Recommendations: reasoning, not verdicts

Each carries four things:

1. **What to do**, specifically enough to act on.
2. **The number that justifies it**, from a result.
3. **Why that follows** — the mechanism, in a sentence or two.
4. **What would change it** — the condition under which the advice is wrong.

The third is what most reports skip. "Retire in September 2028" is an
instruction; "September rather than August because the mortgage and the last
university support run until then, which is why August scores 95.4% and
September 97.6%" is a reason.

Prefer the counter-intuitive finding when the model supports it, and explain the
mechanism rather than softening it — de-risking a short bridge makes it worse
(the money must grow through it, not merely survive it); good tax strategy
produces a smaller estate and a larger inheritance (tax paid earlier, lower).

**Where two reasonable models disagree, report the disagreement.**

## Speculative actions

Proactive suggestions — gifting, spending more, the holiday home, helping the
children early — are expected, and carry extra obligations:

- **Model it, do not assert it.** `Scenario.gifts`, `one_off_spends` and the
  withdrawal rules exist so a suggestion can be costed. Label anything
  unmodelled as such.
- **Label it** as a possibility tested, not a recommendation made.
- **State the assumption the answer depends on**, especially where it flips.
  Gifting inverts on whether the gift is spent on receipt or invested: report
  both numbers and name the `gift_growth_rate` behind each.
- **Check it does not endanger the plan.** Improving the inheritance while
  dropping success from 98% to 39% is a trap. Quote success probability
  alongside.
- **Say when the real lever is outside the model** — timing of death against
  gifts, care costs, first death. Refer them onward.

## Assumptions

A dedicated section in the client's language: what was assumed, why, and which
way it cuts. Every `standard-assumptions` default appears with its source and
direction of error, translated into the client's terms. Cover at minimum: any
figure inferred rather than stated; return and inflation assumptions and the
sampling window; the tax year modelled and that rules change over 40 years;
anything quoted as a headline rate and how it was treated (a nominal yield is
not a real return); what is not modelled, flagged where it flatters the plan;
how long people are assumed to live, since bequest figures are conditional on
it. The household module's docstring is the audit trail intake left.

## Writing

- Short sentences, one idea each. Second person: "you stop working".
- Lead with the conclusion, then support it.
- Concrete over abstract: "£43,000 a year", not "a reduced level of spending".
- No hedging stacks. If it is uncertain, give the probability.
- Gloss jargon on first use: sequence-of-returns risk, nil-rate band, PCLS,
  drawdown.
- Never imply certainty a Monte Carlo cannot provide.

## Sections

Eight. Sections 3 and 4 stay separate: 3 compares every scenario on the same few
numbers, 4 goes deep on the recommended one.

1. **Current position** — household, income, debts, assets, goals, restated so
   the client can check the model understood them.
2. **Scenarios tested** — what each is, why chosen, and its operating
   instructions (above), including spending composition and guardrail behaviour.
3. **Results** — the cross-scenario comparison and nothing else.
   `section3.rows`, one per scenario: success dial, median spend, worst-case 5%
   spend, and the **net bequest range, 10th to 90th percentile**. A single
   median bequest implies precision the model does not have. Keep it scannable.

   **Success probability means different things per rule, in one column.** A
   needs-based rule fails when the money runs out; an adjusting rule
   (`GuytonKlinger`, `PercentOfPortfolio`, `VariablePercentage`) mostly cuts
   spending instead, so a high figure states flexibility, not safety, and 100%
   is honestly reachable. Where a scenario uses an adjusting rule, say in the
   intro that its figure is read alongside worst-case spend. Never let a 100%
   stand alone.
4. **Detailed analysis of the recommended scenario** — keys under `section4`.

   **Bridge table** (`section4.bridge_rows`, "assets outside a pension
   remaining when it becomes accessible") — 10th/50th/90th percentile of
   everything outside a pension in the plan-year *before* access, from
   `result.bridge_before_access()` and
   `result.bridge_at(result.pension_access_year - 1, 50)`.
   **Never `bridge_at_access()`** (see `run-scenario-simulation`, which owns
   that explanation) and never `isa_percentiles`, which understates a bridge a
   GIA partly carries. Skip the table when `bridge_before_access()` is `None`.

   It answers what success probability cannot. **Do not describe a failing
   scenario as running dry "and never recovering" without checking**: one bad
   year fails the whole-horizon test, but the assets can recover when the
   pension unlocks. Report severity — how many bad years, how large the worst —
   via `median_shortfall_year` and individual failing trials.

   **Wealth fan chart** (`section4.fanchart_svg`, from
   `retireplan.reporting.fan_chart_svg`) — 5/10/50/90/95 bands, matching the
   results and asset-mix tables. **Do not pass `horizon_years`** unless no
   bequest figure appears near it: the full-horizon default makes the chart end
   on the year the bequest is read from, and a 25-year chart beside a 45-year
   bequest number shows two different plans. If the bequest tail compresses the
   early years badly, say so in the caption rather than cropping.

   **Per-asset-type fan charts** (`section4.asset_fan_charts`, a list of
   `{title, svg}` under `asset_fan_charts_title`/`_caption`) — same bands, one
   per type, from `fan_chart_svg(result.year_labels(),
   result.asset_type_percentiles[t], label=<plain English name>)`, same
   full-horizon default. Give each its own y-scale — forcing a Pension in the
   tens of millions and a flat £750k Property onto one axis is the shared-scale
   mistake `dataviz` warns about. **Skip any type flat at zero across the whole
   horizon**, and say in the caption that it was omitted and why.

   **Asset-mix table** (`section4.asset_mix`, per block under `title`/`caption`)
   — one row per type present plus **Total**, columns 5th/10th/median/90th/95th,
   from `result.asset_type_percentiles` at the final plan year, so it answers
   what the estate is made of. Plain-English row labels, not `AssetType.value`.
   **The Total row comes from `result.wealth_percentiles`, never a sum of the
   rows**: per-type percentiles do not add (see the field's docstring), and
   summing produces a Total that disagrees with the bequest figures.

   Repeat the charts for other headline scenarios if there is room.
5. **Recommendations** — the four-part structure, speculative options labelled.
6. **Structuring and estate protection** — how the money is held and who it
   passes to. Load `legal-and-trust-structuring` first.

   The list key is `section6.structures`, **not `items`**: Jinja resolves
   `.items` to the dict method and fails with
   `'builtin_function_or_method' object is not iterable`. Avoid `items`, `keys`
   and `values` as context keys anywhere.

   Tag each entry, which is the point of the section:

   - **Modelled** — gifting, an immediate needs annuity, the draw order, the
     nil-rate bands. Quote the number and the scenario it came from.
   - **Not modelled** — will trusts, severing a joint tenancy, powers of
     attorney, deprivation-of-assets risk. Explain the mechanism and what is at
     stake, then refer to a STEP solicitor. **Never quote a figure for these.**

   Lead with the structural point, not the vehicle: "everything passing
   outright to the survivor doubles what a later care assessment looks at"
   beats "consider an IPDI". Care is the natural hook, since the means test is
   per person and disregards the home while a spouse lives there.

   **Never present a structure as a way to avoid care fees** — deprivation of
   assets has no time limit and turns on intention. Present it as an ownership
   and succession decision, note the side effect, let the solicitor take the
   view.

   Close with the cheap checks that are usually wrong: pension death-benefit
   nomination, whether the will post-dates the last major life event, how the
   property is held, and whether LPAs exist — one cannot be created once needed.
7. **Steps and timeline** — dated actions from the client's real accounts.
   **Build it as `(date, text)` pairs and sort by date.** Entries get added
   through the engagement in the order they are thought of, and a timeline whose
   rows run 2027, 2029, 2027 is worse than none.
8. **Notes and assumptions** — as above, plus the disclaimer.

## The dial

Semicircular gauge, status-palette bands: red `[0, 90%)`, amber `[90%, 95%)`,
green `[95%, 100%]`, triangle pointer, percentage in primary ink (never coloured
by the band). Load `dataviz` before touching chart code. A text key for the
thresholds is required: amber and red do not clear 3:1 contrast on a light
surface, so colour alone cannot carry meaning.

## Typography

Settled and deliberate — Fraunces headings, Public Sans text, muted ink-and-slate
palette, generous white space. **Do not restyle it.** What keeps it considered:

- **Prose is justified and hyphenated** — justification without hyphenation
  opens rivers down a narrow measure. Both are already in the template, which
  sets the `lang` WeasyPrint's Pyphen hyphenation needs.
- **Justify running prose only.** Narrow table cells and short timeline entries
  stay ragged-right; extend the template's selector list deliberately rather
  than moving the rule onto a wildcard.
- **`orphans: 2; widows: 2`** on paragraphs and list items.
- **Let content breathe.** Card padding and chart margins are tuned; leave them.
- **One idea per block** — split the prose rather than styling around a wall.

## Rendering

WeasyPrint, not a headless browser:

- SVG shapes do not reliably inherit page CSS — set fill/stroke inline.
- Give every SVG explicit `width`/`height`, not just a `viewBox`.
- `break-inside: avoid` on cards, tables and charts.
- Autoescape is on, so inside a CSS `content:` string use `|safe`.
- **Pass `client_name` as plain text** — `"Pat & Robin Smith"`, never
  `"Pat &amp; Robin Smith"`. The title autoescapes and the footer is `|safe`,
  so a pre-escaped string renders wrong one way or the other. This has shipped
  once; see REVIEW.md's bug table.

**Always render to PNG and read the pages before calling it done.** Orphaned
lines, split charts and overflow are invisible in the HTML:

`pymupdf` is in the `report` extra. If the venv predates that, the system
Python usually has it — the step is not optional, so use whichever has it.

```python
import fitz
doc = fitz.open("workspace/<name>/report.pdf")
for i in range(doc.page_count):
    doc[i].get_pixmap(dpi=105).save(f"/tmp/p{i+1}.png")
```

Render to a new filename if the target PDF is locked open in a viewer.
