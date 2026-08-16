---
name: legal-and-trust-structuring
description: Wills, trusts and ownership structure for UK estate planning — IPDI and discretionary will trusts, severing a joint tenancy, the care means test and why it is assessed per person, deprivation of assets, and immediate needs annuities. Use when advising on what reaches the children rather than on what the portfolio earns.
---

# Legal and trust structuring

The rest of this project optimises what the money *does*. This is about how it
is *held* and who it passes to — which above the nil-rate bands, or facing care
costs, moves more money than any drawdown decision available.

**You are not a solicitor and must not draft anything.** Every structure here
needs a STEP-qualified solicitor, and several are actively harmful done badly.
Your job: identify what is worth a conversation, model what the engine can cost,
and be explicit about which is which.

**`uk-trusts` owns the trusts themselves** — the types, the relevant property
charges, trust income tax and CGT, registration and the traps. This skill owns
the care means test, deprivation, ownership and gifting, and says only which
structure the situation points at. Load both when they meet, which is often.

**Verify before advising.** Figures are England 2025/26 and move most years.
Scotland, Wales and Northern Ireland differ materially — Scotland has legal
rights that override a will, and different care funding.

The two questions: **what reaches the children after both deaths** (IHT plus the
beneficiaries' income tax on an inherited pension), and **what survives a care
episode** (means-tested per person). They interact, and that is where the value
is: the structure protecting against care often saves IHT too, and the one that
looks best on paper is often the one a local authority disregards.

## The care means test: "per person" is the whole game

England assesses each resident on **their own** capital, not the household's.

| | 2025/26 |
|---|---|
| Upper capital limit | £23,250 — above this, pay in full |
| Lower capital limit | £14,250 — below this, capital ignored |
| Tariff income between them | £1/week per £250 of capital |
| Personal expenses allowance | £30.15/week |

Three consequences drive most of the advice:

- **The home is disregarded entirely** — not tapered — while a spouse, partner
  or dependent relative lives there. A first admission does not put the house at
  risk; the exposure arrives on the second, when nobody is left living there.
- **Jointly held capital is normally split 50/50**, so £400,000 between two
  people is £200,000 each. Whose name an asset sits in is a planning decision.
- **A will can stop the first death doubling the survivor's exposure.** Passing
  everything outright means the survivor owns the lot and is assessed on the
  lot. The most common structural mistake; the fix is a will trust.

## Structures worth raising

**Severing a joint tenancy + a will trust over the half share — not modelled.**
Most couples own as joint tenants, so the home passes automatically to the
survivor and joins their estate. Severing to tenants in common lets each leave
their half in trust — typically an IPDI giving the survivor the right to live
there for life, the half share passing to the children afterwards. On a later
assessment the survivor owns half a house, and the trust half is generally
outside their assessable capital; it also protects the children's share against
remarriage. Two cautions: the survivor's security depends entirely on drafting,
and a trust holding property carries its own tax and administration — see
`uk-trusts`, and cost it with `tools/trust_charges.py` rather than waving at it.

**Discretionary vs IPDI will trusts.** The choice turns on what is being
protected against — tax, care, a beneficiary's circumstances, or remarriage — so
ask that before naming a structure. The comparison itself, the charges each
carries and the residence nil-rate band consequence are in `uk-trusts`, as is
the two-year window (IHTA s144) that can still fix a discretionary will trust
after the death. **Check the date of death before saying anything is settled.**

**Nil-rate bands — modelled.** Both transfer between spouses: £650,000 nil-rate
plus up to £350,000 residence nil-rate. The residence band tapers £1 per £2
above a £2m estate and is usually gone entirely for the households modelled
here — worth checking, since a structure keeping the estate under £2m at the
second death can be worth £140,000. It also requires the home to pass to direct
descendants, and some trust structures qualify while others do not: solicitor
territory, not model territory.

**Lifetime gifting — modelled** (`Scenario.gifts`): seven-year taper, nil-rate
band consumed earliest-first. Run it rather than asserting it — the answer flips
on whether the recipient spends or invests, and heavy gifting can *lose* the
family money. Not modelled and worth naming: the £3,000 annual exemption, small
gifts, gifts in consideration of marriage, and — often the most valuable for a
high-income household — **normal expenditure out of surplus income**, exempt
immediately with no seven-year wait if the pattern is documented. That last is
an adviser referral with real money attached.

**Immediate needs annuity — modelled** (`care.ImmediateNeedsAnnuity`). A single
premium at the point of entering care buys guaranteed income for life paid
**direct to the provider**, which is what makes it tax-free, converting an
open-ended liability into a known one-off. State the trade honestly: die soon
after buying and most of the premium is gone; live long in care and it pays out
many times over. It is longevity insurance, judged on what it protects, not on
expected return. Engine pricing is a planning approximation — a real premium is
medically underwritten, and only an FCA-regulated specialist's quote is real.

**Pensions after April 2027 — modelled.** Unused pensions enter the estate,
inverting the old "spend ISAs first" rule (see `uk-pension-tax-strategy`). The
structural point here: a pension death benefit nomination is a separate document
from the will, frequently out of date, and the cheapest thing on this list to
check.

## Deprivation of assets: what it actually catches

Frequently overstated, and overstating it is not harmless — it scares households
out of early gifting, the largest IHT lever most of them have.

The Care Act 2014 statutory guidance (Annex E) sets a **motive and foresight**
test, not a look-back period. The authority must consider whether avoiding the
charge was a significant motivation, and:

> whether, **at the point the capital was disposed of**, the person could have
> had a **reasonable expectation of the need for care and support**, and a
> reasonable expectation of needing to contribute towards its cost.

The converse is given directly: it would be **unreasonable** to treat a disposal
as deprivation where the person was fit and healthy and could not have foreseen
the need. Deliberate deprivation is not assumed; the authority must make the
case. So:

- **Getting older is not foresight.** A healthy person in their fifties or
  sixties gifting for IHT reasons is doing what the guidance contemplates as
  legitimate.
- **The risk concentrates once care is foreseeable** — a diagnosis, a decline, a
  first assessment. Gifts then invite the question; gifts a decade earlier,
  while well, generally do not.
- **There is no fixed look-back period.** "Seven years" is the *IHT* rule and
  has nothing to do with care charging. But no time limit does not make old
  gifts vulnerable: foresight decides, and distance plus good health at the time
  is exactly what satisfies it.
- **Motive is judged on evidence** — a documented IHT plan, helping a child buy
  a house, a pattern of regular gifting from income.

**For advice:** never tell a healthy client that gifting is blocked by
deprivation rules — that is wrong and expensive. Give the timing logic instead:
gifts made early, while well, for recorded reasons unrelated to care stand on
entirely different ground from gifts made once care is on the horizon. Then note
that the assessment is the authority's judgement on facts — a solicitor's
question, and one the model does not attempt to score.

## How to advise with this

- **Model what can be modelled, say plainly what cannot.** The engine costs
  gifting, an immediate needs annuity, a draw order and the nil-rate bands. It
  cannot cost a will trust, whose outcome depends on drafting and on a local
  authority's judgement. A report that blurs the two is worse than one that only
  does the first.
- **Lead with the structural point, not the vehicle.** "Everything passing
  outright to the survivor doubles what a later care assessment looks at" is
  actionable; "consider an IPDI" is a word.
- **Quantify, then refer**: "this is worth around £X, here is the mechanism,
  take it to a STEP solicitor".
- **Check the cheap things first** — pension death benefit nomination, whether a
  will exists and post-dates the last major life event, joint tenants vs tenants
  in common, and lasting powers of attorney. An LPA cannot be created once it is
  needed.

This is a modelling tool, not legal advice. Everything here belongs in front of
a STEP-qualified solicitor, and anything touching investments in front of an
FCA-regulated adviser, before anyone acts.
