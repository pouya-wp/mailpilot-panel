"""A/B decisions, and refusing to make them too early.

The two scenarios the brief calls out by name are the two failure modes
this feature has if nobody guards them:

  * a variant with more OPENS but fewer positive replies must not be
    called the winner, because an open is a tracking pixel that Apple
    Mail fires whether or not a human looked;

  * a test with too few recipients must return INCONCLUSIVE rather than
    a confident-looking percentage.

Both are tested here against the real decision function.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("MAILPILOT_DB", str(Path(tempfile.mkdtemp(prefix="opt-")) / "t.db"))
os.environ.setdefault("MAILPILOT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("MAILPILOT_SENDER", "0")

from app import db, optimize  # noqa: E402
from app.domain import iso  # noqa: E402
from app.security import new_id  # noqa: E402

CID = "c-abtest"


@pytest.fixture(autouse=True)
def _fresh():
    db.init_db()
    for table in ("outbox", "threads", "suppression", "campaign_variants"):
        db.execute(f"DELETE FROM {table}")
    yield


def _test_on(field: str = "subject") -> None:
    optimize.set_variants(CID, field, ["short and plain", "long and salesy"])


def _sent(variant: str, n: int, *, prefix: str) -> list[str]:
    """n delivered messages on one arm. Returns the addresses."""
    made = []
    for i in range(n):
        email = f"{prefix}{i}@example.com"
        db.insert("outbox", {
            "id": new_id("out"), "campaign_id": CID, "contact_id": "",
            "email": email, "name": "", "status": "sent", "variant": variant,
            "queued_at": iso(), "sent_at": iso(),
        })
        made.append(email)
    return made


def _reply(email: str, intent: str) -> None:
    db.insert("threads", {
        "id": new_id("th"), "from_en": "x", "from_fa": "x", "email": email,
        "subject_en": "re", "subject_fa": "re", "preview_en": "", "preview_fa": "",
        "intent": intent, "received_at": iso(),
    })


def _unsub(email: str) -> None:
    db.insert("suppression", {"id": new_id("sup"), "email": email,
                              "reason": "unsub", "created_at": iso()})


# ------------------------------------------------------- too little evidence


def test_a_thin_test_is_inconclusive_not_a_winner():
    """The brief's scenario 7. Twenty recipients an arm is not a result."""
    _test_on()
    a = _sent("A", 20, prefix="a")
    _sent("B", 20, prefix="b")
    for e in a[:6]:
        _reply(e, "interested")

    out = optimize.decide(CID)
    assert out["result"] == "INCONCLUSIVE"
    assert out["reason"] == "sample"
    assert out["needed"] == 100


def test_a_lead_without_separation_is_still_inconclusive():
    """Two rates being different is not evidence that they differ."""
    _test_on()
    a = _sent("A", 200, prefix="a")
    b = _sent("B", 200, prefix="b")
    for e in a[:22]:
        _reply(e, "interested")
    for e in b[:18]:
        _reply(e, "interested")

    out = optimize.decide(CID)
    assert out["result"] == "INCONCLUSIVE"
    assert out["reason"] == "overlap"


# ------------------------------------------------------ opens are not a win


def test_the_arm_with_more_positive_replies_wins_not_the_one_with_more_opens():
    """The brief's scenario 6.

    Opens are not an input to this decision at all, which is the strongest
    possible form of "do not pick the winner on opens" — there is no code
    path by which an open could influence it.
    """
    _test_on()
    a = _sent("A", 300, prefix="a")
    b = _sent("B", 300, prefix="b")
    # A gets a handful of replies; B gets many more
    for e in a[:5]:
        _reply(e, "interested")
    for e in b[:60]:
        _reply(e, "interested")

    out = optimize.decide(CID)
    assert out["result"] == "B"
    assert out["winner"]["positives"] == 60

    # and nothing in the arm figures is an open
    assert "opens" not in out["arms"][0]


def test_a_variant_that_wins_replies_and_loses_subscribers_does_not_win():
    """More replies and triple the unsubscribes is not an improvement."""
    _test_on()
    a = _sent("A", 300, prefix="a")
    b = _sent("B", 300, prefix="b")
    for e in a[:30]:
        _reply(e, "interested")
    for e in b[:36]:
        _reply(e, "interested")
    for e in b[100:160]:        # 60 unsubscribes against A's none
        _unsub(e)

    arms = {x["variant"]: x for x in optimize.decide(CID)["arms"]}
    assert arms["A"]["score"] > arms["B"]["score"]


# ------------------------------------------------------- what counts as a reply


def test_an_out_of_office_is_not_engagement():
    """A mail server is not a person, and counting it is how a badly-timed
    campaign looks like a successful one."""
    _test_on()
    a = _sent("A", 120, prefix="a")
    for e in a[:40]:
        _reply(e, "ooo")

    stats = optimize.arm(CID, "A")
    assert stats["replies"] == 0
    assert stats["positives"] == 0


def test_an_opt_out_is_a_reply_but_never_a_positive_one():
    _test_on()
    a = _sent("A", 120, prefix="a")
    for e in a[:10]:
        _reply(e, "unsubscribe")

    stats = optimize.arm(CID, "A")
    assert stats["replies"] == 10
    assert stats["positives"] == 0


def test_questions_are_counted_separately():
    """Commercial engagement before anyone has said yes."""
    _test_on()
    a = _sent("A", 120, prefix="a")
    for e in a[:7]:
        _reply(e, "question")
    assert optimize.arm(CID, "A")["questions"] == 7


# --------------------------------------------------------------- assignment


def test_nobody_receives_two_first_touch_variants():
    _test_on()
    people = [{"email": f"p{i}@example.com"} for i in range(40)]
    first = optimize.assign(CID, people)

    # write them down the way the queue does
    for email, label in first.items():
        db.insert("outbox", {
            "id": new_id("out"), "campaign_id": CID, "contact_id": "",
            "email": email, "name": "", "status": "queued", "variant": label,
            "queued_at": iso(),
        })

    again = optimize.assign(CID, people)
    assert again == first, "a re-queue must not reshuffle people already assigned"


def test_the_arms_come_out_even():
    _test_on()
    people = [{"email": f"p{i}@example.com"} for i in range(100)]
    dealt = optimize.assign(CID, people)
    counts = {}
    for label in dealt.values():
        counts[label] = counts.get(label, 0) + 1
    assert abs(counts["A"] - counts["B"]) <= 4


def test_a_campaign_with_no_test_assigns_nobody():
    """The overwhelming majority of sends are not tests and must be
    untouched by any of this."""
    assert optimize.assign("c-no-test", [{"email": "x@example.com"}]) == {}
    assert optimize.decide("c-no-test")["result"] == "NO_TEST"


def test_a_test_needs_two_variants():
    with pytest.raises(ValueError):
        optimize.set_variants(CID, "subject", ["only one"])


def test_only_one_variable_may_be_tested():
    with pytest.raises(ValueError):
        optimize.set_variants(CID, "subject_and_cta", ["a", "b"])
