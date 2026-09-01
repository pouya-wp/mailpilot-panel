"""Does "use for all" reach the mail that actually goes out?

It did not. The house template was applied in exactly one place — `POST
/campaigns`, at the moment of creation — so marking a template as the default
changed nothing about anything that already existed, nothing the agent made
through its own tools, and nothing sent as a one-off. The operator switched it
on, the panel agreed, and the mail went out as bare paragraphs.

These tests pin the template to SEND time, which is the only moment at which
the question "which template is current?" has a useful answer.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="mailpilot-house-"))
os.environ["MAILPILOT_DB"] = str(_TMP / "test.db")
os.environ["MAILPILOT_SECRET"] = "test-secret-not-for-production"
os.environ["MAILPILOT_SENDER"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app import db, emaildesign, emailhtml  # noqa: E402
from app.domain import iso  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402
from app.security import new_id  # noqa: E402

WRAPPER = (
    '<html><body><table><tr><td>NORTHWIND HEADER</td></tr>'
    '<tr><td>{{content}}</td></tr>'
    '<tr><td><a href="{{unsubscribe}}">out</a></td></tr></table></body></html>'
)


@pytest.fixture(scope="module")
def client():
    db.init_db()
    seed(force=True)
    with TestClient(app) as c:
        yield c
    db.close()


@pytest.fixture(autouse=True)
def _no_template(client):
    yield
    db.execute("DELETE FROM templates WHERE name_en LIKE 'T-%'")
    db.execute("UPDATE templates SET is_default = 0")


def _house(html: str = WRAPPER) -> str:
    tid = new_id("tpl")
    db.insert("templates", {"id": tid, "name_en": "T-house", "name_fa": "T-house",
                            "html": html, "is_default": 1, "created_at": iso()})
    db.execute("UPDATE templates SET is_default = 0 WHERE id != ?", (tid,))
    return tid


# ============================================================ the actual bug


def test_a_template_chosen_AFTER_a_campaign_still_applies_to_it():
    """The reported failure, in one test.

    The operator writes a campaign, then designs a template and marks it "use
    for all". Applying the template at creation meant this campaign — every
    campaign that already existed — was never wrapped.
    """
    body = "<p>Spring is here.</p>"
    _house()  # marked default AFTER the body was written
    out = emailhtml.wrap_for_send(db, body, subject="Spring")

    assert "NORTHWIND HEADER" in out
    assert "Spring is here." in out


def test_changing_the_default_changes_what_goes_out_next():
    body = "<p>Hello.</p>"
    _house()
    assert "NORTHWIND HEADER" in emailhtml.wrap_for_send(db, body)

    db.execute("UPDATE templates SET is_default = 0")
    _house(WRAPPER.replace("NORTHWIND HEADER", "SECOND HEADER"))
    assert "SECOND HEADER" in emailhtml.wrap_for_send(db, body)


def test_with_no_house_template_the_message_goes_out_as_written():
    db.execute("UPDATE templates SET is_default = 0")
    assert emailhtml.wrap_for_send(db, "<p>Plain.</p>") == "<p>Plain.</p>"


def test_a_finished_email_is_not_nested_inside_another_one():
    """Someone who pasted a whole document has already said what they want."""
    _house()
    whole = "<!doctype html><html><body>Mine</body></html>"
    assert emailhtml.wrap_for_send(db, whole) == whole


def test_a_template_with_no_slot_is_not_used_as_a_wrapper():
    """A complete email marked default is its own thing, not a frame."""
    _house("<html><body>A whole email with no slot</body></html>")
    assert emailhtml.wrap_for_send(db, "<p>Body.</p>") == "<p>Body.</p>"


def test_the_subject_reaches_the_template():
    _house(WRAPPER.replace("NORTHWIND HEADER", "{{subject}}"))
    out = emailhtml.wrap_for_send(db, "<p>x</p>", subject="Half price today")
    assert "Half price today" in out


def test_merge_tags_survive_the_wrap():
    """They are filled per recipient, much later, by the sender."""
    _house()
    out = emailhtml.wrap_for_send(db, "<p>Hi {{first_name}}</p>")
    assert "{{first_name}}" in out and "{{unsubscribe}}" in out


# ================================================== the paths that send mail


def test_the_agents_one_off_send_is_wrapped_too(client, monkeypatch):
    """`send_email` never touched the template at all.

    Gmail is stubbed at the two functions that reach the network, so this
    exercises the real path — validation, wrap, MIME — and captures what would
    have been put on the wire.
    """
    import base64

    from app import deployment, google, mailer, tools

    _house()
    deployment.save_google(google_refresh="r", google_email="agent@example.com")
    sent = {}

    monkeypatch.setattr(mailer, "access_token", lambda: "stub-token")
    monkeypatch.setattr(google, "send_message",
                        lambda token, raw: sent.update(raw=raw) or {"id": "m1"})
    try:
        out = tools.run("send_email", {"to": ["nobody@example.com"], "subject": "S",
                                       "body": ["Hello there"]})
    finally:
        deployment.save_google(google_refresh="", google_email="")

    assert out["sent"] == ["nobody@example.com"]
    mime = base64.urlsafe_b64decode(sent["raw"] + "=" * (-len(sent["raw"]) % 4)).decode()
    # the house frame reached the actual message, not just the preview
    assert "NORTHWIND HEADER" in mime
    assert "Hello there" in mime


def test_a_campaign_stores_what_was_written_not_the_wrapper(client):
    """The body is the message; the frame is applied on the way out.

    Storing the wrapped copy is what made the template un-changeable after the
    fact, and it also made the stored body impossible to edit sensibly.
    """
    r = client.post("/api/auth/login",
                    json={"email": "pouya@acme.io", "password": "mailpilot"})
    auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

    _house()
    made = client.post("/api/campaigns", headers=auth, json={
        "name": "Stored plain", "subject": "S", "body": "Just a line",
    })
    assert made.status_code == 201, made.text
    row = db.one("SELECT body_en FROM campaigns WHERE id = ?", (made.json()["id"],))
    assert "NORTHWIND HEADER" not in row["body_en"]
    client.delete(f"/api/campaigns/{made.json()['id']}", headers=auth)


# ================================================================ the design


@pytest.mark.parametrize("lang", ["en", "fa"])
def test_the_house_template_is_email_safe(lang):
    html = emaildesign.starter(lang)
    assert emailhtml.lint(html) == []
    assert "display:flex" not in html and "display:grid" not in html
    # every slot the sender fills later
    for slot in ("{{content}}", "{{unsubscribe}}", "{{cta_url}}", "{{subject}}"):
        assert slot in html


@pytest.mark.parametrize("lang", ["en", "fa"])
def test_the_house_template_asks_for_estedad_and_survives_without_it(lang):
    """Gmail will not load the font. The stack has to stand on its own."""
    html = emaildesign.starter(lang)
    assert "Estedad" in html
    assert "fonts.googleapis.com" in html
    # a real fallback chain, not just the one name
    assert "Tahoma" in html and "sans-serif" in html


def test_the_persian_template_is_right_to_left():
    html = emaildesign.starter("fa")
    assert 'dir="rtl"' in html
    assert "text-align:right" in html


def test_the_brief_tells_the_model_about_the_font():
    text = emaildesign.brief(lang="fa")
    assert "Estedad" in text
    assert "{{content}}" in text and "{{unsubscribe}}" in text


def test_the_brief_changes_when_a_reference_is_attached():
    without = emaildesign.brief(lang="en")
    with_ref = emaildesign.brief(lang="en", has_reference_images=True)
    assert "REFERENCE" not in without
    assert "REFERENCE" in with_ref
    # taking direction, not tracing
    assert "logos" in with_ref or "pixel" in with_ref
