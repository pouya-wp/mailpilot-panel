"""Who may be sent to.

This is the module that stands between a campaign and somebody who asked
not to hear from us again, so the tests are mostly about refusals rather
than about the happy path.

Two properties are load-bearing:

  * THE SUMMARY AND THE QUEUE AGREE. The pre-flight figures a customer
    reads before launching come from the same call the sender uses to fill
    the outbox. A test that only checked the summary would pass while the
    sender did something else entirely.

  * A REFUSAL IS NOT OVERRIDABLE. There is deliberately no argument
    anywhere in this module that lets a caller past suppression or an
    unsubscribe, and nothing here should ever add one.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("MAILPILOT_DB", str(Path(tempfile.mkdtemp(prefix="elig-")) / "t.db"))
os.environ.setdefault("MAILPILOT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("MAILPILOT_SENDER", "0")

from app import db, eligibility, mailer  # noqa: E402
from app.domain import iso  # noqa: E402
from app.security import new_id  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh():
    db.init_db()
    for table in ("outbox", "suppression", "contacts"):
        db.execute(f"DELETE FROM {table}")
    yield


def _suppress(email: str, reason: str = "unsub") -> None:
    db.insert("suppression", {"id": new_id("sup"), "email": email,
                              "reason": reason, "created_at": iso()})


def _contact(email: str, status: str = "subscribed") -> None:
    db.insert("contacts", {
        "id": new_id("p"), "name_en": "X", "name_fa": "X", "email": email,
        "status": status, "score": 0, "ltv": 0, "orders": 0, "tags": "[]",
        "source_id": "test", "source_en": "", "source_fa": "",
        "country": "", "device": "desktop", "last_open_at": None,
        "created_at": iso(),
    })


# ------------------------------------------------------------- the refusals


def test_an_unsubscribed_contact_is_refused():
    _contact("gone@example.com", status="unsubscribed")
    out = eligibility.classify("c-1", [{"email": "gone@example.com"}])
    assert out["eligibleCount"] == 0
    assert out["counts"]["unsubscribed"] == 1


def test_a_suppressed_address_is_refused():
    _suppress("stop@example.com")
    out = eligibility.classify("c-1", [{"email": "stop@example.com"}])
    assert out["eligibleCount"] == 0
    assert out["counts"]["suppressed"] == 1


def test_a_previous_hard_bounce_is_refused_and_named_as_such():
    """The reason matters: "suppressed" and "this address does not exist"
    lead a customer to different actions."""
    _suppress("dead@example.com", reason="bounce")
    out = eligibility.classify("c-1", [{"email": "dead@example.com"}])
    assert out["counts"]["hard_bounced"] == 1
    assert out["counts"]["suppressed"] == 0


@pytest.mark.parametrize("bad", ["", "not-an-address", "no@domain", "two@@at.com",
                                 "spaces in@example.com", "@example.com"])
def test_malformed_addresses_are_refused(bad):
    out = eligibility.classify("c-1", [{"email": bad}])
    assert out["eligibleCount"] == 0
    assert out["counts"]["malformed"] == 1


def test_the_same_address_twice_in_one_list_is_sent_to_once():
    out = eligibility.classify("c-1", [
        {"email": "one@example.com"},
        {"email": "ONE@example.com"},   # case is not a different person
    ])
    assert out["eligibleCount"] == 1
    assert out["counts"]["duplicate"] == 1


# ------------------------------------------------- the summary and the queue


def test_the_preflight_figures_are_what_the_sender_actually_does():
    """The whole reason these share an implementation."""
    _contact("good@example.com")
    _contact("gone@example.com", status="unsubscribed")
    _suppress("stop@example.com")
    people = [
        {"id": "a", "email": "good@example.com"},
        {"id": "b", "email": "gone@example.com"},
        {"id": "c", "email": "stop@example.com"},
        {"id": "d", "email": "broken"},
        {"id": "e", "email": "good@example.com"},
    ]

    promised = eligibility.summary("c-queue", people)
    assert promised["selected"] == 5
    assert promised["eligible"] == 1

    actually = mailer.enqueue("c-queue", recipients=people)
    assert actually == promised["eligible"]


def test_every_exclusion_is_recorded_with_its_reason():
    """"912 of 1,000" is only acceptable if the other 88 can be named."""
    _suppress("stop@example.com")
    mailer.enqueue("c-why", recipients=[
        {"id": "a", "email": "fine@example.com"},
        {"id": "b", "email": "stop@example.com"},
    ])
    rows = db.query("SELECT email, status, error FROM outbox WHERE campaign_id = 'c-why'")
    blocked = [r for r in rows if r["status"] == "blocked"]
    assert len(blocked) == 1
    assert blocked[0]["error"] == "suppressed"


def test_a_blocked_row_is_never_picked_up_by_the_sender():
    """It exists to be read, not to be sent."""
    _suppress("stop@example.com")
    mailer.enqueue("c-claim", recipients=[{"id": "b", "email": "stop@example.com"}])
    assert mailer.pending("c-claim") == 0
    assert mailer._claim() is None


def test_approving_the_same_campaign_twice_queues_nobody_again():
    """Idempotency, not an exclusion — it must not be counted as a problem
    or recorded as a blocked recipient."""
    people = [{"id": "a", "email": "one@example.com"}]
    assert mailer.enqueue("c-twice", recipients=people) == 1
    assert mailer.enqueue("c-twice", recipients=people) == 0

    rows = db.query("SELECT status FROM outbox WHERE campaign_id = 'c-twice'")
    assert len(rows) == 1
    assert eligibility.classify("c-twice", people)["counts"]["duplicate"] == 0


# ------------------------------------------------------- the last-second check


def test_someone_who_unsubscribes_mid_campaign_is_stopped_at_send_time():
    """The queue check is a courtesy. This is the one that protects anybody:
    hours pass between approving a campaign and the last message leaving."""
    assert eligibility.may_send_now("late@example.com") == ""
    _suppress("late@example.com")
    assert eligibility.may_send_now("late@example.com") == "suppressed"


def test_the_last_second_check_names_a_hard_bounce_specifically():
    _suppress("dead@example.com", reason="bounce")
    assert eligibility.may_send_now("dead@example.com") == "hard_bounced"


def test_there_is_no_way_to_override_a_refusal():
    """A guard against a future kindness. If someone adds a `force` flag to
    get a stuck campaign out, this is where it will be noticed."""
    import inspect

    for fn in (eligibility.classify, eligibility.may_send_now, eligibility.summary):
        params = set(inspect.signature(fn).parameters)
        assert not params & {"force", "override", "ignore_suppression", "skip_checks"}
