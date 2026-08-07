---
name: intake-financial-data
description: Turn a client's raw notes into a retireplan Household definition, applying published standard assumptions where information is missing and asking only where the answer is a decision the client alone can make. Use before any scenario or simulation work for a client.
---

# Intake financial data

Produces `workspace/<name>/household.py` (a `Household` from the `retireplan`
package) and, via `python -m workspace.<name>.household`, a `household.json`
snapshot the client can check.

Read `src/retireplan/model.py` for the current schema rather than relying on
memory of it. `workspace/sample_client/` is a fabricated but complete worked
example — notes, household, and the hand-verified arithmetic behind it in
`tests/test_integration_sample_client.py` — worth reading once as a template.

**Surplus income is invested automatically — you don't need to model it.**
Every plan-year that income exceeds spending, the engine splits the surplus
equally across the household's people and routes it into an ISA (up to the
£20,000 annual allowance) then a GIA for the rest. Do not add an explicit
"savings" `Asset` or `Expense` to model this — it would double it. Only ask
the client about this if their *actual* behaviour is meant to differ from
that default (they hold everything in cash, say, or subscribe to a partner's
ISA instead of their own) — that is a real per-household fact worth
capturing, the mechanism above is not.

**A person with no ISA `Asset` gets one anyway — `plan.py` synthesises a
zero-balance ISA per person who doesn't already have one, the same way it
already synthesises a GIA.** You do not need to add a placeholder to make
sheltering possible; that used to be a real gap (a household with no ISA
`Asset` had nowhere for surplus, a PCLS or Bed-and-ISA to shelter money, for
the whole plan, with no error — it once understated a PCLS comparison by
tens of thousands of pounds) and is now closed at the engine level.

**Still record an explicit `ISA` `Asset` whenever the client actually holds
one.** The synthetic fallback opens at zero and uses a generic tracker
return — it is a safety net for "holds none today," not a substitute for the
client's real account, its real balance, or a return model that actually
matches what it's invested in. Skipping a real ISA because "the engine will
add one anyway" silently understates the household's current wealth.

**Real client directories are gitignored** (everything under `workspace/`
except `workspace/sample_client/` — see `.gitignore`). That is deliberate:
client names, salaries and balances must never be committed. Do not add a
real client directory to git, and do not treat its absence from `git status`
after a fresh checkout as a problem to fix.

## Steps

1. Read the client's raw notes (`workspace/<name>/notes.txt`).
2. Map every stated fact onto the model: `Person`, `IncomeSource`, `Expense`,
   `Debt`, `Asset`, `Goal`, `Assumptions`.
   - **For `Debt`, prefer `last_payment` (a date) over `remaining_months` (a
     count) whenever the client can give one.** A month count is only ever
     correct on the day it was stated and silently goes stale the moment the
     plan is regenerated later — a real mortgage balance updated without its
     term being updated to match is what this was built to stop happening
     again. If the notes say "N months/years remaining" rather than a date,
     use `remaining_months` and note in the docstring that it will need
     re-stating if the plan sits unused for a while; don't compute a
     `last_payment` date yourself from a vague count, that just relocates
     the same staleness one step earlier.
3. **Choose each asset's `ReturnModel` deliberately** — this is the decision
   most likely to flatter a plan:
   - `SampledSeries("global_equity")` — a tracker or equity fund.
   - `FixedNominal(rate)` — anything quoted as a headline yield: a bond held
     to maturity, a fixed-rate product, a savings account. The rate is
     *nominal*, so inflation decides what it is really worth. Never model a
     quoted yield as `FixedReal`; that hands the client an inflation-proof
     return nothing actually offers.
   - `FixedReal(rate)` — only where a real return is genuinely intended
     (property assumptions, index-linked instruments).
   - Check `MarketData.load().window([...])` before choosing a series with
     short history: it narrows the bootstrap for the *whole* simulation.
4. **Assume the standard; ask where it is a decision.** Load
   `standard-assumptions` — it holds the published default for each common
   gap, which way each errs, and the rule for when a default is not good
   enough. In short: assume how the world behaves (mortality, inflation, care
   incidence, property growth), ask about anything that is a fact the client
   holds or a preference only they can state.
   - **Never estimate a balance, salary, contribution or debt.** Those are
     facts they can look up, and a plan built on a guessed balance is worth
     nothing.
   - **Always ask** the goal, the flexibility around it, any hard constraint
     on timing, risk tolerance, and who the money should go to.
   - **Record every default you used**, with its source and direction, in the
     household docstring. It becomes the report's notes section.
   - Where the notes imply an answer without stating it, take the reading,
     say which you took and why, and invite correction rather than blocking.
   - **`Person.sex` is worth asking for**, awkward as it is: mortality rates
     differ enough that a unisex assumption is roughly three and a half years
     out per person, which moves every bequest figure. Unstated blends the
     two evenly, which is honest but less accurate. Frame it as the actuarial
     input it is.
   - **Ask whether national-average longevity is wanted.** An affluent
     household typically outlives the published tables by two to four years;
     `LifeTable(age_rating=...)` is the lever, and it defaults to no
     adjustment rather than applying one silently.

5. **Capture goals and flexibility as two separate questions, not one.** This
   is step 2 of the core process (see the `retirement-planner` agent) and it
   is not satisfied by recording the goal alone. A goal ("retire as early as
   possible", a target date, a purchase) becomes exactly one number for the
   base case in step 3. Flexibility is what step 4 later turns into
   alternatives — it does not exist yet unless you ask for it now:
   - **Timing**: notice period at work (a real floor on "as early as
     possible", not in the model's structured fields — record it in the
     household docstring), willingness to work part-time or phase down
     rather than stop outright, willingness to work *later* than hoped if
     the base case needs it.
   - **Spending**: would they cut spending in a downturn, and roughly how
     much — this is what a guardrail strategy needs to be worth choosing
     deliberately rather than defaulted to. Also ask the opposite: is there
     headroom to spend *more* if the base case clears comfortably, or is the
     stated spending figure already their ceiling?
   - **The goal itself**: is the stated date or amount a hard requirement or
     an opening position? A "£450k holiday house" goal that's actually
     "somewhere between £300k and £500k depending on what we can afford" is
     a materially different, more useful fact than a single number.
   Silence on any of these is itself information worth recording ("did not
   specify") — but ask before assuming it.
6. Resolve ambiguity out loud rather than silently. "House repairs, car
   replacement etc. £10,000/yr": essential or discretionary? For life, or only
   while there is a car to replace? Take the defensible reading, record which
   one and why, and invite correction — see `standard-assumptions`.
7. Call `household.validate()`, then write `household.json` and show the
   client a short summary to confirm before anything downstream uses it.

## Recording assumptions

Every assumption you had to make goes in the module docstring of
`household.py`, in the client's own terms. That docstring is the audit trail —
the report's notes section is written from it, and a reader who disagrees with an
assumption needs to be able to find it.
