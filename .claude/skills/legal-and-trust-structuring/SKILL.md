---
name: legal-and-trust-structuring
description: Wills, trusts and ownership structure for UK estate planning — IPDI and discretionary will trusts, severing a joint tenancy, the care means test and why it is assessed per person, deprivation of assets, and immediate needs annuities. Use when advising on what reaches the children rather than on what the portfolio earns.
---

# Legal and trust structuring

Everything else in this project optimises what the money *does*. This skill is
about how it is *held* and who it passes to — which for an estate above the
nil-rate bands, or a household facing care costs, moves more money than any
drawdown decision available.

**You are not a solicitor and must not draft anything.** Every structure below
needs a STEP-qualified solicitor to draw up and execute, and several are
actively harmful if done badly. Your job is to identify which structures are
worth a conversation, model the ones the engine can cost, and be explicit
about which is which.

**Verify before advising.** Figures here are England 2025/26 and move most
years. Check gov.uk. Scotland, Wales and Northern Ireland differ materially —
Scotland has legal rights that override a will, and its care funding is
different. Nothing here applies outside England without re-checking.

---

## The two questions this skill answers

1. **What reaches the children after both deaths**, given IHT and the
   beneficiaries' own income tax on an inherited pension.
2. **What survives a care episode**, given a means test assessed on each
   person separately.

They interact, and the interaction is where the value is: the structure that
protects against care costs is often the same one that saves IHT, and the
structure that looks best on paper is often the one a local authority will
disregard.

---

## The care means test, and why "per person" is the whole game

England assesses each resident on **their own** capital, not the household's.

| | 2025/26 |
|---|---|
| Upper capital limit | £23,250 — above this, pay in full |
| Lower capital limit | £14,250 — below this, capital ignored |
| Tariff income between them | £1/week per £250 of capital |
| Personal expenses allowance | £30.15/week |

Three consequences that drive most of the advice:

**The home is disregarded entirely while a spouse, partner or dependent
relative still lives there.** Not tapered — disregarded. So a first spouse
entering care does not put the house at risk. The exposure arrives on the
*second* admission, when nobody is left living there.

**Jointly held capital is normally split 50/50.** Two people with £400,000
between them are assessed at £200,000 each, not £400,000 each. This is why
whose name an asset sits in is a planning decision, not an administrative
detail.

**A will can stop the first death doubling the survivor's exposure.** If
everything passes outright to the survivor, the survivor now owns the lot and
is assessed on the lot. This is the single most common structural mistake, and
the fix is a will trust — see below.

---

## Structures worth raising

Each is flagged for whether this engine can cost it.

### Severing a joint tenancy, plus a will trust over the half share

**Not modelled — solicitor required.** Most couples own their home as *joint
tenants*, so it passes automatically to the survivor and forms part of their
estate. Severing to *tenants in common* lets each leave their half into a
trust instead — typically an immediate post-death interest (IPDI) giving the
survivor the right to live there for life, with the half share passing to the
children afterwards.

Why it matters: on a later care assessment the survivor owns half a house, not
a whole one, and the trust half is generally outside their assessable capital.
It also protects the children's share against remarriage.

Two cautions worth stating plainly: the survivor's security depends on the
trust being drafted properly, and a trust holding a share of a property has
its own tax and administrative consequences. This is not a DIY structure.

### Discretionary vs IPDI will trusts

**Not modelled — solicitor required.** An IPDI gives the survivor a defined
right (usually to income, or to occupy) and is treated as theirs for IHT, so
the spouse exemption still applies. A discretionary trust gives trustees
freedom over who benefits and when, which is more flexible and better at
protecting a vulnerable or divorcing beneficiary, but sits under the relevant
property regime with its own ten-year and exit charges.

The choice turns on what the client is protecting against — tax, care, a
beneficiary's circumstances, or a future remarriage — and those pull in
different directions. Ask which one they actually care about before naming a
structure.

### Nil-rate band and residence nil-rate band

**Modelled.** Both bands transfer between spouses, so a couple has £650,000 of
nil-rate band plus up to £350,000 of residence nil-rate band. The residence
band tapers away £1 for every £2 above a £2m estate and is usually gone
entirely for the households this project models — worth checking rather than
assuming, because a structure that keeps the estate under £2m at the second
death can be worth £140,000 of tax.

Note the interaction: the residence nil-rate band requires the home to pass to
direct descendants. Some trust structures qualify and some do not, which is
exactly the kind of detail that needs the solicitor and not the model.

### Lifetime gifting

**Modelled** (`Scenario.gifts`) — seven-year taper, nil-rate band consumed
earliest-gift-first. Run it rather than asserting it: the answer flips
depending on whether the recipient spends or invests, and heavy gifting can
*lose* the family money against doing nothing.

Not modelled, and worth naming: the £3,000 annual exemption, small gifts, gifts
in consideration of marriage, and — often the most valuable of all for a
high-income household — **normal expenditure out of surplus income**, which is
immediately exempt with no seven-year wait if the pattern is documented. That
last one is an adviser referral with real money attached.

### Immediate needs annuity

**Modelled** (`care.ImmediateNeedsAnnuity`). A single premium at the point of
entering care buys a guaranteed income for life paid **direct to the care
provider**, which is what makes it tax-free. It converts an open-ended
liability into a known one-off cost, so whatever remains afterwards is safe
from the care bill however long the stay lasts.

State the trade honestly: die soon after buying one and most of the premium is
gone; live a long time in care and it can pay out many times over. It is
insurance against longevity in care, not an investment, and should be judged on
what it protects rather than on expected return. Pricing in this engine is a
planning approximation — a real premium is medically underwritten, and only a
quote from an FCA-regulated specialist is a real number.

### Pensions after April 2027

**Modelled.** Unused pensions enter the estate from 6 April 2027, which
inverted the old "spend ISAs first" rule. See `uk-pension-tax-strategy`; the
structural point here is that a pension death benefit nomination is a separate
document from the will, is frequently out of date, and is the single cheapest
thing on this list to check.

---

## Deprivation of assets: what it actually catches

Frequently overstated, including in earlier versions of this skill, and
overstating it is not harmless — it scares households out of early gifting,
which is the single largest inheritance tax lever most of them have.

The Care Act 2014 statutory guidance (Annex E) sets a **motive and foresight**
test, not a look-back period. A local authority must consider whether avoiding
the care charge was a **significant motivation**, and critically:

> whether, **at the point the capital was disposed of**, the person could have
> had a **reasonable expectation of the need for care and support**, and a
> reasonable expectation of needing to contribute towards its cost.

The guidance gives the converse directly: it would be **unreasonable** to
treat a disposal as deprivation where, at the time, the person was **fit and
healthy and could not have foreseen the need for care and support**. Deliberate
deprivation is not to be assumed; the authority has to make the case.

So the practical picture is close to the opposite of the folk version:

- **Getting older is not foresight.** Age alone does not create a reasonable
  expectation of needing care. A healthy person in their fifties or sixties
  making gifts for inheritance tax reasons is doing something the guidance
  explicitly contemplates as legitimate.
- **The risk concentrates once care is foreseeable** — a diagnosis, a decline,
  a first care assessment. Gifts made at that point invite the question;
  gifts made a decade earlier, while well, generally do not.
- **There is no fixed look-back period.** That much of the folk version is
  true, and it is why "seven years" is the wrong frame — seven years is the
  *inheritance tax* rule and has nothing to do with care charging. But the
  absence of a time limit does not make old gifts vulnerable: it is the
  foresight test that decides, and distance in time plus good health at the
  time is exactly what satisfies it.
- **Motive is judged on the evidence.** Contemporaneous reasons — a documented
  inheritance tax plan, helping a child buy a house, a pattern of regular
  gifting from income — are what distinguish an ordinary gift from one aimed
  at the means test.

**What this means for advice.** Do not tell a healthy client that gifting is
blocked by deprivation rules, because that is wrong and expensive. Tell them
the timing logic: gifts made early, while well, for reasons that are recorded
and are not about care, stand on entirely different ground from gifts made
once care is on the horizon. Then note that the assessment is the local
authority's judgement on facts, so it is a solicitor's question and not this
model's — and that the model does not attempt to score it.

## How to advise with this

**Model what can be modelled, and say plainly what cannot.** The engine can
cost gifting, an immediate needs annuity, a draw order and the nil-rate bands.
It cannot cost a will trust, because the outcome depends on drafting and on a
local authority's judgement. A report that blurs the two is worse than one
that only does the first.

**Lead with the structural point, not the vehicle.** "Everything passing
outright to the survivor doubles what a later care assessment looks at" is
something a client can act on. "Consider an IPDI" is a word.

**Quantify what is at stake, then refer.** The useful output is "this is worth
somewhere around £X, here is the mechanism, take it to a STEP solicitor" — not
a recommendation to execute a structure you cannot draft.

**Check the cheap things first.** A pension death benefit nomination, whether
the will exists at all and post-dates the last major life event, whether the
property is held as joint tenants or tenants in common, and whether lasting
powers of attorney are in place. These cost little, are frequently wrong, and
an LPA that does not exist by the time it is needed cannot be created at all.

This is a modelling and planning tool, not legal advice. Everything here
belongs in front of a STEP-qualified solicitor, and anything touching
investments in front of an FCA-regulated adviser, before anyone acts.
