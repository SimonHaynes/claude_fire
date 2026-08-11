---
name: uk-tax-relief-and-allowances
description: Money going into pensions and ISAs, and the allowances a couple has two of — pension tax relief and who it belongs to, funding a non-earning partner's pension, whose name to build wealth in, State Pension gaps and voluntary NI. Use when advising on contributions, on splitting assets between partners, or on anything before the drawdown starts.
---

# UK tax relief and the two-person allowances

`uk-pension-tax-strategy` owns money coming **out** — drawdown order, PCLS,
IHT, the April 2027 change. This skill owns money going **in**, and the
allowances that belong to a person rather than a household. Read both for a
couple; the rates table lives there and is not repeated here.

**Verify every figure before advising, and compute rather than assert** — the
same rules as the drawdown skill, for the same reasons.

## The rule that drives everything

> **Contribute whenever the relief going in exceeds three quarters of the
> marginal rate coming out: `r > 0.75m`.**

A pound of pot costs `(1-r)`. It comes out worth `0.25 + 0.75(1-m)` — a quarter
tax-free, the rest at the member's rate then. Verified against
`tax.uk` for a £2,880 payment grossed to £3,600:

| Member's rate in drawdown | Comes out as | Return on the cash paid |
|---|---|---|
| Nil (inside the personal allowance) | £3,600 | **+25%** |
| 20% | £3,060 | **+6.25%** |
| 40% | £2,520 | **−12.5%** |

Break-even is **m = 26.7%**. So the familiar advice — "always pay £2,880 into a
non-earning spouse's pension" — is right for a partner who will retire with
unused personal allowance or basic-rate room, and **destroys money** for one who
will be a higher-rate taxpayer in retirement. Check the projected marginal rate
before recommending it; a partner with a large DB pension coming is the case
that fails.

Assumes the PCLS is available: below the Lump Sum Allowance, not already used,
no MPAA. Above the LSA the tax-free quarter is gone and the test tightens to
`r > m`.

## Relief belongs to the member, not the payer

This is the whole mechanism, and it is what makes a couple worth planning as a
couple:

- **A third party can pay; the member gets the relief.** One partner funds the
  other's pension out of their own money and relief is computed on the
  *member's* tax status and earnings.
- **The member's relevant earnings set the cap** — employment income only.
  Pension, rental and investment income are not relevant earnings however
  large, so a wealthy retired member is still stuck at the flat limit.
- **The cap is the higher of £3,600 gross and 100% of relevant earnings**,
  and everything is capped again by the £60,000 Annual Allowance.
- **£3,600 has been fixed in cash terms since 2001** and has no uprating
  mechanism. `FiscalDrag.allowance_inflation` erodes it by default, so the
  capacity shrinks in every year of a long plan. Do not quote it as a constant
  thirty-year opportunity.
- **Relief stops at 75.** After that a pension contribution is a worse ISA.

## Salary sacrifice beats relief at source for anyone with the choice

| Route | Relief | NI | Model as |
|---|---|---|---|
| Salary sacrifice through payroll | full marginal rate | **relieved too** | `Contribution` |
| Relief at source (SIPP, third-party) | basic rate into the pot; higher rate reclaimed as cash | not relieved | `ReliefAtSource` |

`ReliefAtSource(net_annual=2_880)` on a `DC_PENSION` asset states the **net**
payment; the engine grosses it up, caps it against that year's earnings and the
eroding flat limit, stops it at 75, and charges the net cash to `fixed_spend`.
It needs no salary, which is the point — it is the only route that funds a
person with no earnings at all.

**Higher-rate relief is not modelled.** A 40% member reclaims a further 20%
through self-assessment, as cash rather than into the pot. Every plan here
understates their return — an error that errs *against* contributing, so a
contribution the model already likes is safe.

## Whose name to build it in

A couple has two of almost everything. Filling one person's allowances while the
other's go unused is the most common avoidable loss in a household plan:

| Two of | Each | Together |
|---|---|---|
| Personal allowance | £12,570 | £25,140 of income at 0% |
| Basic-rate band | to £50,270 | ~£100,000 a year of cheap income |
| ISA subscription | £20,000 | £40,000 |
| CGT annual exempt amount | £3,000 | £6,000 |
| Dividend allowance | £500 | £1,000 |
| Lump Sum Allowance | £268,275 | £536,550 of tax-free cash |

**Interspousal transfers are unlimited and tax-free**, and pass at no gain / no
loss for CGT, so the allocation is a free choice — which means an unequal one is
a decision, not a fact. Practical consequences:

- **Build the smaller pension.** A household with one £1.5m pot and one £180,000
  pot has one person deep into higher rate in drawdown and one with an unused
  personal allowance. Equalising the pots is worth far more than optimising the
  order they are drawn in.
- **Equalise a GIA** to use both CGT exemptions and both dividend allowances,
  and to keep dividends inside the lower earner's bands.
- **The ISA subscription already spills between partners** — `credit_isa` fills
  the owner then a spouse with room. That is modelled; the GIA equalisation
  above is not.

**`TaxEfficientOrder` fills each person's band in dictionary order, not levelled
across the household** (REVIEW.md §1.6). Say so when quoting its output for a
couple with lopsided pots: it understates what good cross-spouse planning would
achieve, so a plan built on it is conservative rather than wrong.

## State Pension gaps

`Person.state_pension_qualifying_years` — from a gov.uk forecast, never a guess.
35 years buys the full rate, below 10 pays nothing at all, in between it is
straight-line.

**Voluntary Class 3 contributions are the best guaranteed return available to a
household**: about £925 buys a year worth £359 a year for life, triple-locked —
`UKTaxSystem.class_3_payback_years()` returns **2.6 years**. The person with the
gap is usually the one who took time out to raise children, which is why this
belongs in a couples conversation rather than an individual one.

Ask about it at intake for anyone with career breaks, part-time years, or time
working abroad. Model a buy-back as a raised `state_pension_qualifying_years`
plus a `Scenario.one_off_spend` for the cost, and run it both ways.

Check before recommending: **Specified Adult Childcare Credit and Home
Responsibilities Protection may fill the gap for free**, and buying a year that
was going to be earned anyway before State Pension age wastes the money. Both
are questions for HMRC, not for this engine. `CLASS_3_ANNUAL_COST` carries the
2025/26 figure and is **not verified for 2026/27** — it is uprated most years.

## What this engine does not model

Name these and refer them onward. Do not estimate them.

| | Why it matters |
|---|---|
| Marriage Allowance | £1,260 of personal allowance transferable where one partner is a non-taxpayer and the other basic-rate. £252 a year, claimable four years back |
| Carry forward | three years of unused Annual Allowance, which is how a large one-off contribution before retirement is funded |
| MPAA enforcement | contributions are not capped after a taxable withdrawal; a plan that keeps contributing overstates the relief remaining |
| Higher-rate relief reclaimed | see above; errs against contributing |
| Tapered Annual Allowance | falls toward £10,000 above £260,000 of adjusted income |
| GIA equalisation between partners | two CGT exemptions and two dividend allowances |
| Cross-spouse income levelling | REVIEW.md §1.6 |

## The April 2027 interaction

Funding a partner's pension used to be a double win: relief on the way in *and*
outside the estate for IHT. **From 6 April 2027 the IHT shelter is gone**, so
all that survives is the `r > 0.75m` arithmetic above. Advice written before the
Finance Act 2026 will overstate the case, and habit pulls a reader back to it.
State which rule a recommendation rests on.

Note the direction of travel this sets up: contributions fill the pension while
`uk-pension-tax-strategy`'s decision rule empties it into an ISA. Those are not
in conflict — they are the same test applied at different rates, `r > 0.75m`
going in and `m < b` coming out — but a plan doing both at once in the same year
is churning, and should be checked rather than assumed clever.
