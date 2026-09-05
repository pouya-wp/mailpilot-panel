"""The sending window.

These two settings were editable in Settings and drawn on the
Deliverability screen for the whole life of the product, and consulted by
nothing — the sender emptied the outbox at one message per 1.2 seconds
whatever the hour and whatever the cap. A five thousand person campaign
approved at nine in the morning went out as a single hundred-minute
burst, which is the sending shape that gets a Gmail account suspended.

The quiet window is the part worth testing hardest: it normally WRAPS
midnight (21:00 to 08:00), so the obvious `start <= t <= end` is false
all night — exactly when it should be true — and true through the middle
of the working day.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("MAILPILOT_DB", str(Path(tempfile.mkdtemp(prefix="pacing-")) / "t.db"))
os.environ.setdefault("MAILPILOT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("MAILPILOT_SENDER", "0")

from app import pacing  # noqa: E402


def at(hhmm: str) -> datetime:
    hour, minute = (int(x) for x in hhmm.split(":"))
    return datetime(2026, 9, 5, hour, minute)


# ------------------------------------------------- a window across midnight


def test_late_evening_is_inside_an_overnight_window():
    assert pacing.in_quiet_hours(at("21:30"), "21:00", "08:00") is True


def test_the_small_hours_are_inside_an_overnight_window():
    """The case a naive comparison gets wrong: 03:00 is not between 21:00
    and 08:00 by simple ordering, and is very much inside the window."""
    assert pacing.in_quiet_hours(at("03:00"), "21:00", "08:00") is True


def test_the_working_day_is_outside_an_overnight_window():
    assert pacing.in_quiet_hours(at("13:00"), "21:00", "08:00") is False


def test_the_boundaries_belong_to_the_expected_side():
    # the window opens at 21:00 and has closed by 08:00
    assert pacing.in_quiet_hours(at("21:00"), "21:00", "08:00") is True
    assert pacing.in_quiet_hours(at("08:00"), "21:00", "08:00") is False


# --------------------------------------------------- a window inside a day


def test_a_daytime_window_does_not_wrap():
    assert pacing.in_quiet_hours(at("13:00"), "12:00", "14:00") is True
    assert pacing.in_quiet_hours(at("23:00"), "12:00", "14:00") is False


# ------------------------------------------------------------- bad input


def test_an_unparseable_window_never_holds_sending():
    """A malformed setting must not silently stop all mail forever. Failing
    open is right here: the cap still applies, and a stuck queue nobody can
    explain is worse than a window that is not enforced."""
    assert pacing.in_quiet_hours(at("03:00"), "", "08:00") is False
    assert pacing.in_quiet_hours(at("03:00"), "nonsense", "08:00") is False


def test_an_empty_window_is_not_a_window():
    """from == to would otherwise mean either "never" or "always"; it means
    the customer has not set one."""
    assert pacing.in_quiet_hours(at("03:00"), "08:00", "08:00") is False
