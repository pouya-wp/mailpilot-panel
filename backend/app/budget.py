"""Spend guards for the AI.

The failure this exists to prevent is not a big prompt. It is a loop: a retry
that never gives up, a component that re-renders and re-asks, a scheduled job
that fires every second instead of every day. Any of those will empty an OpenAI
account overnight, and the first anyone hears about it is the bill.

Three guards, because each one catches something the others cannot:

  * PER REQUEST — `AISettings.cap()` in ai_provider. Bounds one call.
  * PER MINUTE — the burst guard here. Bounds a runaway loop, which is the only
    guard that acts fast enough to matter when something is wrong RIGHT NOW.
  * PER DAY / PER MONTH — the ledger here. Bounds the bill, survives a restart,
    and is what an implementer actually sets when selling a fixed-price plan.

The burst guard is in memory on purpose. It is watching for something happening
in the space of seconds, a database round trip per call would itself become part
of the problem, and a process restart is exactly when you WANT the count reset.

The ledger is in the database because it is about money and must survive
anything.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone

from . import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_usage (
  day     TEXT PRIMARY KEY,
  tokens  INTEGER NOT NULL DEFAULT 0,
  calls   INTEGER NOT NULL DEFAULT 0
);
"""

# How many calls may start in any 60-second window. Sized so no human working
# normally will ever meet it — 30 requests a minute is one every two seconds —
# while a loop hits it almost immediately.
BURST_WINDOW_SECONDS = 60
BURST_MAX_CALLS = 30

_recent: deque[float] = deque()


class BudgetExceeded(RuntimeError):
    """A guard tripped. Always the operator's problem, never a server fault."""


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def used_today() -> int:
    return db.scalar("SELECT tokens FROM ai_usage WHERE day = ?", (_today(),), default=0) or 0


def used_this_month() -> int:
    return db.scalar(
        "SELECT COALESCE(SUM(tokens), 0) FROM ai_usage WHERE day LIKE ?",
        (_month() + "%",),
        default=0,
    ) or 0


def calls_today() -> int:
    return db.scalar("SELECT calls FROM ai_usage WHERE day = ?", (_today(),), default=0) or 0


def check(daily_cap: int = 0, monthly_cap: int = 0) -> None:
    """Called BEFORE every model request. Raises rather than returning a flag,
    because every caller must treat this as fatal to the request."""
    now = time.monotonic()
    while _recent and now - _recent[0] > BURST_WINDOW_SECONDS:
        _recent.popleft()
    if len(_recent) >= BURST_MAX_CALLS:
        raise BudgetExceeded(
            f"Too many AI requests in the last minute ({len(_recent)}). "
            "This usually means something is looping; the agent has been paused "
            "for a moment rather than spending more."
        )

    if monthly_cap > 0 and used_this_month() >= monthly_cap:
        raise BudgetExceeded(
            f"This deployment's monthly AI budget ({monthly_cap:,} tokens) is used up. "
            "An owner can raise it in Setup."
        )
    if daily_cap > 0 and used_today() >= daily_cap:
        raise BudgetExceeded(
            f"This deployment's daily AI budget ({daily_cap:,} tokens) is used up. "
            "It resets at midnight UTC."
        )

    _recent.append(now)


def record(tokens: int) -> None:
    """Called AFTER a request, with whatever the provider said it cost.

    Never raises: a failure to write the ledger must not turn a successful
    answer into an error for the reader.
    """
    try:
        db.execute(
            "INSERT INTO ai_usage (day, tokens, calls) VALUES (?, ?, 1) "
            "ON CONFLICT(day) DO UPDATE SET tokens = tokens + excluded.tokens, calls = calls + 1",
            (_today(), max(0, int(tokens or 0))),
        )
    except Exception:  # noqa: BLE001 - the ledger is not worth failing a request over
        pass


def snapshot(daily_cap: int = 0, monthly_cap: int = 0) -> dict:
    """What the wizard shows the implementer."""
    return {
        "today": {"tokens": used_today(), "calls": calls_today(), "cap": daily_cap},
        "month": {"tokens": used_this_month(), "cap": monthly_cap},
        "burstWindow": BURST_WINDOW_SECONDS,
        "burstMax": BURST_MAX_CALLS,
    }
