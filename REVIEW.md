# Critical review of the model, the skills, and the method

Written 6 August 2026, after adding IHT, PCLS and tax-aware drawdown.
Revised the same day, after closing items 1.1-1.5 and the skills section.

**Status of the priority list.** Items 1.1 (first death), 1.2 (stochastic
mortality), 1.3 (frozen thresholds), 1.4 (care costs) and 1.5 (gifting) are now
modelled — each is marked below with what shipped and what remains simplified.
Every one of them made plans *worse*, which is what the closing line of this
document predicted. The medium and low items are untouched.

**The headline number moved.** On the sample household, a plan that scored
95.6% under the old assumptions scores 93.5% with real mortality, and its
median net bequest fell 31% — the old figure was quoting a tail as a median.
Adding five years of care takes the same plan to 84%. Do not compare a
probability produced before this revision with one produced after it.

The purpose here is to be specific about what this engine gets wrong, in
priority order, so nobody mistakes a confident-looking probability for a
reliable one. Bugs found in passing are listed at the end.

Every item is graded by how much it could move a real decision:
**high** = could change the recommended retirement date or the advice;
**medium** = changes numbers, not conclusions; **low** = tidiness.

---

## 1. Blind spots, worst first

### 1.1 No first death — **high** — NOW MODELLED

The model runs both people to life expectancy and taxes the estate once. Real
couples do not die together, and the survivor's position is materially worse:

- **One personal allowance instead of two.** The survivor loses ~£12,570 of
  tax-free income a year, so the same spending costs more tax — for possibly
  fifteen or twenty years.
- **One State Pension instead of two.** Roughly £12,000 a year of income
  simply stops. It does not transfer.
- **The DB pension usually halves.** Teachers' Pension pays a survivor
  benefit, typically around 50%.
- Spending does *not* halve to match.

This is the single largest missing risk, and it cuts the opposite way to
almost everything else in the model: it makes plans worse, not better. A plan
scoring 97% might score meaningfully less with first death modelled. **Do not
present current success probabilities as if this were included.**

**Shipped.** Each person's death is modelled separately: the survivor loses
one personal allowance and one State Pension, keeps a configurable fraction of
the deceased's DB pension (default 50%), and inherits their pots — re-keyed to
the survivor's name, since income left under a dead person's name would keep
drawing on tax bands that no longer exist. Spending falls by category rather
than by half: essentials to 90%, discretionary to 75%. IHT settles on the
second death only.

*Still simplified:* gifts within seven years of the first death are attributed
to the second, which favours the household. With more than one survivor, the
inheritance goes to the eldest rather than being split.

### 1.2 Mortality is a fixed age, not a distribution — **high** — NOW MODELLED

Everyone dies at 95. That is conservative for *success* (funding 45 years is
harder than funding the ~25 a 52-year-old should expect) but wrong for
*bequest*, which is quoted as though the plan certainly runs that long. Real
planning uses joint life expectancy or stochastic mortality, and the "£19M
estate" figure is really "£19M conditional on both living to 95".

**Shipped.** `LifeTable` samples per trial from ONS national life tables
(England and Wales, 2022-2024), by sex and single year of age. `FixedAge`
remains the default so the change is opt-in and attributable. Every result
carries `alive_fraction` and `median_second_death_year`.

*Still simplified:* these are **period** rates, which assume 2022-2024
mortality lasts forever and so understate a living person's life expectancy by
roughly two to three years — a cohort table would be better. National averages
also understate an affluent household by two to four years; `age_rating`
exists for that and defaults to 0, i.e. no silent adjustment. The two deaths
are sampled independently, which is deliberate and argued in `mortality.py`.

### 1.3 Tax thresholds are assumed to rise with inflation — **high** — NOW MODELLED

The engine works in real terms, so holding thresholds constant implicitly
uprates them annually. In reality the personal allowance, the basic-rate
ceiling, the £100k taper, the nil-rate bands and the Lump Sum Allowance are
all **frozen in nominal terms** — the IHT bands to April 2031. Real fiscal
drag pulls more income into higher bands and more estate above the nil-rate
band every year.

This flatters every projection, and compounds over 45 years. The IHT numbers
are the worst affected: a £650,000 nil-rate band frozen while an estate grows
in real terms is a steadily shrinking shelter.

**Shipped.** `Assumptions.fiscal_drag` erodes frozen thresholds in real
terms, on two clocks: income tax and NI to the announced 2028 freeze end, IHT
bands to 2031, and the allowances with no uprating mechanism at all (Lump Sum
Allowance, ISA limit, CGT exempt amount, dividend allowance) indefinitely. The
State Pension is deliberately *not* dragged — it is triple-locked. Defaults to
`inflation=0.0`, i.e. off.

*Worth knowing:* the effect is smaller than this section implies, because the
announced freezes end. A household that expects them to be extended, as they
repeatedly have been, should move the freeze dates and re-run.

### 1.4 No care costs — **high** — NOW MODELLED

Late-life care is the largest single spending risk a retired household faces
and it is entirely absent. Residential care runs to £50,000–£70,000 a year and
can last years. The English cost cap has been repeatedly deferred.

Ironically this household could absorb it, but a plan that never mentions it
is not a complete plan. It also interacts with 1.1: care costs usually fall on
the survivor.

**Shipped, and since reworked.** `Scenario.care` now samples *whether* each
person needs residential care and for how long, per trial, from published
incidence (~1 in 4 aged 65, higher for women) and a right-skewed
length-of-stay distribution (mean ~2.5 years, median nearer 18 months). An
earlier version charged care deterministically; the objection to attaching a
probability was that no defensible calibration existed, which turned out to be
wrong — the planning figures are published, and quoting one scenario as though
it were the risk was the less honest option.

The means test is modelled **per person**, which is how the rule works and is
the reason ownership matters more than total wealth here: above £23,250 of
that person's own capital they self-fund; below it the local authority meets
the balance. **The home is disregarded while a spouse still lives there.**

The state is a floor. Nobody in England goes without essential care for lack
of money, so exhausting capital on care is not a plan failure — it is a
fallback, reported as `state_funded_care_probability` rather than folded into
the success rate. `ImmediateNeedsAnnuity` models capping the liability with a
single premium at the point of need.

Care remains **off by default and analysed separately**: it answers a
different question from the rest of the plan, and mixing them produces a
headline number that is neither.

*Not modelled, deliberately:* deprivation of assets, which has no time limit
and turns on intention — see the `legal-and-trust-structuring` skill for why
that belongs with a solicitor rather than in arithmetic.

### 1.5 Gifting is not modelled — **high for this household** — NOW MODELLED

For an estate far above the nil-rate bands, lifetime gifting moves more money
than any drawdown optimisation the engine performs. Outright gifts leave the
estate after seven years; there are annual exemptions and the "gifts from
surplus income" exemption. The stated goal is helping the children buy
houses — which is a gift, and the tax treatment of *when* it happens is worth
more than the tax-band tuning we do model.

**Shipped** (earlier). `Scenario.gifts` models dated gifts with the
seven-year taper and the nil-rate band consumed earliest-gift-first. Annual
exemptions and gifts from surplus income are still not modelled — refer those
onward rather than estimating them.

### 1.6 Cross-spouse tax optimisation is crude — **medium**

`TaxEfficientOrder` fills each person's band in dictionary order rather than
levelling income across the household. Two personal allowances and two
basic-rate bands are worth ~£125,000 a year of cheap income between them;
drawing predominantly from one person's pension wastes part of that. It also
ignores that the pensions are unevenly sized (Pat's is ten times Robin's),
which is itself a planning issue.

### 1.7 One tax system for 45 years — **medium**

We model a single snapshot of 2025/26 rules for four decades, having just
lived through a change (pensions into IHT) that inverted the standard advice.
The probability that the 2060s tax code resembles today's is approximately
zero. This is not fixable, but it should be stated: **the further out a number
is, the more it is about the rules than the markets.**

### 1.8 Sequence risk is tested, not searched — **medium**

`market_stress` tests a crash we choose. We do not search history for the
worst *actual* sequence a retiree could have retired into (1929, 1937, 1973,
2000). A "worst historical start" run would be more informative than an
invented −35%.

### 1.9 The bootstrap destroys long-horizon structure — **medium**

Five-year blocks preserve short-run autocorrelation but not mean reversion or
valuation effects over decades. Sampling equally from all history also ignores
that starting valuations predict long-run returns — retiring at a high CAPE
has historically been worse than average, and the model cannot see that.

### 1.10 Charges are understated — **low/medium**

Only explicit fund charges and one platform fee are modelled. No advice fees
(commonly 0.5–1%/yr, which over 45 years is enormous), no transaction costs,
no bid-offer spread, no CGT on rebalancing a GIA. Allocation strategies
rebalance frictionlessly every year.

### 1.11 `worst_case_5pct_min_spend` is an awkward statistic — **low**

It is the 5th percentile *across trials* of each trial's single leanest year.
That mixes two different questions — how bad does it get, and how often —
into one number. "Years spent below £X" or "worst decade average" would tell
a household more about what a bad outcome feels like.

### 1.12 `GuytonKlinger`'s anchor makes success non-monotonic in the retirement date — **high**

Found on a real engagement, 7 August 2026, and the reason a recommended date
was nearly chosen on a six-point illusion.

`GuytonKlinger` sets `initial_rate` in **the first year of retirement** and
compares every later year against it. Where retirement begins with a *bridge*
— years funded entirely from ISAs because no pension is accessible yet — that
first-year draw rate is abnormally high, so the anchor is set high, so the
capital-preservation rule never fires and the prosperity rule fires instead.

The result is that success is **not monotonic in the retirement date**.
Sweeping one person's retirement quarterly across a household with a
2027-2031 bridge:

    Partner retires GuytonKlinger   SpendNominal   PostAccessStepUp
    2029-04-01          97.7%           92.8%           93.0%
    2029-07-01          97.9%           94.0%           93.6%
    2029-10-01          90.9%           94.5%           93.9%    <- GK drops 7 points
    2030-04-01          91.8%           94.9%           94.5%
    2030-10-01          97.8%           95.4%           94.8%

Under every other withdrawal rule, working longer improves the plan
monotonically, as it must. Only the GK column has a hole in it, and the hole
lines up exactly with the median spend: where GK scores ~91% its median spend
is the full unreduced £64,200, i.e. **the guardrail never engaged at all**.

This is Guyton-Klinger behaving as specified rather than an implementation
fault, but it means a date can score six points better than its neighbour for
reasons that have nothing to do with the household's finances. **Never
recommend a date on a single withdrawal rule's number.** Sweep across at least
`GuytonKlinger`, `SpendNominal` and `PostAccessStepUp` and recommend on the
worst of the three, which does slope smoothly.

Worth fixing properly: anchoring `initial_rate` on the first year *after*
pension access, or on a portfolio-relative target rather than the realised
first-year rate, would remove the artifact. Until then this is a trap for
exactly the households the engine is most used on.

### 1.13 Corporate credit model limits — **low/medium**

Better than it was, but: default rates are calibrated to *US* speculative-grade
history applied to sterling holdings; recovery is a flat assumption rather
than issuer-specific; and reinvestment risk is ignored — a ladder maturing in
a low-rate world reinvests at lower yields, which the fixed `nominal_yield`
does not capture.

### 1.14 No UFPLS — only PCLS + drawdown is modelled — **medium** — NOW MODELLED

`Scenario.take_pcls` used to be a single boolean: crystallise and take the
maximum tax-free lump sum, or don't. There was no way to model an
Uncrystallised Funds Pension Lump Sum — a withdrawal taken directly from the
uncrystallised pot, automatically split 25% tax-free / 75% taxable, with no
separate drawdown wrapper.

**Shipped.** `Scenario.pension_access: PensionAccess` (`NONE` / `PCLS` /
`UFPLS`) replaces the boolean. Under `UFPLS`, every withdrawal the drawdown
strategies make from an accessible DC pension is split 25% tax-free / 75%
taxable, capped by remaining Lump Sum Allowance headroom, solved exactly
(`RateSchedule.gross_for_net_partly_relieved` — closed-form band-walking,
not a search, cross-checked against 2,000+ random cases by bisection to
£1e-10). PCLS and UFPLS share one lifetime tax-free-cash counter per person,
so taking a PCLS lump sum reduces what UFPLS can still give tax-free, and
vice versa. Also added: `Scenario.pension_lump_sums`, a one-off dated
withdrawal (`PensionLumpSum`) — a partial crystallisation, for "I want
£50,000 of cash now" without touching the ongoing `pension_access` mode.

*Still not modelled:* the Money Purchase Annual Allowance itself — the
engine doesn't cap contributions after a taxable withdrawal, under any of
`NONE`, `PCLS` or `UFPLS`, so a household still contributing after triggering
it will overstate how much further relief they get. Both `TaxEfficientOrder`
and the account of when PCLS vs UFPLS wins in `uk-pension-tax-strategy` say
so, but nothing in the engine enforces it.

### 1.15 Cash-buffer and bucket drawdown strategies underperform — tested, not assumed — **high**

`CashBondLadder` and `ThreeBucketStrategy` both exist because "hold a cash
buffer so you never sell equities in a crash" is close to universal advice.
Stress-tested both against a same-average-allocation rebalanced portfolio
(one blended fund, no bucket mechanic) on a single retiree, £1m pot, £40k/yr
real spend, `StandardOrder`/`SpendNominal`, no state pension: the six classic
worst historical retirement starts (1929, 1937, 1966, 1973, 2000, 2007)
deterministically, and 2,000-trial historical block-bootstrap Monte Carlo.
**Both bucket strategies did worse, not better, than the rebalanced
comparison — and the more faithfully-implemented one did worse than the
cruder one:**

| Strategy | Monte Carlo success | Worst-decile (p10) ending wealth |
|---|---|---|
| `ThreeBucketStrategy` (2y cash + 5y bonds, the canonical Evensky/Benz form) | 84.5% | £0 |
| `CashBondLadder` (3y, single fixed-rate reserve) | 87.1% | £0 |
| All-equity, no buffer at all | 88.8% | £0 |
| Rebalanced, same average allocation, no bucket mechanic | **92.2%** | **£112,940** |

**Mechanism, traced through the 1973–1987 sequence:** both strategies refill
their reserve to its *full* target on every qualifying year, not just enough
to cover that year's actual need. In 1979, 1980 and 1982 — all *positive*
equity years — the equity sleeve craters anyway, because a full refill pulls
far more out than the year required. `ThreeBucketStrategy` is worse because
its reserve is bigger (7 years vs 3), so the periodic over-extraction is
bigger too, and its cash tier refills from bonds *unconditionally* every
year regardless of market direction, adding a second drain the simpler
strategy doesn't have.

**What actually does help, tested the same way: a plain, static equity/bond
ratio, no bucket mechanic at all.** Same setup, varying `Blend.of` weights —
success probability peaks at 60% equity (92.8%, worst-decile £144,566),
comfortably inside Bengen's independently-published 47–75% optimal range,
and both tails are covered from 80% down to 40% equity. Going too
conservative is its own failure mode, not just a safer choice: 0% equity
scored 48.0% success with a **median** ending wealth of zero.

**Practical takeaway for `define-scenarios`:** when the goal is genuinely
reducing sequence-risk, prefer `StaticMix`/`ByAssetTypeMix` at a tested
equity percentage over `CashBondLadder` or `ThreeBucketStrategy`. The
protection people credit to "having a buffer" is actually just holding a
lower average equity allocation, continuously — the bucket structure itself
is not merely inert (the earlier, weaker finding from secondary research)
but actively counter-productive under both refill rules tested here.

**Caveat:** this indicts the specific refill rule tested — top up to full
target, unconditionally or on any non-negative return year — not bucket
strategies in general. A gentler rule (partial refills, or refilling only
after a sustained shortfall) was not built or tested and might behave
differently. Until it is, treat any bucket/cash-buffer recommendation as
needing the same stress test before it reaches a client, not an assumed
good.

---

## 2. Skills and agents

**What works.** Splitting intake / scenarios / simulate / report matches how
the work actually proceeds. Encoding hard-won traps into the skills has paid
for itself — the "0% or 100% is a red flag" note came directly from a bug that
would otherwise have shipped.

**What was fixed** (all four, same day this was written):

- **`challenge-the-model` now owns "is this model still right?"** It is loaded
  at the start of an engagement and again before the report, and points here
  rather than copying this list — so a limitation that has since been closed
  cannot go on being disclosed, which damages trust exactly as much as
  omitting one.
- **`retirement-planner` consults `uk-tax-strategist`.** It has the Agent tool
  and named triggers: estate above the nil-rate bands, a pot over the Lump Sum
  Allowance, gifting, or fixing a draw order.
- **Net-of-tax is enforced structurally.** `reporting.check_report` runs on
  every render and refuses a results table built from `bequest_percentiles`.
  It also catches a pre-escaped `client_name` and markdown the template cannot
  render — both of which had shipped.
- **Verification speaks up.** `verified_on` on the tax system and IHT rules,
  with `run_monte_carlo` warning when it is stale — before consulting the
  cache, since a cache hit is exactly when nobody is looking at the tax
  module.

**What is still worth doing:**

- The cheap-model split (`simulation-runner`, `report-proofreader`) is new and
  unproven. Watch whether a checklist agent on a small model actually catches
  what a careful reading would.
- Nothing yet checks that a report's stated assumptions match the household it
  was built from. That is still a human reading two documents side by side.

---

## 3. Method

- **Parity testing worked.** Matching median bequests to the pound made the
  deliberate changes attributable. Keep doing it on every refactor.
- **The engine is fast enough to test claims, and that changes behaviour.**
  Several confident intuitions (de-risking the bridge, cash ladders) turned
  out wrong when run. The remaining risk is claims cheap enough to assert but
  never checked.
- **Caching is load-bearing and has failed silently once.** The
  `_strategy_spec` dataclass guard exists because of it. Worth an occasional
  deliberate cache-miss check.
- **Findings should be reported when they surprise us, not smoothed.** The
  100%-success degeneracy and the shrinking-estate result are both more
  informative than the headline numbers they sit beside.

---

## 4. Bugs found and fixed

| Bug | How it surfaced | Impact |
|---|---|---|
| UK basic-rate band mis-sized inside the £100k taper | Rewriting tax as a marginal-rate schedule | Wrong tax above £100k |
| `ByAssetTypeMix` re-priced every asset, including a £750k house, at equity returns | A variant returned an implausibly high bequest | Estate overstated ~two thirds |
| `StandardOrder` not a dataclass → id()-based cache key | Cached second pass took as long as the first | Cache silently disabled |
| WiseAlpha yields modelled as *real* returns | Reviewing the return-model design | Assumed an inflation-proof 8% risk-free |
| HTML entity leaked into the PDF footer | Reading rendered pages | `Pat &amp; Robin` in print |
| Sampled-credit window collapsed to 18 years, producing 100% success | Sanity-checking a suspiciously round number | False confidence |
| `Scenario.death_ages` silently ignored by `run_monte_carlo` | A survivor variant returned results identical to its base *to the pound* | First-death scenarios were untestable; the knob keyed the cache but changed nothing |
| `take_pcls`'s docstring claimed proceeds landed in cash "spent before anything else" | Tracing actual balances in a test run, not trusting the comment | Would have misled anyone reading the doc rather than the code; the code was already correct |
| PCLS greedily claimed the whole Lump Sum Allowance before a same-day `PensionLumpSum` request got to it | A test asserting the two should share the allowance failed with PCLS taking the full £268,275 | An explicit request would have silently received none of the relief it asked for, if scheduled the same plan-year as automatic PCLS-at-access |
| A household with no `ISA` `Asset` had nowhere for surplus, a PCLS, or Bed-and-ISA to shelter money — the GIA fallback was synthesised automatically, the ISA was not, and neither errored | The user asking "does this assume part of the income comes from the GIA/ISA?" of a PCLS-vs-UFPLS comparison | Understated PCLS's tax advantage by tens of thousands of pounds over 30+ years in that comparison. **Fixed at the engine level**, not just documented: `plan.py` now synthesises a zero-balance ISA per person the same way it already did a GIA, `SURPLUS_ISA_NAME`, only for people without an explicit one already |

The pattern: **every one was caught by looking at a number that seemed too
good, by rendering the output and reading it, or by someone asking why a
number was built the way it was.** None of the three is automatable.

---

## 5. What I would do next, in order

Items 1–5 of the original list are done (see §1). What remains:

1. **Re-anchor `GuytonKlinger` (1.12)** so success stops being non-monotonic
   in the retirement date. This is now top of the list because it silently
   misranks the one decision every engagement turns on.
2. **Worst-historical-sequence search (1.8)**, replacing invented stress
   numbers with the worst start a retiree could actually have had.
3. **Cross-spouse tax levelling (1.6)** — roughly £125,000 a year of cheap
   band sits between two people and `TaxEfficientOrder` fills them in
   dictionary order.
4. **Cohort rather than period life tables (1.2)** — the shipped table
   understates a living person's life expectancy by two to three years.
5. **Advice fees and transaction costs (1.10)**, which compound over decades.
6. **A better tail statistic than `worst_case_5pct_min_spend` (1.11)**.

The closing line of the original list said this engine's errors were, on
balance, optimistic. Closing 1.1–1.5 confirmed it: **every one of those five
changes made plans worse**, and together they moved the sample household from
95.6% to 93.5% before care and to 84% with it. The remaining errors still
point the same way, but less far.
