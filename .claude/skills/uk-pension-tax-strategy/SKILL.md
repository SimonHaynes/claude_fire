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

**When applying a rule here to a specific household's numbers, compute it —
`retireplan.tax.iht.effective_pension_death_rate`, `tax.pcls_available`, or a
short script — rather than doing the arithmetic by hand.** The tables below
are reference points, not a template for mental maths on a client's actual
figures.

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

**A person with no ISA `Asset` gets a synthetic one too** (`{name} — Surplus
ISA (Global Tracker)`), the same way the GIA below has always been
synthesised — so surplus income, a PCLS lump sum, or Bed-and-ISA always has
somewhere to shelter money up to the annual allowance, whether or not intake
recorded a real ISA for that person. This closed a real gap: before it, a
household with no explicit ISA `Asset` had nowhere for any of that to go,
ever, and everything intended for an ISA silently stayed in the GIA instead —
paying CGT and dividend tax for the rest of the plan, with no error. A full
PCLS-and-invest comparison understated PCLS's tax advantage by tens of
thousands of pounds over 30+ years this way before the fix.

**Still record the client's real ISA explicitly whenever they have one.**
The synthetic fallback opens at zero — it is there so the *possibility* of
sheltering money always exists, not as a substitute for the household's
actual current balance.

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

## The tax-free lump sum: PCLS vs UFPLS

Two different mechanisms get tax-free cash out of a DC pension, and they are
not interchangeable.

**PCLS + flexi-access drawdown.** Crystallise some or all of the pot in one
event; take up to 25% of *what you crystallise* as tax-free cash, **capped at
£268,275** (25% of the old Lifetime Allowance figure, which did not rise with
pot values, so it binds for anyone above about £1.07m — exactly the people
who assume "25% tax-free" applies to all of it; check `tax.pcls_available(pot)`
rather than multiplying by 0.25). The remaining 75% moves into a drawdown
account and stays invested; you decide separately, later, how much *taxable*
income to draw from it, including none at all.

**UFPLS (Uncrystallised Funds Pension Lump Sum).** Take a lump sum directly
from the uncrystallised pot, no drawdown wrapper. Every payment is
automatically 25% tax-free / 75% taxable in the same instant — there is no
way to take the tax-free part on its own.

**The decisive practical difference is the MPAA.** Taking PCLS alone does
**not** trigger it. Taking *any* taxable income does — permanently cutting
money-purchase contribution room from £60,000 to £10,000 — and a UFPLS
cannot be taken without a taxable slice, so **every UFPLS triggers it
immediately**, even a small one. This dominates the decision for anyone still
contributing meaningfully to a pension: PCLS + drawdown (crystallise, take
the tax-free cash, leave the 75% untouched) preserves the full Annual
Allowance; UFPLS does not.

**For someone who has stopped contributing, the choice comes down to the Lump
Sum Allowance.** Above it (pot > £1,073,100), there is no future benefit to
waiting — value above the cap never gets tax-free treatment whether taken now
or in ten years, so take the maximum PCLS immediately, invest it (see the GIA
section below), and start reducing the eventual beneficiary-income-tax
exposure on that slice. Below it, UFPLS's incremental, no-commitment
withdrawals are the more natural fit — draw what's needed, when it's needed,
without forcing a crystallisation event or a drawdown pot to manage.

**Delaying crystallisation on a pot comfortably below the LSA genuinely grows
the tax-free entitlement, in absolute pounds, alongside the pot** — confirmed,
this is correct, and worth stating explicitly because it's easy to get
backwards. Crystallising early locks in a PCLS calculated on today's
(smaller) value; every pound of growth on the 75% left in drawdown after that
is now part of a pot that only ever produces *taxable* income, never more
tax-free cash. Leave it uncrystallised instead, and 25% of a *larger* future
value is tax-free when it's eventually accessed. This stops mattering once
the pot's projected 25% would reach the LSA cap — beyond that point further
growth buys no additional tax-free entitlement, only a larger taxable
balance (still growing free of CGT and dividend tax inside the pension
wrapper, which a GIA does not offer, but not generating more tax-free cash).

**This is an argument about the owner's own eventual spending, not a
universal "always delay."** It can conflict with the decision rule above
("move money from pension to ISA whenever your rate now is below your
beneficiary's rate later") for a pot that is more likely to be inherited than
spent: money left uncrystallised avoids nothing on the IHT side once
pensions enter the estate in April 2027, and if the eventual death is after
75, the beneficiary still pays income tax on it at their own rate — the
extra tax-free entitlement from delaying only helps if the *owner* lives to
use it. Run both framings rather than defaulting to either.

**Recycling anti-avoidance:** you cannot take a PCLS and pay it back into a
pension for further relief. The test bites where contributions rise by more
than 30% of the PCLS across a five-year window. Moving PCLS into an *ISA* is
not caught by this; paying it into a pension is.

**The engine invests PCLS proceeds, not you** — see the GIA section below. A
PCLS landing in cash in a trace or a fan chart is a regression, not a
modelling choice to explain away.

**Set `Scenario.pension_access` to choose the mechanism.** `PensionAccess.NONE`
(the default) is fully taxable, no lump sum, ever. `PensionAccess.PCLS`
crystallises and takes the maximum tax-free lump sum the moment access
begins, same as before. `PensionAccess.UFPLS` splits every ongoing
withdrawal from the pension 25% tax-free / 75% taxable automatically —
solved exactly against the actual tax bands, not approximated — and shares
one lifetime tax-free-cash counter with PCLS, so the two compose correctly
if a household somehow uses both. **This is the field to set to model the
below-LSA, no-longer-contributing case above** — pick `UFPLS` rather than
leaving `pension_access` at `NONE` and hand-approximating it.

**For a specific one-off amount — "I want £50,000 of cash now" — without
committing to either ongoing mode, use `Scenario.pension_lump_sums`.** A
dated `PensionLumpSum(on, person, amount)`, also split 25%/75%, drawing
against the same lifetime allowance as PCLS/UFPLS. This is the practical
form of "partial crystallisation": the engine doesn't track a separate
crystallised-vs-uncrystallised ledger, so there is nothing to partially
commit to — only how much of the pot's *future* tax-free entitlement a
withdrawal today uses up. If a `PensionLumpSum` and an automatic
PCLS-at-access event land in the same plan-year, the explicit request is
honoured first, then PCLS takes whatever allowance is left — not the other
way round, which would silently starve a deliberate request of the relief
it asked for.

**Neither mode enforces the MPAA itself.** The engine doesn't cap
contributions after a taxable withdrawal under any mode — say so explicitly
if a household intends to keep contributing after triggering it, since the
plan will otherwise overstate how much further relief remains available.

**A fourth option, orthogonal to the three above: annuitise part of the pot
instead of drawing it down.** `Scenario.income_annuity = IncomeAnnuity(enabled=True,
fraction_of_pot=...)` buys a lifetime annuity once, at first access, from
whatever's left of the pot after any automatic PCLS — converting that
fraction into guaranteed income for the rest of that person's life, taxed as
ordinary pension income throughout (no special tax-free routing, unlike
`ImmediateNeedsAnnuity`, whose fees go tax-free direct to a care provider).
Single-life: nothing passes to the estate, and payments stop outright at
that person's own death regardless of a surviving spouse. This is the
Bodie/Pfau safety-first case for a household anxious about *running out*
rather than about maximising what's left — the trade-off worth stating
plainly is the mirror image of drawdown flexibility: money committed to an
annuity cannot be redirected later, however markets or circumstances change.

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
