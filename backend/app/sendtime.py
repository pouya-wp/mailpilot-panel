"""When to send.

The panel could already schedule a campaign for a time a human picked, and it
had an "optimal" mode that returned a hardcoded offset — the next 08:40,
forever, for every account. That is the kind of feature that is worse than not
having one: it invites the operator to trust a recommendation nobody computed.

This works it out from the account's own history, and the metric is OPEN RATE
rather than volume. Volume tells you when this business happens to send, which
is a fact about the marketer. Open rate tells you when their audience reads,
which is the question actually being asked.

Two guards keep it honest:

  * A slot needs a MINIMUM VOLUME before it counts. One campaign that went to
    twelve people and got three opens is a 25% slot and means nothing.
  * With no usable history the answer says so (`basis: "default"`) and falls
    back to a mid-morning weekday, which is a convention rather than a
    discovery. The caller is expected to say which it is.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import db

#: Below this many recipients a slot is noise, not a signal.
MIN_VOLUME = 200

#: Where the fallback lands: 10:00 on the next weekday.
DEFAULT_HOUR = 10


def _slots() -> dict[tuple[int, int], dict[str, int]]:
    """Every (weekday, hour-block) this account has sent in, with its results."""
    out: dict[tuple[int, int], dict[str, int]] = {}
    for row in db.query(
        "SELECT sent, opens, COALESCE(updated_at, created_at) at "
        "FROM campaigns WHERE sent > 0"
    ):
        stamp = row["at"] or ""
        try:
            when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        key = (when.weekday(), when.hour // 2 * 2)
        bucket = out.setdefault(key, {"sent": 0, "opens": 0, "campaigns": 0})
        bucket["sent"] += row["sent"] or 0
        bucket["opens"] += row["opens"] or 0
        bucket["campaigns"] += 1
    return out


def best_slot() -> dict:
    """The weekday and hour this audience opens most.

    Returns the shape the API serves, including `basis` so the reader is never
    shown a convention dressed up as a finding.
    """
    ranked = [
        {
            "weekday": day,
            "hour": hour,
            "openRate": round(data["opens"] / data["sent"] * 100, 1),
            "sent": data["sent"],
            "campaigns": data["campaigns"],
        }
        for (day, hour), data in _slots().items()
        if data["sent"] >= MIN_VOLUME
    ]
    if not ranked:
        return {"weekday": 1, "hour": DEFAULT_HOUR, "basis": "default",
                "openRate": None, "sent": 0, "campaigns": 0}

    ranked.sort(key=lambda s: (-s["openRate"], -s["sent"]))
    best = ranked[0]
    best["basis"] = "history"
    return best


def next_occurrence(weekday: int, hour: int, *, now: datetime | None = None) -> datetime:
    """The next time that weekday and hour comes round, always in the future.

    Never returns "today at 10:00" when it is already noon — a schedule in the
    past is a send-now with extra steps, and the operator would not find out
    until the mail had gone.
    """
    now = now or datetime.now(timezone.utc)
    candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    days_ahead = (weekday - now.weekday()) % 7
    candidate += timedelta(days=days_ahead)
    if candidate <= now:
        candidate += timedelta(days=7 if days_ahead == 0 else 0)
        # a later weekday whose hour has passed today only happens when
        # days_ahead was 0, so the week bump above is the whole correction
        if candidate <= now:
            candidate += timedelta(days=7)
    return candidate


def recommend() -> dict:
    """What `GET /campaigns/best-time` answers with."""
    slot = best_slot()
    at = next_occurrence(slot["weekday"], slot["hour"])
    return {
        **slot,
        "at": at.isoformat().replace("+00:00", "Z"),
    }
