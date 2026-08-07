---
name: challenge-the-model
description: Establish what this engine currently gets wrong and which way each error cuts, before quoting any probability to a client. Use at the start of an engagement and again before writing the report.
---

# Challenge the model

Every other skill here describes how to *operate* the engine. This one exists
to ask whether the engine is still right, because nothing else does, and
because a success probability is the most confidently-wrong number this project
produces.

Load it twice: at the start of an engagement, so you know what you are working
with, and before the report is written, so the assumptions section names what
actually bears on this household.

## REVIEW.md is the list

`REVIEW.md` at the repo root is the canonical, dated record of what this engine
gets wrong, graded by how much each item could move a real decision. **Read it
rather than reciting from memory** — it changes as gaps get closed, and a
limitation you disclose that has since been fixed is as damaging to trust as
one you omit.

It also carries a table of bugs found and fixed, and the pattern behind them:
every one surfaced either from a number that looked too good, or from rendering
the output and reading it. Neither is automatable, which is why this is a skill
and not a test.

## Before quoting any probability

1. **Check the tax rules are current.** `retireplan.tax.uk` and
   `retireplan.tax.iht` each carry a `verified_on` date. If either is stale,
   verify against gov.uk before the number reaches a client — do not note the
   staleness and continue.
2. **Check the sampling window.** A probability computed over 18 years of
   history is a statement about those 18 years. Report the window wherever you
   report the probability.
3. **Ask which direction the omissions point.** `REVIEW.md`'s standing
   conclusion is that this engine's errors are, on balance, **optimistic**. If
   that line is still in the document, the probability you are about to quote
   is an upper bound, and the report must say so.

## For this household specifically

A generic limitations list is close to useless — readers skip it, and it
protects the writer rather than informing the client. Work out which
limitations actually bite here:

- **Does it turn on when someone dies?** Bequest figures always do. Check
  which mortality model the household uses: under the `FixedAge` default,
  every estate figure is conditional on both people reaching that exact age,
  and on the sample household switching to real rates cut the median net
  bequest by 31%. If the plan is about what the children receive and it was
  run on `FixedAge`, say so or re-run it.
- **Was care tested?** It is off by default and is usually the largest single
  downside available — five years of it took a 95% plan to 84%. A report that
  never mentions care implies a completeness the plan does not have.
- **Were frozen thresholds turned on?** `fiscal_drag` defaults to zero
  inflation, which quietly assumes every frozen allowance rises with prices.
- **Is the estate above the nil-rate bands?** Then threshold policy over
  decades matters more than drawdown tuning.
- **Is there a long single-survivor period likely?** A large age gap between
  partners makes the survivor's position central rather than a footnote.
- **Does the plan depend on a series with short history?** Then the tail risk
  is understated by construction.
- **Are charges realistic?** Advice fees and transaction costs compound over
  four decades and are only partly modelled.

Name the ones that bite, in the client's language, with **which way each cuts**.
A reader can judge an assumption they can see.

## What to do when you find something

**Report it when it surprises you, rather than smoothing it.** A result that
contradicts the recommendation is the most valuable output the engine produces,
and burying it is the most damaging thing available here.

If you find an actual defect — a number that cannot be explained by any
mechanism you can trace — stop and investigate before building anything on top
of it. Then add it to `REVIEW.md`'s bug table with how it surfaced, so the next
engagement inherits the lesson rather than rediscovering it.

If a limitation is large enough to change the advice, say so in the
recommendation itself, not only in the notes. "Retire in September" and
"retire in September, though this assumes both of you live to 95" are different
pieces of advice.
