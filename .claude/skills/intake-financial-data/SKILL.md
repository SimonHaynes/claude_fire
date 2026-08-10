---
name: intake-financial-data
description: Turn a client's raw notes into a retireplan Household definition, applying published standard assumptions where information is missing and asking only where the answer is a decision the client alone can make. Use before any scenario or simulation work for a client.
---

# Intake financial data

Produces `workspace/<name>/household.py` and, via
`python -m workspace.<name>.household`, a `household.json` the client can check.

Read `src/retireplan/model.py` for the schema rather than recalling it.
`workspace/sample_client/` is a complete fabricated worked example — notes,
household, and hand-verified arithmetic in
`tests/test_integration_sample_client.py` — worth reading once as a template.

**Real client directories are gitignored** (everything under `workspace/` except
`sample_client/`). Client names, salaries and balances must never be committed;
their absence from `git status` is not a problem to fix.

**Two things the engine already does — do not model them yourself:**

- **Surplus income is invested automatically**, split across the household into
  an ISA (to £20,000) then a GIA. An explicit "savings" `Asset` or `Expense`
  would double it. Ask only if the client's *actual* behaviour differs (all cash,
  or subscribing to a partner's ISA) — that is a real per-household fact.
- **A person with no ISA `Asset` gets a synthetic zero-balance one**, as they
  already did for a GIA, so no placeholder is needed to make sheltering possible.
  **But still record a real ISA whenever the client holds one**: the fallback
  opens at zero with a generic tracker return, so skipping a real account
  silently understates current wealth.

## Steps

1. Read `workspace/<name>/notes.txt`.
2. Map every stated fact onto `Person`, `IncomeSource`, `Expense`, `Debt`,
   `Asset`, `Goal`, `Assumptions`.
   - **For `Debt`, prefer `last_payment` (a date) over `remaining_months`.** A
     month count is correct only on the day it was stated and goes stale
     silently when the plan is regenerated. If the notes give a count, use
     `remaining_months` and say in the docstring that it needs re-stating —
     computing a date from a vague count just relocates the staleness.
   - **A client who stops contributing while still working is
     `Contribution.end`, not a scenario decision.** That is Coast FIRE:
     contribute until a date, then let the pot compound while salary, tax and NI
     carry on to an independently chosen retirement date. `start`/`end` default
     to `None` — active exactly as long as the linked salary — so set them only
     for a stated date.
3. **Choose each asset's `ReturnModel` deliberately** — the decision most likely
   to flatter a plan:

   | Model | Use for |
   |---|---|
   | `SampledSeries("global_equity")` | a tracker or equity fund |
   | `FixedNominal(rate)` | anything quoted as a headline yield — a bond held to maturity, a fixed-rate product, a savings account |
   | `FixedReal(rate)` | only where a real return is genuinely intended (property, index-linked) |

   Never model a quoted yield as `FixedReal`: that hands the client an
   inflation-proof return nothing offers. Check
   `MarketData.load().window([...])` before choosing a short-history series — it
   narrows the bootstrap for the whole simulation.
4. **Assume the standard; ask where it is a decision.** Load
   `standard-assumptions` for the default, direction of error and when a default
   is not good enough. In short: assume how the world behaves (mortality,
   inflation, care incidence, property growth); ask for facts the client holds
   or preferences only they can state.
   - **Never estimate a balance, salary, contribution or debt.**
   - **Always ask** the goal, flexibility around it, hard timing constraints,
     risk tolerance, and who the money should go to.
   - **Record every default used**, with source and direction, in the household
     docstring — it becomes the report's notes section.
   - Where the notes imply an answer, take the reading, say which and why, and
     invite correction rather than blocking.
   - **Ask for `Person.sex`**, awkward as it is: a unisex assumption is roughly
     three and a half years out per person and moves every bequest figure.
     Unstated blends the two evenly. Frame it as the actuarial input it is.
   - **Ask whether national-average longevity is wanted.** An affluent household
     typically outlives the tables by two to four years; `LifeTable(age_rating=…)`
     is the lever and defaults to no adjustment rather than applying one
     silently.
5. **Capture goals and flexibility as two separate questions.** The goal becomes
   one number for the base case; flexibility is what phase 2 turns into
   alternatives, and does not exist unless asked for now:
   - **Timing** — notice period (a real floor on "as early as possible"; it has
     no structured field, so record it in the docstring), willingness to phase
     down rather than stop, willingness to work later if needed.
   - **Spending** — would they cut in a downturn, and by how much (this is what
     makes a guardrail a deliberate choice)? And the opposite: is there headroom
     to spend more if the base case clears, or is the stated figure a ceiling?
   - **The goal itself** — hard requirement or opening position? A "£450k
     holiday house" that is really "£300k–£500k depending" is a materially more
     useful fact.

   Silence on any of these is worth recording as "did not specify" — but ask
   before assuming it.
6. Resolve ambiguity out loud. "House repairs, car replacement etc. £10,000/yr":
   essential or discretionary? For life, or only while there is a car? Take the
   defensible reading, record which and why, invite correction.
7. Call `household.validate()`, write `household.json`, and show the client a
   short summary to confirm before anything downstream uses it.

Every assumption goes in `household.py`'s module docstring, in the client's own
terms. That docstring is the audit trail: the report's notes section is written
from it, and a reader who disagrees with an assumption must be able to find it.
