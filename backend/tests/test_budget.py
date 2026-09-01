"""The spend guards.

These protect an actual OpenAI account from an actual bug, so they are tested
against the failure that would cause the loss: not one expensive request, but
hundreds of cheap ones in a row.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="mailpilot-budget-"))
os.environ["MAILPILOT_DB"] = str(_TMP / "test.db")
os.environ["MAILPILOT_SECRET"] = "test-secret-not-for-production"

from app import budget, db  # noqa: E402
from app.ai_provider import DEFAULT_MAX_TOKENS, HARD_MAX_TOKENS, AISettings  # noqa: E402


@pytest.fixture(autouse=True)
def clean():
    db.init_db()
    db.execute("DELETE FROM ai_usage")
    budget._recent.clear()
    yield
    budget._recent.clear()


# ============================================================== per request


def test_a_request_cannot_exceed_the_deployment_ceiling():
    settings = AISettings(key="k", max_tokens=500)
    assert settings.cap(100) == 100        # a modest ask is honoured
    assert settings.cap(50_000) == 500     # a huge one is clamped


def test_no_deployment_can_raise_the_hard_ceiling():
    """Even a deployment configured with a silly number is bounded."""
    settings = AISettings(key="k", max_tokens=10_000_000)
    assert settings.cap(10_000_000) == HARD_MAX_TOKENS


def test_the_ceiling_still_leaves_room_for_an_answer():
    assert AISettings(key="k", max_tokens=0).cap(2000) == 64
    assert DEFAULT_MAX_TOKENS <= HARD_MAX_TOKENS


# ================================================================== burst


def test_a_runaway_loop_is_stopped_within_a_minute():
    """The scenario this exists for: something calls in a tight loop."""
    for _ in range(budget.BURST_MAX_CALLS):
        budget.check()

    with pytest.raises(budget.BudgetExceeded, match="looping"):
        budget.check()


def test_normal_use_never_trips_the_burst_guard():
    """A person working quickly is not a loop."""
    for _ in range(10):
        budget.check()  # no raise


def test_the_burst_window_rolls_forward(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(budget.time, "monotonic", lambda: clock["t"])

    for _ in range(budget.BURST_MAX_CALLS):
        budget.check()
    with pytest.raises(budget.BudgetExceeded):
        budget.check()

    # a minute later the window has emptied and work resumes on its own
    clock["t"] += budget.BURST_WINDOW_SECONDS + 1
    budget.check()


# ================================================================== ledger


def test_usage_accumulates_across_calls():
    budget.record(120)
    budget.record(80)
    assert budget.used_today() == 200
    assert budget.calls_today() == 2


def test_a_daily_cap_stops_further_spending():
    budget.record(1000)
    with pytest.raises(budget.BudgetExceeded, match="daily"):
        budget.check(daily_cap=1000)


def test_a_monthly_cap_stops_further_spending():
    budget.record(5000)
    with pytest.raises(budget.BudgetExceeded, match="monthly"):
        budget.check(monthly_cap=4000)


def test_zero_means_unlimited():
    budget.record(10_000_000)
    budget.check(daily_cap=0, monthly_cap=0)  # no raise


def test_the_ledger_never_breaks_a_good_answer(monkeypatch):
    """Recording is bookkeeping; failing to record must not fail the request."""

    def boom(*_a, **_k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(budget.db, "execute", boom)
    budget.record(100)  # must not raise


def test_the_monthly_total_counts_only_this_month():
    from datetime import datetime, timedelta, timezone

    last_month = (datetime.now(timezone.utc).replace(day=1) - timedelta(days=5)).strftime("%Y-%m-%d")
    db.execute("INSERT INTO ai_usage (day, tokens, calls) VALUES (?, ?, ?)", (last_month, 999_999, 1))
    budget.record(50)
    assert budget.used_this_month() == 50


def test_the_snapshot_reports_what_the_wizard_shows():
    budget.record(300)
    snap = budget.snapshot(daily_cap=1000, monthly_cap=5000)
    assert snap["today"]["tokens"] == 300
    assert snap["today"]["cap"] == 1000
    assert snap["month"]["cap"] == 5000
    assert snap["burstMax"] == budget.BURST_MAX_CALLS
