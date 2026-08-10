# Data setup

`src/retireplan/data/` is empty on a fresh clone. The engine needs real market
and mortality data to simulate against, and this repo ships none of it.

That is a licensing decision, not an oversight. Damodaran publishes his
datasets free but attaches no licence, so there is no grant to republish them;
Yahoo Finance's terms restrict redistribution outright; the JST Macrohistory
database is free for research but requires citation, an obligation that
disappears the moment the file is vendored into someone else's repo. Only the
ONS tables (Open Government Licence v3.0) could clearly be shipped. Rather
than commit a mixture of files carrying five different sets of obligations,
every clone fetches its own copy under whatever terms apply to that user —
which is the use all four publishers intend. README's [Data
section](README.md#data) has the per-source table. This is how the terms read
to us and is not legal advice; check them yourself for commercial use.

Note that `pyproject.toml` packages `data/*.csv` by glob, so a wheel built
after fetching will contain the CSVs. Building one for yourself is fine;
publishing it is redistribution.

Rebuild the data locally, once, with the tools below.

## Market data (equity, bonds, inflation, recession, corporate credit)

```bash
.venv/bin/python tools/fetch_market_data.py
```

**A FRED API key is optional.** It buys one file. Without it you get everything
else, and lose only `retireplan.market.HeldToMaturityCredit`, which keys
corporate-default incidence off the recession series — a plan holding no
corporate bonds is unaffected. To have it:

```bash
cp .env.example .env
# edit .env: add a free, instant key from https://fredaccount.stlouisfed.org/apikeys
```

| File | Source | Needs a key? |
|---|---|---|
| `us_long_<start>_<end>.csv` | NYU Stern (Damodaran) nominal returns for seven asset classes, deflated by his own CPI sheet | No |
| `us_short_corporate_<start>_<end>.csv` | Yahoo Finance IGSB adjusted close, deflated by the same CPI | No |
| `us_recession_<start>_<end>.csv` | FRED `USREC`, aggregated to a fractional per-year figure | **Yes** |

`us_long_*.csv` carries seven real return series from one table — `global_equity`
(S&P 500), `gov_bonds` (10-year Treasury), `small_cap`, `tbills`,
`baa_corporate`, `real_estate` and `gold` — plus the `inflation` column that
`FixedNominal` needs. Point a `SampledSeries` at any of them.

**The deflator is Damodaran's own December-to-December CPI series**, taken from
the `Inflation Rate` sheet of his `histretSP.xlsx`, not from FRED's API. It is
the same underlying CPIAUCNS data, measured over the same window as the annual
returns it deflates, and it is what removes the key requirement. It differs
year by year from an annual-average measure — 2008 deflates at 0.09% rather
than 3.8%, so the crash reads as −36.6% real rather than −38.9% — but the
long-run annualised figures are unmoved, at 6.699% against 6.701% real on
equities across 1928–2024.

**A rebuilt file will not be byte-identical between two people, or between
two runs a year apart.** CPI gets revised after first publication, and both
sources extend their series forward every year. `tests/test_market.py`
checks landmark years to a loose tolerance for exactly this reason — treat a
large divergence (wrong sign, wrong order of magnitude) as a sign something
upstream broke, not a normal difference.

If a source changes shape and the script starts failing, the CSV header
comments it writes document the exact source URL and method, so a manual
rebuild is always possible even if the automation needs fixing.

## Global market data (optional — `global_equity_gdpw`/`global_bonds_gdpw`)

Not needed for normal use. The engine's default return series
(`global_equity`/`gov_bonds`, above) is a US proxy, deliberately — see
`.claude/skills/standard-assumptions/SKILL.md` for when that default is
right and when it isn't. This second series exists for the specific,
stated-reason case: a GDP-PPP-weighted, 16-country historical panel, for
comparing against or knowingly opting into instead of the US-only default.

```bash
.venv/bin/python tools/fetch_global_market_data.py
```

Writes `global_gdpw_<start>_<end>.csv` (currently `global_gdpw_1900_2020.csv`).
No API key needed — the source (Jorda-Schularick-Taylor Macrohistory
Database, macrohistory.net) needs no authentication. Like every file in
`src/retireplan/data/`, it is fetched, not committed (`.gitignore`'s
`src/retireplan/data/*.csv` already covers it — nothing extra to configure).

**Read `tools/fetch_global_market_data.py`'s module docstring before using
the series it produces.** It documents, in detail, exactly what this
construction is not: not true market-cap weighting (GDP-PPP is the
industry-standard proxy where cap data doesn't reach, not the same thing),
not free of survivorship bias (no Russia 1917, no China 1949 — the country
panel only includes markets that kept functioning continuously), and not
the whole world (16-18 advanced economies, no emerging markets, ever).

After fetching, `tools/validate_market_data.py` checks both this file and
the default `us_long_*.csv` against external, independently-sourced
figures (Damodaran's own page, the UBS Global Investment Returns Yearbook,
MSCI World's official index returns) and prints the gap against each —
see REVIEW.md sec.6 for the full write-up of what it found and why the
gaps are the size they are.

## Mortality (ONS life tables)

```bash
.venv/bin/python tools/build_mortality_csv.py --fetch
```

ONS publishes the actual workbook behind a versioned filename that changes
with each release, but keeps a stable `.../current/<versioned-name>.xlsx`
link pointing at whichever one is newest — `--fetch` follows that link,
downloads the workbook, auto-detects the most recent `YYYY-YYYY` sheet
inside it (also not hardcoded, for the same reason), and writes
`src/retireplan/data/mortality/ons_qx_ew_<period>.csv`.

If ONS ever restructures that page enough to break the link-scraping (their
last redesign predates this repo, so treat it as a "when", not "if"), fall
back to the manual path — same script, one extra step:

1. Open the dataset page: [ONS national life tables, England and
   Wales](https://www.ons.gov.uk/peoplepopulationandcommunity/birthsdeathsandmarriages/lifeexpectancies/datasets/nationallifetablesenglandandwalesreferencetables)
2. Download the current `.xlsx` reference table by hand.
3. Run the build script against the downloaded file instead of `--fetch`:

   ```bash
   .venv/bin/python tools/build_mortality_csv.py path/to/downloaded.xlsx \
       src/retireplan/data/mortality/ons_qx_ew_<period>.csv
   ```

Either way, the script reads the raw XML inside the `.xlsx` (no dependency
needed), auto-detects the sheet rather than assuming a fixed period, and
refuses to write anything if a value looks out of range.

## Running the tests without data

Most of the test suite doesn't touch real data. The tests that do
(`tests/test_market.py`'s `MarketData.load()` checks, the sample-household
integration tests, anything that runs a full `run_monte_carlo`) will fail
with a clear `FileNotFoundError` until you've run the steps above — that's
expected on a fresh clone, not a bug.
