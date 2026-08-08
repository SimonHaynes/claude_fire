"""Check both shipped return series against external, independently-sourced
figures -- not just against each other, and not from memory.

Every simulation this engine runs is downstream of `src/retireplan/data/*.csv`.
A sign error, a unit slip, or a subtly wrong deflator there would produce
plausible-looking, confidently-wrong output for every household, which is
exactly the kind of error internal testing (the two series agreeing with
each other, or a plan's own numbers looking sane) cannot catch on its own.
This checks against sources this engine did not produce.

## What's checked, and why these particular numbers

**`us_long_*.csv` (S&P 500 + 10yr Treasury, Damodaran/NYU Stern):**
`tests/test_market.py::test_nominal_returns_match_the_cited_source_exactly`
already pins this to the pound against Damodaran's own page for five landmark
years, on every test run. Re-stated here (not re-asserted -- that test is the
source of truth) as `pytest.approx`-free arithmetic anyone can read without
running pytest.

**`global_gdpw_*.csv` (GDP-PPP-weighted, 16 countries, JST Macrohistory,
shipped from 1900):** No existing test covers this -- it isn't part of the
standard fetch pipeline `DATA_SETUP.md` documents, so nothing should
hard-depend on it existing. Checked here against three independent,
external, directly-quoted (not paraphrased) figures:

  1. **UBS Global Investment Returns Yearbook 2025**, quoted verbatim via
     Cambridge Judge Business School (jbs.cam.ac.uk, retrieved 2026-08-09;
     Cambridge is Yearbook co-author Elroy Dimson's home institution, not a
     random secondary source): *"the annualised real returns were 5.2% for
     worldwide equities versus 1.7% on bonds"* over the Yearbook's full
     125-year history (1900-2024). This file's own 1900- figures should
     sit *above both*, by design -- see the module docstring in
     `tools/fetch_global_market_data.py` for why (survivorship: no Russia
     1917, no China 1949, in a panel of countries whose markets never
     stopped functioning). A number below either UBS figure, or one that
     isn't at least in the same order of magnitude (3-9% equity real, say),
     would mean something is actually broken, not just methodologically
     different.
  2. **The same Yearbook's own public summary PDF** (ubs.com, retrieved
     2026-08-09) states a second, shorter-window figure: *"global equity
     investors ... enjoyed an annualized real return of 3.5%"*, 2000-2024.
     Useful precisely because it's a different period from (1) -- two
     independent checks bound the comparison rather than resting on one.
     This file's data ends in 2020, so treat this one as directional, not
     exact: it's missing 2021-2024 on our side.
  3. **MSCI World Index, 2008, official MSCI factsheets**: -40.71% nominal
     USD -- one of the most widely-cited and independently-confirmed index
     figures there is. This file's GDP-weighted 16-country panel is not
     the same universe MSCI World covers (broader country and company
     coverage, true market-cap weights, not a GDP proxy), so exact
     agreement is not expected -- but the two should land in the same
     ballpark for the worst year in the sample.

Run: .venv/bin/python tools/validate_market_data.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from retireplan.market import MarketData  # noqa: E402

DAMODARAN_NOMINAL = {
    # (year, series_key): externally-cited nominal return.
    # Verified 2026-08-09 against pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histretSP.html
    (1929, "global_equity"): -0.0830,
    (1974, "global_equity"): -0.2590,
    (1974, "gov_bonds"): 0.0199,
    (2008, "global_equity"): -0.3655,
    (2008, "gov_bonds"): 0.2010,
    (2022, "global_equity"): -0.1804,
}

# UBS Global Investment Returns Yearbook 2025, quoted verbatim via Cambridge Judge
# Business School (jbs.cam.ac.uk), retrieved 2026-08-09:
# "the annualised real returns were 5.2% for worldwide equities versus 1.7% on bonds"
UBS_YEARBOOK_2025_EQUITY_SINCE_1900 = 0.052  # 125-year annualised, real, USD
UBS_YEARBOOK_2025_BONDS_SINCE_1900 = 0.017
# The same edition's public summary PDF (ubs.com), retrieved 2026-08-09:
# "global equity investors ... enjoyed an annualized real return of 3.5%"
UBS_YEARBOOK_2025_EQUITY_SINCE_2000 = 0.035
MSCI_WORLD_2008_NOMINAL = -0.4071


def _geo_mean(values: list[float]) -> float:
    product = 1.0
    for v in values:
        product *= 1 + v
    return product ** (1 / len(values)) - 1


def check_us_series(data: MarketData) -> bool:
    print("--- us_long_*.csv vs Damodaran's own page (NYU Stern) ---")
    ok = True
    for (year, key), external in DAMODARAN_NOMINAL.items():
        row = data.by_year[year]
        nominal = (1 + row[key]) * (1 + row["inflation"]) - 1
        diff = nominal - external
        flag = "OK" if abs(diff) < 0.002 else "CHECK"
        print(f"  {year} {key:14} ours={nominal:+.2%}  Damodaran={external:+.2%}  "
              f"diff={diff:+.3%}  [{flag}]")
        ok &= abs(diff) < 0.002
    print()
    return ok


def check_global_series(data: MarketData) -> bool:
    if not data.window(["global_equity_gdpw"]):
        print("--- global_gdpw_*.csv not found -- run tools/fetch_global_market_data.py first ---\n")
        return True  # optional file; absence is not a failure

    print("--- global_gdpw_*.csv vs external benchmarks ---")
    window = sorted(data.window(["global_equity_gdpw"]))
    since_1900_eq = [data.by_year[y]["global_equity_gdpw"] for y in window if y >= 1900]
    since_1900_bd = [data.by_year[y]["global_bonds_gdpw"] for y in window
                      if y >= 1900 and data.by_year[y].get("global_bonds_gdpw") is not None]
    ours_eq = _geo_mean(since_1900_eq)
    ours_bd = _geo_mean(since_1900_bd)
    gap_eq = ours_eq - UBS_YEARBOOK_2025_EQUITY_SINCE_1900
    gap_bd = ours_bd - UBS_YEARBOOK_2025_BONDS_SINCE_1900
    print(f"  Since 1900, equity real geo mean: ours={ours_eq:.2%}  "
          f"UBS Yearbook 2025 (125yr)={UBS_YEARBOOK_2025_EQUITY_SINCE_1900:.2%}  gap={gap_eq:+.2%}")
    print(f"  Since 1900, bonds  real geo mean: ours={ours_bd:.2%}  "
          f"UBS Yearbook 2025 (125yr)={UBS_YEARBOOK_2025_BONDS_SINCE_1900:.2%}  gap={gap_bd:+.2%}")
    plausible_range = 0.02 < ours_eq < 0.10  # same order of magnitude as every published "world equity" figure
    above_ubs = ours_eq > UBS_YEARBOOK_2025_EQUITY_SINCE_1900  # expected direction -- see docstring
    print(f"  Plausible order of magnitude: {'OK' if plausible_range else 'CHECK'}  "
          f"| Sits above UBS as expected (survivorship): {'OK' if above_ubs else 'CHECK'}")

    since_2000 = [data.by_year[y]["global_equity_gdpw"] for y in window if y >= 2000]
    if since_2000:
        ours_2000 = _geo_mean(since_2000)
        print(f"  Since 2000 (missing 2021-2024 on our side, so directional only): "
              f"ours={ours_2000:.2%}  UBS 2025 (2000-2024)={UBS_YEARBOOK_2025_EQUITY_SINCE_2000:.2%}  "
              f"gap={ours_2000 - UBS_YEARBOOK_2025_EQUITY_SINCE_2000:+.2%}")

    if 2008 in data.by_year and "global_equity_gdpw" in data.by_year[2008]:
        row = data.by_year[2008]
        nominal = (1 + row["global_equity_gdpw"]) * (1 + row["inflation_gdpw"]) - 1
        diff = nominal - MSCI_WORLD_2008_NOMINAL
        print(f"  2008 nominal: ours={nominal:+.2%}  MSCI World (official)={MSCI_WORLD_2008_NOMINAL:+.2%}  "
              f"diff={diff:+.2%}  [{'OK' if abs(diff) < 0.05 else 'CHECK'}]")
    print()
    return plausible_range and above_ubs


def main() -> None:
    data = MarketData.load()
    us_ok = check_us_series(data)
    global_ok = check_global_series(data)
    if us_ok and global_ok:
        print("All checks within expected tolerance of their external source.")
    else:
        print("One or more checks fell outside tolerance -- read the diffs above before trusting a number.")


if __name__ == "__main__":
    main()
