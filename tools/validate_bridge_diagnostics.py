"""Check that `diagnose()`'s coverage ratios actually predict which family of
withdrawal rule wins, rather than only doing so for the one household that
suggested them.

REVIEW.md 1.18 measured three fabricated households and found that a rule
keyed off the whole portfolio helps a bridge by luck, while one keyed off the
accessible money helps on purpose. Two ratios were proposed as the screen:

    C = accessible money ÷ everything the bridge must draw   (`bridge_coverage`)
    E = the same against essential spending alone   (`essential_bridge_coverage`)

Three claims follow, and none of them is established by three data points:

    1. E < 1 caps what any withdrawal rule can achieve — the bridge is
       under-funded and spending rules are the wrong lever.
    2. C < 1 with E comfortable is where `BridgeGuardrail` earns its place.
    3. C well above 1 makes every bridge rule inert, so testing one is a
       wasted run.

This sweeps a grid — accessible share × spending level, total wealth and
allocation held constant — and reports the gain each rule family delivers
against the coverage ratio, so the bands in `define-scenarios` are read off a
surface rather than asserted from a corner of it.

Everything is fabricated: one person, £800,000, retiring at 50 with the
pension locked to 57, 60% equity throughout.

Run: .venv/bin/python tools/validate_bridge_diagnostics.py [n_trials]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from compare_withdrawal_rules import AS_OF, CACHE, WEALTH, household, scenario  # noqa: E402

from retireplan import (  # noqa: E402
    BridgeGuardrail,
    EndowmentSmoothing,
    PercentOfPortfolio,
    SpendNominal,
    compile_plan,
    diagnose,
    run_monte_carlo,
)
from retireplan.tax.uk import UK  # noqa: E402

ACCESSIBLE = (120_000.0, 160_000.0, 200_000.0, 240_000.0, 280_000.0, 320_000.0, 400_000.0)
SPEND = (34_000.0, 40_000.0, 46_000.0)
ESSENTIAL_SHARE = 0.65
"""Held constant across spending levels so that E and C move together with the
plan's size rather than with a changing definition of "essential"."""

BASELINE = "baseline"
BRIDGE_RULES = ("BridgeGuardrail", "BridgeGuardrail floor 0")
WHOLE_PORTFOLIO_RULES = ("PercentOfPortfolio", "EndowmentSmoothing")

RULES = {
    BASELINE: lambda: SpendNominal(),
    "BridgeGuardrail": lambda: BridgeGuardrail(),
    "BridgeGuardrail floor 0": lambda: BridgeGuardrail(floor=0.0),
    "PercentOfPortfolio": lambda: PercentOfPortfolio(rate=0.04),
    "EndowmentSmoothing": lambda: EndowmentSmoothing(),
}


def cell(accessible: float, spend: float, n_trials: int) -> dict:
    hh = household(
        50, isa=accessible,
        essential=spend * ESSENTIAL_SHARE,
        discretionary=spend * (1 - ESSENTIAL_SHARE),
    )
    d = diagnose(compile_plan(hh, scenario("screen", SpendNominal()), UK, AS_OF))
    success = {
        name: run_monte_carlo(hh, scenario(name, make()), AS_OF,
                              n_trials=n_trials, seed=42, cache_dir=CACHE).success_probability
        for name, make in RULES.items()
    }
    best = lambda names: max(success[n] for n in names)  # noqa: E731
    return {
        "spend": spend,
        "C": d.bridge_coverage,
        "E": d.essential_bridge_coverage,
        "draw": d.initial_draw_rate,
        "success": success,
        "bridge_gain": best(BRIDGE_RULES) - success[BASELINE],
        "whole_gain": best(WHOLE_PORTFOLIO_RULES) - success[BASELINE],
        "ceiling": max(success.values()),
    }


def band(value: float, edges: tuple[float, ...]) -> str:
    """Which half-open interval `value` falls in, as a label."""
    for lo, hi in zip((0.0,) + edges, edges + (float("inf"),)):
        if lo <= value < hi:
            return f"{lo:.1f}–{hi:.1f}" if hi != float("inf") else f"{lo:.1f}+"
    return "?"


def summarise(cells: list[dict], key: str, edges: tuple[float, ...], *, of: str) -> None:
    grouped: dict[str, list[float]] = {}
    for c in cells:
        grouped.setdefault(band(c[key], edges), []).append(c[of])
    print(f"\n  {key} band     n   mean {of}     range")
    for label in sorted(grouped, key=lambda s: float(s.split("–")[0].rstrip("+"))):
        values = grouped[label]
        print(f"  {label:<12} {len(values):>3}   {sum(values) / len(values):>+9.1%}   "
              f"{min(values):>+7.1%} to {max(values):>+7.1%}")


def main() -> None:
    n_trials = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    print(f"{n_trials} trials per cell, £{WEALTH:,.0f} total, retiring at 50, "
          f"pension locked to 57\n")

    header = (f"{'spend':>7} {'access':>8} {'C':>6} {'E':>6} {'draw':>6} | "
              + " ".join(f"{n[:9]:>9}" for n in RULES)
              + f" | {'bridge':>7} {'whole':>7}")
    print(header)

    cells = []
    for accessible in ACCESSIBLE:
        for spend in SPEND:
            c = cell(accessible, spend, n_trials)
            cells.append(c)
            print(f"{spend:>7,.0f} {accessible:>8,.0f} {c['C']:>6.2f} {c['E']:>6.2f} "
                  f"{c['draw']:>6.1%} | "
                  + " ".join(f"{c['success'][n]:>9.1%}" for n in RULES)
                  + f" | {c['bridge_gain']:>+7.1%} {c['whole_gain']:>+7.1%}")

    print("\n--- Claim 1: below E = 1 no withdrawal rule rescues the plan ---")
    summarise(cells, "E", (0.8, 1.0, 1.2, 1.5), of="ceiling")

    print("\n--- Claim 2: BridgeGuardrail earns its place where C is below 1 ---")
    summarise(cells, "C", (0.6, 0.8, 1.0, 1.2), of="bridge_gain")

    print("\n--- Claim 3: a whole-portfolio rule's gain is not about the bridge ---")
    summarise(cells, "C", (0.6, 0.8, 1.0, 1.2), of="whole_gain")


if __name__ == "__main__":
    main()
