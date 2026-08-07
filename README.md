# retireplan

Cashflow modelling and Monte Carlo simulation for retirement planning, with
pluggable withdrawal, drawdown and allocation strategies, and a seven-section
client PDF report.

Everything works in **real (today's money) terms**: every figure in and out is
purchasing power, not future pounds.

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
.venv/bin/python -m pytest
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
.venv/bin/python tools/fetch_market_data.py     # equity, bond, recession, corporate
.venv/bin/python tools/build_mortality_csv.py --help   # mortality (manual download step)
```

See [`DATA_SETUP.md`](DATA_SETUP.md) for exactly what each script fetches,
from where, and the one manual step (an ONS spreadsheet) that can't be
automated. In outline:

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

## Workspace

Household definitions live outside the package, under `workspace/` — they are
data about real people, not library code. `workspace/sample_client/` is a
fabricated fixture used by the tests and docs; everything else under
`workspace/` is gitignored, since real financial data should never be
committed. Set up your own the same way:

```bash
mkdir workspace/<name>
touch workspace/<name>/__init__.py
# write household.py, scenarios.py, run_scenarios.py, build_report.py
# — workspace/sample_client/ is the pattern to copy.
.venv/bin/python -m workspace.<name>.run_scenarios   # compare every scenario
.venv/bin/python -m workspace.<name>.build_report    # PDF report
```

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
