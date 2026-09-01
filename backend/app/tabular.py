"""Reading a contact list out of whatever the customer exported.

They will not hand over a tidy CSV with a column called `email`. They will hand
over the .xlsx their shop produced, with headers in their own language, columns
in an order nobody chose, and three sheets of which only the first matters.

So this does two things:

  * PARSES both CSV and XLSX to the same (headers, rows) shape.
  * Nothing else. Deciding which column is the email address is a separate
    problem, solved a layer up by asking the model — because "Correo",
    "نشانی رایانامه" and "Contact E-Mail" are all the email column and no
    amount of pattern matching will keep up with that list.

XLSX is read with the standard library rather than openpyxl. A .xlsx is a zip
of XML; a contact export is the simple case of that format — one sheet, inline
or shared strings, no formulas worth evaluating — and the whole reader is sixty
lines. That keeps this backend's dependency list at "the web framework", which
is the property that makes it easy to deploy anywhere.
"""

from __future__ import annotations

import csv
import io
import zipfile
from xml.etree import ElementTree

#: Enough of a file to show the operator and to let the model recognise columns.
SAMPLE_ROWS = 5

#: A refusal, not a guess: past this the request should be a background job.
MAX_ROWS = 50_000

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class UnreadableFile(ValueError):
    """The bytes are not a table we can read. Always the operator's problem."""


def parse(data: bytes, *, filename: str = "") -> tuple[list[str], list[list[str]]]:
    """(headers, rows) from a CSV or XLSX file.

    The format is decided by the CONTENT, not the extension: a file named .csv
    that is really a spreadsheet is a normal thing to be handed, and the zip
    magic number settles it in two bytes.
    """
    if not data:
        raise UnreadableFile("The file is empty")

    if data[:2] == b"PK":
        return _xlsx(data)
    return _csv(data)


# ---------------------------------------------------------------------- csv


def _csv(data: bytes) -> tuple[list[str], list[list[str]]]:
    text = _decode(data)
    try:
        # sniff the delimiter: European exports are routinely semicolon-separated
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect)
    rows = [r for r in reader if any((c or "").strip() for c in r)]
    if not rows:
        raise UnreadableFile("The file has no rows")

    headers = [(h or "").strip() for h in rows[0]]
    return headers, [_pad(r, len(headers)) for r in rows[1 : MAX_ROWS + 1]]


def _decode(data: bytes) -> str:
    """Excel writes UTF-8 with a BOM, and Windows exports are often cp1256 in
    this part of the world. Try the likely encodings before giving up."""
    for encoding in ("utf-8-sig", "utf-8", "cp1256", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnreadableFile("Could not read the file's text encoding")


# --------------------------------------------------------------------- xlsx


def _xlsx(data: bytes) -> tuple[list[str], list[list[str]]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UnreadableFile("That file is not a readable spreadsheet") from exc

    shared = _shared_strings(archive)
    sheet = next((n for n in archive.namelist()
                  if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")), None)
    if sheet is None:
        raise UnreadableFile("The spreadsheet has no sheets")

    grid: list[list[str]] = []
    root = ElementTree.fromstring(archive.read(sheet))
    for row in root.findall(".//m:sheetData/m:row", _NS):
        cells: list[str] = []
        for cell in row.findall("m:c", _NS):
            # Cells are addressed, not positional: an empty cell is simply
            # absent, so the column letter is what keeps a row aligned.
            column = _column_index(cell.get("r", ""))
            while len(cells) < column:
                cells.append("")
            cells.append(_cell_text(cell, shared))
        if any(c.strip() for c in cells):
            grid.append(cells)
        if len(grid) > MAX_ROWS + 1:
            break

    if not grid:
        raise UnreadableFile("The sheet is empty")

    headers = [h.strip() for h in grid[0]]
    return headers, [_pad(r, len(headers)) for r in grid[1:]]


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    """Most text in a workbook lives in one shared table, referenced by index."""
    try:
        raw = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ElementTree.fromstring(raw)
    out = []
    for si in root.findall("m:si", _NS):
        # a string can be split across runs when parts of it are styled
        out.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
    return out


def _cell_text(cell, shared: list[str]) -> str:
    kind = cell.get("t", "n")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(f"{{{_NS['m']}}}t")).strip()

    value = cell.find("m:v", _NS)
    if value is None or value.text is None:
        return ""
    if kind == "s":
        try:
            return shared[int(value.text)].strip()
        except (ValueError, IndexError):
            return ""
    text = value.text.strip()
    # 42.0 is how a spreadsheet stores 42, and an id or a phone number that
    # comes back with a trailing .0 is wrong in a way people notice
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _column_index(ref: str) -> int:
    """'C4' -> 2. The letters are base-26 with no zero."""
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return max(0, n - 1)


def _pad(row: list[str], width: int) -> list[str]:
    row = [(c or "").strip() for c in row[:width]]
    return row + [""] * (width - len(row))


def sample(headers: list[str], rows: list[list[str]]) -> list[dict[str, str]]:
    """The first few rows as dicts, for showing the operator what was read."""
    return [dict(zip(headers, r)) for r in rows[:SAMPLE_ROWS]]
