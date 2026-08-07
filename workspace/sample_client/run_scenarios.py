"""Run every sample-client scenario and print a comparison table.

    .venv/bin/python3 -m workspace.sample_client.run_scenarios

**Not a real client.** See `household.py`.

This is the worked example the `run-scenario-simulation` skill points to.

Results are cached in `workspace/sample_client/.cache`, so re-running after an
unrelated edit is near-instant — only what actually changed re-computes. The
cache key covers the engine version, so it cannot outlive a change to the
logic that produced it.

Phase 1 runs `BASE_CASE` alone and prints its result before anything else, so
the phase 2 set below reads as a consequence of it rather than a template
chosen in advance. This script is for eyeballing the comparison; it is *not* a
dependency `build_report.py` needs run first — that re-runs everything itself
through the same cache.
"""
from __future__ import annotations

import time

from retireplan import CashBondLadder, run_monte_carlo

from .household import AS_OF, SAMPLE_CLIENT
from .scenarios import BASE_CASE, HEADLINE, RECOMMENDED, VARIANTS

N_TRIALS = 2000
SEED = 42
CACHE_DIR = "workspace/sample_client/.cache"

HEADER = (
    f"{'':38} {'success':>8} {'median spend':>13} "
    f"{'net p10':>10} {'net p50':>10} {'net p90':>10}"
)


def run_all(scenarios: dict, label: str = "") -> dict:
    """Run each scenario, printing a row per result.

    Always passes `seed` and `cache_dir`: a report whose numbers move each
    time it is regenerated is not a report.
    """
    if label:
        print(f"\n{label}")
        print(HEADER)
        print("-" * len(HEADER))
    results = {}
    for key, scenario in scenarios.items():
        started = time.time()
        result = run_monte_carlo(
            SAMPLE_CLIENT, scenario, AS_OF,
            n_trials=N_TRIALS, block_years=5, seed=SEED, cache_dir=CACHE_DIR,
        )
        results[key] = result
        if label:
            net = result.net_bequest_percentiles
            print(
                f"{key[:38]:38} {result.success_probability:>7.1%} "
                f"£{result.median_annual_spend:>12,.0f} "
                f"£{net[10]:>9,.0f} £{net[50]:>9,.0f} £{net[90]:>9,.0f}"
                f"  ({time.time() - started:.1f}s)"
            )
    return results


def sanity_check(results: dict, scenarios: dict) -> list[str]:
    """The checks from the `run-scenario-simulation` skill that can be automated.

    The ones that matter most cannot be: reading a fan chart, or noticing that
    a number is too good. This catches the mechanical subset so attention is
    left for the rest.

    `scenarios` is needed because a check without its context produces false
    positives, and a check that cries wolf gets ignored -- `CashBondLadder`
    holds cash on purpose, so the idle-cash check must not fire on it.
    """
    flags = []
    for key, r in results.items():
        scenario = scenarios.get(key)
        if r.success_probability in (0.0, 1.0):
            flags.append(
                f"{key}: success is exactly {r.success_probability:.0%} — check "
                f"sample_years ({r.sample_years}); a narrow window is the usual cause"
            )
        if r.sample_years < 40:
            flags.append(
                f"{key}: bootstrap window is only {r.sample_years} years "
                f"({r.sample_first_year}–{r.sample_last_year}) — too short to "
                f"contain a 1929- or 1973-scale crash"
            )
        holds_cash_deliberately = isinstance(
            getattr(scenario, "drawdown", None), CashBondLadder
        )
        cash = r.asset_type_percentiles.get("cash")
        if cash and not holds_cash_deliberately and max(cash[50]) > 25_000:
            flags.append(
                f"{key}: median cash peaks at £{max(cash[50]):,.0f} — cash should "
                f"be invested the plan-year it arrives, so a sustained balance "
                f"is a real finding, not a quirk"
            )
        bridge = r.bridge_before_access()
        if bridge and bridge[0] < 10_000:
            flags.append(
                f"{key}: bridge 10th percentile is £{bridge[0]:,.0f} the year "
                f"before pension access — worth a sentence in the report even "
                f"though the plan succeeded"
            )
    return flags


def main() -> None:
    base = run_all({"base_case": BASE_CASE}, label="PHASE 1: BASE CASE (run alone)")
    print(
        f"\nBASE_CASE: {base['base_case'].success_probability:.1%} over "
        f"{base['base_case'].sample_years} years of history "
        f"({base['base_case'].sample_first_year}–{base['base_case'].sample_last_year}). "
        f"Phase 2 below is a consequence of this number."
    )

    headline = run_all(HEADLINE, label="\nPHASE 2: HEADLINE SCENARIOS")
    variants = run_all(VARIANTS, label=f"VARIANTS on {RECOMMENDED:%B %Y}")

    flags = sanity_check(
        {**base, **headline, **variants},
        {"base_case": BASE_CASE, **HEADLINE, **VARIANTS},
    )
    print("\nSANITY CHECKS")
    if flags:
        for flag in flags:
            print(f"  ! {flag}")
    else:
        print("  no mechanical flags — the judgement-based checks still apply")


if __name__ == "__main__":
    main()
