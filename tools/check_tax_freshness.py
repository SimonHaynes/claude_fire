"""What tax and legislation figures are due to be rechecked, and against what.

`retireplan.tax.provenance` records, for every figure the engine hardcodes, the
source that establishes it, when it was last checked and when it should be
checked again. This turns that register into a work list.

Run it before writing anything a client will read. A report is a dated claim
about the law, and the cheapest moment to discover a stale allowance is before
the number is in a PDF.

    .venv/bin/python tools/check_tax_freshness.py              # what is due now
    .venv/bin/python tools/check_tax_freshness.py --all        # the whole register
    .venv/bin/python tools/check_tax_freshness.py --check-urls # are the sources still there
    .venv/bin/python tools/check_tax_freshness.py --as-of 2027-04-06

Exit status is 1 when something is due, so it works as a pre-report gate.

Clearing an item is the `verify-tax-figures` skill: check the figure against
the source, update the constant if it moved, move `checked_on` and `recheck_by`
together, and say in the report which figures were verified and which were not.
Moving `checked_on` without opening the source is the one thing that makes this
register worse than having none.
"""
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from retireplan.tax import provenance  # noqa: E402

MODULE_VERIFIED_ON = {
    "retireplan.tax.uk": "UK",
    "retireplan.tax.iht": "UK_IHT",
    "retireplan.tax.trusts": "UK_RELEVANT_PROPERTY",
}
"""Modules exposing a rules object with a `verified_on`, so the register and the
constant can be checked against each other rather than drifting apart."""


def show(source: provenance.Source, as_of: date) -> None:
    checked = f"{source.checked_on:%d %b %Y}" if source.checked_on else "never recorded"
    overdue = (as_of - source.recheck_by).days
    when = (
        f"due {overdue} days ago" if overdue >= 0
        else f"due in {-overdue} days ({source.recheck_by:%d %b %Y})"
    )
    print(f"  {source.covers}")
    print(f"    module     {source.module}")
    print(f"    source     {source.url}")
    print(f"    checked    {checked}")
    print(f"    recheck    {when}")
    print(f"    moved by   {source.moved_by}")
    print()


def check_urls(sources: tuple[provenance.Source, ...]) -> int:
    """A source that 404s is worse than no source: it makes a recheck look done.

    gov.uk reorganises guidance without redirecting, so this drifts on its own
    over time rather than only when someone edits the register.
    """
    seen: set[str] = set()
    broken = 0
    for source in sources:
        if source.url in seen:
            continue
        seen.add(source.url)
        request = urllib.request.Request(source.url, headers={"User-Agent": "retireplan"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
        except OSError as exc:
            print(f"  [ERROR] {source.url}\n          {exc}")
            broken += 1
            continue
        if status >= 400:
            print(f"  [{status}] {source.url}")
            broken += 1
        else:
            print(f"  [{status}] {source.url}")
    return broken


def check_agreement(as_of: date) -> int:
    """Whether each module's own `verified_on` matches its oldest recorded check."""
    import importlib

    problems = 0
    for module_name, attribute in MODULE_VERIFIED_ON.items():
        recorded = provenance.last_checked(module_name)
        rules = getattr(importlib.import_module(module_name), attribute)
        if recorded is None:
            print(f"  [FAIL] {module_name}: register has an unchecked source, but "
                  f"{attribute}.verified_on claims {rules.verified_on:%d %b %Y}")
            problems += 1
        elif rules.verified_on != recorded:
            print(f"  [FAIL] {module_name}: {attribute}.verified_on is "
                  f"{rules.verified_on:%d %b %Y}, register's oldest check is "
                  f"{recorded:%d %b %Y}")
            problems += 1
        else:
            print(f"  [ok]   {module_name}: {recorded:%d %b %Y}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--all", action="store_true", help="print the whole register")
    parser.add_argument("--check-urls", action="store_true",
                        help="fetch every source to see it still exists")
    parser.add_argument("--horizon", type=int, default=90,
                        help="days ahead to count as upcoming (default 90)")
    args = parser.parse_args(argv)

    due = provenance.due(args.as_of)
    soon = provenance.upcoming(args.as_of, args.horizon)

    print(f"Tax figure register as at {args.as_of:%d %b %Y}\n")

    if args.all:
        print(f"All {len(provenance.SOURCES)} sources\n")
        for source in provenance.SOURCES:
            show(source, args.as_of)

    if due:
        print(f"DUE NOW ({len(due)})\n")
        for source in due:
            show(source, args.as_of)
    else:
        print("Nothing due.\n")

    if soon:
        print(f"DUE WITHIN {args.horizon} DAYS ({len(soon)})\n")
        for source in soon:
            show(source, args.as_of)

    print("Register against the modules' own verified_on")
    disagreements = check_agreement(args.as_of)
    print()

    if args.check_urls:
        print("Sources still reachable")
        broken = check_urls(provenance.SOURCES)
        print()
        if broken:
            print(f"{broken} source(s) unreachable — find the replacement page and "
                  "update the register, do not delete the entry.")
            return 1

    if due or disagreements:
        print("Clear these with the `verify-tax-figures` skill before quoting any "
              "figure to a client.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
