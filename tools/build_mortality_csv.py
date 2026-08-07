"""Turn the ONS national life tables workbook into the CSV the engine reads.

    python tools/build_mortality_csv.py nltew198020223.xlsx \
        src/retireplan/data/mortality/ons_qx_ew_2022_2024.csv

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
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

#: Column offsets within a sheet: males start at A, females after a blank
#: separator column at H. Both blocks are (age, mx, qx, lx, dx, ex).
MALE_AGE_COL, MALE_QX_COL = 0, 2
FEMALE_AGE_COL, FEMALE_QX_COL = 7, 9


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
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    source, destination = Path(sys.argv[1]), Path(sys.argv[2])
    sheet = "2022-2024"

    with zipfile.ZipFile(source) as z:
        qx = extract(read_rows(z, sheet_path(z, sheet)))

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
            f"# Extracted from {source.name} by tools/build_mortality_csv.py.\n"
            f"# No figure was transcribed by hand.\n"
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
