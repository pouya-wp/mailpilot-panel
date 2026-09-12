"""Drafting a reply, and refusing to invent one.

The model is faked at the completion boundary throughout. That is
deliberate: what is being tested is the code AROUND the model — which
intents are answered at all, what happens to a draft that asks for a
price, whether a stale thread can still be sent — and none of that should
depend on a network call or on what a model happens to say today.

The scenarios the brief names by number are 9 (asks for pricing), 10
(asks for a meeting time), 11 (unsubscribe) and 12 (thread moved on).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("MAILPILOT_DB", str(Path(tempfile.mkdtemp(prefix="copilot-")) / "t.db"))
os.environ.setdefault("MAILPILOT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("MAILPILOT_SENDER", "0")

from app import brandprofile, db, replycopilot  # noqa: E402
from app.domain import iso  # noqa: E402
from app.security import new_id  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh():
    db.init_db()
    db.execute("DELETE FROM threads")
    db.execute("DELETE FROM brand_profile")
    brandprofile.ensure_row()
    brandprofile.save({
        "brand_name": "Beyondex",
        "business_summary": "We build sales agents that answer enquiries.",
        "offers": [{"name": "Sales agent", "description": "Answers first"}],
        "ideal_customer_profile": "Small importers",
        "customer_outcomes": ["Faster replies"],
        "brand_voice": ["professional"],
    })
    yield


def _thread(intent: str = "question", body: str = "Sounds good, can you send pricing?"):
    tid = new_id("th")
    db.insert("threads", {
        "id": tid, "from_en": "Ali", "from_fa": "Ali", "email": "ali@example.com",
        "subject_en": "Re: hello", "subject_fa": "Re: hello",
        "preview_en": body[:400], "preview_fa": body[:400],
        "intent": intent, "received_at": iso(), "body": body,
    })
    return db.one("SELECT * FROM threads WHERE id = ?", (tid,))


def _model(monkeypatch, answer: dict):
    """Pin what the model returns, so the surrounding rules are what is tested."""
    monkeypatch.setattr(replycopilot, "complete_json", lambda *a, **k: answer)


# ------------------------------------------- messages that get no draft at all


def test_an_unsubscribe_never_gets_a_reply_draft(monkeypatch):
    """The brief's scenario 11, and the worst thing this module could do.

    The suppression has already happened. Drafting a persuasive answer to
    somebody who asked to be left alone would be indefensible, so the
    generator is never even reached.
    """
    called = []
    monkeypatch.setattr(replycopilot, "complete_json",
                        lambda *a, **k: called.append(1) or {})

    out = replycopilot.draft_for(_thread("unsubscribe", "please remove me"))
    assert out["drafted"] is False
    assert out["text"] == ""
    assert not called, "the model must not be asked to answer an opt-out"


def test_an_out_of_office_gets_no_sales_reply(monkeypatch):
    called = []
    monkeypatch.setattr(replycopilot, "complete_json",
                        lambda *a, **k: called.append(1) or {})

    out = replycopilot.draft_for(_thread("ooo", "I am away until Monday"))
    assert out["drafted"] is False
    assert not called


def test_an_empty_message_is_sent_for_human_review(monkeypatch):
    out = replycopilot.draft_for(_thread("question", ""))
    assert out["status"] == replycopilot.NEEDS_HUMAN


# -------------------------------------------------------- no invented facts


def test_a_request_for_pricing_asks_the_user_instead_of_inventing_one(monkeypatch):
    """The brief's scenario 9.

    There is no pricing anywhere in this product. A draft containing a
    number would be a business quoting a figure it never agreed to.
    """
    _model(monkeypatch, {
        "can_answer": False,
        "missing": ["price"],
        "reply": [],
        "notes": "no pricing in the brand profile",
    })
    out = replycopilot.draft_for(_thread("question", "can you send pricing?"))
    assert out["status"] == replycopilot.MISSING
    assert "price" in out["missing"]


def test_a_request_for_a_meeting_time_does_not_promise_one(monkeypatch):
    """The brief's scenario 10. There is no calendar in this system."""
    _model(monkeypatch, {
        "can_answer": False,
        "missing": ["availability"],
        "reply": [],
    })
    out = replycopilot.draft_for(_thread("interested", "Book me for Tuesday at 3."))
    assert out["status"] == replycopilot.MISSING
    assert "availability" in out["missing"]


def test_missing_information_wins_even_when_the_model_also_wrote_prose(monkeypatch):
    """A model that says "I cannot answer" and then answers anyway must not
    produce a Ready draft. The flag decides, not the presence of text."""
    _model(monkeypatch, {
        "can_answer": False,
        "missing": ["price"],
        "reply": ["Our pricing starts at $99 a month."],
    })
    out = replycopilot.draft_for(_thread("question", "how much?"))
    assert out["status"] == replycopilot.MISSING


def test_the_prohibitions_are_actually_in_the_prompt():
    """The rules are the safeguard, so their absence should fail a test
    rather than being discovered in a customer's sent folder."""
    rules = "\n".join(replycopilot._rules("question", brandprofile.get(), "en")).lower()
    for forbidden in ("price", "discount", "meeting time", "calendar",
                      "link", "integration", "client name"):
        assert forbidden in rules


def test_an_incomplete_brand_profile_refuses_rather_than_writing_generically(monkeypatch):
    """Writing on behalf of a business we cannot describe produces generic
    copy with the customer's name on it."""
    db.execute("DELETE FROM brand_profile")
    brandprofile.ensure_row()
    called = []
    monkeypatch.setattr(replycopilot, "complete_json",
                        lambda *a, **k: called.append(1) or {})

    out = replycopilot.draft_for(_thread())
    assert out["status"] == replycopilot.MISSING
    assert out["reason"] == "brand-profile-incomplete"
    assert not called


# --------------------------------------------------------- a good draft


def test_a_answerable_question_produces_a_ready_draft(monkeypatch):
    _model(monkeypatch, {
        "can_answer": True,
        "missing": [],
        "reply": ["Yes — it answers enquiries automatically.", "Worth a quick look?"],
        "next_step": "offer a short example",
        "used_facts": ["Answers first"],
    })
    out = replycopilot.draft_for(_thread("question", "does it answer enquiries?"))
    assert out["status"] == replycopilot.READY
    assert "answers enquiries" in out["text"]


def test_a_draft_is_stored_with_its_state_and_never_sent(monkeypatch):
    _model(monkeypatch, {"can_answer": True, "missing": [],
                         "reply": ["Yes."], "next_step": "", "used_facts": []})
    row = _thread()
    out = replycopilot.draft_for(row)
    replycopilot.save_draft(row["id"], out, row)

    saved = db.one("SELECT * FROM threads WHERE id = ?", (row["id"],))
    assert saved["draft_status"] == replycopilot.READY
    assert saved["draft_en"] == "Yes."
    # drafting must never mark the thread dealt with
    assert saved["handled"] == 0


# ------------------------------------------------------------- staleness


def test_a_thread_that_moved_on_marks_the_draft_stale(monkeypatch):
    """The brief's scenario 12.

    Sending an answer to a message that has been superseded reads as not
    having been listening.
    """
    _model(monkeypatch, {"can_answer": True, "missing": [],
                         "reply": ["Yes."], "next_step": "", "used_facts": []})
    row = _thread()
    replycopilot.save_draft(row["id"], replycopilot.draft_for(row), row)

    fresh = db.one("SELECT * FROM threads WHERE id = ?", (row["id"],))
    assert replycopilot.is_stale(fresh) is False

    # the prospect writes again
    db.execute("UPDATE threads SET body = ? WHERE id = ?",
               ("Actually, ignore that — what about next year?", row["id"]))
    moved = db.one("SELECT * FROM threads WHERE id = ?", (row["id"],))
    assert replycopilot.is_stale(moved) is True


def test_an_unrelated_change_does_not_make_a_draft_stale(monkeypatch):
    """Staleness is about the conversation, not about the row. Snoozing
    a thread must not force the operator to regenerate."""
    _model(monkeypatch, {"can_answer": True, "missing": [],
                         "reply": ["Yes."], "next_step": "", "used_facts": []})
    row = _thread()
    replycopilot.save_draft(row["id"], replycopilot.draft_for(row), row)

    db.execute("UPDATE threads SET snoozed_until = '2030-01-01T00:00:00Z' WHERE id = ?",
               (row["id"],))
    assert replycopilot.is_stale(
        db.one("SELECT * FROM threads WHERE id = ?", (row["id"],))) is False


def test_a_thread_with_no_draft_is_not_stale():
    assert replycopilot.is_stale(_thread()) is False


# ------------------------------------------------------- it cannot send


def test_the_copilot_module_contains_no_send_path():
    """Task 17 is draft-assist only. If somebody later wires sending into
    the generator, this is where it is caught."""
    source = (Path(__file__).resolve().parents[1] / "app" / "replycopilot.py").read_text(encoding="utf-8")
    for forbidden in ("send_message", "google.send", "_send_reply", "smtp"):
        assert forbidden not in source
