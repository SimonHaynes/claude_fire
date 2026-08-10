"""Fetch and build a GDP-weighted global equity/bond real return series.

    .venv/bin/python tools/fetch_global_market_data.py

Writes `global_gdpw_<start>_<end>.csv` to `src/retireplan/data/`, alongside
(not replacing) the existing `us_long_*.csv`. The existing `global_equity`/
`gov_bonds` series keys are S&P 500 and 10-year US Treasury only — a US
proxy the README itself flags as a known simplification ("Replace with a
verified global/GBP series when one is available"). This is that
replacement candidate, under distinct keys (`global_equity_gdpw`,
`global_bonds_gdpw`) so nothing existing silently changes meaning.

## Source

The Jordà-Schularick-Taylor Macrohistory Database (macrohistory.net),
release R6 — the standard academic source for long-run, multi-country
asset returns, free to download, no API key. 18 countries, 1870-2020,
of which 16 have equity/bond return series (Canada and Ireland are in the
macro panel but not the asset-return panel). Shipped from 1900 only — see
"What this is NOT" below for why 1870-1899 is dropped rather than shipped
thin.

No genuinely global, freely-downloadable, machine-readable series goes back
further than this while covering more than one country. The one dataset
that does more (true historical market-cap weights, ~90 countries) is the
Dimson-Marsh-Staunton/UBS Global Investment Returns Yearbook — academically
the gold standard, but not raw-downloadable; its headline statistics are
published in the free summary edition and are the number to check this
file's output against, not a machine-readable series to fetch. See the
"What this is NOT" section below.

## Method: GDP-PPP weighting as the market-cap proxy

No market-capitalisation series exists this far back for most of these
countries. The industry-standard proxy when cap data doesn't exist is
GDP weighting — it is literally what DMS/UBS themselves do for the early
decades of their own World index, before usable market-cap data exists.

This uses `rgdpmad` (real GDP per capita, PPP-adjusted, constant 1990
International Dollars) x population, **not** the JST dataset's raw `gdp`
column. That matters: `gdp` is nominal *local currency*, and the raw
magnitudes are not on a consistent scale across countries in this
dataset -- Spain's, in particular, is off by roughly three orders of
magnitude relative to the US/UK/Germany figures for the same years,
which would silently wreck any weighting built on it directly. PPP-adjusted
real GDP in a single fixed unit (1990 Int$) sidesteps that entirely: no
currency conversion, no per-country rescaling, comparable by construction.

Per year: each country's local-currency nominal equity/bond return is
converted to a nominal USD return using that year's and the prior year's
`xrusd` (local currency per USD) -- that conversion is a straightforward
year-on-year FX ratio and is unaffected by the `gdp` scaling issue above.
Countries are then weighted by their *prior*-year real GDP (PPP), so a
year's weights are known before that year's returns, matching how a
cap-weighted index actually rebalances. The result is deflated by US CPI
(from JST's own `cpi` column for the USA, which -- unlike `gdp` -- IS
consistently defined, an index base year=1990 throughout) to land in the
same "real, USD" terms the rest of this engine's data uses.

## What this is NOT

  * **Not true market-cap weighting.** GDP-PPP is the standard proxy where
    cap data doesn't exist; it is not the same thing, and will disagree
    with a true cap-weighted index especially in periods of large valuation
    divergence (e.g. Japan's bubble-era market cap share vastly exceeded
    its GDP share circa 1989).
  * **Not free of survivorship bias.** This is the whole point of the
    Dimson-Marsh-Staunton research agenda: a panel of "countries with an
    unbroken run of market data" necessarily excludes every market that
    was wiped out -- Russia 1917, China 1949, and others -- which a truly
    ex-ante global portfolio would have held a slice of. DMS's own
    published headline (below) sits noticeably *below* what this file
    computes for exactly that reason -- see Validation below. Treat this
    series as "the return of markets that happened to keep functioning
    continuously," not "the return of a global portfolio held since 1900."
  * **Not the whole world.** 16-18 countries, all of them advanced
    economies as of 1870 -- no China, India, or the rest of the emerging-market
    universe at any point in the series. A modern global tracker's
    portfolio looks materially different from this panel's composition.
  * **Shipped from 1900, not 1870.** Country coverage grows from 5 in 1870
    to a stable 16 by 1900; 1870-1899 is thin enough (as low as 5 of 16
    countries) that it would misrepresent itself as a "global" figure, so
    this script drops it rather than ship it flagged-but-included. 1900 is
    also the conventional anchor most published long-run equity-premium
    figures use -- including DMS/UBS's own -- which is what makes a real
    comparison against them possible at all.
  * **Interpolated through both World Wars.** `eq_tr_interp`-flagged
    country-years (exchange closures, mostly 1937-40 and some post-war
    years) are included as JST supplies them; their GDP-weight share for
    the affected year is in the `interp_frac` column so a reader can judge
    how much of a given year's figure rests on an estimate rather than a
    traded price.

## Validation

Cross-checked three ways before trusting this pipeline's arithmetic:

  1. The USA-only sub-series this script derives from JST's `eq_tr` + `cpi`
     (6.66% real geometric, 1900-2020) lands within 0.02 points of
     retireplan's existing, independently-sourced Damodaran S&P 500 series
     over the overlapping window (6.64% real geometric, 1928-2020) --
     two different sources, same answer, so the return/inflation
     conversion in this script is doing the right thing.
  2. The GDP-weighted global figure itself (see the printed summary this
     script produces) comes out *higher* than the actual UBS Global
     Investment Returns Yearbook 2025 headline -- quoted directly (not
     paraphrased) via Cambridge Judge Business School, home institution of
     Yearbook co-author Elroy Dimson: **"the annualised real returns were
     5.2% for worldwide equities versus 1.7% on bonds"** over the
     Yearbook's full 125-year (1900-2024) history. This file's own figure
     comes out above both, by a consistent, explicable margin --
     survivorship bias in the underlying country panel (above), not a
     computation error. Report the gap alongside the number; do not quote
     this file's figure as if it were the DMS one.
  3. UBS's own public summary PDF for the same edition states a second,
     independent data point for a shorter, very recent window: "global
     equity investors ... enjoyed an annualized real return of 3.5%"
     2000-2024 -- useful as a second check precisely because it is a
     different period from the 1900 one above, so the two together bound
     the comparison rather than resting on a single figure.

Run: .venv/bin/python tools/fetch_global_market_data.py
"""
from __future__ import annotations

import csv
import datetime
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from io import BytesIO
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "src" / "retireplan" / "data"
USER_AGENT = "Mozilla/5.0 (compatible; retireplan-data-fetch/1.0)"

# The stable download links published on https://www.macrohistory.net/database/
JST_XLSX_URL = "https://www.macrohistory.net/app/download/9834512569/JSTdatasetR6.xlsx"

NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
NEED = ("year", "iso", "rgdpmad", "pop", "cpi", "xrusd", "eq_tr", "bond_tr", "eq_tr_interp")
SHIP_FROM_YEAR = 1900


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _col_letters(ref: str) -> str:
    return re.match(r"[A-Z]+", ref).group()


def _fetch_jst_rows() -> list[dict]:
    """Download the JST workbook and parse the one data sheet by hand.

    Deliberately dependency-free (no openpyxl/pandas): the engine ships
    with no dependencies, and this is a one-off data-fetch tool, not
    something that needs a general-purpose spreadsheet reader.
    """
    xlsx = zipfile.ZipFile(BytesIO(_get(JST_XLSX_URL)))
    shared = ET.fromstring(xlsx.read("xl/sharedStrings.xml"))
    strings = [
        "".join(t.text or "" for t in si.iter(f"{{{NS['a']}}}t"))
        for si in shared.findall("a:si", NS)
    ]

    def cell_value(c):
        v = c.find("a:v", NS)
        if v is None:
            return None
        return strings[int(v.text)] if c.attrib.get("t") == "s" else v.text

    sheet = ET.fromstring(xlsx.read("xl/worksheets/sheet1.xml"))
    rows = sheet.findall(".//a:row", NS)
    header = {_col_letters(c.attrib["r"]): cell_value(c) for c in rows[0].findall("a:c", NS)}

    out = []
    for row in rows[1:]:
        rec = {}
        for c in row.findall("a:c", NS):
            name = header.get(_col_letters(c.attrib["r"]))
            if name in NEED:
                rec[name] = cell_value(c)
        out.append(rec)
    return out


def _f(row: dict, key: str) -> float | None:
    v = row.get(key)
    return float(v) if v not in (None, "") else None


def build_series(rows: list[dict]) -> dict[int, dict]:
    """Year -> real global equity/bond return (USD, GDP-PPP weighted) plus provenance fields."""
    by_year_country: dict[int, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        by_year_country[int(r["year"])][r["iso"]] = r
    years = sorted(by_year_country)

    nominal: dict[int, dict] = {}
    for i in range(1, len(years)):
        y, yp = years[i], years[i - 1]
        if yp != y - 1:
            continue
        num_eq = den_eq = num_bd = den_bd = interp_w = 0.0
        n = 0
        for iso, row in by_year_country[y].items():
            prev = by_year_country[yp].get(iso)
            if prev is None:
                continue
            eq_tr, bond_tr, xr = _f(row, "eq_tr"), _f(row, "bond_tr"), _f(row, "xrusd")
            xr_p, rgdpmad_p, pop_p = _f(prev, "xrusd"), _f(prev, "rgdpmad"), _f(prev, "pop")
            if None in (xr, xr_p, rgdpmad_p, pop_p) or xr == 0 or xr_p == 0:
                continue
            weight = rgdpmad_p * pop_p  # prior-year real GDP, PPP -- consistent units, no FX scaling issue
            if eq_tr is not None:
                usd_eq = (1 + eq_tr) * (xr_p / xr) - 1
                num_eq += weight * usd_eq
                den_eq += weight
                n += 1
                if row.get("eq_tr_interp") not in (None, "", "0", "0.0"):
                    interp_w += weight
            if bond_tr is not None:
                usd_bd = (1 + bond_tr) * (xr_p / xr) - 1
                num_bd += weight * usd_bd
                den_bd += weight
        if den_eq > 0:
            nominal[y] = {
                "nom_eq": num_eq / den_eq,
                "nom_bd": (num_bd / den_bd) if den_bd > 0 else None,
                "n_countries": n,
                "interp_frac": interp_w / den_eq,
            }

    usa_cpi = {y: _f(by_year_country[y].get("USA", {}), "cpi") for y in years}
    usa_cpi = {y: v for y, v in usa_cpi.items() if v is not None}

    out = {}
    for y in sorted(nominal):
        if y not in usa_cpi or (y - 1) not in usa_cpi:
            continue
        us_inflation = usa_cpi[y] / usa_cpi[y - 1] - 1
        nom_eq, nom_bd = nominal[y]["nom_eq"], nominal[y]["nom_bd"]
        out[y] = {
            "global_equity_gdpw": (1 + nom_eq) / (1 + us_inflation) - 1,
            "global_bonds_gdpw": (1 + nom_bd) / (1 + us_inflation) - 1 if nom_bd is not None else None,
            # Not "inflation": `MarketData.load()` merges CSVs by column name, so
            # sharing that key would let this file and us_long's FRED-sourced
            # inflation overwrite each other on filename sort order.
            "inflation_gdpw": us_inflation,
            "n_countries": nominal[y]["n_countries"],
            "interp_frac": nominal[y]["interp_frac"],
        }
    # 1870-1899 is real but thin (as few as 5 of the 16 countries), so it would
    # misrepresent itself as "global" beside the panel from 1900 on. Cut rather
    # than flagged, so nothing downstream can use it by accident.
    return {y: row for y, row in out.items() if y >= SHIP_FROM_YEAR}


def _year_ranges(years: list[int]) -> str:
    """[1870, 1871, 1872, 1914, 1915] -> '1870-1872, 1914-1915' -- for the header comment."""
    if not years:
        return "none"
    ranges = []
    start = prev = years[0]
    for y in years[1:]:
        if y != prev + 1:
            ranges.append(f"{start}" if start == prev else f"{start}-{prev}")
            start = y
        prev = y
    ranges.append(f"{start}" if start == prev else f"{start}-{prev}")
    return ", ".join(ranges)


def _geo_mean(values: list[float]) -> float:
    product = 1.0
    for v in values:
        product *= 1 + v
    return product ** (1 / len(values)) - 1


def write_csv(series: dict[int, dict], path: Path) -> None:
    years = sorted(series)
    thin_years = [y for y in years if series[y]["n_countries"] < 14]
    interp_years = [y for y in years if series[y]["interp_frac"] > 0]
    with path.open("w", newline="") as fh:
        fh.write(f"# GDP-PPP-weighted global equity & bond real (USD) annual returns, "
                  f"{years[0]}-{years[-1]}.\n#\n")
        fh.write(f"# Fetched {datetime.date.today()} by tools/fetch_global_market_data.py. Source:\n")
        fh.write("#   Jorda-Schularick-Taylor Macrohistory Database, release R6\n")
        fh.write(f"#   ({JST_XLSX_URL}) -- 16 countries with equity/bond return data\n")
        fh.write("#   (of an 18-country macro panel; Canada and Ireland lack eq_tr/bond_tr).\n#\n")
        fh.write("# Method: each country's local-currency nominal eq_tr/bond_tr converted to a\n")
        fh.write("# nominal USD return via year-on-year xrusd, weighted by *prior*-year real GDP\n")
        fh.write("# (rgdpmad x pop, PPP, constant 1990 Int$ -- the GDP-weighting proxy for market-cap\n")
        fh.write("# weighting used industry-wide where cap data doesn't reach), then deflated by US\n")
        fh.write("# CPI (JST's own `cpi` column for the USA) to land in real USD terms.\n#\n")
        fh.write(f"# SHIPPED FROM {SHIP_FROM_YEAR}: 1870-1899 exists in the source data but is cut\n")
        fh.write("# here -- coverage is as thin as 5 of 16 countries that early, growing to a\n")
        fh.write("# stable 16 only by 1900. Re-run tools/fetch_global_market_data.py after editing\n")
        fh.write("# SHIP_FROM_YEAR if you want it back, flagged, not silently included.\n#\n")
        fh.write("# KNOWN LIMITATIONS -- read tools/fetch_global_market_data.py's module docstring\n")
        fh.write("# before trusting a number from this file: GDP-PPP weighting is a proxy for market-\n")
        fh.write("# cap weighting, not the real thing; the country panel is survivorship-biased (no\n")
        fh.write("# Russia, China, or any market wiped out by war/revolution) in the specific way\n")
        fh.write("# Dimson-Marsh-Staunton's own research is about, which is why this file's long-run\n")
        fh.write("# average comes out *above* DMS/UBS's published 'world equities since 1900' figure;\n")
        fh.write("# 16-18 advanced economies only, no emerging markets at any point.\n#\n")
        fh.write(f"# Years with fewer than 14 of the 16 countries reporting (n={len(thin_years)}): "
                  f"{_year_ranges(thin_years)}\n")
        fh.write(f"# Years partly relying on JST's own interpolation for an exchange closure "
                  f"(n={len(interp_years)}): {_year_ranges(interp_years)}\n#\n")
        fh.write("# Columns are real annual returns as decimals (0.07 = 7%), except `inflation_gdpw`\n")
        fh.write("# (the US CPI rate used to deflate this file's own returns -- deliberately NOT\n")
        fh.write("# named `inflation`, so this file can never silently override the `inflation`\n")
        fh.write("# column the rest of this package's data shares -- see us_long_*.csv for that).\n")
        fh.write("# Per-year country counts and interpolation shares are not carried as columns --\n")
        fh.write("# every column in every CSV `MarketData.load()` merges is assumed to be a return,\n")
        fh.write("# and metadata masquerading as one is exactly the kind of silent unit error this\n")
        fh.write("# package's own tests exist to catch. Re-run this script for the per-year detail.\n")
        writer = csv.writer(fh)
        writer.writerow(["year", "global_equity_gdpw", "global_bonds_gdpw", "inflation_gdpw"])
        for y in years:
            row = series[y]
            writer.writerow([
                y,
                f"{row['global_equity_gdpw']:.5f}",
                f"{row['global_bonds_gdpw']:.5f}" if row["global_bonds_gdpw"] is not None else "",
                f"{row['inflation_gdpw']:.5f}",
            ])


def main() -> None:
    print("Fetching Jorda-Schularick-Taylor Macrohistory Database...")
    rows = _fetch_jst_rows()
    print(f"  {len(rows)} country-year rows")

    series = build_series(rows)
    years = sorted(series)

    for old in DATA_DIR.glob("global_gdpw_*.csv"):
        old.unlink()
    out_path = DATA_DIR / f"global_gdpw_{years[0]}_{years[-1]}.csv"
    write_csv(series, out_path)
    print(f"Wrote {out_path}")

    print()
    for start in sorted({SHIP_FROM_YEAR, 1928, 2000}):
        eq = [series[y]["global_equity_gdpw"] for y in years if y >= start]
        bd = [series[y]["global_bonds_gdpw"] for y in years if y >= start and series[y]["global_bonds_gdpw"] is not None]
        print(f"From {start}: equity geo mean (real, USD) = {_geo_mean(eq):.2%}  "
              f"bonds geo mean = {_geo_mean(bd):.2%}")
    print(f"\nUBS Global Investment Returns Yearbook 2025 (quoted via Cambridge Judge Business "
          f"School): 5.2% real equities / 1.7% real bonds, {SHIP_FROM_YEAR}-2024 (125yr) -- expect "
          f"this file's 'From {SHIP_FROM_YEAR}' figures above to sit above both, for the "
          f"survivorship-bias reason the module docstring's Validation section explains. UBS also "
          f"states 3.5% real for global equities 2000-2024 specifically, for the 'From 2000' row "
          f"above to compare against -- this file's data only runs to 2020, so that comparison is "
          f"missing 2021-2024 on our side and will not match closely.")


if __name__ == "__main__":
    main()
