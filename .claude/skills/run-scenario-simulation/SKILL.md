---
name: run-scenario-simulation
description: Run retireplan Monte Carlo simulations for a client's scenarios and sanity-check the output. Use after define-scenarios and before build-retirement-report.
---

# Run scenario simulation

This is arithmetic, so it runs as code — never re-derive a figure in prose.

Used twice per engagement, matching `define-scenarios`' two phases: once to
run the single base case before any alternative is chosen, and again once
`define-scenarios` has turned the base case's result into a real `HEADLINE`
set. The sanity-checks below apply the same way both times — a base case
deserves the same scrutiny as a headline scenario, since it's what every
alternative gets compared against.

```bash
.venv/bin/python3 -m workspace.<name>.run_scenarios
```

Each scenario goes through `retireplan.run_monte_carlo(household, scenario,
as_of, n_trials=2000, seed=42, cache_dir="workspace/<name>/.cache")`.

- **Always pass `cache_dir`.** Re-running an unchanged scenario then returns in
  milliseconds; only what actually changed re-computes.
- **Always pass `seed`** for anything that will appear in a report. A report
  whose numbers move each time it is regenerated is not a report.
- **`run_scenarios.py` is for eyeballing a comparison table before you write
  prose — it is not a dependency `build_report.py` needs run first.**
  `build_report.py` re-runs every scenario itself through the same cache, so
  an unchanged scenario returns instantly either way. Do not duplicate a
  `run(...)` helper between the two scripts; write it once and import it if
  both genuinely need it.
- **Every `ReturnModel` an asset can use needs a case in
  `retireplan/serde.py`.** If one is missing, `run_monte_carlo(...,
  cache_dir=...)` fails outright the moment a household uses that asset —
  this has happened with a fully-exported, documented model
  (`HeldToMaturityCredit`) that simply hadn't been wired up yet. If caching
  fails on a model that looks otherwise fine, check `serde.py` before
  assuming the household is wrong.

## Sanity-check before handing on

1. **A success probability of exactly 0% or 100% is a red flag, not a
   result.** Across thousands of trials it almost always means the sample has
   no diversity rather than that the outcome is certain. Check
   `result.sample_years` first — a narrow window is the usual cause.

   **The second cause is an adjusting withdrawal rule**, and it is not a bug.
   `GuytonKlinger`, `PercentOfPortfolio` and `VariablePercentage` cut spending
   to fit what remains, so they convert failure risk into income volatility
   and can legitimately reach 100%. Confirm it by looking at the spend
   percentiles: a real 100% comes with a worst-case spend well below the
   median. One headline scenario scored exactly 1.0 over the full 98-year
   window while its worst 5% of years spent 71% of the median — the plan did
   not fail because it spent less, which is a different and much weaker claim
   than "this plan always works". **Never report 100% for an adjusting rule
   without the worst-case spend beside it.**
2. **Check the sampling window.** `sample_years`, `sample_first_year`,
   `sample_last_year` are on every result. A series with short history narrows
   the bootstrap for the *entire* simulation, and a window that excludes 1929
   and the 1970s will look far safer than reality. Report the window wherever
   you report the probability.
3. **Check the percentile bands are ordered** and that wealth paths do not
   behave impossibly.
4. **Compare against the previous run** when the engine or data changed. A
   moved number is fine; an unexplained moved number is not.
5. **Pull `result.bridge_before_access()` — not `bridge_at_access()` — for
   every scenario that retires before pension access.** A 98% success
   probability can still hide a bridge that was down to its last few
   thousand pounds in a bad decile — the median success figure does not
   tell you that, the range does. Use the *before* variant: a strategy that
   draws pension aggressively once it unlocks can recycle surplus straight
   into the ISA the same plan-year access begins, so `bridge_at_access()`
   can already reflect a refill and look fine even for trials that already
   failed the year before — confirmed against a real client's numbers,
   where every failing trial in one scenario showed a healthy
   `bridge_at_access()` balance despite having run the bridge dry twelve
   months earlier. `None` means the household has no DC pension to unlock,
   or it's accessible from day one (nothing to check). A range whose low
   end is close to zero is worth a sentence in the report even if the plan
   technically succeeded.
6. **A failed trial is not necessarily a ruined one — check before saying
   so.** `success_probability` is a single bad year anywhere in the whole
   horizon counting the same as total collapse. Look at the failing trials
   specifically (total unmet shortfall, number of bad years, the single
   worst year) before describing a scenario as running dry "and never
   recovering" — the asset picture can fully recover once a pension unlocks
   the next year even though the trial is already counted as failed.
7. **The engine has no resolution finer than a plan-year.** A one-off spend or
   goal dated close to a pension-access birthday is resolved against whichever
   plan-year that birthday falls in, not the exact day — see
   `dc_accessible_by_person` in `plan.py`. It is deliberately the version of
   this trade-off that never delays access past the birthday, so a result can
   occasionally look a little more generous than the exact legal date allows.
   If a result right at an access boundary looks suspiciously good or bad,
   check `dc_accessible_by_person` for that year before trusting the number.
8. **Cash should not accumulate.** Every legitimate source of cash — ordinary
   surplus, a PCLS, a DB lump sum — is invested the same plan-year it arrives
   (`uk-pension-tax-strategy` covers the mechanism), so `__cash_reserve`
   should sit at or near zero throughout. A visible, sustained balance in
   `result.asset_type_percentiles["cash"]` or a fan chart is a real finding to
   investigate, not a quirk to caption around.

## When results look wrong

Run a single deterministic projection and read it year by year — it is far
easier to spot a broken mechanism in one path than in an aggregate:

```python
from retireplan import project_once
projection = project_once(household, scenario, as_of)
for y in projection.years:
    print(y.year, y.essential_spending, y.isa_withdrawn, y.dc_withdrawn_gross, y.unmet_shortfall)
```

Then say plainly what you found. Do not smooth over a number you cannot
explain.
