# claude_fire

*Financial Independence, Retire Early — modelled by an actual Monte Carlo
engine, driven by talking to it.*

## Why this exists

Retirement calculators mostly come in two flavours: a spreadsheet that
assumes 7% a year forever and calls it a plan, or a black box that takes your
numbers and hands back a probability with no way to ask why, or to see what
changes if you retire six months later, skip a holiday, or the market falls
the week you stop working.

`claude_fire` is neither. It's a real cashflow and Monte Carlo engine —
historical market returns back to 1928, UK income/NI/inheritance tax,
per-person mortality, care costs — wired up to a set of [Claude
Code](https://claude.com/claude-code) skills that turn a conversation about
your finances into a running model of them.

**Tax and estate rules are UK-specific today** (`tax/uk.py`, `tax/iht.py`) —
income tax, NI, State Pension, the pension IHT change coming in April 2027.
The cashflow, mortality and Monte Carlo machinery underneath none of that is
UK-specific, so another jurisdiction is a new `tax` module and a rewrite of
the tax-facing skills, not a different engine.

## An example

You, in Claude Code, inside this repo:

> I'm 52, my partner's 50. About £900k across pensions and ISAs, a paid-off
> house worth £480k. We'd like to retire as soon as we can without wrecking
> the numbers — when's that?

Claude Code — using the skills in `.claude/skills/` — asks a few clarifying
questions, turns your answers into a household definition, runs a handful of
scenarios (retire now, in two years, in four — each 2,000 times against a
different draw of market history) and comes back with something like:

> Retiring now clears 55% of simulated outcomes — most of the failures come
> from the first five years, before either pension unlocks. Waiting until
> July 2030 clears 98%, and costs less in lifestyle than you'd think.

And then it keeps going, because it's a conversation, not a form submission:

> What if we downsize instead of waiting?
> What if the market drops 30% the year we retire?
> Show me what happens if we leave more to the kids and spend less ourselves.

Each of those is a new scenario, run for real against thousands of simulated
years — not guessed at, not interpolated from the first answer.

## What it produces

The end product is an eight-section PDF: current position, the scenarios
tested and why, results, a detailed breakdown of the recommended plan, tax
and estate recommendations, structuring, a timeline, and notes on every
assumption made along the way. A few pages from the sample report, generated
from the fabricated household in `workspace/sample_client/`:

<p align="center"><img src="docs/scenarios.png" width="720" alt="Scenarios tested — three retirement dates explained in prose, plus how spending is modelled"></p>

<p align="center"><img src="docs/results.png" width="720" alt="Results table — success probability dial, median spend, worst case, and net-to-heirs range for each scenario"></p>

<p align="center"><img src="docs/fan-charts.png" width="720" alt="ISA balance fan chart, widening from £0 to a £26M 95th-percentile by the end of the plan"></p>

Nobody's real numbers — see [Workspace](#workspace) to generate your own.

## Requires Claude Code

There's no server and no hosted app. `retireplan` (the `src/retireplan/`
package) is a normal, dependency-free Python engine you can import and script
directly — see the snippet below. But the point of this repo is
`.claude/agents/` and `.claude/skills/`: instructions that teach Claude Code
how to gather your numbers, design scenarios, run the engine, sanity-check
the output against a fixed checklist, and write the report — so the actual
interface to a fairly serious piece of financial modelling is just talking to
it, in this repo, with Claude Code running.

```python
from datetime import date
from retireplan import Household, Scenario, GuytonKlinger, run_monte_carlo

result = run_monte_carlo(
    household, Scenario("retire at 60", retirement_dates={"Alex": date(2030, 6, 1)},
                        withdrawal=GuytonKlinger()),
    as_of=date.today(), n_trials=2000, seed=42,
)
print(f"{result.success_probability:.1%} over {result.sample_years} years of history")
```

`run_many(household, scenarios, as_of, ...)` takes a dict of them and runs it
across processes — a sweep of a few dozen dates is a minute rather than twenty.

Everything works in **real (today's money) terms**: every figure in and out
is purchasing power, not future pounds.

## Install

```bash
python -m venv .venv
.venv/bin/pip install -e ".[report,dev]"    # core engine has no dependencies
```

`report` adds jinja2 + weasyprint for the PDF. The engine itself is
dependency-free.

The market and mortality data the engine simulates against is **not checked
into this repo** — see [Data](#data) below. Fetch it once before running
`pytest` or any simulation:

```bash
cp .env.example .env               # add your own free FRED API key
.venv/bin/python tools/fetch_market_data.py
.venv/bin/python tools/build_mortality_csv.py --fetch
.venv/bin/python -m pytest
```

## Workspace

Household definitions live outside the package, under `workspace/` — they
are data about real people, not library code. `workspace/sample_client/` is
a fabricated fixture used by the tests and this README; everything else
under `workspace/` is gitignored, since real financial data should never be
committed. With Claude Code running in this repo, describe your situation and
ask it to build you a plan — that invokes the `retirement-planner` agent
(`.claude/agents/retirement-planner.md`), which runs the whole chain in
order: `intake-financial-data` to build the household, `define-scenarios` to
turn your goals into concrete scenarios, `run-scenario-simulation` to
actually run them, then `build-retirement-report` for the PDF — delegating
the tax and legal reasoning inside that to two further agents along the way.
It's several documents deep, not one skill in isolation; you don't need to
read any of them to use it, only if you want to see the reasoning it's
following. Or set a household up by hand the same way:

```bash
mkdir workspace/<name>
touch workspace/<name>/__init__.py
# write household.py, scenarios.py, run_scenarios.py, build_report.py
# — workspace/sample_client/ is the pattern to copy.
.venv/bin/python -m workspace.<name>.run_scenarios   # compare every scenario
.venv/bin/python -m workspace.<name>.build_report    # PDF report
```

## Layout

| Module | Responsibility |
|---|---|
| `model`, `serde` | what a household is; JSON round-tripping |
| `tax` | jurisdiction rules behind one interface (UK 2025/26 supplied) |
| `market` | historical data, return models, block-bootstrap sampler |
| `plan` | compiles household + scenario into a fixed year-by-year schedule |
| `cashflow` | runs one path of returns through that schedule |
| `simulation` | runs thousands; disk-cached results |
| `strategies` | withdrawal / drawdown / allocation, independently composable |
| `reporting` | charts and the PDF report |

`plan` exists for speed and clarity: everything market-independent (dates,
income, tax bands, expenses, debt schedules) is computed once rather than
re-derived on every trial.

## Strategies

Three independent axes, freely combinable. Varying one at a time is how you
find out which is doing the work — and, often, which is doing nothing.

**Withdrawal — how much to spend.** Two families answering different
questions. *Needs-based* rules start from the spending plan and cut only when
they must (`SpendNominal`, `PostAccessStepUp`);
*portfolio-based* rules derive spending from what the portfolio is currently
worth (`PercentOfPortfolio`, `VariablePercentage`). `GuytonKlinger` sits
between them. Portfolio rules essentially cannot run out of money — they spend
a fraction of whatever remains — so they convert failure risk into income
volatility. Compare them on spend percentiles, not success probability alone.

**Drawdown — which pots to sell.** `StandardOrder` (cash → ISA → pension),
`CashBondLadder` (a pre-funded safe bucket), `TaxEfficientOrder` (fill cheap
tax bands from the pension deliberately and bank the surplus in an ISA).

**Allocation — what each asset earns.** `StaticMix`, `ByAssetTypeMix`,
`GlidePath`.

## Tax

`tax/uk.py` covers income tax (as an effective marginal-rate schedule, so the
£100k allowance taper falls out naturally), NI, State Pension, pension access
age, and the tax-free lump sum with its Lump Sum Allowance cap.

`tax/iht.py` covers Inheritance Tax including **unused pensions entering the
estate from 6 April 2027** — which inverts the long-standing advice to spend
ISAs first and leave the pension for the heirs. Every result carries both
`bequest_percentiles` (gross) and `net_bequest_percentiles` (after IHT and
beneficiaries' income tax on inherited pension funds).

**Quote the net figure.** For a pension-heavy estate the gross number can
overstate what reaches the children by more than half. Expect a good tax
strategy to produce a *smaller* estate and a *larger* inheritance.

## Return models

The choice that most often flatters a plan:

| Model | For |
|---|---|
| `SampledSeries("global_equity")` | trackers and funds — draws from history |
| `FixedNominal(0.07)` | anything quoted as a headline yield |
| `HeldToMaturityCredit(0.07)` | bonds bought at a yield and held to maturity |
| `FixedReal(0.02)` | where a real return is genuinely intended |
| `Blend.of(global_equity=0.6, gov_bonds=0.4)` | a fixed mix |
| `ParametricNormal(mean=0.052, stdev=0.19)` | Monte Carlo from a distribution, not history |

`HeldToMaturityCredit` models the instrument rather than a bond fund: held to
maturity there is no mark-to-market risk (it redeems at par), so the risk is
**default**. Defaults are driven off the NBER recession series, because they
cluster in exactly the years equities fall and a retiree is selling to eat —
treating them as independent puts the losses in the wrong years. Recoveries
worsen in the same years, and `n_holdings` makes losses lumpy for a
concentrated ladder. Defaults are calibrated to Moody's long-run
speculative-grade statistics (4.5% through the cycle, ~10% in a recession).

A quoted 6–8% is a **nominal** coupon. Modelling it as a real return grants an
inflation-proof yield that no product offers, and hides the risk that actually
threatens fixed-income holdings: a 1970s-style decade.

`ParametricNormal` is the other family entirely: an independent Normal draw
every year, no sequence that ever actually happened, no autocorrelation or
mean reversion. `BlockBootstrap`-sampled history (the default) is what
FIRECalc and cFIREsim both do and what this engine defaults to; this is the
parametric alternative the same tools offer alongside it — for a household
using capital market assumptions instead of a resampled historical panel, or
wanting a global equity assumption without the survivorship bias inherent in
any panel of markets that happened to keep functioning continuously (see
`tools/fetch_global_market_data.py` and REVIEW.md sec.6 for that bias,
measured, not guessed at — the 5.2%/1.7% real figures above are the UBS
Global Investment Returns Yearbook's own published equity/bond means). Never
silently swap one family for the other: they answer different questions and
the choice should be attributable in the same way every other assumption in
this engine is.

## Sampling windows

Different series cover different periods. `MarketData.window` returns only
years where *every* series a scenario needs is present, and every result
carries `sample_years` / `sample_first_year` / `sample_last_year`.

This matters more than it sounds. Short-dated corporate bond data starts in
2008; using it narrows the bootstrap from 98 years to 18, and those 18 contain
no crash on the scale of 1929 or 1973-74. Plans then score ~100% — a statement
about the sample, not the plan. **Report the window wherever you report a
probability**, and treat any 0% or 100% as a red flag rather than a result.

## Data

`src/retireplan/data/` holds real annual returns and a mortality table, each
with a full provenance header once fetched. Read them before trusting a
number. **The CSVs are gitignored, not committed** — third-party market data
redistribution terms are unclear enough that this repo ships none of it.
Instead:

```bash
.venv/bin/python tools/fetch_market_data.py            # equity, bond, recession, corporate
.venv/bin/python tools/build_mortality_csv.py --fetch   # mortality
```

See [`DATA_SETUP.md`](DATA_SETUP.md) for exactly what each script fetches and
from where — including what to do if the ONS page's layout ever changes
under `--fetch` and it needs a manually-downloaded workbook instead. In
outline:

- `us_long_*.csv` — S&P 500 and 10-year Treasury total returns (NYU Stern /
  Damodaran) deflated by US CPI. A US proxy for a global portfolio.
- `us_short_corporate_*.csv` — short-dated corporate credit, from IGSB
  adjusted closes (Yahoo Finance). A documented proxy for a WiseAlpha-style
  holding; the file states the gaps (investment grade vs sub-IG, USD vs
  sterling, diversified vs concentrated).
- `us_recession_*.csv` — fraction of each year spent in an NBER-dated
  recession (FRED `USREC`), which drives credit default incidence.
- `mortality/ons_qx_ew_*.csv` — ONS national life tables, England & Wales.

`fetch_market_data.py` needs a free FRED API key (see `.env.example`); the
Damodaran and Yahoo Finance sources need no key. The fetched numbers should
match the originals to within data-revision noise — the header each script
writes documents the exact source and method, so a mismatch is diagnosable.

## Mortality, survivorship and care

Deaths are modelled per person, not as one shared horizon. On a first death the
survivor loses a personal allowance and a State Pension outright, keeps part of
the deceased's DB pension, inherits their pots, and sees spending fall by
category rather than by half. IHT settles on the second death.

Age at death is either fixed (`FixedAge`, the default, reproducing older
results) or sampled per trial from ONS life tables (`LifeTable`). Sampling
matters more than it sounds: on the sample household it cut the median net
bequest by 31%, because a fixed age 95 was quoting a tail as a median, and it
*lowered* success, because a fixed age hides the trials where someone lives
past 100.

`Scenario.care` adds late-life residential care, off by default and
deliberately without a probability attached.

`Assumptions.fiscal_drag` erodes tax thresholds frozen in nominal terms.
Defaults to off, because turning it on should be attributable.

## Not modelled

Annual gift exemptions and gifts from surplus income, advice fees and
transaction costs, cross-spouse tax levelling, currency effects, and a search
for the worst historical retirement start. Life tables are period rather than
cohort, which understates longevity by a couple of years.

**The remaining omissions are, on balance, still optimistic** — see REVIEW.md
for the full list and priorities.

**This is a modelling tool, not regulated financial advice.**
