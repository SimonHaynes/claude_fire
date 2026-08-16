---
name: uk-trusts
description: UK trusts end to end — types, the relevant property regime and its charges, trust income tax and trustee CGT, registration, the packaged structures (discounted gift, loan, bypass, will trusts), and the traps. Use for any question about putting assets in trust, running one, taking money out, or whether a trust is worth its cost.
---

# UK trusts

Owns everything about trusts. `legal-and-trust-structuring` owns the care means
test, deprivation of assets, joint tenancy and lifetime gifting, and calls here
for anything about the trust itself. `uk-pension-tax-strategy` owns pensions,
including the April 2027 change this skill applies to bypass trusts.

**You are not a solicitor and must not draft.** Every structure here needs a
STEP-qualified solicitor. Your job: identify what is worth a conversation, cost
what can be costed, and be explicit about which is which.

**Figures are 2026/27 England & Wales, from `retireplan.tax.provenance`.** Check
`tools/check_tax_freshness.py` before quoting any of them, and re-verify with
`verify-tax-figures` if it flags something.

## The frame that prevents most errors

A settlement is a **separate taxpayer from the person who made it**. Its own
nil-rate band, fixed for life. Its own decennial charge. A CGT exemption at half
an individual's and no uplift on death. Income tax at the top of the scale from
the first pound. "Outside the estate" is one line of a balance sheet, not a
conclusion.

The relevant property regime charges roughly a generation's worth of IHT in
instalments — 6% per decade against 40% per generation. Over a long enough
horizon a trust is not cheaper than dying. The question is never "does this beat
40%"; it is **what does the control or protection buy, and what does it cost.**

`tools/trust_charges.py` costs both arms. Run it rather than asserting.

## Parties and mechanics

| | |
|---|---|
| Settlor | Puts assets in. Gone for good — a settlor who can still benefit wrecks the tax treatment |
| Trustees | Legal owners. Personally liable; act unanimously unless the deed says otherwise |
| Beneficiaries | Equitable owners. A fixed entitlement, or membership of a class with no entitlement at all |
| Protector | Optional. Consent powers over trustee decisions; not a trustee |

Created by deed in life, by will on death, or by statute/court. Certainty of
intention, subject matter and objects — fail any and there is no trust.

Trustee duties, mostly **Trustee Act 2000**: a statutory duty of care (higher
for a professional), a general power of investment, a duty to have regard to
the *standard investment criteria* (suitability and diversification), to **take
and consider proper advice**, and to review. Delegation to agents is allowed
with appointment and review done properly. Trustee Act 1925 s31 and s32 give
default powers of maintenance and advancement; s32 has covered a beneficiary's
whole share since October 2014.

## Types, and what each costs

| Type | IHT | Income tax | CGT |
|---|---|---|---|
| **Bare / absolute** | The beneficiary's asset; a gift into it is a PET | Beneficiary's own, at their rates and allowances | Beneficiary's own |
| **Discretionary** | Relevant property: entry, 10-year, exit | Trust rates from the first pound above £500 | Trustee rate, halved exemption |
| **Accumulation** | Relevant property | As discretionary | As discretionary |
| **Interest in possession (lifetime, post-2006)** | Relevant property | Trustees 20% / 10.75%, life tenant tops up | Trustee rate, halved exemption |
| **IPDI** (by will, immediate) | In the life tenant's estate at 40% — **no** decennial charge | As IIP | Uplift when the life tenant dies |
| **Pre-22 March 2006 IIP** | In the life tenant's estate | As IIP | Uplift on death |
| **Disabled person's / vulnerable** | Outside relevant property; aggregates with the beneficiary's estate | Beneficiary's rates on election | £3,000 exemption; beneficiary's rates on election |
| **Bereaved minor's (s71A)** | Outside relevant property | Trust rates until absolute at 18 | Trustee |
| **18-to-25 (s71D)** | Reduced exit charge for the years after 18 | Trust rates | Trustee |
| **Discretionary will trust** | Relevant property, but see s144 below | Trust rates | Trustee |

Everything not privileged is relevant property. That is the default, and the
list of exceptions is short and closed.

### The two that get confused

**IPDI vs discretionary will trust.** An IPDI gives the survivor a defined right
(income, or occupation), so the spouse exemption applies and there is no
decennial charge — but the fund lands in *their* estate at 40% and follows the
will's terms whatever happens to the family. A discretionary trust gives
trustees complete freedom and keeps the fund out of the survivor's estate
permanently, at the price of the relevant property regime. Ask what is being
protected against — tax, a remarriage, a divorcing child, a vulnerable
beneficiary — before naming either.

**The RNRB does not survive a discretionary will trust.** The residence band
needs the home *closely inherited* by a direct descendant. An IPDI for a
descendant, a bereaved minor's trust, an 18-to-25 trust and a disabled person's
trust qualify; a discretionary trust does not, even where the children are the
only beneficiaries. Up to £350,000 of band for a couple turns on this. It is
recoverable within two years — see s144.

## The relevant property regime

### Entry

A lifetime transfer into a relevant property trust is a **chargeable lifetime
transfer**, not a PET. Above the available nil-rate band:

- **20%** where the trustees pay
- **25%** where the settlor pays, because paying someone else's tax is itself a
  gift

Available band = £325,000 less the settlor's chargeable transfers in the seven
years before. Death within seven years recharges at death rates with credit for
the lifetime tax and taper relief on the excess.

The band the settlement gets is **fixed at commencement and never refreshes**,
so the order a settlor creates trusts in decides which one has a band.

### Ten-year anniversary

Up to **6% of the whole fund**, valued the day before the anniversary.

    effective rate = 20% x (fund − available band) / fund
    charge rate    = effective rate x 3/10        (capped at 6%)

Both rates are stated to three decimal places. A fund at the band pays nothing;
at twice the band, 3%; the marginal pound above the band always costs 6p. "6% of
the excess" is the misreading that costs the most.

### Exit

    before the first anniversary: rate from the settlement's *opening* value
    after an anniversary:         the last anniversary's charge rate
    either way:                   x complete quarters / 40

Three consequences worth acting on:

- **Nothing leaves in the first three months of a cycle at any charge.** Zero
  complete quarters, zero tax — including the three months after every
  anniversary.
- A growing fund exiting before its first anniversary is charged on its
  *historic* value, so a distribution in year nine of a bull market is priced as
  if the market had not moved.
- After an anniversary the rate is frozen for a decade regardless of growth.

### Two-year window on a will trust (IHTA s144)

An appointment out of a discretionary will trust within **two years of death**
is read back into the will. No exit charge, and the destination gets its own
treatment: spouse exemption, charity exemption and the 36% rate, or the RNRB if
the home reaches a direct descendant. This is the most valuable planning
window in UK estate practice and it closes silently. **Check the date of death
on any discretionary will trust you meet.**

### Reporting

IHT100 within six months of the end of the month of the event, unless the
settlement is *excepted* — broadly, a notional transfer within 80% of the
nil-rate band. Report even where no tax is due.

### Agricultural and business relief

100% relief is capped at **£2.5m** from 6 April 2026, 50% above. A settlement
has its own allowance refreshing every ten years — but every settlement one
settlor made **on or after 30 October 2024** shares a single allowance,
allocated to the earliest first. Also from 6 April 2026, exit charges are
computed on *unrelieved* values throughout the cycle.

## Income tax

| | Non-dividend | Dividend |
|---|---|---|
| Discretionary / accumulation | 45% | 39.35% |
| Interest in possession (trustees) | 20% | 10.75% |
| From 6 April 2027, property and savings income | **47%** | 39.35% unchanged |

First **£500** of income is exempt — a de minimis, not a band, so no tax is paid
on it and nothing enters the tax pool. Divided between a settlor's settlements,
floored at £100 once there are five or more.

**The tax pool.** A discretionary distribution reaches the beneficiary net of a
45% credit whatever the trustees actually paid, and the pool is only what they
did pay. Two structural leaks:

- dividends taxed at 39.35% against a credit given at 45%
- the £500 exemption, which pays nothing in

A trust living on dividends and distributing all of it runs a permanent
deficit that the trustees must fund. The flip side is the reason discretionary
trusts exist for low-income beneficiaries: a non-taxpayer reclaims the whole
45%, a basic-rate beneficiary most of it, an additional-rate one nothing.

**Settlor-interested (ITTOIA s624).** If the settlor *or their spouse* can
benefit in any circumstances, the income is taxed on the settlor however it is
applied. Under s629, a parent settling for their own minor unmarried child is
taxed on the income once it exceeds £100 a year — which quietly defeats most
"bare trust for the grandchildren" plans made by parents rather than
grandparents.

## Capital gains tax

| | |
|---|---|
| Trustee rate | 24%, flat — no basic-rate band to fall into |
| Annual exempt amount | £1,500 (£3,000 for a vulnerable beneficiary trust) |
| Multiple settlements | Divided between them, floored at £300 |
| Death of a beneficiary | **No uplift**, except when a qualifying interest in possession ends |
| Into and out of a relevant property trust | Hold-over available (TCGA s260) |
| Business assets | Hold-over available (TCGA s165) |
| Settlor-interested | Hold-over **denied** (TCGA s169B) |

Hold-over is what makes a trust practical: without it, settling a pregnant
asset triggers CGT and IHT on the same day. It defers rather than forgives, and
claiming it on a residence blocks private residence relief later (s226A).

**The missing uplift compounds.** An individual's gains die with them. A
settlement's do not — decades of gain survive into the beneficiaries' hands.
Weigh that against the 40% avoided before calling the trust cheaper.

## Registration

Trust Registration Service, **90 days** from creation or from becoming liable to
tax, £5,000 penalty. Schedule 3A excludes pension schemes, charitable trusts,
life policy trusts, co-ownership trusts and will trusts wound up within two
years of death — but any of them registers anyway once it has a tax liability.
Not optional, not dormant-friendly, and a common surprise for a trust set up
before 2020 and forgotten.

## Packaged structures

| Structure | What it does | Watch |
|---|---|---|
| **Discounted gift trust** | Gift with a fixed lifetime income stream carved out; the retained right discounts the transfer immediately | Irreversible, and the income cannot be varied. Discount is medically underwritten |
| **Loan trust** | Lends rather than gifts; growth is outside the estate from day one, the loan is not | No immediate IHT saving at all — only the growth escapes |
| **Flexible reversionary trust** | Bond segments maturing on a schedule the settlor may take or leave in trust | More flexible than a DGT, more moving parts, and reversion mechanics are drafting-sensitive |
| **Spousal bypass trust** | Pension death benefits into discretionary trust rather than to the survivor | See below — April 2027 changed the arithmetic |
| **Property protection / IPDI over a half share** | Survivor occupies for life, the half share passes to the children | Owned by `legal-and-trust-structuring`; drafting decides whether it works |
| **Disabled person's trust** | Provision without losing means-tested benefits | Requires a qualifying benefit; election is a deadline, not a formality |

### Spousal bypass trusts after April 2027

The old case — keeping death benefits out of the survivor's estate — survives.
The tax case does not:

- unused pension funds enter the deceased's estate from **6 April 2027**, and a
  payment to a bypass trust gets **no spousal exemption** even where the spouse
  is a beneficiary
- where death is after 75, a lump sum to a trust also suffers the **special lump
  sum death benefit charge at 45%**, stacking on the IHT

Paying benefits **directly to a surviving spouse** keeps the exemption and
defers everything to the second death. Recommend a bypass trust now for what it
protects — a remarriage, a vulnerable or divorcing beneficiary, control over a
large fund reaching a young adult — never for the tax alone. And check the
nomination: it is a separate document from the will and is usually out of date.

## The traps

- **Gift with reservation.** A settlor who keeps benefiting leaves the asset in
  their estate — the classic being the home given away and still lived in.
  Seven years pass and nothing has moved.
- **Pre-owned assets tax.** The backstop where GROB does not bite: an annual
  income tax charge on the benefit of an asset you gave away or funded.
- **Settlor-interested by accident.** "Or their spouse" is doing the work.
  A widely drawn beneficiary class can catch the settlor's spouse and pull all
  the income back.
- **Same-day additions.** Creating several small settlements on the same day no
  longer multiplies nil-rate bands. Separate days, separate years, and the
  shared APR/BPR allowance still applies from 30 October 2024.
- **Excluded property is now about residence, not domicile.** Since 6 April
  2025, long-term residence (10 of the previous 20 UK tax years) decides. A
  trust that was excluded property when settled can stop being so because the
  settlor's residence changed.
- **The trust that was never registered.** And the one whose trustees have all
  died or lost capacity.
- **Trustee investment.** No advice taken, no diversification, no review — the
  Trustee Act 2000 breaches nobody notices until a beneficiary does.
- **Care and deprivation.** Owned by `legal-and-trust-structuring`. Never tell a
  healthy client that gifting or settling is blocked by deprivation rules; the
  test is motive and foresight, not a look-back period.

## Jurisdiction

**Scotland** differs materially: liferent and fee rather than interest in
possession, legal rights that override a will, and the Trusts and Succession
(Scotland) Act 2024 rewriting trust law once commenced. Northern Ireland
differs again. If the client or the land is not in England and Wales, say so
and stop — do not translate.

## How to advise with this

- **Cost both arms.** `tools/trust_charges.py` prints the charges beside the
  do-nothing case. A trust that costs money and is still right is a normal
  outcome; the number tells the client what the protection costs.
- **Lead with the mechanism, not the vehicle.** "Everything passing outright to
  the survivor puts the whole fund in their estate and their care assessment" is
  actionable. "Consider a discretionary trust" is a word.
- **Name what the model cannot score** — protection from a divorce, a
  remarriage, a beneficiary who cannot manage money. These are usually the real
  reason and never appear in a projection.
- **Check the cheap things first**: pension death benefit nomination, whether a
  will post-dates the last major life event, TRS registration, whether a will
  trust is inside its two-year s144 window, and lasting powers of attorney.
- **Quantify, then refer**: "this is worth around £X, here is the mechanism,
  take it to a STEP solicitor."

A modelling tool, not legal or tax advice. Everything here belongs in front of a
STEP-qualified solicitor, and anything touching investments in front of an
FCA-regulated adviser, before anyone acts.
