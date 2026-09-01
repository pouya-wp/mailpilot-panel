"""Handing data back as a spreadsheet.

One module because four screens offered an export button and none of them had
anything behind it — and writing the CSV four times would have meant getting
the encoding right four times.

TWO DETAILS THAT ARE NOT PEDANTRY. A UTF-8 byte-order mark, because Excel on
Windows reads a UTF-8 file without one as the system codepage and turns every
Persian name into mojibake; that is most of this product's audience opening
most of its exports. And CRLF line endings, which the same reader expects.

Neither matters on a Mac or in a text editor, which is exactly why they get
missed until a customer says the file is broken.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Iterable

from fastapi import Response

#: The character Excel looks for before it will believe a file is UTF-8.
BOM = "﻿"


def csv_response(rows: Iterable[dict[str, Any]], columns: list[str],
                 filename: str) -> Response:
    """Rows to a downloadable CSV.

    `extrasaction="ignore"` so a caller may hand over richer dicts than the
    column list asks for, which keeps the query and the header from having to
    be edited in lockstep.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore",
                            lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    return Response(
        content=BOM + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        # `attachment` rather than `inline`: this is a file to keep, and a
        # browser that renders it in a tab has thrown away the filename.
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def rate(part: Any, whole: Any) -> float | str:
    """A percentage, or an empty cell when there is no denominator.

    Empty, not zero. A campaign that has sent nothing has no open rate; writing
    0% claims it was opened by nobody, which is a different and false statement
    — and it is the one a spreadsheet will happily average into a chart.
    """
    try:
        whole = float(whole or 0)
        if whole <= 0:
            return ""
        return round(float(part or 0) / whole * 100, 2)
    except (TypeError, ValueError):
        return ""
