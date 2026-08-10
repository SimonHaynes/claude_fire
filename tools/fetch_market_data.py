"""Fetch and rebuild the market-data CSVs in `src/retireplan/data/`.

    .venv/bin/python tools/fetch_market_data.py

Writes `us_long_<start>_<end>.csv`, `us_recession_<start>_<end>.csv` and
`us_short_corporate_<start>_<end>.csv`. Deletes any differently-named files
of the same shape left over from a previous run, so the data directory never
accumulates stale, differently-dated copies.

These files are not committed to the repo (see `.gitignore` and
`DATA_SETUP.md`) -- third-party redistribution terms for scraped market data
are unclear, so every clone rebuilds its own copy from the original sources.
This script automates that rebuild; nothing here is transcribed by hand.

Needs a free FRED API key (https://fredaccount.stlouisfed.org/apikeys) in the
environment as FRED_API_KEY, or in a `.env` file at the repo root (copy
`.env.example`). No key is needed for the Damodaran or Yahoo Finance sources.

Sources, matching the provenance each written CSV documents in its own
header:
  * NYU Stern (Damodaran) "Annual Returns on Stock, T.Bonds and T.Bills" --
    nominal S&P 500 and 10-year US Treasury total returns.
  * FRED CPIAUCNS -- US CPI (not seasonally adjusted), used both to deflate
    the above into real returns and as the `inflation` column.
  * FRED USREC -- NBER-based recession indicator, aggregated to a fractional
    per-year figure.
  * Yahoo Finance chart API -- IGSB (iShares 1-5 Year Investment Grade
    Corporate Bond ETF) monthly adjusted close, reduced to December-to-
    December nominal total returns and deflated by the same CPI series.

A rebuilt file will not be byte-identical to a previous run: CPI is revised
after first publication, and both Yahoo Finance and FRED extend their series
forward each year. Expect agreement to several decimal places on years more
than a year or two old, and treat any larger divergence as a reason to look
at what changed upstream, not a bug in this script.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "src" / "retireplan" / "data"
USER_AGENT = "Mozilla/5.0 (compatible; retireplan-data-fetch/1.0)"


def _load_dotenv(repo_root: Path) -> None:
    """Populate os.environ from a `.env` file, without overriding what's already set."""
    env_path = repo_root / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def _fred_observations(series_id: str, api_key: str, start: str) -> list[dict]:
    url = "https://api.stlouisfed.org/fred/series/observations?" + urllib.parse.urlencode({
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
    })
    data = json.loads(_get(url))
    return data["observations"]


def fetch_damodaran_nominal() -> dict[int, tuple[float, float]]:
    """Returns {year: (sp500_nominal, tbond10_nominal)}, as decimals."""
    url = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histretSP.html"
    html = _get(url).decode("utf-8", "replace")
    rows = re.findall(r"<tr.*?>(.*?)</tr>", html, re.S)
    out: dict[int, tuple[float, float]] = {}
    for row in rows:
        cells = re.findall(r"<td.*?>(.*?)</td>", row, re.S)
        cells = [re.sub(r"<.*?>", "", c).strip() for c in cells]
        if len(cells) < 5:
            continue
        year_text, sp500_text, _small_cap, _tbill, tbond_text = cells[:5]
        if not re.fullmatch(r"\d{4}", year_text):
            continue
        try:
            sp500 = float(sp500_text.rstrip("%")) / 100
            tbond = float(tbond_text.rstrip("%")) / 100
        except ValueError:
            continue
        out[int(year_text)] = (sp500, tbond)
    if len(out) < 50:
        raise SystemExit(
            f"only parsed {len(out)} years from Damodaran's page -- its table "
            "layout may have changed; inspect histretSP.html by hand"
        )
    return out


def fetch_cpi_inflation(api_key: str) -> dict[int, float]:
    """Mean of the twelve monthly year-over-year CPIAUCNS rates, per calendar year."""
    observations = _fred_observations("CPIAUCNS", api_key, "1912-01-01")
    monthly: dict[tuple[int, int], float] = {}
    for obs in observations:
        if obs["value"] == ".":
            continue
        year, month, _day = obs["date"].split("-")
        monthly[(int(year), int(month))] = float(obs["value"])

    years = sorted({y for y, _m in monthly})
    out: dict[int, float] = {}
    for year in years:
        rates = []
        for month in range(1, 13):
            cur = monthly.get((year, month))
            prev = monthly.get((year - 1, month))
            if cur is not None and prev is not None:
                rates.append(cur / prev - 1)
        if len(rates) == 12:
            out[year] = sum(rates) / 12
    return out


def fetch_recession_fraction(api_key: str) -> dict[int, float]:
    """Fraction of each calendar year's months FRED's USREC marks as in recession."""
    observations = _fred_observations("USREC", api_key, "1920-01-01")
    by_year: dict[int, list[float]] = {}
    for obs in observations:
        if obs["value"] == ".":
            continue
        year = int(obs["date"][:4])
        by_year.setdefault(year, []).append(float(obs["value"]))
    return {year: sum(vals) / len(vals) for year, vals in by_year.items()}


def fetch_igsb_nominal() -> dict[int, float]:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/IGSB"
        "?range=max&interval=1mo&events=div"
    )
    data = json.loads(_get(url))
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    closes = result["indicators"]["adjclose"][0]["adjclose"]

    december_close: dict[int, float] = {}
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
        if dt.month == 12:
            december_close[dt.year] = close

    out: dict[int, float] = {}
    for year in sorted(december_close):
        prev = december_close.get(year - 1)
        if prev is not None:
            out[year] = december_close[year] / prev - 1
    return out


def real_return(nominal: float, inflation: float) -> float:
    return (1 + nominal) / (1 + inflation) - 1


def write_csv(path: Path, header: str, columns: list[str], rows: dict[int, tuple]) -> None:
    # Gitignored, so a fresh clone has no data/ directory at all.
    path.parent.mkdir(parents=True, exist_ok=True)
    for stale in path.parent.glob(f"{path.stem.split('_')[0]}_{path.stem.split('_')[1]}_*.csv"):
        stale.unlink()
    with path.open("w", encoding="utf-8") as f:
        f.write(header)
        f.write(",".join(columns) + "\n")
        for year in sorted(rows):
            values = ",".join(repr(v) for v in rows[year])
            f.write(f"{year},{values}\n")
    print(f"wrote {path} -- {len(rows)} years")


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    _load_dotenv(repo_root)
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "FRED_API_KEY is not set. Copy .env.example to .env and add a free "
            "key from https://fredaccount.stlouisfed.org/apikeys"
        )

    today = datetime.date.today()

    print("fetching Damodaran nominal equity/bond returns...")
    nominal_eq_bond = fetch_damodaran_nominal()

    print("fetching CPI from FRED...")
    inflation = fetch_cpi_inflation(api_key)

    print("fetching NBER recession indicator from FRED...")
    recession = fetch_recession_fraction(api_key)

    print("fetching IGSB adjusted close from Yahoo Finance...")
    igsb_nominal = fetch_igsb_nominal()

    long_years = sorted(set(nominal_eq_bond) & set(inflation))
    if not long_years:
        raise SystemExit("no overlapping years between Damodaran and CPI data")
    long_rows = {
        year: (
            round(real_return(nominal_eq_bond[year][0], inflation[year]), 5),
            round(real_return(nominal_eq_bond[year][1], inflation[year]), 5),
            round(inflation[year], 3),
        )
        for year in long_years
    }
    first_year, last_year = long_years[0], long_years[-1]

    write_csv(
        DATA_DIR / f"us_long_{first_year}_{last_year}.csv",
        f"""# Long-run US real (inflation-adjusted) annual returns, {first_year}-{last_year}.
#
# Fetched {today.isoformat()} by tools/fetch_market_data.py. Sources:
#   global_equity, gov_bonds (nominal, before deflation):
#     NYU Stern (Damodaran), "Annual Returns on Stock, T.Bonds and T.Bills" --
#     S&P 500 total return (incl. dividends) and 10-year US Treasury total return.
#     https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histretSP.html
#   inflation:
#     FRED CPIAUCNS (US CPI, not seasonally adjusted), mean of the twelve
#     monthly year-over-year rates in each calendar year.
#
# real_return = (1 + nominal_return) / (1 + inflation) - 1
#
# KNOWN SIMPLIFICATION: a US-market proxy, not a global or GBP-denominated
# series. A UK investor in a global tracker also carries multi-decade currency
# effects this does not model. Used because it is the longest reliable series
# obtainable byte-exactly, and tail behaviour matters more to a block
# bootstrap than the US/global distinction. Replace with a verified
# global/GBP series when one is available.
#
# Columns are real annual returns as decimals (0.07 = 7%), except `inflation`,
# which is the inflation rate itself (needed to convert fixed *nominal* yields
# into real terms -- see retireplan.market.FixedNominal).
""",
        ["year", "global_equity", "gov_bonds", "inflation"],
        long_rows,
    )

    write_csv(
        DATA_DIR / f"us_recession_{sorted(recession)[0]}_{sorted(recession)[-1]}.csv",
        f"""# US recession intensity by year, {sorted(recession)[0]}-{sorted(recession)[-1]}.
#
# Fetched {today.isoformat()} by tools/fetch_market_data.py from FRED USREC
# (NBER-based Recession Indicators for the United States), aggregated here
# from the monthly series -- FRED's own annual aggregation is NOT used, since
# it disagrees with the monthly series in short-recession years.
# https://fred.stlouisfed.org/series/USREC
#
# `recession` is the fraction of the year the US economy was in an NBER-dated
# recession: 0.0 for a clean year, 1.0 for a year entirely in contraction.
#
# WHY THIS EXISTS. Corporate bond defaults are not spread evenly through time:
# they cluster in recessions, which is also when equities fall and a retiree
# is selling assets to fund spending. That correlation is the actual risk in
# holding corporate credit, so `retireplan.market.HeldToMaturityCredit` drives
# default incidence off this series rather than treating defaults as
# independent events. An independent-default model puts the losses in the
# wrong years and understates the damage.
""",
        ["year", "recession"],
        {year: (round(value, 4),) for year, value in recession.items()},
    )

    short_years = sorted(set(igsb_nominal) & set(inflation))
    short_rows = {
        year: (round(real_return(igsb_nominal[year], inflation[year]), 5),)
        for year in short_years
    }
    write_csv(
        DATA_DIR / f"us_short_corporate_{short_years[0]}_{short_years[-1]}.csv",
        f"""# Short-dated corporate bond real annual returns, {short_years[0]}-{short_years[-1]}.
#
# Fetched {today.isoformat()} by tools/fetch_market_data.py.
#
# THE WISEALPHA PROXY. WiseAlpha sells fractional slices of individual
# short-dated corporate bonds (sterling, largely senior secured, much of it
# sub-investment-grade, quoted at ~6-8% nominal yields). There is no public
# WiseAlpha return history, so this is a proxy, and the gap matters:
#   * Credit quality: this index is INVESTMENT GRADE. WiseAlpha's higher quoted
#     yields come with materially more default risk, so real drawdowns in a
#     credit event would be deeper than the numbers below.
#   * Currency: this is USD. WiseAlpha is sterling.
#   * Concentration: an index is diversified across hundreds of issuers;
#     a WiseAlpha holding may be a handful of names.
# Treat this series as "how short-dated corporate credit behaves", not as
# "what WiseAlpha returned".
#
# ALSO NOTE: for a WiseAlpha slice held to maturity at a *fixed* quoted rate,
# this series is the wrong model entirely -- use retireplan.market.FixedNominal,
# which holds the nominal yield fixed and lets the sampled inflation rate
# determine the real return. That is the honest model of a fixed nominal
# coupon, and it is what makes 1970s-style inflation show up as the risk it is.
#
# Source: iShares 1-5 Year Investment Grade Corporate Bond ETF (IGSB),
# adjusted close (dividends reinvested), Yahoo Finance chart API,
# reduced to December-to-December nominal total returns, deflated by the
# same CPI series as us_long_*.csv.
""",
        ["year", "short_corporate"],
        short_rows,
    )

    print("done. Run `.venv/bin/python -m pytest tests/test_market.py` to sanity-check.")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as exc:
        raise SystemExit(f"network error fetching data: {exc}") from exc


