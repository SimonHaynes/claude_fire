"""Fetch UK gilt yields and implied inflation from the Bank of England.

    .venv/bin/python tools/fetch_gilt_yields.py

Writes `src/retireplan/data/gilts/uk_gilt_yields_<start>_<end>.csv`: one row a month,
six columns of yields. Run once per clone (the CSV is gitignored, not
committed — see DATA_SETUP.md).

Annuity pricing needs a discount curve, and a gilt curve is the right one: UK
insurers back annuity liabilities with gilts and long corporate bonds, which is
why annuity rates move within weeks of a gilt selloff. `retireplan.annuity`
reads this file.

## What is fetched

Six daily series from the Bank of England's Interest & Exchange Rates database,
averaged to calendar months:

| Code | Meaning |
|---|---|
| `IUDSNPY` `IUDMNPY` `IUDLNPY` | nominal par yield, 5 / 10 / 20 year |
| `IUDSIZC` `IUDMIZC` `IUDLIZC` | implied inflation, zero coupon, 5 / 10 / 20 year |

**Real yields are derived, not published here.** The Bank's index-linked real
yields are not in this database, so the file carries nominal yields and implied
inflation and lets `annuity.py` compute `(1+n)/(1+i) - 1`. That is the Fisher
relation applied to two published series rather than a fourth-hand number, and
it makes the inflation risk premium buried in the breakeven visible instead of
silently folded into a "real yield" column.

**There is no 15-year series**, which is the maturity the annuity market
usually quotes against. `annuity.py` interpolates between the 10 and 20 year
points; the curve is close to linear over that span, and interpolating two
published figures beats sourcing a third from somewhere less authoritative.

Monthly averages rather than daily closes, deliberately: an annuity quote is
priced off a curve on one day, but a *plan* built on one day's gilt yield
inherits that day's noise. A month is the shortest window that is about the
level rather than the weather.
"""
from __future__ import annotations

import csv
import datetime as dt
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

DATA_DIR = (
    Path(__file__).resolve().parent.parent / "src" / "retireplan" / "data" / "gilts"
)
USER_AGENT = "retireplan/1.0 (research; contact via repository)"

IADB = "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"

SERIES = {
    "gilt_5y": "IUDSNPY",
    "gilt_10y": "IUDMNPY",
    "gilt_20y": "IUDLNPY",
    "inflation_5y": "IUDSIZC",
    "inflation_10y": "IUDMIZC",
    "inflation_20y": "IUDLIZC",
}

COLUMNS = list(SERIES)

START = "01/Jan/1990"
"""The earliest any of the six begins. The 20-year nominal par yield only
starts in 2000 and the 20-year breakeven in 1996, so early rows are sparse —
`annuity.py` requires a complete row and simply ignores the rest."""


def _get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def fetch_series(code: str) -> dict[str, float]:
    """One BoE series, averaged to calendar months keyed `YYYY-MM`."""
    today = dt.date.today().strftime("%d/%b/%Y")
    url = (
        f"{IADB}?csv.x=yes&Datefrom={START}&Dateto={today}"
        f"&SeriesCodes={code}&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N"
    )
    daily: dict[str, list[float]] = defaultdict(list)
    for row in csv.DictReader(_get(url).splitlines()):
        raw = (row.get(code) or "").strip()
        if not raw:
            continue
        observed = dt.datetime.strptime(row["DATE"].strip(), "%d %b %Y").date()
        daily[f"{observed:%Y-%m}"].append(float(raw))
    return {month: sum(values) / len(values) for month, values in daily.items()}


def write_csv(months: dict[str, dict[str, float]]) -> Path:
    complete = sorted(m for m, row in months.items() if len(row) == len(COLUMNS))
    if not complete:
        raise SystemExit("no month has all six series — the BoE codes may have changed")
    start, end = complete[0][:4], complete[-1][:4]
    path = DATA_DIR / f"uk_gilt_yields_{start}_{end}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)

    fetched = dt.date.today().isoformat()
    with path.open("w", newline="", encoding="utf-8") as fh:
        fh.write(
            f"# UK gilt yields and implied inflation, monthly averages of daily rates,"
            f" {complete[0]} to {complete[-1]}.\n"
            f"#\n"
            f"# Fetched {fetched} by tools/fetch_gilt_yields.py from the Bank of\n"
            f"# England Interest & Exchange Rates database:\n"
            f"#   https://www.bankofengland.co.uk/boeapps/database/\n"
            f"#\n"
            f"# Series codes, all 'Yield from British Government Securities':\n"
        )
        for column, code in SERIES.items():
            fh.write(f"#   {column:<14} {code}\n")
        fh.write(
            "#\n"
            "# Percent per year, not decimal fractions. Nominal par yields and\n"
            "# implied (zero coupon) inflation; REAL YIELDS ARE NOT PUBLISHED HERE\n"
            "# and are derived by retireplan.annuity as (1+n)/(1+i) - 1.\n"
            "#\n"
            "# Only months where all six series printed are written, so the file\n"
            "# starts when the shortest series does, not when the longest does.\n"
            "#\n"
            "# No figure was transcribed by hand.\n"
        )
        writer = csv.writer(fh)
        writer.writerow(["month", *COLUMNS])
        for month in complete:
            row = months[month]
            writer.writerow([month, *(f"{row[c]:.4f}" for c in COLUMNS)])
    return path


def main() -> int:
    months: dict[str, dict[str, float]] = defaultdict(dict)
    for column, code in SERIES.items():
        print(f"fetching {code} ({column})...")
        try:
            for month, value in fetch_series(code).items():
                months[month][column] = value
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            print(f"  failed: {exc}", file=sys.stderr)
            return 1

    path = write_csv(months)
    rows = sum(1 for line in path.read_text(encoding="utf-8").splitlines()
               if line and not line.startswith("#")) - 1
    print(f"\nwrote {path} ({rows} months)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
