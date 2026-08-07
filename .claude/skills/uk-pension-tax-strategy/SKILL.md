---
name: uk-pension-tax-strategy
description: UK pension, ISA and inheritance tax rules and the drawdown strategy that follows from them — PCLS, the Lump Sum Allowance, pensions entering the IHT estate in April 2027, death before/after 75, MPAA, and whether to draw from pension or ISA. Use when advising on tax-efficient withdrawal, estate planning, or which wrapper to spend first.
---

# UK pension and IHT strategy

**Verify every figure before advising.** These are 2026/27 and rates change
each Budget. Check gov.uk. If a number here disagrees with
`retireplan.tax.uk` or `retireplan.tax.iht`, find out which is stale before
using either.

**This is modelling, not regulated advice.** Say so, and mean it. Anything
here that affects a real decision belongs in front of an FCA-regulated adviser.

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
| CGT rate (shares, since the 30 Oct 2024 Budget) | 18% basic rate, 24% higher — no separate lower "shares" rate any more |
| Dividend allowance | £500 |
| Dividend tax rate | 8.75% basic, 33.75% higher, 39.35% additional |
| IHT nil-rate band | £325,000, transferable between spouses |
| Residence nil-rate band | £175,000, transferable, **tapered £1 per £2 above £2m** |
| IHT rate | 40% |
| Pensions in the IHT estate | **from 6 April 2027** |

## The April 2027 change, and why it inverts the old advice

Unused pension funds enter the estate for IHT on deaths from 6 April 2027
(Finance Act 2026). Before this, pensions sat *outside* the estate, so the
standard advice was: spend ISAs first, leave the pension untouched, pass it on
IHT-free. **That advice is now backwards.** After April 2027 a large unspent
pension is the most heavily taxed asset a household can die holding.

**Old rule: "pensions last" (spend ISAs first, preserve the pension for
heirs). New rule: "pensions first" (draw pension up to a chosen tax band
every year, top up spending from the ISA, and recycle any surplus withdrawal
back into the ISA).** This flip is the single most consequential change this
skill makes to standard financial-planning wisdom, and it is easy for a
client — or an agent reasoning from habit — to default back to the old rule
without noticing. **State which rule a plan follows, by name, in every
report and every piece of advice.** Do not leave it to be inferred from a
strategy class name in a table; see `build-retirement-report`'s requirement
to name the draw order explicitly.

This does not apply below the personal allowance, and it weakens the closer
someone's own marginal rate is to their beneficiary's — see the decision rule
below. It is a household-level conclusion to check, not a rule to apply
unconditionally.

The spouse exemption survives: nothing is due on the first death when
everything passes to a spouse or civil partner. The bill lands on the second.

### What a pound left in a pension is actually worth

Death after 75 means beneficiaries pay income tax at *their* marginal rate on
what they draw. That stacks with IHT — but not as the naive 80% often quoted,
because the rules exempt from income tax the portion equal to the IHT paid.
For a fund taxed at IHT rate `i` and a beneficiary on rate `b`, they receive
`(1-i)(1-b)`:

| Beneficiary's rate | Effective tax on an inherited pension | On an inherited ISA |
|---|---|---|
| 20% | **52%** | 40% |
| 40% | **64%** | 40% |
| 45% | **67%** | 40% |

`retireplan.tax.iht.effective_pension_death_rate` computes this.

### The decision rule

> **Move money from pension to ISA during life whenever your marginal rate
> now is below your beneficiary's expected rate later.**

Both wrappers bear the same IHT once pensions are in the estate, so the only
remaining difference is the beneficiary's income tax on the pension — which
you can pre-pay at your own, usually lower, rate. Withdraw £1 at rate `m` and
the ISA holds £(1-m); leave it and the children keep £(1-b) of it. Move when
`m < b`.

For a basic-rate retiree with higher-rate children — extremely common — that
is 20% now against 64% later. Assume children are higher-rate unless you know
otherwise: an inherited pension is drawn on top of a working-age salary.

**But note the ceiling on this.** Recycling is limited by the £20,000 ISA
subscription per person per year, so shifting a seven-figure pension takes
decades. Starting early matters far more than optimising the rate.

## Drawdown: which wrapper, and how much

1. **Fill the personal allowance every year.** It does not carry forward.
   Every year a retiree draws nothing taxable throws away £12,570 each that
   could have left the pension at 0%.
2. **Then fill to the basic-rate ceiling** if the beneficiary comparison
   favours it (£50,270 at 20%, against 64% later — usually yes).
3. **Top up from the ISA beyond that**, rather than paying 40% now.
4. **Use both people's bands.** Two personal allowances and two basic-rate
   bands are worth roughly £25,000 and £100,000 a year of cheap income
   between them. Drawing everything from one person's pension wastes half of
   that. *(`TaxEfficientOrder` fills each person's band in turn but does not
   yet optimise across them — see REVIEW.md.)*
5. **Avoid the £100,000–£125,140 band** where the taper makes the marginal
   rate 60%. Rarely worth crossing.

`retireplan.strategies.TaxEfficientOrder(fill_to=...)` implements 1–3 and
recycles the surplus into the ISA.

## GIAs: the wrapper between ISA and pension

Every household carries a per-person General Investment Account by default
(`plan.py`'s synthetic "Surplus GIA" — see below), and every built-in
drawdown strategy spends it in the same place: **ISA, then GIA, then
pension.** The reasoning:

- **CGT (18%/24%, £3,000 exempt every year) is usually cheaper than income
  tax on an equivalent pension withdrawal**, so a GIA should empty before a
  pension does, all else equal.
- **CGT is wiped entirely on death** — the estate pays IHT on a GIA like any
  other asset, but there is no capital-gains charge on death the way there is
  income tax on an inherited pension after 75. A GIA held to the end is more
  tax-efficient than one sold during life; that only bears on what is left
  unsold, not on the ISA-then-GIA-then-pension order for what must be spent.
- **Dividend tax (8.75%/33.75%/39.35%, £500 allowance) applies every year**
  on an assumed distribution yield (`gia_dividend_yield`, default 2%),
  whether or not anything is withdrawn — a GIA is not a buy-and-forget
  tax shelter the way an ISA is.

**Surplus income is invested automatically, not left in cash.** Whenever a
household's income exceeds spending — working or retired — the engine splits
the surplus equally across the household's people, then invests each
person's share via `credit_isa` (see below) and their GIA for anything an
ISA can't absorb. This happens regardless of which `DrawdownStrategy` the
scenario uses; it is a saving decision, not a drawdown one. **Say so
explicitly if it materially grows the plan** — a household with real
pre-retirement surplus (unlike one running a slight pre-retirement shortfall
once debts are counted) will see meaningfully more wealth by
retirement than a naive "surplus does nothing" mental model predicts, and a
client should be told the assumption behind that, not just the number.

**A PCLS or DB pension lump sum is invested the same way, the same
plan-year it's taken** — into an ISA then GIA, never left in cash. This was
a real bug once: a large PCLS sat in the shared cash reserve, uninvested,
for years, and was found because a client asked why anything was ever in
cash at all.

**Money is then progressively moved from GIA to ISA every year — "Bed and
ISA," run automatically rather than left for someone to remember.** After
every other mechanism that can credit an ISA has had its turn each
plan-year, the engine sells just enough GIA to net whatever ISA headroom is
left and subscribes it, paying CGT on the realised gain if there is one. A
household with a GIA balance and no further surplus arriving will see it
fully migrated into the ISA within a few years, not held indefinitely —
report this as the expected shape of the GIA line in a wealth-by-account
chart, not a fault to explain away.

**A couple's ISA capacity is modelled as shared, not two hard £20,000
ceilings.** `credit_isa` (`retireplan.strategies`) fills the money's own
owner first, then spills any excess to a spouse's ISA if theirs still has
room — the real-world mechanism is an interspousal gift (tax-free, no
limit) followed by the recipient's own subscription, so a single large PCLS
or a lopsided pension between two people can legitimately fill up to
~£40,000/year of combined ISA room, not just £20,000. This applies
everywhere an ISA can be credited — the surplus sweep, a lump sum,
`TaxEfficientOrder`'s own recycling, and the Bed-and-ISA sweep — and **all
of them share one real £20,000-per-person counter for the plan-year**
(`DrawdownContext.isa_headroom_used`), so the combined ~£40,000 capacity is
a ceiling, never something two mechanisms can each credit independently and
double past. If a household has only one ISA (or one person has none),
this reduces to the single-person £20,000 case automatically — there is no
separate code path to keep in sync.

## The tax-free lump sum (PCLS)

25% of the pot, **capped at £268,275**. The cap is 25% of the old Lifetime
Allowance and did not rise with pot values, so it binds for anyone above about
£1.07m — exactly the people who assume "25% tax-free" applies to all of it.
Check `tax.pcls_available(pot)` rather than multiplying by 0.25.

Taking PCLS alone does **not** trigger the MPAA. Taking any *taxable* income
does, permanently cutting money-purchase contribution room from £60,000 to
£10,000 — which matters for anyone who might return to work or keep
contributing.

**Recycling anti-avoidance:** you cannot take a PCLS and pay it back into a
pension for further relief. The test bites where contributions rise by more
than 30% of the PCLS across a five-year window. Moving PCLS into an *ISA* is
not caught by this; paying it into a pension is.

**The engine invests it, not you** — see the GIA section above. A PCLS
landing in cash in a trace or a fan chart is a regression, not a modelling
choice to explain away.

## Estate planning beyond drawdown

- **The residence nil-rate band is probably already gone.** It tapers away
  £1 per £2 above a £2m estate, so a couple's combined £350,000 disappears
  entirely by £2.7m. Any household with a large pension has likely lost it
  and may not realise.
- **Gifting is modelled (`Scenario.gifts`), and it is the biggest lever for an
  estate far above the bands** — bigger than any drawdown optimisation this
  skill covers. Outright gifts fall out of the estate after seven years, with
  taper relief on the tax and the nil-rate band consumed by the earliest
  gifts first; there are also annual exemptions and gifts from surplus income
  (neither is modelled — treat those as an adviser referral). **Run it before
  recommending it**: the comparison is assumption-heavy and can go either way
  — for one modelled household, gifting valued as spent on receipt *lost* the
  family money against doing nothing, because decades of compounding on the
  unspent side outweighed the IHT saved, while valued as invested by the
  recipient it came out roughly neutral. Quote both the net-to-family effect
  and the success-probability effect, and state which growth assumption
  (`gift_growth_rate`) produced which answer — do not just cite "gifting
  helps" as a rule of thumb.
- **Spend-down is a strategy.** A household that would rather enjoy the money
  than have 40–64% of it taxed should consider spending more, earlier — see
  `VariablePercentage`.

## How to use this in analysis

Run the comparison rather than asserting it. `SimulationResult` reports
`bequest_percentiles` (gross) and `net_bequest_percentiles` (after IHT and
beneficiary income tax) — **always quote the net figure to a client**, because
the gross one overstates what reaches the children by around 40% and more for
a pension-heavy estate.

Expect the counter-intuitive result and do not "correct" it: a good tax
strategy often produces a *smaller* estate on paper and a *larger* inheritance,
because tax was paid earlier at a lower rate.
