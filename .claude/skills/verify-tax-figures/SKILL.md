---
name: verify-tax-figures
description: Recheck a hardcoded tax or legislation figure against its source and record the result — the dates, the source URL and the next check. Use when tools/check_tax_freshness.py flags something, before a client report, after a Budget or at a tax year start, or whenever a figure is about to be quoted and its check date has passed.
---

# Verifying tax and legislation figures

Every hardcoded figure in this engine is a claim about the law on a date.
`src/retireplan/tax/provenance.py` records, for each one: the **source**, when it
was last **checked**, when to **check again**, and **what would move it**.

`tools/check_tax_freshness.py` turns that into a work list. This skill is how to
clear an item.

**The rule that makes the register worth having: never move `checked_on`
without opening the source.** A date that means "someone looked" is valuable; a
date that means "someone rolled it forward" is worse than no date, because it
converts an unknown into a false assurance.

## When to run

| Trigger | Scope |
|---|---|
| `check_tax_freshness.py` reports anything due | just those entries |
| Before a client report | run it; clear whatever is due, do not caveat it |
| After a Budget | everything with `recheck_by = BUDGET_FOLLOW_UP` |
| 6 April | everything uprated in April, and any commencement date that has passed |
| A figure has never been checked (`checked_on=None`) | that entry, before its module is used in anything a client reads |

## The procedure

1. **List what is due.**

       .venv/bin/python tools/check_tax_freshness.py
       .venv/bin/python tools/check_tax_freshness.py --check-urls   # after a gov.uk reshuffle

2. **Open the source.** Fetch the URL in the register. If it 404s, find the
   replacement page and update the URL — do not delete the entry, and do not
   substitute a secondary source for a primary one. gov.uk, HMRC manuals and
   legislation.gov.uk are primary; an adviser technical page is a way to find
   the primary source, never a substitute for citing it.

3. **Compare every figure the entry `covers`**, not just the one that prompted
   the check. The `covers` field names them so this can be done without reading
   the module.

4. **If a figure moved**, update the constant, run the tests, and check whether
   anything downstream assumed the old value — a rate change usually implies a
   comment, a docstring and a skill table are now wrong too. Bump
   `retireplan.__version__` if a simulation result could change, so cached
   results invalidate.

5. **If nothing moved**, that is still a successful check. Record it.

6. **Update the register**, moving both dates together:
   - `checked_on` → today
   - `recheck_by` → the next date this figure could move, from its own
     timetable, not today plus a year
   - `moved_by` → revise if the timetable itself changed

7. **Update the module's `verified_on`** to match the oldest check across its
   sources. `tests/test_provenance.py` fails if they disagree, and
   `check_tax_freshness.py` reports it.

8. **Run the suite**: `.venv/bin/python -m pytest`.

## Choosing the next check date

The recheck date is the **earliest date the figure could move**, which is a
property of the figure and not a uniform interval.

| What sets the figure | Recheck by |
|---|---|
| A rate or allowance a Budget can change | once the Budget's rate tables are published |
| Uprated each April — state pension, care capital limits, Class 3 NI | 6 April |
| A change already legislated for a future date | its commencement date |
| A frozen threshold | the Budget that could unfreeze it, **not** the end of the freeze |
| Primary legislation with no announced change | the next tax year |

A freeze is not a reason to skip a check: it binds only what it names, and can
be extended or cut short. The nil-rate band freeze has been extended twice.

Two traps in choosing dates:

- **Mid-year changes happen.** CGT rates changed on 30 October 2024, not at a
  tax year boundary. Do not assume 6 April is the only date anything moves.
- **A figure legislated but not yet in force still needs checking** — it can be
  amended or deferred before commencement, and nothing in the engine warns
  because nothing uses it yet. The deferred Dilnot care cap is the standing
  example.

## Adding a new figure

A new hardcoded tax or legislation constant needs a `Source` in the register in
the same change. If you cannot name a primary source for it, it is an
assumption rather than a figure — put it in `standard-assumptions` instead, with
the direction it errs.

## What to say in a report

State which figures were verified and when, and name any that were not. "Rates
verified against gov.uk on 16 August 2026" is a fact a reader can act on;
"rates are correct at the time of writing" is not.
