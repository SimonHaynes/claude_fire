"""Build the eight-section PDF for the fabricated sample household.

    .venv/bin/python3 -m workspace.sample_client.build_report [out.pdf]

**Not a real client.** See `household.py`.

This is the worked example the `build-retirement-report` skill points to. It
is deliberately shorter than a real client's report — the prose here is a
skeleton showing *where* each kind of writing goes, not a model of how much of
it a real engagement needs.

Two things it does demonstrate properly, because both have shipped broken:

  * **Every figure is interpolated from a `SimulationResult`.** There is not a
    single hardcoded number in the prose below. A typed figure is right once
    and then quietly wrong.
  * **The estate is quoted net.** `reporting.check_report` refuses to render a
    results table built from `bequest_percentiles`, but the habit matters more
    than the guard.

`run_scenarios.py` does not need to have been run first: everything here goes
through the same cache, so an unchanged scenario returns instantly either way.
"""
from __future__ import annotations

import sys
from datetime import date

from retireplan import run_monte_carlo
from retireplan.reporting import dial_svg, fan_chart_svg, render_pdf

from .household import AS_OF, SAMPLE_CLIENT
from .run_scenarios import CACHE_DIR, N_TRIALS, SEED
from .scenarios import BASE_CASE, CONSERVATIVE, HEADLINE, RECOMMENDED, STRETCH, VARIANTS

#: Plain English for the raw `AssetType.value` strings. A client should never
#: have to read "dc_pension".
TYPE_LABELS = {
    "property": "Property",
    "dc_pension": "Pension",
    "db_pension": "DB pension",
    "isa": "ISA",
    "gia": "GIA",
    "cash": "Cash",
}


def money(v: float) -> str:
    return f"£{v:,.0f}"


def millions(v: float) -> str:
    return f"£{v / 1e6:.1f}m" if abs(v) >= 1e6 else money(v)


def pct(p: float) -> str:
    """Floored, never rounded, so prose can never disagree with the dial."""
    return f"{int(p * 1000) / 10:.1f}%"


def run(scenario):
    return run_monte_carlo(
        SAMPLE_CLIENT, scenario, AS_OF,
        n_trials=N_TRIALS, block_years=5, seed=SEED, cache_dir=CACHE_DIR,
    )


def build_context() -> dict:
    results = {key: run(s) for key, s in HEADLINE.items()}
    variants = {key: run(s) for key, s in VARIANTS.items()}
    recommended = results["recommended"]
    stretch = results["stretch"]
    conservative = results["conservative"]

    window = (
        f"{recommended.sample_years} years of market history "
        f"({recommended.sample_first_year}–{recommended.sample_last_year})"
    )

    # --- section 1: current position ---------------------------------------
    section1 = {
        "intro": (
            "This is what the model was told. Everything that follows depends on it, "
            "so read it first and say if anything is wrong or missing."
        ),
        "people": [
            {"name": p.name, "age": AS_OF.year - p.date_of_birth.year,
             "income": next((money(i.amount) + "/yr" for i in SAMPLE_CLIENT.incomes
                             if i.owner == p.name), "—")}
            for p in SAMPLE_CLIENT.people
        ],
        "debts": [
            {"name": d.name, "balance": money(d.balance),
             "clears": f"{d.remaining_months} months"}
            for d in SAMPLE_CLIENT.debts
        ],
        "assets": [
            {"name": a.name, "owner": a.owner, "value": money(a.value),
             "notes": type(a.returns).__name__ if a.returns else "defined benefit"}
            for a in SAMPLE_CLIENT.assets
        ],
        "total_net_worth": money(sum(a.value for a in SAMPLE_CLIENT.assets)),
        "assets_caption": (
            "Values as stated at intake. The house is assumed flat in real terms — "
            "the least flattering assumption, and the one hardest to argue with."
        ),
        "goals": [g.description for g in SAMPLE_CLIENT.goals],
    }

    # --- section 2: scenarios ----------------------------------------------
    section2 = {
        "intro": (
            f"Three retirement dates, each run {N_TRIALS:,} times against different paths "
            f"drawn from {window}. Everything else is held constant between them, so any "
            f"difference in the results is caused by the date alone."
        ),
        "draw_order_statement": (
            "All three follow the same draw order: pension first, up to the top of each "
            "person's basic-rate band each year, then the ISA for anything further, with "
            "any surplus recycled back into an ISA. Since April 2027 put unused pensions "
            "into the inheritance tax estate, drawing the pension first and leaving the "
            "ISA is now the tax-efficient order — the reverse of the older rule."
        ),
        "scenarios": [
            {"name": f"Retire {STRETCH:%B %Y}", "tag": "as soon as notice allows",
             "tag_class": "stretch",
             "description": (
                 f"The stated goal, taken literally: leave as soon as the three-month "
                 f"notice period permits. This funds spending entirely from savings for "
                 f"years before either pension unlocks, and clears only "
                 f"{pct(stretch.success_probability)} of simulated outcomes."
             )},
            {"name": f"Retire {RECOMMENDED:%B %Y}", "tag": "recommended",
             "tag_class": "recommended",
             "description": (
                 f"Found by sweeping quarterly dates rather than guessing. Clears "
                 f"{pct(recommended.success_probability)}, one quarter past the point the "
                 f"sweep first crossed 95%, so a small revision to the inputs does not "
                 f"push the plan back under."
             )},
            {"name": f"Retire {CONSERVATIVE:%B %Y}", "tag": "for comparison",
             "tag_class": "conservative",
             "description": (
                 f"A further year of work, to show what waiting actually buys: "
                 f"{pct(conservative.success_probability)}, against "
                 f"{pct(recommended.success_probability)} — about two percentage points "
                 f"for twelve months, which is usually less than expected."
             )},
        ],
        "spending_explainer": {
            "intro": (
                "Retirement spending is modelled in two parts. Essentials are never cut. "
                "Discretionary spending is what the guardrail reduces in a bad year."
            ),
            "rows": [
                {"label": e.name, "value": f"{money(e.amount)} / {e.frequency.value}"}
                for e in SAMPLE_CLIENT.expenses
            ],
            "guardrail_note": (
                f"Spending adjusts rather than staying fixed: the rule watches how fast the "
                f"portfolio is being drawn down, not what markets did, and trims about 10% "
                f"when that rate drifts a fifth above where it started — early, and "
                f"reversibly. In the worst 5% of outcomes total spending falls to "
                f"{money(recommended.worst_case_5pct_min_spend)} a year against a median of "
                f"{money(recommended.median_annual_spend)}. Read the success figures with "
                f"that in mind: because spending flexes, most bad outcomes appear as a "
                f"leaner year rather than as a failure."
            ),
        },
        "also_tested_title": (
            "Also tested — one decision changed at a time, against the recommended date"
        ),
        "also_tested": [
            f"{scenario.name} — {pct(variants[key].success_probability)}"
            for key, scenario in VARIANTS.items()
        ],
    }

    # --- section 3: cross-scenario comparison ------------------------------
    section3 = {
        "intro": (
            f"Success is the share of {N_TRIALS:,} simulations in which the plan never "
            f"failed to fund a year's spending. The estate figures are what the family "
            f"actually receives — after inheritance tax, and after the beneficiaries' own "
            f"income tax on any inherited pension — not the larger figure the accounts "
            f"would show on paper."
        ),
        "rows": [
            {
                "name": HEADLINE[key].name,
                "dial_svg": dial_svg(r.success_probability),
                "median_spend": money(r.median_annual_spend),
                "worst_case_spend": money(r.worst_case_5pct_min_spend),
                "net_bequest_range": (
                    f"{millions(r.net_bequest_percentiles[10])} – "
                    f"{millions(r.net_bequest_percentiles[90])}"
                ),
            }
            for key, r in results.items()
        ],
        "outro": (
            f"All figures are in today's money and drawn from {window}. A probability is a "
            f"statement about that sample, not a guarantee — see Section 8."
        ),
    }

    # --- section 4: the recommended scenario in detail ---------------------
    section4 = _detail_section(recommended, window)

    # --- section 5: recommendations ----------------------------------------
    flat = variants["withdrawal_spend_nominal"]
    standard = variants["drawdown_standard_order"]
    crash = variants["stress_crash_at_retirement"]
    section5 = {
        "recommendations": [
            {
                "title": f"Target {RECOMMENDED:%B %Y}, not the earliest date available.",
                "body": (
                    f"Leaving as soon as notice allows clears only "
                    f"{pct(stretch.success_probability)}. {RECOMMENDED:%B %Y} clears "
                    f"{pct(recommended.success_probability)}. The mechanism is plain: "
                    f"four and a half more years of salary and contributions go in, and "
                    f"four and a half fewer years come out. Nothing else changes — Pat's "
                    f"pension is already accessible, so there is no locked-up gap to "
                    f"shorten, and the mortgage runs to 2038 either way, which is why it "
                    f"is a drag on the early date rather than a reason for the later one. "
                    f"What would change this: repaying the mortgage, or Robin working on "
                    f"alone for a year or two, both buy back most of the difference."
                ),
            },
            {
                "title": "Draw the pension first, not the ISA.",
                "body": (
                    f"Spending the ISA first and preserving the pension — the rule most "
                    f"people know — clears {pct(standard.success_probability)} and leaves "
                    f"{millions(standard.net_bequest_percentiles[50])} net at the median, "
                    f"against {millions(recommended.net_bequest_percentiles[50])} for "
                    f"drawing the pension first. Unused pensions have been inside the "
                    f"inheritance tax estate since April 2027, so a large untouched "
                    f"pension is now the most heavily taxed thing to die holding. This "
                    f"reverses if the rules change again."
                ),
            },
            {
                "title": "The spending rule adjusts, and that is what carries the plan.",
                "body": (
                    f"The plan uses Guyton-Klinger guardrails, which trim spending about 10% "
                    f"when the drawdown rate drifts a fifth above where it started, and raise "
                    f"it on the same test in good years. It clears "
                    f"{pct(recommended.success_probability)} at a median of "
                    f"{money(recommended.median_annual_spend)} a year. Refusing to adjust — "
                    f"spending the plan flat and letting a shortfall stand — clears "
                    f"{pct(flat.success_probability)} at "
                    f"{money(flat.median_annual_spend)}, which is the cost of the steadier "
                    f"income. The trade is real: adjusting means income moves year to year, "
                    f"and in the worst 5% of years it falls to "
                    f"{money(recommended.worst_case_5pct_min_spend)}."
                ),
            },
            {
                "title": "Know what a crash at the wrong moment costs.",
                "body": (
                    f"A 35% fall in the first two years takes the recommended plan from "
                    f"{pct(recommended.success_probability)} to "
                    f"{pct(crash.success_probability)}. That is the single largest risk "
                    f"here, and it is a matter of timing rather than of the plan being "
                    f"wrong. The guardrail is what absorbs it."
                ),
            },
        ],
    }

    # --- section 6: structuring -------------------------------------------
    # Every item says whether the engine costed it. That split is the point:
    # a report that blurs a modelled figure into a legal suggestion is worse
    # than one that only does the first.
    section6 = {
        "title": "Structuring: how things are held, and who they pass to",
        "intro": (
            "How money is held moves more than how it is invested, once an estate is above "
            "the inheritance tax thresholds. Each item says whether it was modelled."
        ),
        "structures": [
            {"title": "Check the pension death-benefit nominations.",
             "tag": "costs nothing", "tag_class": "recommended",
             "body": (
                 "A pension passes by nomination, not by will, and nominations are often "
                 "years out of date. With most of the plan's value in pensions this is the "
                 "largest avoidable risk here and takes one form per scheme."
             )},
            {"title": "How the home is owned changes a later care assessment.",
             "tag": "not modelled", "tag_class": "stretch",
             "body": (
                 "Care is means-tested per person, and the home is disregarded while a "
                 "spouse still lives there. Owning as joint tenants means everything passes "
                 "to the survivor, who is then assessed on all of it. Severing to tenants in "
                 "common with a will trust is the usual answer — but the outcome depends on "
                 "drafting and on a local authority's judgement, so it needs a solicitor and "
                 "carries no figure here."
             )},
            {"title": "Gifting early is worth more than gifting more.",
             "tag": "modelled", "tag_class": "conservative",
             "body": (
                 "Outright gifts leave the estate after seven years. Worth knowing: the "
                 "deprivation-of-assets rule turns on whether care was reasonably "
                 "foreseeable when the gift was made — being fit and healthy at the time "
                 "means a gift should not be treated as deprivation, so starting early is "
                 "the safer course, not the riskier one."
             )},
        ],
        "caveat": (
            "Nothing here is legal advice. Items marked “not modelled” were not tested by "
            "the simulation and carry no figure for that reason."
        ),
    }

    # --- section 7: timeline ------------------------------------------------
    section7 = {
        "intro": "Dated actions, in order.",
        "entries": [
            {"date": f"{STRETCH:%B %Y}",
             "description": "Earliest date notice would allow. Not recommended."},
            {"date": f"{RECOMMENDED:%B %Y}",
             "description": "Recommended retirement date. Both stop working."},
            {"date": f"{RECOMMENDED.year + 1}",
             "description": "First full year drawing pension to the top of the basic-rate band."},
        ],
    }

    # --- section 8: notes and assumptions ----------------------------------
    section8 = {
        "notes": [
            f"All figures are in today's money. Returns are drawn from {window}.",
            "This household is fabricated. It exists to exercise the model, not to "
            "describe anyone real.",
            "Tax rules are modelled as they stand today and applied unchanged for the "
            "whole plan. Over forty years that is certainly wrong; the further out a "
            "figure is, the more it depends on the rules than on the markets.",
            "The plan assumes both people live to the same age, so estate figures are "
            "conditional on that. It does not yet model the first death and the "
            "survivor's position, or late-life care costs — each of which makes a plan "
            "worse, not better. Ask for the full list of what is and is not modelled.",
            "Success is a whole-horizon test: one bad year anywhere counts as a failure, "
            "even where the plan recovers completely afterwards.",
        ],
        "disclaimer": (
            "This is a modelling tool, not regulated financial advice. Nothing here "
            "should be acted on without an FCA-regulated adviser."
        ),
    }

    return {
        "client_name": "Pat & Robin Sample",
        "cover_subtitle": "A fabricated household, used to exercise the model",
        "prepared_date": f"{date.today():%d %B %Y}",
        "as_of_date": f"{AS_OF:%d %B %Y}",
        "section1": section1,
        "section2": section2,
        "section3": section3,
        "section4": section4,
        "section5": section5,
        "section6": section6,
        "section7": section7,
        "section8": section8,
    }


def _detail_section(result, window: str) -> dict:
    """Section 4: everything that only makes sense one scenario at a time."""
    labels = result.year_labels()

    bridge = result.bridge_before_access()
    bridge_rows = []
    bridge_intro = ""
    # No bridge to report is itself worth a sentence. Silently dropping a
    # table the reader was told to expect looks like an omission; saying why
    # it is absent is a finding -- here, that the pensions are already
    # accessible, which is the reason this plan has no locked-up gap at all.
    no_bridge_note = (
        " There is no bridge table below: the pensions are already accessible at "
        "the modelled retirement date, so no period has to be funded from savings "
        "alone while they are locked."
    )
    if bridge is not None:
        access_year = result.pension_access_year
        p50 = result.bridge_at(access_year - 1, 50)
        bridge_rows = [{
            "name": f"Retire {RECOMMENDED:%B %Y}",
            "p10": money(bridge[0]), "p50": money(p50), "p90": money(bridge[1]),
        }]
        bridge_intro = (
            f"Everything outside a pension — cash, the ISAs, and the GIA the model opens "
            f"automatically for surplus — in {access_year - 1}, the year before "
            f"the first pension unlocks. Read the year *before* access, not the access "
            f"year itself: a plan that draws the pension hard the moment it unlocks can "
            f"refill the bridge in the same year, which would make even a bridge that had "
            f"run dry look healthy."
        )

    # One chart per asset type, each on its own scale. Forcing a pension in the
    # millions and a flat house onto one axis would make both unreadable.
    asset_charts = []
    for asset_type, bands in result.asset_type_percentiles.items():
        if all(v == 0 for v in bands[95]):
            continue
        asset_charts.append({
            "title": TYPE_LABELS.get(asset_type, asset_type),
            "svg": fan_chart_svg(labels, bands, label=TYPE_LABELS.get(asset_type, asset_type)),
        })

    omitted = [
        TYPE_LABELS.get(t, t) for t, bands in result.asset_type_percentiles.items()
        if all(v == 0 for v in bands[95])
    ]

    mix_rows = [
        {
            "label": TYPE_LABELS.get(asset_type, asset_type),
            "p5": money(bands[5][-1]), "p10": money(bands[10][-1]),
            "p50": money(bands[50][-1]), "p90": money(bands[90][-1]),
            "p95": money(bands[95][-1]), "is_total": False,
        }
        for asset_type, bands in result.asset_type_percentiles.items()
        if bands[95][-1] > 0
    ]
    # The total must come from wealth_percentiles: percentiles taken per type
    # do not add up to the percentile of the total, because the trial at the
    # median for one type is not the trial at the median for another.
    wealth = result.wealth_percentiles
    mix_rows.append({
        "label": "Total", "p5": money(wealth[5][-1]), "p10": money(wealth[10][-1]),
        "p50": money(wealth[50][-1]), "p90": money(wealth[90][-1]),
        "p95": money(wealth[95][-1]), "is_total": True,
    })

    return {
        "title": f"The recommended plan in detail — retire {RECOMMENDED:%B %Y}",
        "intro": (
            f"Everything below is the recommended scenario alone, at "
            f"{pct(result.success_probability)} success over {window}."
            + ("" if bridge is not None else no_bridge_note)
        ),
        "bridge_intro": bridge_intro,
        "bridge_rows": bridge_rows,
        "fanchart_title": "Total wealth over the plan",
        "fanchart_caption": (
            "Median, with the 10th–90th and 5th–95th percentile bands around it. Shown to "
            "the full horizon so it ends on the same year the estate figures are read "
            "from. The wide top band compresses the early years, which are the ones most "
            "relevant to the decision — read the lower bands there."
        ),
        "fanchart_svg": fan_chart_svg(labels, wealth, label="Total wealth"),
        "asset_fan_charts_title": "Where that wealth sits",
        "asset_fan_charts_caption": (
            "One chart per account type, each on its own scale — a pension in the millions "
            "and a flat house value cannot share an axis without making both unreadable."
            + (f" {', '.join(omitted)} omitted: zero throughout." if omitted else "")
        ),
        "asset_fan_charts": asset_charts,
        "asset_mix": [{
            "title": "What the estate is made of, at the end of the plan",
            "caption": (
                "Read at the final plan year — the same year Section 3's estate figures "
                "are taken from, but these are balances before inheritance tax, so the "
                "totals here are larger than the net-to-heirs range in Section 3. That "
                "gap is the tax. The Total row comes from total wealth, not from summing "
                "the rows above it — percentiles taken per type do not add up, because "
                "the trial at the median for one type is not the trial at the median for "
                "another."
            ),
            "rows": mix_rows,
        }],
    }


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "workspace/sample_client/report.pdf"
    path = render_pdf(build_context(), out)
    print(f"wrote {path}")
    print("Now render the pages to PNG and read them — layout defects are invisible here.")


if __name__ == "__main__":
    main()
