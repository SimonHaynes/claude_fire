---
name: uk-pension-tax-strategy
description: UK pension, ISA and inheritance tax rules and the drawdown strategy that follows from them — PCLS, the Lump Sum Allowance, pensions entering the IHT estate in April 2027, death before/after 75, MPAA, and whether to draw from pension or ISA. Use when advising on tax-efficient withdrawal, estate planning, or which wrapper to spend first.
---

# UK pension and IHT strategy

This skill covers money coming **out**. Contributions, tax relief, whose name to
build wealth in and State Pension gaps are `uk-tax-relief-and-allowances`.

**Verify every figure before advising.** These are 2026/27 and change each
Budget. If a number here disagrees with `retireplan.tax.uk` or
`retireplan.tax.iht`, find out which is stale before using either.

**This is modelling, not regulated advice.** Anything affecting a real decision
belongs in front of an FCA-regulated adviser.

**Compute, never hand-calculate.** Apply these rules to a household's numbers
through `tax.iht.effective_pension_death_rate`, `tax.pcls_available`, or a short
script. The tables here are reference points, not a template for mental maths.

## The rules that drive everything

| | 2026/27 |
|---|---|
| Personal allowance | £12,570 (tapered £1 per £2 above £100,000, gone at £125,140) |
| Basic rate ceiling | £50,270 |
| Additional rate from | £125,140 |
| Pension access age | 57 from 6 Apr 2028 (legislated, not proposed) |
| Tax-free lump sum (PCLS) | 25% of the pot, **capped by the Lump Sum Allowance** |
| Lump Sum Allowance (LSA) | £268,275 |
| Lump Sum & Death Benefit Allowance | £1,073,100 |
| Annual Allowance | £60,000 |
| Money Purchase Annual Allowance | £10,000 |
| ISA subscription | £20,000 per person per year |
| CGT annual exempt amount | £3,000 |
| CGT rate (shares, since 30 Oct 2024) | 18% basic, 24% higher — no separate "shares" rate |
| Dividend allowance | £500 |
| Dividend tax rate | 10.75% basic, 35.75% higher (both +2pp from 6 Apr 2026), 39.35% additional |
| Dividends vs the personal allowance | Dividends are income: unused personal allowance covers them. The £500 allowance is a 0% *band*, so it uses up basic-rate room |
| CGT band | Gains stack on income *after* the personal allowance, against the £37,700 band. The allowance is not available against gains; leaving it unused does not widen the band |
| IHT nil-rate band | £325,000, transferable between spouses |
| Residence nil-rate band | £175,000, transferable, **tapered £1 per £2 above £2m** |
| IHT rate | 40% |
| Pensions in the IHT estate | **from 6 April 2027** |

## April 2027 inverts the old advice

Unused pension funds enter the estate for IHT on deaths from 6 April 2027
(Finance Act 2026). The old rule was "pensions last" — spend ISAs first, pass
the pension on IHT-free. **The new rule is "pensions first"**: draw pension up
to a chosen band each year, top up spending from the ISA, recycle surplus back
into the ISA.

This is the most consequential departure from standard planning wisdom in this
skill, and habit pulls a client — or an agent — back to the old rule without
noticing. **Name the rule a plan follows, explicitly, in every report and every
piece of advice**; do not leave it inferrable from a strategy class name.

It does not apply below the personal allowance, and weakens as the owner's
marginal rate approaches the beneficiary's. Check it per household. The spouse
exemption survives: nothing is due on the first death; the bill lands on the
second.

**What a pound left in a pension is worth.** After 75, beneficiaries pay income
tax at their own rate on what they draw. That stacks with IHT, but not to the
naive 80%: the portion equal to the IHT paid is exempt from income tax, so they
receive `(1-i)(1-b)`.

| Beneficiary's rate | Inherited pension | Inherited ISA |
|---|---|---|
| 20% | **52%** | 40% |
| 40% | **64%** | 40% |
| 45% | **67%** | 40% |

`tax.iht.effective_pension_death_rate` computes it.

> **The decision rule: move money from pension to ISA during life whenever your
> marginal rate now is below your beneficiary's expected rate later.**

Both wrappers bear the same IHT once pensions are in the estate, so the only
difference left is the beneficiary's income tax — which you can pre-pay at your
own, usually lower, rate. Withdraw £1 at rate `m` and the ISA holds £(1-m);
leave it and the children keep £(1-b). Move when `m < b`. For a basic-rate
retiree with higher-rate children — very common — that is 20% now against 64%
later. Assume children are higher-rate unless told otherwise: an inherited
pension is drawn on top of a working-age salary.

The ceiling: recycling is limited to £20,000 per person per year, so shifting a
seven-figure pension takes decades. Starting early matters more than optimising
the rate.

## Drawdown: which wrapper, and how much

1. **Fill the personal allowance every year** — it does not carry forward.
2. **Then fill to the basic-rate ceiling** if the beneficiary comparison favours
   it (£50,270 at 20% against 64% later — usually yes).
3. **Size the draw to empty the pension over the horizon** — roughly **5% of the
   pot per person per year** — and go past the basic-rate ceiling to do it. 40%
   now beats 64% later, so the optimum for a large pot sits well into higher
   rate: ~£77,500 on a £1.5m pot, £100,000 on £2m+. Stop at the basic-rate
   ceiling only where the beneficiary is a basic-rate taxpayer.
4. **£100,000 is a hard ceiling, not a caution.** The taper makes £100,000–
   £125,140 a 60% band; drawing to £125,140 instead of £100,000 costs a £3m pot
   about £109,000.
5. **Use both people's bands** — two allowances and two basic-rate bands are
   worth roughly £25,000 and £100,000 a year of cheap income between them.
   (`TaxEfficientOrder` fills each person's band in turn but does not yet
   optimise across them — see REVIEW.md.) Equalising the *pots* beats optimising
   the order they are drawn in: `uk-tax-relief-and-allowances`.
6. **Spend the pension, not the shelters.** Under the optimum the pension funds
   96–100% of spending and the ISA/GIA are a *destination* for the tax-free cash
   and surplus, not a source. A PCLS that gets spent has been wasted: its value
   is the wrapper transfer, 40% at death instead of 64%.
7. **Where a top-up is needed, take it from the GIA before the ISA** — worth up
   to ~£13,500 over 30 years. Draining the GIA early stops it generating annual
   dividend tax; the ISA shelters better, so leave it intact. **This reverses the
   built-in ISA→GIA→pension order** and has to be set deliberately.
8. **Above roughly £2.5m, income cannot drain the pot** — £100,000 a year still
   leaves £1.9m+ at death. Gifting is the lever there, not drawdown order.

`strategies.TaxEfficientOrder(fill_to=...)` implements 1–3 and recycles surplus
into the ISA.

## GIAs and the ISA machinery

Every built-in strategy spends **ISA, then GIA, then pension**:

- **CGT (18%/24%, £3,000 exempt yearly) is usually cheaper than income tax** on
  an equivalent pension withdrawal, so a GIA empties before a pension.
- **CGT is wiped on death.** A GIA held to the end beats one sold during life —
  which bears on what is left unsold, not on the spending order.
- **Dividend tax applies every year** on an assumed 2% distribution yield
  (`gia_dividend_yield`), withdrawn or not: a GIA is not a buy-and-forget
  shelter the way an ISA is.

**Everyone gets a synthetic GIA, and anyone without an ISA `Asset` gets a
synthetic ISA too**, both opening at zero, so surplus income, a PCLS or a
Bed-and-ISA always has somewhere to shelter. Without the ISA fallback, money
intended for an ISA silently stayed in the GIA for the whole plan — that bug
understated PCLS's advantage by tens of thousands over 30+ years. **Still record
a client's real ISA explicitly**: the fallback provides the possibility, not the
current balance.

**Surplus income is invested automatically**, split equally across the
household, into each person's ISA then GIA — a saving decision independent of
the `DrawdownStrategy`. **Say so explicitly if it materially grows the plan**: a
household with real pre-retirement surplus ends up meaningfully wealthier than a
"surplus does nothing" mental model predicts, and the client should be told the
assumption, not just the number.

**A PCLS or DB lump sum is invested the same way, the same plan-year** — ISA
then GIA, never cash. A PCLS sitting in cash in a trace or chart is a
regression, not a modelling choice.

**Bed and ISA runs automatically every year.** After every other ISA-crediting
mechanism has had its turn, the engine sells just enough GIA to net the
remaining headroom and subscribes it, paying CGT on any realised gain. Expect a
GIA balance with no further surplus arriving to migrate fully into the ISA
within a few years — that is the shape of the GIA line, not a fault.

**A couple's ISA capacity is shared, not two hard ceilings.** `credit_isa` fills
the money's owner first, then spills to a spouse with room — an interspousal
gift (tax-free, unlimited) followed by their own subscription — so a large PCLS
or a lopsided pension can fill up to ~£40,000 of combined room. Every mechanism
shares one £20,000-per-person counter (`DrawdownContext.isa_headroom_used`), so
that is a ceiling, never something two mechanisms can double past. With one ISA
it reduces to the single-person case automatically.

## PCLS, phased crystallisation and UFPLS

Three routes, not two.

**PCLS + flexi-access drawdown.** Crystallise part or all of the pot; take up to
25% of what you crystallise tax-free, **capped at £268,275** — which binds above
about £1.07m, exactly the people who assume "25% tax-free" applies to all of it.
Use `tax.pcls_available(pot)`, not `pot * 0.25`. The remaining 75% moves to
drawdown and stays invested; taxable income is a separate later decision.

**Phased crystallisation.** The same mechanism in tranches: crystallise only
what is needed, each tranche releasing 25% of itself. What is left stays
uncrystallised, so its 25% keeps tracking a growing pot.

**UFPLS.** A lump sum straight from the uncrystallised pot, automatically 25%
tax-free / 75% taxable in the same instant. There is no way to take the tax-free
part alone.

**Phased weakly dominates UFPLS at every pot size.** It leaves funds
uncrystallised exactly as UFPLS does, so it captures the same growth in
entitlement, but it does not force three pounds of taxable income out per pound
of tax-free cash and it does not trigger the MPAA. UFPLS ties it on small pots
and loses above. **UFPLS is never the best answer** — say so rather than
offering it as the below-cap default.

**The MPAA decides it.** PCLS alone does not trigger it. *Any* taxable income
does, permanently cutting money-purchase contribution room from £60,000 to
£10,000 — and since a UFPLS always carries a taxable slice, **every UFPLS
triggers it immediately**. For anyone still contributing meaningfully, PCLS +
drawdown preserves the full Annual Allowance and UFPLS does not.

**Once contributions have stopped, the LSA decides it**, at roughly **90% of the
pot size at which the cap binds**:

| Pot per household | Route |
|---|---|
| Below ~£980,000 single / ~£1.93m couple | **Phased** |
| Above it | **Full PCLS at outset** |

**Delaying crystallisation on a pot comfortably below the LSA genuinely grows
the tax-free entitlement in absolute pounds** — easy to get backwards.
Crystallising early locks the PCLS to today's smaller value, and growth on the
75% left behind only ever produces taxable income. On a modelled £400,000 pot
over 30 years the delayed routes release £143,000 of tax-free cash against
£100,000 taken today. That advantage dies as the projected 25% approaches the
cap; above the cap, waiting buys nothing at all, so take the maximum now and
start reducing the beneficiary's eventual income tax on that slice.

**The threshold falls in real terms every year**, because the LSA is frozen in
cash terms and the pot is not — see `standard-assumptions`. Recompute it against
the household's own projection rather than quoting the figures above, which
assume 2% inflation and 4% real growth.

**It is an argument about the owner's own spending, not "always delay"**: for a
pot more likely inherited than spent it conflicts with the decision rule above,
since delay avoids nothing on IHT and the beneficiary still pays income tax
after 75. Run both framings.

**Recycling anti-avoidance:** a PCLS cannot be paid back into a pension for
further relief — the test bites where contributions rise by more than 30% of the
PCLS across a five-year window. Moving PCLS into an *ISA* is not caught.

**Choosing the mechanism** — `Scenario.pension_access`:

| Value | Behaviour |
|---|---|
| `NONE` (default) | fully taxable, no lump sum, ever |
| `PCLS` | crystallises and takes the maximum tax-free lump sum at first access |
| `UFPLS` | splits every ongoing withdrawal 25/75, solved exactly against the bands |
| `PHASED` | crystallises a tranche a year, sheltering the tax-free cash; taxable income stays independent |

All modes share one lifetime tax-free-cash counter, so they compose correctly.

**Size the tranche with `Scenario.phased_tranche`.** `None` sizes it to
remaining ISA room, which is the sensible default: the cash lands somewhere
sheltered instead of a GIA paying dividend tax for a decade. Crystallising only
the minimum each withdrawal needs reduces `PHASED` exactly to `UFPLS` — the gain
comes from crystallising *ahead* of the taxable need.

**Only uncrystallised funds carry a further entitlement**, which the engine now
tracks, so delay grows the tax-free cash in cash terms: on a £400,000 pot at 4%
real, the routes release £104,000 (`PCLS`), £113,872 (`PHASED`) and £155,825
(`UFPLS`). Quote the engine, not the direction.

**The Lump Sum Allowance erodes by default** — `FiscalDrag.allowance_inflation`,
2%/yr, because the allowance has no uprating provision at all. Delay therefore
costs real money in every comparison, which is the honest starting point. The
*announced* freezes are separate and still opt-in: set `FiscalDrag.inflation`
too whenever income-tax drag matters to the answer.

**For a specific one-off — "£50,000 of cash now" — use
`Scenario.pension_lump_sums`**: a dated `PensionLumpSum(on, person, amount)`,
also split 25/75 against the same lifetime allowance. This is the practical form
of partial crystallisation; the engine tracks no crystallised-vs-uncrystallised
ledger, only how much future tax-free entitlement a withdrawal uses. When one
lands in the same plan-year as an automatic PCLS, the explicit request is
honoured first, so a deliberate request is never starved of relief.

**No mode enforces the MPAA.** Contributions are not capped after a taxable
withdrawal — say so explicitly where a household intends to keep contributing,
or the plan overstates the relief remaining.

**Annuitising is the fourth, orthogonal option.**
`Scenario.income_annuity = IncomeAnnuity(enabled=True, fraction_of_pot=...)`
buys a lifetime annuity once at first access, from whatever remains after any
automatic PCLS, taxed as ordinary pension income throughout (unlike
`ImmediateNeedsAnnuity`, whose fees go tax-free direct to a care provider).
Priced by `retireplan.annuity` at the buyer's actual age, so annuitising later
buys a better rate; `joint_life_proportion` keeps a share paying the survivor.
This is the safety-first case for a household anxious about running out — state
the mirror-image trade plainly: money committed to an annuity cannot be
redirected however circumstances change. **The default is level, meaning flat in
pounds and falling in purchasing power**; `uk-annuities` owns that argument.

## Estate planning beyond drawdown

- **The residence nil-rate band is probably already gone.** Tapering £1 per £2
  above £2m, a couple's combined £350,000 disappears by £2.7m. Any household
  with a large pension has likely lost it and may not know.
- **Gifting (`Scenario.gifts`) is the biggest lever for an estate far above the
  bands** — bigger than any drawdown optimisation here. Outright gifts leave the
  estate after seven years, with taper relief on the tax and the nil-rate band
  consumed by the earliest gifts first. Annual exemptions and gifts from surplus
  income are not modelled — refer those. **Run it before recommending it**: for
  one modelled household, gifting valued as spent on receipt *lost* the family
  money against doing nothing, while valued as invested it came out neutral.
  Quote the net-to-family and success-probability effects and name the
  `gift_growth_rate` behind each.
- **Spend-down is a strategy.** A household that would rather enjoy the money
  than have 40–64% of it taxed should consider spending more, earlier — see
  `VariablePercentage`.

## Using this in analysis

Run the comparison rather than asserting it. **Always quote
`net_bequest_percentiles`**, never `bequest_percentiles`: gross overstates what
reaches the children by around 40%, more for a pension-heavy estate.

Expect the counter-intuitive result and do not "correct" it: good tax strategy
often produces a smaller estate on paper and a larger inheritance, because tax
was paid earlier at a lower rate.
