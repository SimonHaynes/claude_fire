# Data setup

`src/retireplan/data/` is empty on a fresh clone. The engine needs real
market and mortality data to simulate against, and this repo ships none of
it: the market series are scraped from third parties whose redistribution
terms are unclear, and shipping them without checking would be worse than
not shipping them at all. Rebuild them locally instead, once, with the tools
below.

## Market data (equity, bonds, inflation, recession, corporate credit)

```bash
cp .env.example .env
# edit .env: add a free FRED API key from https://fredaccount.stlouisfed.org/apikeys
.venv/bin/python tools/fetch_market_data.py
```

This writes three files:

| File | Source | Needs a key? |
|---|---|---|
| `us_long_<start>_<end>.csv` | NYU Stern (Damodaran) nominal S&P 500 / 10yr Treasury returns, deflated by FRED CPI | Yes (CPI) |
| `us_recession_<start>_<end>.csv` | FRED `USREC`, aggregated to a fractional per-year figure | Yes |
| `us_short_corporate_<start>_<end>.csv` | Yahoo Finance IGSB adjusted close, deflated by FRED CPI | Yes (CPI) |

The FRED API key is free and instant — no approval wait. The Damodaran and
Yahoo Finance requests need no authentication.

**A rebuilt file will not be byte-identical between two people, or between
two runs a year apart.** CPI gets revised after first publication, and both
sources extend their series forward every year. `tests/test_market.py`
checks landmark years to a loose tolerance for exactly this reason — treat a
large divergence (wrong sign, wrong order of magnitude) as a sign something
upstream broke, not a normal difference.

If a source changes shape and the script starts failing, the CSV header
comments it writes document the exact source URL and method, so a manual
rebuild is always possible even if the automation needs fixing.

## Mortality (ONS life tables)

This one step can't be automated: ONS publishes the workbook behind a
versioned filename that changes with each release, so there is no stable
URL to fetch.

1. Open the dataset page: [ONS national life tables, England and
   Wales](https://www.ons.gov.uk/peoplepopulationandcommunity/birthsdeathsandmarriages/lifeexpectancies/datasets/nationallifetablesenglandandwalesreferencetables)
2. Download the current `.xlsx` reference table.
3. Run the build script against it:

   ```bash
   .venv/bin/python tools/build_mortality_csv.py path/to/downloaded.xlsx \
       src/retireplan/data/mortality/ons_qx_ew_<period>.csv
   ```

The script reads the raw XML inside the `.xlsx` (no dependency needed) and
refuses to write anything if a sheet it expects is missing or a value looks
out of range — see its docstring for the sheet name it looks for, which you
may need to update if ONS renames the current period's tab.

## Running the tests without data

Most of the test suite doesn't touch real data. The tests that do
(`tests/test_market.py`'s `MarketData.load()` checks, the sample-household
integration tests, anything that runs a full `run_monte_carlo`) will fail
with a clear `FileNotFoundError` until you've run the steps above — that's
expected on a fresh clone, not a bug.
