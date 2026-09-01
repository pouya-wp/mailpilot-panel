"""Choosing when to send.

The date arithmetic here is the kind that looks obvious and is not: "next
Tuesday at 10" has to mean a different Tuesday depending on what time it
already is, and getting that wrong schedules a campaign into the past, where it
sends immediately and nobody finds out until it has.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="mailpilot-sendtime-"))
os.environ["MAILPILOT_DB"] = str(_TMP / "test.db")
os.environ["MAILPILOT_SECRET"] = "test-secret-not-for-production"

from app import db, sendtime  # noqa: E402
from app.domain import iso  # noqa: E402

TUESDAY_3PM = datetime(2026, 3, 10, 15, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clean():
    db.init_db()
    db.execute("DELETE FROM campaigns")
    yield


def _campaign(when: str, sent: int, opens: int, cid: str) -> None:
    db.insert("campaigns", {
        "id": cid, "name_en": cid, "name_fa": cid, "subject_en": "", "subject_fa": "",
        "body_en": "", "body_fa": "", "type": "broadcast", "status": "sent",
        "recipients": sent, "sent": sent, "delivered": sent, "opens": opens,
        "clicks": 0, "replies": 0, "unsubs": 0, "bounces": 0, "revenue": 0,
        "trend": "[]", "created_at": when, "updated_at": when,
    })


# ============================================================ the arithmetic


def test_a_slot_later_this_week_stays_this_week():
    when = sendtime.next_occurrence(2, 10, now=TUESDAY_3PM)   # Wednesday 10:00
    assert when.isoformat().startswith("2026-03-11T10:00")


def test_todays_slot_that_has_already_passed_rolls_a_full_week():
    """Tuesday 10:00, asked on Tuesday at 15:00, is NEXT Tuesday."""
    when = sendtime.next_occurrence(1, 10, now=TUESDAY_3PM)
    assert when.isoformat().startswith("2026-03-17T10:00")


def test_todays_slot_still_ahead_is_today():
    morning = TUESDAY_3PM.replace(hour=7)
    when = sendtime.next_occurrence(1, 10, now=morning)
    assert when.isoformat().startswith("2026-03-10T10:00")


def test_the_recommendation_is_always_in_the_future():
    """The property that matters: a schedule in the past is a send-now in
    disguise, and the operator would not find out until the mail had gone."""
    now = datetime.now(timezone.utc)
    for weekday in range(7):
        for hour in range(0, 24, 2):
            assert sendtime.next_occurrence(weekday, hour) > now, (weekday, hour)


# ================================================================ the signal


def test_with_no_history_it_says_so():
    slot = sendtime.best_slot()
    assert slot["basis"] == "default"
    assert slot["openRate"] is None


def test_it_picks_the_slot_with_the_best_open_rate_not_the_most_volume():
    # a big Monday send that nobody opened
    _campaign("2026-03-09T09:00:00Z", sent=50_000, opens=2_500, cid="c-monday")   # 5%
    # a smaller Thursday send that landed well
    _campaign("2026-03-12T15:00:00Z", sent=5_000, opens=2_000, cid="c-thursday")  # 40%

    slot = sendtime.best_slot()
    assert slot["basis"] == "history"
    assert slot["weekday"] == 3          # Thursday, despite ten times less volume
    assert slot["hour"] == 14            # the 14:00-16:00 block
    assert slot["openRate"] == 40.0


def test_a_slot_below_the_volume_floor_is_ignored():
    """One campaign to twelve people is not a discovery."""
    _campaign("2026-03-12T15:00:00Z", sent=12, opens=12, cid="c-tiny")   # a perfect 100%
    assert sendtime.best_slot()["basis"] == "default"


def test_campaigns_in_the_same_slot_are_pooled():
    _campaign("2026-03-12T15:00:00Z", sent=1_000, opens=100, cid="c-a")
    _campaign("2026-03-19T15:30:00Z", sent=1_000, opens=300, cid="c-b")

    slot = sendtime.best_slot()
    assert slot["campaigns"] == 2
    assert slot["sent"] == 2_000
    assert slot["openRate"] == 20.0      # pooled, not averaged per campaign


def test_unsent_campaigns_do_not_vote():
    db.insert("campaigns", {
        "id": "c-draft", "name_en": "d", "name_fa": "d", "subject_en": "", "subject_fa": "",
        "body_en": "", "body_fa": "", "type": "broadcast", "status": "draft",
        "recipients": 0, "sent": 0, "delivered": 0, "opens": 0, "clicks": 0,
        "replies": 0, "unsubs": 0, "bounces": 0, "revenue": 0, "trend": "[]",
        "created_at": iso(), "updated_at": iso(),
    })
    assert sendtime.best_slot()["basis"] == "default"


def test_recommend_returns_a_usable_timestamp():
    _campaign("2026-03-12T15:00:00Z", sent=5_000, opens=2_000, cid="c-thursday")
    out = sendtime.recommend()
    assert out["at"].endswith("Z")
    assert datetime.fromisoformat(out["at"].replace("Z", "+00:00")) > datetime.now(timezone.utc)
