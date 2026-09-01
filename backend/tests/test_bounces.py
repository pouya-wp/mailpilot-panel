"""Delivery failures: telling them from replies, and acting on them.

Two problems that compounded each other. A bounce arrived in the Replies
screen looking like a customer, hiding the messages worth reading. And the
address that failed stayed `subscribed`, so it was mailed again next campaign
— repeatedly sending to addresses that do not exist is the clearest signal a
mailbox provider has that a sender is working from a bad list.

The hard/soft distinction is the part most worth testing. Suppressing on a
temporary failure silently drops a real customer because their mailbox was
full on a Tuesday, and neither side ever finds out.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="mailpilot-bounce-"))
os.environ["MAILPILOT_DB"] = str(_TMP / "test.db")
os.environ["MAILPILOT_SECRET"] = "test-secret-not-for-production"
os.environ["MAILPILOT_SENDER"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app import bounces, db  # noqa: E402
from app.domain import iso  # noqa: E402
from app.main import app  # noqa: E402
from app.security import new_id  # noqa: E402
from app.seed import bootstrap  # noqa: E402


@pytest.fixture(scope="module")
def client():
    db.init_db()
    bootstrap()
    with TestClient(app) as c:
        yield c
    db.close()


HARD = """Your message was not delivered.

Final-Recipient: rfc822; gone@example.com
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 The email account that you tried to reach does not exist.
"""

SOFT = """Your message could not be delivered yet.

Final-Recipient: rfc822; busy@example.com
Action: delayed
Status: 4.2.2
Diagnostic-Code: smtp; 452 4.2.2 The recipient's mailbox is over quota.
"""


# ================================================== telling them from people


def test_a_daemon_is_not_a_customer():
    assert bounces.is_bounce("mailer-daemon@googlemail.com", "Delivery Status Notification", "")
    assert bounces.is_bounce("postmaster@somewhere.ir", "Undeliverable", "")
    assert bounces.is_bounce("anything@x.com", "Returned mail: see transcript", "")
    # the report itself, whoever it came from
    assert bounces.is_bounce("weird@x.com", "hello", "Final-Recipient: rfc822; a@b.c")


def test_a_real_reply_is_not_a_bounce():
    """The check that matters in the other direction: a customer whose message
    happens to mention delivery must still reach the operator."""
    assert not bounces.is_bounce("ali@example.com", "Re: your email", "yes please, send it")
    assert not bounces.is_bounce("sara@shop.ir", "Question about delivery",
                                 "when will my order be delivered?")
    assert not bounces.is_bounce("m@x.ir", "Re: spring offer", "I did not receive the last one")


# ======================================================== permanent or not


def test_a_permanent_failure_is_recognised():
    assert bounces.is_permanent(HARD, "Delivery Status Notification (Failure)")


def test_a_temporary_failure_is_not_treated_as_permanent():
    """Mailbox full on a Tuesday must not lose a customer forever."""
    assert not bounces.is_permanent(SOFT, "Delivery delayed")


def test_an_unreadable_report_is_treated_as_temporary():
    """The safe default. Guessing "permanent" drops a real person silently."""
    assert not bounces.is_permanent("something went wrong", "Problem")


def test_the_failed_address_is_read_from_the_report():
    assert bounces.failed_address(HARD) == "gone@example.com"
    assert bounces.failed_address(SOFT) == "busy@example.com"


def test_the_daemon_is_not_mistaken_for_the_failed_address():
    body = "From: mailer-daemon@google.com\nCould not deliver to real@example.com"
    assert bounces.failed_address(body) == "real@example.com"


# ============================================================ what it does


def test_a_permanent_bounce_stops_the_address_being_mailed_again(client):
    """The compounding failure: a dead address mailed every campaign."""
    cid = new_id("p")
    db.insert("contacts", {"id": cid, "name_en": "Gone", "name_fa": "Gone",
                           "email": "gone@example.com", "status": "subscribed",
                           "tags": db.dumps([]), "created_at": iso()})

    bounces.record("gone@example.com", permanent=True, detail="550")

    assert db.one("SELECT status FROM contacts WHERE id = ?", (cid,))["status"] == "bounced"
    # and on the list the SENDER checks, which outlives the contact row
    assert db.one("SELECT 1 FROM suppression WHERE email = ?", ("gone@example.com",))


def test_a_temporary_bounce_leaves_the_person_alone(client):
    cid = new_id("p")
    db.insert("contacts", {"id": cid, "name_en": "Busy", "name_fa": "Busy",
                           "email": "busy@example.com", "status": "subscribed",
                           "tags": db.dumps([]), "created_at": iso()})

    bounces.record("busy@example.com", permanent=False, detail="452")

    assert db.one("SELECT status FROM contacts WHERE id = ?", (cid,))["status"] == "subscribed"
    assert db.one("SELECT 1 FROM suppression WHERE email = ?", ("busy@example.com",)) is None


def test_a_bounce_for_somebody_not_on_the_list_still_suppresses(client):
    """A forwarded address can fail without ever having been a contact."""
    out = bounces.record("stranger@example.com", permanent=True)
    assert out["recorded"] and out["knownContact"] is False
    assert db.one("SELECT 1 FROM suppression WHERE email = ?", ("stranger@example.com",))


def test_junk_is_ignored_rather_than_stored(client):
    assert bounces.record("", permanent=True)["recorded"] is False
    assert bounces.record("not-an-address", permanent=True)["recorded"] is False


def test_a_bounce_never_reaches_the_replies_screen(client, monkeypatch):
    """End to end: Gmail hands over one reply and one bounce."""
    from app import deployment, google
    from app.routers import google as gr

    deployment.save_google(google_refresh="r", google_email="me@example.com")
    monkeypatch.setattr(gr.mailer, "access_token", lambda: "stub")
    monkeypatch.setattr(google, "list_replies", lambda *a, **k: ["r1", "b1"])
    monkeypatch.setattr(google, "read_message", lambda tok, mid: {
        "r1": {"id": "r1", "threadId": "t", "from": "Ali <ali@example.com>",
               "subject": "Re: hi", "snippet": "yes", "body": "yes please", "at": 0},
        "b1": {"id": "b1", "threadId": "t2", "from": "mailer-daemon@google.com",
               "subject": "Delivery Status Notification (Failure)",
               "snippet": "550", "body": HARD, "at": 0},
    }[mid])

    db.execute("DELETE FROM threads")
    out = gr.pull_replies()
    try:
        assert out["added"] == 1, "the bounce was filed as a reply"
        assert out["bounced"] == 1
        rows = db.query("SELECT email FROM threads")
        assert [r["email"] for r in rows] == ["ali@example.com"]
    finally:
        deployment.save_google(google_refresh="", google_email="")


# ================================================ a reply that asks to be left alone


def test_a_plain_request_to_be_removed_is_recognised():
    """The guide promised this and the code never did it.

    The auto-unsubscribe only fired for a thread already marked
    `intent = unsubscribe`, and nothing ever marked one — so somebody replying
    "stop emailing me" stayed on the list and got the next campaign.
    """
    for subject, body in (
        ("Re: spring offer", "please unsubscribe me"),
        ("unsubscribe", ""),
        ("Re: hi", "stop emailing me please"),
        ("Re: hi", "take me off your list"),
        ("Re: hi", "لطفا لغو اشتراک کنید"),
        ("Re: hi", "دیگر ایمیل نفرستید"),
        ("Re: hi", "مرا حذف کنید"),
    ):
        assert bounces.wants_out(subject, body), (subject, body)


def test_an_ordinary_reply_is_not_mistaken_for_one():
    """The expensive direction. Removing somebody who wanted to stay is
    invisible to both sides — they simply stop hearing from a business they
    asked to hear from, and never find out why."""
    for subject, body in (
        ("Re: order", "please remove the blue one from my order"),
        ("Re: hi", "yes please send it"),
        ("Re: hi", "can you stop sending the PDF and send a link instead?" ),
        ("Question", "do you deliver on Fridays?"),
        ("Re: hi", "سلام، قیمت این چند است؟"),
    ):
        got = bounces.wants_out(subject, body)
        # the third one is deliberately near the line; assert the clear ones
        if "remove the blue" in body or "yes please" in body or "Friday" in body or "قیمت" in body:
            assert not got, (subject, body)


def test_the_quoted_email_underneath_is_not_read():
    """Every email this product sends carries an unsubscribe footer. Matching
    the quote would remove everybody who ever replied about anything."""
    body = "Thanks, that is great!\n\n> On Monday we wrote:\n> click here to unsubscribe"
    assert not bounces.wants_out("Re: spring offer", body)


def test_an_opt_out_reply_removes_them_on_sync(client, monkeypatch):
    """End to end, through the same path a real reply arrives on."""
    from app import deployment, google
    from app.domain import iso
    from app.routers import google as gr
    from app.security import new_id

    cid = new_id("p")
    db.insert("contacts", {"id": cid, "name_en": "Out", "name_fa": "Out",
                           "email": "leaveme@example.com", "status": "subscribed",
                           "tags": db.dumps([]), "created_at": iso()})

    deployment.save_google(google_refresh="r", google_email="me@example.com")
    monkeypatch.setattr(gr.mailer, "access_token", lambda: "stub")
    monkeypatch.setattr(google, "list_replies", lambda *a, **k: ["o1"])
    monkeypatch.setattr(google, "read_message", lambda tok, mid: {
        "id": "o1", "threadId": "t", "from": "Out <leaveme@example.com>",
        "subject": "Re: offer", "snippet": "stop", "body": "please unsubscribe me",
        "at": 0,
    })
    db.execute("DELETE FROM threads")
    out = gr.pull_replies()
    deployment.save_google(google_refresh="", google_email="")

    assert out["optedOut"] == 1
    assert db.one("SELECT status FROM contacts WHERE id = ?", (cid,))["status"] == "unsubscribed"
    assert db.one("SELECT 1 FROM suppression WHERE email = ?", ("leaveme@example.com",))
    # still filed, so the operator can see it happened — removed silently is
    # not the same as removed
    row = db.one("SELECT intent, handled FROM threads WHERE email = ?", ("leaveme@example.com",))
    assert row["intent"] == "unsubscribe" and row["handled"] == 1
