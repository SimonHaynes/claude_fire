---
name: build-retirement-report
description: Write and render the eight-section client PDF — position, scenarios, results, detailed analysis of the recommended scenario, recommendations, structuring, timeline, notes — from retireplan simulation results. Covers what to explain, how to reason, and how to handle speculative advice. Use as the final step after simulations have been run and checked.
---

# Build retirement report

```bash
.venv/bin/python3 -m workspace.<name>.build_report [out.pdf]
```

`workspace/<name>/build_report.py` builds a context dict; the reusable parts —
charts, template, rendering — live in `retireplan.reporting`.

The reader is an intelligent non-specialist deciding when to stop working.
They need to understand what happens, why it is being recommended, and what
would change their mind. A report that gives a number without a mechanism has
not done its job.

---

## Non-negotiables

**Every figure comes from a `SimulationResult`.** Interpolate; never type a
number into prose. A hardcoded figure is right once and then quietly wrong.

**Quote net, not gross.** `net_bequest_percentiles`, never
`bequest_percentiles`, in anything the client reads — `uk-pension-tax-strategy`
explains why the gap is so large. `reporting.check_report()` enforces this at
render time; do not work around it.

**Say what is not modelled.** Especially where the omission flatters the plan.
Load `challenge-the-model` and name the limitations that bear on *this*
household, not a generic list.

**Percentages are floored, not rounded** — 94.96% is "94.9%", never "95.0%",
so prose can never disagree with the dial beside it.

---

## Explaining a scenario: mechanics, not labels

"Retire September 2028 with a fixed-floor guardrail" tells the reader nothing.
Every scenario needs its **operating instructions** — what actually happens,
in order, in pounds. The block below is written in markdown because that is
readable *in this skill file* — see the warning right after it before you
write the equivalent prose into `build_report.py`.

> What this looks like in practice
>
> You stop working on 1 September 2028. From then until January 2031 the
> pensions are legally locked, so the ISAs fund everything: about £53,200 a
> year, drawn first from the cash reserve and then from the Vanguard tracker.
> That takes roughly £150,000 out of the ISAs over the bridge, leaving about
> £155,000 in them when Simon turns 57.
>
> From January 2031, Simon's pension unlocks. Each year you draw from it up to
> the top of the basic-rate band — around £50,270 of taxable income — pay 20%
> on it, and take anything further from the ISAs so you never pay 40%. Any
> surplus beyond spending goes back into an ISA, up to £20,000 each per year.
>
> If markets fall, discretionary spending is cut first — never essentials —
> by up to 40%, taking total spending from £53,200 to £44,400 until markets
> recover. In the worst 5% of simulated outcomes, that is where you end up.

**The template has no markdown filter and autoescapes.** `**bold**` or
`*emphasis*` typed into a context-dict string renders as literal asterisks in
the PDF, not bold text — this has happened on a first draft before. If a
phrase genuinely needs emphasis in the rendered report, use a real HTML tag
(`<strong>…</strong>`) in a field the template marks `|safe`, or restructure
with a heading/list instead. Otherwise write plain text.

Rules of thumb:

- Give the **order of operations**, not just the components.
- Give **numbers** — "about £150,000 over the bridge", not "a portion".
- State the **trigger and response** for every conditional rule: *if this
  happens, do that, until this*.
- Name the **actual accounts**, not asset classes.
- Say what the household would **notice** — spending, not portfolio mechanics.

**Give the spending rule as a rules table, not as prose.** "A guardrail cuts
spending by up to 40% in a downturn" is four different plans depending on what
the reader assumes. Build `section2.spending_rules` — an if-this/then-this
table a reader can scan — covering, in the order the model evaluates them:

- the normal year, in pounds, split essential and discretionary;
- any time-limited addition (a holiday budget that stops at an age);
- what happens when the full amount **is** affordable;
- what triggers a cut, what may be cut, and how deep;
- the floor, and **what happens below it**;
- what restores full spending.

Prose around it should be short. The table is the explanation.

**Then say what the rule does not do.** This is where a reader is most often
misled, and the class names actively encourage it:

- **Check any cut-and-recover rule actually recovers for *this* household**
  before describing the recovery. A `FixedFloorGuardrail` was removed from the
  engine for failing exactly this: it cut only once the accounts could not
  cover the year, so the pots were already empty and there was nothing to
  recover from — 74 cuts and **zero** recoveries across 2,000 trials, while
  the report described the recovery mechanism in detail. Describing code that
  never executes is how a report ends up promising a safeguard that is not
  there. A **bridge** is the exception worth remembering: a locked pension
  unlocking really does refill the accounts.
- `GuytonKlinger` **is** an early-warning rule: it watches the withdrawal rate
  against the rate set in year one, trims ~10% when that drifts a fifth above,
  and raises it on the same test in good years. On the same bad path it cut
  nine years before failing, and failed a year later than the fixed floor.
- Neither watches "the market". Nothing in either rule keys off an index
  level, an all-time high, or a drawdown percentage — a common and reasonable
  reader assumption that is simply wrong.

Read the class before describing it, then measure two things that are not in
any results table and that decide whether a spending rule is worth having:

- **Years of warning** — trace a deliberately bad `project_once` path and take
  the gap between the first cut and the first failure.
- **Recovery rate** — across the trials, how often does a cut is followed by a
  return to full spending? A rule that cuts and never recovers is a step down,
  not a guardrail, and the client should be told which one they have.

**Every scenario must state its draw order as an explicit, named fact, not
something left for the reader to infer from a strategy class in a table.**
One sentence, near the top of the scenario's mechanics: which wrapper is
spent first, second, and last, and — since April 2027 moved most households
from "pensions last" to "pensions first" (see `uk-pension-tax-strategy`) —
say which rule this plan follows and why, even when the answer is the
old rule. "Pension first, up to £50,270 of taxable income each person each
year, ISA for the rest, surplus recycled back into the ISA" is a draw order a
client can act on; "tax-efficient drawdown" is a label.

Read the strategy docstrings in `retireplan/strategies/` for what each rule
actually does. `withdrawal.py`'s module docstring explains the two families of
spending rule and the trade between them.

---

## Recommendations: reasoning, not verdicts

Each recommendation carries four things:

1. **What to do**, specifically enough to act on.
2. **The number that justifies it**, from a result.
3. **Why that follows** — the mechanism, in one or two sentences.
4. **What would change it** — the condition under which this advice is wrong.

The third is what most reports skip and what makes advice trustworthy. "Retire
in September 2028" is an instruction; "September rather than August because
the mortgage and the last of the university support are still running until
then, which is why August scores 95.4% and September 97.6%" is a reason.

Prefer the counter-intuitive finding when the model supports it, and explain
the mechanism rather than softening it. Examples this engine has produced:

- De-risking a short bridge makes it *worse*, because the money needs to grow
  through the bridge, not merely survive it.
- Good tax strategy produces a *smaller* estate and a *larger* inheritance,
  because tax gets paid earlier at a lower rate.

**Where two reasonable models disagree, report the disagreement.** That gap is
the honest uncertainty and hiding it is the most damaging thing available.

---

## Speculative actions

Proactive suggestions are valuable and expected — gifting, spending more,
buying the holiday home, helping the children early. They are also where a
report can most easily mislead, so they carry extra obligations:

**Model it, do not assert it.** `Scenario.gifts`, `one_off_spends` and the
withdrawal rules exist so a suggestion can be costed. An unmodelled suggestion
must be labelled as such.

**Label it clearly** as a possibility being tested, not a recommendation
already made.

**State the assumption the answer depends on**, especially where the answer
flips. Gifting is the sharp example — the comparison inverts depending on
whether the gift is valued as spent on receipt or invested. Report both
numbers and name the `gift_growth_rate` behind each; `uk-pension-tax-strategy`
has the reasoning.

**Check it does not endanger the plan.** A suggestion that improves the
inheritance while dropping success from 98% to 39% is not a suggestion, it is
a trap. Always quote the success probability alongside.

**Say when the real lever is outside the model.** Some of the largest ones
are — the timing of death relative to gifts, care costs, first death. Name
them and refer them onward rather than implying the model settled them.

---

## Assumptions

A dedicated section, in the client's language, not the model's. For each:
what was assumed, why, and **which way it cuts**. Readers can judge an
assumption they can see; they cannot judge one they cannot.

Every default taken from `standard-assumptions` appears here with its source
and the direction it errs — that table is the raw material for this section,
not a substitute for it: translate it into the client's terms.

Cover at minimum:

- Where a figure was **inferred rather than stated** by the client.
- Return and inflation assumptions, and the **sampling window** used.
- The **tax year** modelled, and that rules will change over a 40-year plan.
- Anything **quoted as a headline rate** and how it was treated — a nominal
  yield is not a real return.
- **What is not modelled**, flagged where it flatters the plan.
- **How long the plan assumes people live**, since bequest figures are
  conditional on it.

Draw these from the household module's docstring, which is the audit trail
intake was supposed to leave.

---

## Writing

- Short sentences. One idea each.
- Second person: "you stop working", not "the household ceases employment".
- Lead with the conclusion, then support it.
- Concrete over abstract: "£44,400 a year" beats "a reduced level of spending".
- No hedging stacks — "may potentially be able to" says nothing. If it is
  uncertain, give the probability.
- No jargon without a plain-English gloss on first use: sequence-of-returns
  risk, nil-rate band, PCLS, drawdown all need one.
- Never imply certainty a Monte Carlo cannot provide.

---

## Sections

Eight sections. Sections 3 and 4 are deliberately separate: 3 compares every
scenario on the same few numbers, 4 goes deep on the one being recommended.
Mixing them produces a results section nobody can scan.

1. **Current position** — household, income, debts, assets, goals, restated so
   the client can check the model understood them.
2. **Scenarios tested** — what each is, why it was chosen, and its operating
   instructions (above). Include how spending is composed and what the
   guardrail does.
**Success probability means different things for different rules, and the
results table puts them in one column.** A needs-based rule fails when the
money runs out. An adjusting rule (`GuytonKlinger`, `PercentOfPortfolio`,
`VariablePercentage`) mostly does not fail at all — it cuts spending instead —
so a high figure is a statement about flexibility, not safety, and 100% is
reachable honestly. Whenever a scenario uses an adjusting rule, say in the
section intro that its success figure should be read alongside the worst-case
spend, and never let a 100% stand alone.

3. **Results** — the cross-scenario comparison, and nothing else.
   `section3.rows`, one row per scenario: success dial, median spend,
   worst-case 5% spend, and the **net bequest range, 10th to 90th percentile**,
   from `net_bequest_percentiles`. A single median bequest implies a precision
   the model does not have; the range is the honest figure and is what the
   client asked for. Keep this section short enough to read at a glance — it is
   the table someone flips back to.
4. **Detailed analysis of the recommended scenario** — everything that only
   makes sense for one scenario at a time. All keys live under `section4`.

   **The bridge table** (`section4.bridge_rows`, rendered under "assets
   outside a pension remaining when it becomes accessible") — the 10th, 50th
   and 90th percentile of everything outside a pension (cash, ISA, GIA) in the
   plan-year *before* pension access begins, from
   `result.bridge_before_access()` (10th/90th) or
   `result.bridge_at(result.pension_access_year - 1, p)` for the median.

   **Use `bridge_before_access()`, never `bridge_at_access()`** — see
   `run-scenario-simulation`, which owns that explanation. Do not populate it
   from `isa_percentiles`/`isa_at()` either: a GIA can carry part of the
   bridge, and ISA alone understates it.

   This table answers something the success probability cannot — a plan can
   look comfortable on average and still carry a real chance the bridge ran
   dry. **Do not describe a failing scenario as running dry "and never
   recovering" without checking**: a single bad year fails the whole-horizon
   test, but the asset picture can recover once the pension unlocks the next
   year. Those are different claims and only one is usually true. Report the
   *severity* of failure (how many bad years, how large the worst one, via
   `median_shortfall_year` and a look at individual failing trials). Skip the
   table for a scenario with no DC pension to unlock, or where it is
   accessible from day one (`bridge_before_access()` returns `None`).

   **The wealth fan chart** (`section4.fanchart_svg`, from
   `retireplan.reporting.fan_chart_svg`) — 5th/10th/median/90th/95th
   percentile bands, the same five the results table and the asset-mix table
   use. **Do not pass `horizon_years` to shorten it** unless you have a
   specific reason and are not quoting a bequest figure anywhere near it: the
   chart defaults to the full horizon precisely so its end lands on the same
   year the bequest figures are read from. A report showing a 25-year chart
   next to a 45-year bequest number is showing two different plans and asking
   the reader not to notice — this happened in a real report and is exactly
   what the default is for. The genuine readability cost (a large bequest tail
   compresses the early, more decision-relevant years toward the bottom of a
   linear axis) does not go away — say so in the caption if it is bad enough
   to name, rather than quietly cropping the chart to hide it.

   **The per-asset-type fan charts** (`section4.asset_fan_charts`, a list of
   `{title, svg}` blocks the template stacks vertically under
   `section4.asset_fan_charts_title`/`_caption`) — the same 5/10/50/90/95 fan
   chart, once per asset type, from
   `fan_chart_svg(result.year_labels(), result.asset_type_percentiles[t],
   label=<plain English type name>)`, same full-horizon default as above.
   Give each its own y-scale (call `fan_chart_svg` once per type; do not force
   a Pension in the tens of millions and a flat £750k Property onto one shared
   axis — that is the dual/shared-scale mistake the `dataviz` skill's "one
   axis" rule warns about, applied within a group of small multiples). **Skip
   any asset type that is zero at every percentile for the entire horizon** —
   a flat line at zero answers nothing and spends report space; say in the
   caption that it was omitted and why, do not silently drop it.

   **The asset-mix table** (`section4.asset_mix`, rendered per block under a
   `title`/`caption`) — one row per asset type present plus a **Total** row,
   columns **5th / 10th / median / 90th / 95th** percentile, from
   `result.asset_type_percentiles`, read at the final plan year: the same
   reference point the bequest figures and the fan charts use, so this table
   answers "what is that estate actually made of." Label rows in plain English
   ("Pension", "ISA", "GIA", "Cash", "Property"), not raw `AssetType.value`
   strings. **The Total row must come from `result.wealth_percentiles`, not a
   sum of the type rows**: percentiles taken independently per type do not add
   up to the percentile of the total, because the trial at the median for one
   type is not usually the trial at the median for another —
   `asset_type_percentiles`'s own docstring explains why. Summing the rows
   yourself produces a Total that silently disagrees with the bequest figures.

   If the report has room, repeat the charts for the other headline scenarios.
   The recommended one is the minimum.
5. **Recommendations** — the four-part structure above, including speculative
   options clearly labelled.
6. **Structuring and estate protection** — how the money is *held* and who it
   passes to, rather than what it earns. Load `legal-and-trust-structuring`
   before writing this.

   The list key is `section6.structures`, **not `items`** — Jinja resolves
   `section6.items` to the dict's built-in `.items` method and silently
   iterates that instead, which fails at render time with an unhelpful
   `'builtin_function_or_method' object is not iterable`. Avoid `items`,
   `keys` and `values` as context keys anywhere.

   Each entry carries a tag saying whether the engine costed it or not, and
   that distinction is the whole point of the section:

   - **Modelled** — gifting, an immediate needs annuity, the draw order, the
     nil-rate bands. Quote the number and the scenario it came from.
   - **Not modelled** — will trusts, severing a joint tenancy, powers of
     attorney, deprivation-of-assets risk. Explain the mechanism and what is
     at stake, then refer to a STEP solicitor. **Never quote a figure for
     these**, and never imply the model tested them.

   Lead with the structural point, not the vehicle: "everything passing
   outright to the survivor doubles what a later care assessment looks at" is
   actionable; "consider an IPDI" is a word. Care is the natural hook here,
   because the means test is assessed per person and disregards the home while
   a spouse still lives in it — which is exactly why *who* owns what matters.

   **Do not present any structure as a way to avoid care fees.** Deprivation
   of assets has no time limit and turns on intention. Present a structure as
   an ownership and succession decision, note the side effect, and let the
   solicitor take the view.

   Close with the cheap checks that are usually wrong and cost nothing: the
   pension death-benefit nomination, whether the will post-dates the last
   major life event, how the property is held, and whether lasting powers of
   attorney exist — an LPA cannot be created once it is needed.
7. **Steps and timeline** — dated actions from the client's real accounts.
8. **Notes and assumptions** — as above, plus the disclaimer.

## The dial

Semicircular gauge, status-palette bands: red `[0, 90%)`, amber `[90%, 95%)`,
green `[95%, 100%]`, triangle pointer, percentage in primary ink (never
coloured by the band). Load the `dataviz` skill before touching chart code. A
text key for the thresholds is required, not optional — amber and red do not
clear 3:1 contrast on a light surface, so colour alone cannot carry meaning.

## Typography

The look is deliberate and settled — Fraunces for headings, Public Sans for
text, a muted ink-and-slate palette, generous white space. **Do not restyle
it.** What follows is what keeps it looking considered rather than merely
plain:

- **Prose is justified and hyphenated.** The two go together: justification
  without hyphenation opens rivers of white space down a narrow measure.
  WeasyPrint hyphenates through Pyphen and needs `lang` on `<html>`, which is
  set. Both are already in the template.
- **Justify running prose only.** A narrow table cell or a two-word timeline
  entry justifies into gaps — those stay ragged-right. The selector list in
  the template is explicit for that reason; extend it deliberately rather than
  moving the rule onto a wildcard.
- **`orphans: 2; widows: 2`** on paragraphs and list items, so a single line
  never strands across a page break.
- **Let content breathe.** A section that fills every page edge to edge reads
  as dense rather than thorough. Card padding and chart margins are tuned;
  leave them.
- **One idea per block.** A wall of text in a scenario card is harder to fix
  with styling than by splitting the prose.

## Rendering

WeasyPrint, not a headless browser. Consequences to design around:

- SVG shapes do **not** reliably inherit page CSS — set fill/stroke inline.
- Give every SVG explicit `width`/`height`, not just a `viewBox`.
- Use `break-inside: avoid` on cards, tables and charts.
- Autoescape is on, so inside a CSS `content:` string use `|safe`.
- **Pass `client_name` (and anything else that hits both the title and a
  `|safe` footer) as plain text — `"Pat & Robin Smith"`, never a
  pre-escaped entity like `"Pat &amp; Robin Smith"`.** The title is
  autoescaped and the footer is marked `|safe`; feed either of them an
  already-escaped string and one of the two renders wrong (`&amp;` printed
  literally, or double-escaped to `&amp;amp;`). This has shipped once — see
  REVIEW.md's bug table — and was nearly repeated on the next report build.

**Always render to PNG and read the pages before calling it done.** Orphaned
lines, split charts and overflow are invisible in the HTML:

```python
import fitz
doc = fitz.open("workspace/<name>/report.pdf")
for i in range(doc.page_count):
    doc[i].get_pixmap(dpi=105).save(f"/tmp/p{i+1}.png")
```

If the target PDF is locked (open in a viewer), render to a new filename.
