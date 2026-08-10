---
name: run-scenario-simulation
description: Run retireplan Monte Carlo simulations for a client's scenarios and sanity-check the output. Use after define-scenarios and before build-retirement-report.
---

# Run scenario simulation

This is arithmetic, so it runs as code — never re-derive a figure in prose.

Used twice per engagement, matching `define-scenarios`' phases: once for the
base case alone, again for the `HEADLINE` set. The checks below apply equally
both times — every alternative is compared against the base case.

```bash
.venv/bin/python3 -m workspace.<name>.run_scenarios
```

Each scenario goes through `retireplan.run_monte_carlo(household, scenario,
as_of, n_trials=2000, seed=42, cache_dir="workspace/<name>/.cache")`.

- **Always pass `cache_dir`** — an unchanged scenario then returns in
  milliseconds.
- **Always pass `seed`** for anything reported. Numbers that move on every
  regeneration are not a report.
- **`run_scenarios.py` is for eyeballing a comparison table**, not a dependency
  of `build_report.py`, which re-runs every scenario through the same cache. Do
  not duplicate a `run(...)` helper between them.
- **Every `ReturnModel` an asset can use needs a case in `serde.py`.** A missing
  one makes `run_monte_carlo(..., cache_dir=...)` fail outright — this happened
  with a fully exported, documented model (`HeldToMaturityCredit`) that was
  never wired up. Check `serde.py` before assuming the household is wrong.
- **A wide sweep is many full cache misses, not one.** `cache_key()` hashes the
  whole scenario including its `name`, so runs differing only by quarter or rule
  share nothing. Each 2,000-trial call costs seconds of single-threaded pure
  Python, so a sweep of dozens of points is minutes — trivially parallelizable
  across processes, though nothing does that today.

## Sanity-check before handing on

1. **Exactly 0% or 100% is a red flag, not a result.** Across thousands of
   trials it usually means the sample lacks diversity — check
   `result.sample_years` first.

   **The second cause is an adjusting rule, and is not a bug.**
   `GuytonKlinger`, `PercentOfPortfolio` and `VariablePercentage` cut spending
   to fit what remains, converting failure risk into income volatility, and can
   legitimately reach 100%. Confirm via the spend percentiles: a real 100% comes
   with a worst case well below the median — one scenario scored 1.0 while its
   worst 5% of years spent 71% of the median. "Did not fail because it spent
   less" is a much weaker claim than "always works". **Never report 100% for an
   adjusting rule without the worst-case spend beside it.**
2. **Check the sampling window** — `sample_years`, `sample_first_year`,
   `sample_last_year`. Short history narrows the bootstrap for the entire
   simulation, and a window excluding 1929 and the 1970s looks far safer than
   reality. Report the window wherever you report the probability.
3. **Check the percentile bands are ordered** and wealth paths are possible.
4. **Compare against the previous run** when the engine or data changed. A moved
   number is fine; an unexplained one is not.
5. **Pull `result.bridge_before_access()`, never `bridge_at_access()`**, for
   every scenario retiring before pension access. A 98% success probability can
   hide a bridge down to its last few thousand pounds in a bad decile. Use the
   *before* variant because a strategy drawing pension aggressively at unlock
   can recycle surplus into the ISA in that same plan-year: confirmed against a
   real client where every failing trial showed a healthy `bridge_at_access()`
   despite running dry twelve months earlier. `None` means no DC pension to
   unlock, or access already reached in the first plan-year — it does *not* mean
   access happens at retirement, since someone modelled well before their access
   age still gets a real bridge range. A low end near zero deserves a sentence
   in the report even where the plan technically succeeded.
6. **A failed trial is not necessarily a ruined one.** `success_probability`
   counts one bad year anywhere in the horizon the same as total collapse.
   Inspect the failing trials — total unmet shortfall, number of bad years, the
   single worst — before saying a scenario ran dry "and never recovered": the
   assets can fully recover once a pension unlocks the next year.
7. **The engine has no resolution finer than a plan-year.** A one-off dated near
   a pension-access birthday resolves against whichever plan-year the birthday
   falls in (see `dc_accessible_by_person` in `plan.py`). The trade-off
   deliberately never delays access past the birthday, so a result can look
   slightly more generous than the exact legal date. Check that field before
   trusting a number right at an access boundary.
8. **Cash should not accumulate.** Every legitimate source — surplus, a PCLS, a
   DB lump sum — is invested the plan-year it arrives, so `__cash_reserve` sits
   at or near zero. A sustained balance in `asset_type_percentiles["cash"]` is a
   finding to investigate, not a quirk to caption around.
9. **A GIA that never drains into the ISA is worth investigating**, though a
   missing ISA `Asset` is no longer the cause. Bed-and-ISA should migrate a GIA
   balance within a few years of a lump sum or sustained surplus. If `["gia"]`
   keeps growing while `["isa"]` stays flat, check whether ISA headroom is
   consumed elsewhere that year (`isa_headroom_used`) before trusting the tax
   figures. See `uk-pension-tax-strategy`'s GIA section.

## When results look wrong

Run one deterministic projection and read it year by year — a broken mechanism
is far easier to spot in a single path than in an aggregate:

```python
from retireplan import project_once
projection = project_once(household, scenario, as_of)
for y in projection.years:
    print(y.year, y.essential_spending, y.isa_withdrawn, y.dc_withdrawn_gross, y.unmet_shortfall)
```

Then say plainly what you found. Do not smooth over a number you cannot explain.
