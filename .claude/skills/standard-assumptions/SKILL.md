---
name: standard-assumptions
description: What to assume when a client's information is incomplete — the published default for each gap, which way it errs, and the rule for when to assume versus when to stop and ask. Use whenever intake, a scenario or a report needs a number nobody has stated.
---

# Standard assumptions

Asking about every gap is exhausting and looks indecisive; filling them all in
silently builds a plan on invented numbers.

**The rule: assume where a recognised standard exists, ask where the answer is
a decision only the client can make.** Two obligations follow:

1. **Every assumption is recorded** in the household docstring and surfaces in
   the report's notes, with its source and **which way it errs**.
2. **A default is never presented as a fact.** "Assumed 2% inflation, the Bank
   of England target" is honest; a projection that quietly contains 2% is not.

## Ask — do not assume

Preferences and facts, not parameters, so there is no defensible default:

- **Anything with a real number attached**: balances, salaries, contributions,
  debts, the actual spending figure. Never estimate a balance.
- **The goal itself** — a target date, "as early as possible", a purchase, and
  whether the stated figure is a hard requirement or an opening position.
- **Flexibility**: would they cut spending in a downturn, and roughly how far?
  Would they work longer if they had to? Is there headroom to spend *more*?
  Without this the plan can only be tested once, pass or fail.
- **A notice period or any other hard constraint on timing.**
- **Risk tolerance**, where it drives the allocation.
- **Who money should go to**, and whether a will and lasting powers of
  attorney exist. Nobody can default a beneficiary.
- **Health, where it is materially unusual.** Do not ask intrusively, but a
  client who volunteers a serious condition has changed the mortality
  assumption and should be told so.

If one is missing, ask: one clear question is cheaper than a plan built on a
guess.

## Assume — using these defaults

Each is published or conventional, already the engine's default, and carries the
direction it errs so the bias is visible.

| Gap | Default | Source | Errs toward |
|---|---|---|---|
| Age at death | 95, fixed | Convention | Optimistic on bequest, demanding on success |
| Mortality, when sampled | ONS national life tables, England & Wales | ONS | Short — period not cohort, national not affluent |
| Sex, for mortality | 50/50 blend | — | Neither; ask, it is worth ~3.5 years |
| State pension age | 68 | Legislated | — |
| Pension access age | 57 | Legislated from 2028 | Conservative: assumes the later age now |
| Inflation, for frozen thresholds | 2% | Bank of England target | Understates recent experience |
| Property real growth | 0% | Deliberate | Pessimistic on estate |
| Care: chance of needing it | ~25% (20% men, 30% women) | Published planning figures | — |
| Care: length of stay | Mean ~2.5 years, median ~18 months, long tail | Published planning figures | — |
| Care: cost | £60,000/yr residential | Typical England self-funded range £50–70k | — |
| Care: offset to ordinary spending | 35% | Judgement | Charging none would overstate the hit |
| DB survivor benefit | 50% | Typical public-sector scheme | — |
| Survivor spending | Essentials 90%, discretionary 75% | Above OECD/PLSA equivalence scales | Pessimistic, deliberately |
| Beneficiary marginal rate | 40% | Inherited pension stacks on a working-age salary | — |
| GIA distribution yield | 2% | Long-run global equity | — |
| Immediate needs annuity pricing | 3-year impaired expectation, 25% loading | Planning approximation | Overstates the premium |
| Gift growth rate | 0% (valued as spent on receipt) | Deliberate | Neither; **run both**, the answer flips |
| "Global equities" / "the market", unspecified | `SampledSeries("global_equity")` — the US-proxy series (S&P 500 + 10yr Treasury, Damodaran/NYU Stern) | Same convention FIRECalc and cFIREsim use: one long, clean, well-understood historical series rather than a constructed global one | Not global; see below before reaching for an alternative |

**When a default is doing real work, say so out loud.** Where the
recommendation turns on one — a marginal retirement date, an estate near the £2m
taper — it stops being background and should be put to the client directly.

## Assume, then flag for confirmation

The most common case: the notes imply an answer without stating it. Take the
reading, say which and why, invite correction, and keep working.

*"House repairs, car replacement etc. £10,000/yr"* — essential or discretionary?
For life, or only while there is a car? The defensible call is discretionary and
for life, with the reasoning in the docstring. Better than guessing silently or
blocking on a question the client may never have considered.

## What this does not license

**It is never a licence to invent a number the client holds.** A balance, a
salary, a contribution rate and a debt are facts they can look up. "Assume an
industry standard" applies to how the world behaves, not to what is in their
accounts.

**A default that has never been checked is worse than an obvious gap**,
because it looks like an answer. Tax figures carry `verified_on` for exactly
this reason; treat an unverified figure as an open question, not a default.

**Where two reasonable defaults disagree, run both.** Gifting valued as spent
versus invested is the standing example — the conclusion inverts, so picking
one silently picks the answer.

**`global_equity_gdpw`/`global_bonds_gdpw` and `ParametricNormal` are not
alternative defaults — they are specific-purpose tools that need a reason
and a disclosure, every time.** The US-proxy series above is the one to
reach for whenever a client says "global equities," "the market," or names
no particular assumption. Reach for one of the other two only when there is
a specific, stated reason to (a client asking specifically about
non-US-concentration risk, a request to see a bias-corrected or
capital-market-assumption view, or similar) — and when you do, say so and
state the limitation in the same breath, not as a footnote:

  * `global_equity_gdpw`/`global_bonds_gdpw` is a real historical panel
    (JST Macrohistory, 16 countries, 1900-2020), but survivorship-biased —
    it runs about 2 points/year hot on equities against the UBS Global
    Investment Returns Yearbook's own published figure, for reasons
    documented in `tools/fetch_global_market_data.py` and REVIEW.md sec.6.
  * `ParametricNormal` is an independent year-by-year draw from a
    distribution, not a historical sequence — no autocorrelation, no mean
    reversion, no sequence that ever actually happened. Never swap it in
    for the historical bootstrap silently; the two answer different
    questions and can disagree by a large margin for the same household
    (a 32.4% vs 7.6% success-probability gap on the same test case is the
    standing example — see REVIEW.md sec.6).
