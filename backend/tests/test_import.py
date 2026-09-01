"""Importing the file the customer actually has.

Not a tidy CSV with a column called `email` — an .xlsx from their shop, with
headers in their own language and columns in whatever order it wrote them.
"""

from __future__ import annotations

import base64
import io
import os
import tempfile
import zipfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="mailpilot-import-"))
os.environ["MAILPILOT_DB"] = str(_TMP / "test.db")
os.environ["MAILPILOT_SECRET"] = "test-secret-not-for-production"

from fastapi.testclient import TestClient  # noqa: E402

from app import db, tabular  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture(scope="module")
def client():
    db.init_db()
    seed(force=True)
    with TestClient(app) as c:
        yield c
    db.close()


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/api/auth/login", json={"email": "pouya@acme.io", "password": "mailpilot"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def xlsx(headers, rows):
    """A real .xlsx, built the way a spreadsheet writes one."""
    strings, index = [], {}

    def sid(text):
        if text not in index:
            index[text] = len(strings)
            strings.append(text)
        return index[text]

    body = ""
    for r, row in enumerate([headers] + rows, start=1):
        cells = "".join(
            f'<c r="{chr(65 + c)}{r}" t="s"><v>{sid(str(v))}</v></c>'
            for c, v in enumerate(row) if str(v) != ""
        )
        body += f'<row r="{r}">{cells}</row>'

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        z.writestr("xl/sharedStrings.xml",
                   f"<sst {ns}>" + "".join(f"<si><t>{s}</s" + "i>" if False else f"<si><t>{s}</t></si>"
                                           for s in strings) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml",
                   f"<worksheet {ns}><sheetData>{body}</sheetData></worksheet>")
    return buf.getvalue()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# ================================================================== parsing


def test_a_semicolon_csv_with_a_bom_is_read():
    """What Excel writes when a European locale exports a CSV."""
    raw = "E-Mail;Vorname\r\na@b.co;Ali\r\n".encode("utf-8-sig")
    headers, rows = tabular.parse(raw)
    assert headers == ["E-Mail", "Vorname"]
    assert rows == [["a@b.co", "Ali"]]


def test_a_persian_xlsx_is_read():
    data = xlsx(["ایمیل", "نام"], [["ali@example.com", "علی"]])
    headers, rows = tabular.parse(data)
    assert headers == ["ایمیل", "نام"]
    assert rows == [["ali@example.com", "علی"]]


def test_the_format_is_decided_by_content_not_extension():
    """A spreadsheet named .csv is a normal thing to be handed."""
    data = xlsx(["email"], [["a@b.co"]])
    headers, _ = tabular.parse(data, filename="contacts.csv")
    assert headers == ["email"]


def test_an_empty_file_is_refused_clearly():
    with pytest.raises(tabular.UnreadableFile):
        tabular.parse(b"")


def test_a_file_that_is_not_a_table_is_refused():
    with pytest.raises(tabular.UnreadableFile):
        tabular.parse(b"PK\x03\x04 not really a zip")


# ================================================================= mapping


def test_analyse_reports_the_columns_and_a_mapping(client, auth):
    data = xlsx(["E-Mail Adresse", "Vorname", "Land"],
                [["ali@example.com", "Ali", "DE"], ["sara@example.com", "Sara", "AT"]])

    r = client.post("/api/contacts/import/analyse",
                    json={"data": b64(data), "filename": "kontakte.xlsx"}, headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["headers"] == ["E-Mail Adresse", "Vorname", "Land"]
    assert body["rowCount"] == 2
    assert len(body["sample"]) == 2
    # with no API key in the tests the keyword fallback runs, and it should
    # still find the email column from a German header
    assert body["mapping"].get("email") == "E-Mail Adresse"
    assert body["source"] in {"ai", "guess"}


def test_the_fallback_finds_persian_headers(client, auth):
    data = xlsx(["ایمیل", "نام", "تلفن"], [["a@b.co", "علی", "0912"]])
    body = client.post("/api/contacts/import/analyse",
                       json={"data": b64(data)}, headers=auth).json()
    assert body["mapping"].get("email") == "ایمیل"
    assert body["mapping"].get("name") == "نام"
    assert body["mapping"].get("phone") == "تلفن"


def test_a_suggested_header_is_always_one_that_exists(client, auth):
    """A mapping naming a column the file does not have would fail at import
    time, far away from the thing that invented it."""
    data = xlsx(["col_a", "col_b"], [["a@b.co", "x"]])
    body = client.post("/api/contacts/import/analyse",
                       json={"data": b64(data)}, headers=auth).json()
    for header in body["mapping"].values():
        assert header in body["headers"]


def test_undecodable_upload_is_refused(client, auth):
    r = client.post("/api/contacts/import/analyse",
                    json={"data": "not base64!!"}, headers=auth)
    assert r.status_code == 422


# ================================================================== import


def test_a_mapped_file_imports(client, auth):
    data = xlsx(["Correo", "Nombre", "Etiquetas"],
                [["nuevo1@example.com", "Juan", "vip,activo"],
                 ["nuevo2@example.com", "Maria", "vip"]])

    r = client.post("/api/contacts/import", json={
        "data": b64(data),
        "mapping": {"email": "Correo", "name": "Nombre", "tags": "Etiquetas"},
    }, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 2

    found = client.get("/api/contacts?q=nuevo1@example.com", headers=auth).json()
    assert found["total"] == 1
    # tags split on the comma the file used, not on a pipe we insisted on
    assert set(found["items"][0]["tags"]) >= {"vip", "activo"}


def test_a_phone_column_is_kept_as_a_tag(client, auth):
    """There is no phone field on a contact, and dropping the column silently
    would lose data the operator deliberately included."""
    data = xlsx(["email", "phone"], [["phoney@example.com", "09121112233"]])
    client.post("/api/contacts/import", json={
        "data": b64(data), "mapping": {"email": "email", "phone": "phone"},
    }, headers=auth)

    found = client.get("/api/contacts?q=phoney@example.com", headers=auth).json()
    assert any(t.startswith("phone:") for t in found["items"][0]["tags"])


def test_an_import_without_an_email_mapping_is_refused(client, auth):
    data = xlsx(["a", "b"], [["x", "y"]])
    r = client.post("/api/contacts/import",
                    json={"data": b64(data), "mapping": {"name": "a"}}, headers=auth)
    assert r.status_code == 422
    assert "email" in r.json()["detail"].lower()


def test_the_original_csv_paste_still_works(client, auth):
    """The old path is still the quickest way to add five addresses."""
    r = client.post("/api/contacts/import", json={
        "csv": "email,name\npaste@example.com,Pasted\n",
    }, headers=auth)
    assert r.status_code == 200
    assert r.json()["created"] == 1


def test_bad_rows_are_reported_rather_than_failing_the_file(client, auth):
    data = xlsx(["email"], [["good@example.com"], ["not-an-email"], ["also@example.com"]])
    body = client.post("/api/contacts/import", json={
        "data": b64(data), "mapping": {"email": "email"},
    }, headers=auth).json()

    assert body["created"] == 2
    assert body["error_count"] == 1
