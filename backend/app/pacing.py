"""When the sender is allowed to send.

The workspace has carried an hourly throttle and a quiet-hours window
since the first release. Both are editable in Settings, both are drawn on
the Deliverability screen — "Sending today: 0 / 5,960" — and until now
neither was consulted by anything. The sender drained the whole outbox at
one message every 1.2 seconds regardless, so a five thousand person
campaign approved at nine in the morning went out in a single unbroken
hundred-minute burst.

That is the shape of sending that gets a Gmail account suspended, and the
panel was showing the customer a cap it was not applying. A control that
is displayed and ignored is worse than one that was never offered,
because the customer believes they are protected.

WHY IT LIVES HERE. The sender's loop should ask one question — "may I
send right now?" — and this module is the answer, so the rule can be read
and tested without a worker thread, a queue or a Gmail account.

REFUSING IS NOT FAILING. When the answer is no, nothing is claimed and
nothing is marked failed. The worker simply returns and tries again on
its next tick, so a campaign held by the cap resumes by itself.
"""

from __future__ import annotations

from datetime import datetime, time as time_of_day
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import db
from .domain import ago_iso


def _rules() -> dict:
    row = db.one(
        "SELECT throttle_per_hour, quiet_hours, quiet_from, quiet_to, timezone "
        "FROM workspaces LIMIT 1"
    )
    if row is None:
        return {"throttle": 0, "quiet": False, "from": "", "to": "", "tz": "UTC"}
    return {
        "throttle": int(row["throttle_per_hour"] or 0),
        "quiet": bool(row["quiet_hours"]),
        "from": (row["quiet_from"] or "").strip(),
        "to": (row["quiet_to"] or "").strip(),
        "tz": (row["timezone"] or "UTC").strip() or "UTC",
    }


def _clock(name: str) -> datetime | None:
    """Now, in the workspace's own timezone, or None if that is unknowable.

    Quiet hours are about the hour it is where the RECIPIENTS are, which is
    the workspace's timezone — not the server's, which is UTC in a container
    and would put "no mail after 21:00" three and a half hours out for a
    Tehran deployment.

    NEVER RAISES. `ZoneInfo` throws when the platform has no tz database —
    Windows without `tzdata`, some slim images — and an exception on this
    path propagates out of the sender's drain loop and stops all sending
    until someone reads the log. A clock we cannot read must mean "no quiet
    window enforced", not "no mail ever".
    """
    for candidate in (name, "UTC"):
        try:
            return datetime.now(ZoneInfo(candidate))
        except (ZoneInfoNotFoundError, ValueError, KeyError, OSError):
            continue
    return None


def _parse(hhmm: str) -> time_of_day | None:
    try:
        hour, minute = hhmm.split(":")
        return time_of_day(int(hour), int(minute))
    except (ValueError, AttributeError):
        return None


def in_quiet_hours(now: datetime, start: str, end: str) -> bool:
    """Is `now` inside the window that runs from `start` to `end`?

    The window normally WRAPS midnight — 21:00 to 08:00 — so it cannot be
    tested with a single `start <= t <= end`, which would be false all night
    and true through the middle of the working day.
    """
    a, b = _parse(start), _parse(end)
    if a is None or b is None or a == b:
        return False
    t = now.timetz().replace(tzinfo=None)
    if a < b:
        return a <= t < b          # a window inside one day
    return t >= a or t < b         # a window across midnight


def sent_in_last_hour() -> int:
    """Real sends, counted off the outbox rather than the campaign totals.

    The campaign counters are a running sum that says nothing about when the
    sends happened; the outbox has a timestamp per message, which is the only
    thing that can answer "how many in the last hour".
    """
    return db.scalar(
        "SELECT COUNT(*) FROM outbox WHERE status = 'sent' AND sent_at >= ?",
        (ago_iso(hours=1),), default=0,
    ) or 0


def may_send() -> tuple[bool, str]:
    """May the sender send right now, and if not, why not.

    The reason is returned rather than logged here so the caller can decide
    whether it is worth saying out loud — "held by the hourly cap" every
    thirty seconds for an hour is noise, not information.
    """
    rules = _rules()

    if rules["quiet"]:
        now = _clock(rules["tz"])
        # No readable clock means no quiet window, not no sending.
        if now is not None and in_quiet_hours(now, rules["from"], rules["to"]):
            return False, f"quiet hours ({rules['from']}–{rules['to']} {rules['tz']})"

    cap = rules["throttle"]
    if cap > 0 and sent_in_last_hour() >= cap:
        return False, f"hourly cap reached ({cap}/hour)"

    return True, ""


def room_this_hour() -> int:
    """How many more may go out before the cap bites. -1 means uncapped.

    Used by the sender to stop mid-drain rather than checking the count
    before every single message.
    """
    cap = _rules()["throttle"]
    if cap <= 0:
        return -1
    return max(0, cap - sent_in_last_hour())
