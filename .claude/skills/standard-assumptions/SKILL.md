---
name: standard-assumptions
description: What to assume when a client's information is incomplete — the published default for each gap, which way it errs, and the rule for when to assume versus when to stop and ask. Use whenever intake, a scenario or a report needs a number nobody has stated.
---

# Standard assumptions

Every engagement has gaps. Stopping to ask about all of them is exhausting for
the client and makes the work look indecisive; filling them all in silently
produces a plan built on invented numbers. This skill draws the line.

**The rule: assume where a recognised standard exists, ask where the answer is
a decision only the client can make.**

Two obligations follow, and neither is optional:

1. **Every assumption is recorded** in the household docstring and surfaces in
   the report's notes section, with its source and **which way it errs**. A
   reader can judge an assumption they can see.
2. **A default is never presented as a fact.** "Assumed 2% inflation, the
   Bank of England target" is honest; a projection that quietly contains 2% is
   not.

---

## Ask — do not assume

These change the recommendation and have no defensible default, because they
are preferences or facts, not parameters:

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

If one of these is missing, ask. One clear question is cheaper than a plan
built on a guess.

---

## Assume — using these defaults

Each is a published or conventional figure, already the engine's default, and
each is stated with the direction it errs so the bias is visible rather than
hidden.

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

**When a default is doing real work, say so out loud.** If the recommendation
turns on one of these — a marginal retirement date, an estate near the £2m
residence nil-rate band taper — it stops being a background assumption and
becomes something the client should be asked about directly.

---

## Assume, then flag for confirmation

A middle case worth naming, because it is the most common one: the notes imply
an answer but do not state it. Take the reading, say which reading you took
and why, and invite correction — do not stop the work for it.

Worked example from a real intake: *"House repairs, car replacement etc.
£10,000/yr"*. Essential or discretionary? For life, or only while there is a
car to replace? The defensible call is discretionary and for life, and the
docstring says so along with the reasoning. That is better than either
guessing silently or blocking on a question the client may not have thought
about.

---

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
