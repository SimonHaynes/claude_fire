"""Read an `.xlsx` with the standard library alone — it is a zip of XML.

Shared by `build_mortality_csv.py` (ONS life tables) and
`fetch_market_data.py` (Damodaran's inflation sheet). Both need exactly this
much of the format and nothing more, and the engine is deliberately
dependency-free, so a spreadsheet library is not worth taking on for two
callers reading two rectangles of numbers.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def sheet_names(z: zipfile.ZipFile) -> list[str]:
    workbook = z.read("xl/workbook.xml").decode("utf-8", "replace")
    return re.findall(r'<sheet[^>]*name="([^"]+)"', workbook)


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
