"""Turn the ONS national life tables workbook into the CSV the engine reads.

    python tools/build_mortality_csv.py --fetch
    python tools/build_mortality_csv.py nltew198020223.xlsx \
        src/retireplan/data/mortality/ons_qx_ew_2022_2024.csv

`--fetch` downloads the current workbook itself, via the "current" link ONS
keeps pointing at whatever the latest release is (the filename behind it is
versioned and does change release to release, which is why this script
doesn't hardcode it). Point it at a file you already have instead if you'd
rather not depend on that URL surviving, or you're working from an archived
release.

Either way the target sheet and the CSV's output filename are read from the
workbook itself -- whichever `\\d{4}-\\d{4}` sheet is most recent -- not
hardcoded, so a future ONS release with a new period needs no edit here.

Run once per clone (the CSV is gitignored, not committed — see
DATA_SETUP.md). It exists as a script rather than as a note in a docstring
because a mortality table is exactly the kind of data nobody can eyeball: a
transcription error in the middle of it is invisible and permanent, and would
quietly move every bequest figure the engine produces. Anyone doubting a
number here can re-run this against the published workbook and diff.

Reads `.xlsx` with `zipfile` + `xml.etree` — an xlsx is a zip of XML — so the
package keeps its promise of having no runtime dependencies and this script
adds no build ones either.

Source: ONS, "National life tables: England and Wales", reference tables.
https://www.ons.gov.uk/peoplepopulationandcommunity/birthsdeathsandmarriages/lifeexpectancies/datasets/nationallifetablesenglandandwalesreferencetables
"""
from __future__ import annotations

import re
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
DATASET_PAGE = (
    "https://www.ons.gov.uk/peoplepopulationandcommunity/birthsdeathsandmarriages"
    "/lifeexpectancies/datasets/nationallifetablesenglandandwalesreferencetables"
)
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "src" / "retireplan" / "data" / "mortality"
USER_AGENT = "Mozilla/5.0 (compatible; retireplan-data-fetch/1.0)"

#: Column offsets within a sheet: males start at A, females after a blank
#: separator column at H. Both blocks are (age, mx, qx, lx, dx, ex).
MALE_AGE_COL, MALE_QX_COL = 0, 2
FEMALE_AGE_COL, FEMALE_QX_COL = 7, 9


def fetch_current_workbook() -> Path:
    """Download whatever workbook ONS's "current" link points to right now."""
    request = urllib.request.Request(DATASET_PAGE, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8", "replace")
    match = re.search(r'href="([^"]*/current/[^"]+\.xlsx)"', html)
    if match is None:
        raise SystemExit(
            "couldn't find a 'current/*.xlsx' link on the ONS dataset page -- "
            "its layout may have changed. Download the workbook by hand from "
            f"{DATASET_PAGE} and pass its path instead."
        )
    url = match.group(1)
    if url.startswith("/"):
        url = "https://www.ons.gov.uk" + url
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    tmp = Path(tempfile.mkstemp(suffix=".xlsx")[1])
    tmp.write_bytes(data)
    print(f"fetched {url}")
    return tmp


def sheet_names(z: zipfile.ZipFile) -> list[str]:
    workbook = z.read("xl/workbook.xml").decode("utf-8", "replace")
    return re.findall(r'<sheet[^>]*name="([^"]+)"', workbook)


def latest_period(names: list[str]) -> str:
    """The most recent `YYYY-YYYY` sheet -- everything else here is notes/methodology tabs."""
    periods = [n for n in names if re.fullmatch(r"\d{4}-\d{4}", n)]
    if not periods:
        raise SystemExit(f"no year-range sheet found among {names!r} -- has the workbook changed shape?")
    return max(periods, key=lambda p: int(p[:4]))


def sheet_path(z: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = z.read("xl/workbook.xml").decode("utf-8", "replace")
    rid = None
    for match in re.finditer(r'<sheet[^>]*name="([^"]+)"[^>]*r:id="([^"]+)"', workbook):
        if match.group(1) == sheet_name:
            rid = match.group(2)
    if rid is None:
        raise SystemExit(f"no sheet named {sheet_name!r} in the workbook")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8", "replace")
    targets = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
    return "xl/" + targets[rid].lstrip("/").replace("xl/", "")


def read_rows(z: zipfile.ZipFile, path: str) -> list[list[str]]:
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall(f"{NS}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))

    def value(cell) -> str:
        v = cell.find(f"{NS}v")
        if v is None or v.text is None:
            return ""
        return shared[int(v.text)] if cell.get("t") == "s" else v.text

    rows = []
    for row in ET.fromstring(z.read(path)).iter(f"{NS}row"):
        # Cell references carry the column letter, so a sparse row must be
        # placed rather than appended -- a blank cell is simply absent from
        # the XML, and ignoring that would shift every column after it.
        cells: dict[int, str] = {}
        for cell in row.findall(f"{NS}c"):
            ref = cell.get("r") or ""
            letters = "".join(c for c in ref if c.isalpha())
            index = 0
            for ch in letters:
                index = index * 26 + (ord(ch) - ord("A") + 1)
            cells[index - 1] = value(cell)
        width = max(cells) + 1 if cells else 0
        rows.append([cells.get(i, "") for i in range(width)])
    return rows


def extract(rows: list[list[str]]) -> dict[tuple[str, int], float]:
    qx: dict[tuple[str, int], float] = {}
    for row in rows:
        for sex, age_col, qx_col in (
            ("male", MALE_AGE_COL, MALE_QX_COL),
            ("female", FEMALE_AGE_COL, FEMALE_QX_COL),
        ):
            if len(row) <= qx_col:
                continue
            try:
                age = int(float(row[age_col]))
                rate = float(row[qx_col])
            except (ValueError, TypeError):
                continue
            if 0 <= age <= 120 and 0.0 <= rate <= 1.0:
                qx[(sex, age)] = rate
    return qx


def main() -> None:
    args = sys.argv[1:]
    fetched: Path | None = None

    if args and args[0] == "--fetch":
        source = fetched = fetch_current_workbook()
        destination = Path(args[1]) if len(args) > 1 else None
    elif len(args) == 2:
        source, destination = Path(args[0]), Path(args[1])
    else:
        raise SystemExit(__doc__)

    with zipfile.ZipFile(source) as z:
        names = sheet_names(z)
        sheet = latest_period(names)
        qx = extract(read_rows(z, sheet_path(z, sheet)))

    if fetched is not None:
        fetched.unlink()

    if destination is None:
        destination = DEFAULT_OUTPUT_DIR / f"ons_qx_ew_{sheet.replace('-', '_')}.csv"

    ages = sorted({age for _, age in qx})
    if not ages:
        raise SystemExit("no qx values found — has the sheet layout changed?")
    for sex in ("male", "female"):
        missing = [a for a in ages if (sex, a) not in qx]
        if missing:
            raise SystemExit(f"{sex} qx missing for ages {missing[:5]}...")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as f:
        f.write(
            f"# ONS national life tables, England and Wales, {sheet}.\n"
            f"# Source: https://www.ons.gov.uk/peoplepopulationandcommunity/"
            f"birthsdeathsandmarriages/lifeexpectancies/datasets/"
            f"nationallifetablesenglandandwalesreferencetables\n"
            f"# Extracted by tools/build_mortality_csv.py. No figure was\n"
            f"# transcribed by hand.\n"
            f"#\n"
            f"# qx is the probability that a person aged exactly x dies before\n"
            f"# reaching x+1, under the mortality rates observed in {sheet}.\n"
            f"#\n"
            f"# KNOWN SIMPLIFICATIONS, all of which affect a projection:\n"
            f"#  * These are PERIOD rates: they assume {sheet} mortality lasts\n"
            f"#    forever, which understates the life expectancy of someone\n"
            f"#    alive today by roughly two to three years, because mortality\n"
            f"#    has been improving. A cohort table would be better.\n"
            f"#  * England and Wales only. Scotland and Northern Ireland differ.\n"
            f"#  * National averages. An affluent household typically lives two\n"
            f"#    to four years longer than these rates imply, which flatters\n"
            f"#    success probability and understates bequest. `LifeTable` has\n"
            f"#    an `age_rating` for this; it defaults to 0, i.e. no silent\n"
            f"#    adjustment.\n"
            f"sex,age,qx\n"
        )
        for age in ages:
            for sex in ("male", "female"):
                f.write(f"{sex},{age},{qx[(sex, age)]!r}\n")

    print(f"wrote {destination} — {len(ages)} ages x 2 sexes")


if __name__ == "__main__":
    main()
