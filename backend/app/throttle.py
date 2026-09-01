"""Brute-force protection for sign-in.

On a laptop this was theoretical. On a public IP it is not: an unthrottled
login endpoint with a known email address is a password guess every few
milliseconds, and `hashlib.scrypt` is slow enough that it also becomes a way to
flatten the CPU.

Two counters, because they answer different questions:

  * PER ACCOUNT — stops someone grinding one known address. Locks that email
    for everyone, including the real owner, which is the accepted trade: a
    locked account for fifteen minutes beats a stolen one.
  * PER IP — stops one machine spraying many addresses, which the per-account
    counter would never see.

Successful sign-in clears both, so a person who mistypes twice and then gets it
right is not punished afterwards.

In memory on purpose. The window is minutes, a restart clearing it is
acceptable, and a database write per failed guess would hand the attacker a
cheaper way to cost us disk than they had to cost us CPU.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

#: Failures allowed inside the window before the door closes.
MAX_PER_ACCOUNT = 6
MAX_PER_IP = 20

#: How long a counter remembers, and how long a lock lasts.
WINDOW_SECONDS = 15 * 60

_by_account: dict[str, deque[float]] = defaultdict(deque)
_by_ip: dict[str, deque[float]] = defaultdict(deque)


class TooManyAttempts(RuntimeError):
    """Raised instead of checking the password. Carries the wait in seconds."""

    def __init__(self, retry_after: int):
        super().__init__(f"Too many sign-in attempts. Try again in {retry_after} seconds.")
        self.retry_after = retry_after


def _prune(hits: deque[float], now: float) -> None:
    while hits and now - hits[0] > WINDOW_SECONDS:
        hits.popleft()


def check(email: str, ip: str) -> None:
    """Called BEFORE the password is verified.

    Before, not after, so a locked-out attacker does not get to spend our CPU
    on an scrypt hash with every guess.
    """
    now = time.monotonic()
    key = (email or "").strip().lower()

    for hits, limit in ((_by_account[key], MAX_PER_ACCOUNT), (_by_ip[ip or "?"], MAX_PER_IP)):
        _prune(hits, now)
        if len(hits) >= limit:
            raise TooManyAttempts(int(WINDOW_SECONDS - (now - hits[0])) + 1)


def failed(email: str, ip: str) -> None:
    now = time.monotonic()
    _by_account[(email or "").strip().lower()].append(now)
    _by_ip[ip or "?"].append(now)


def succeeded(email: str, ip: str) -> None:
    """A correct password forgives the fumbles that came before it."""
    _by_account.pop((email or "").strip().lower(), None)
    _by_ip.pop(ip or "?", None)


def reset() -> None:
    """For tests."""
    _by_account.clear()
    _by_ip.clear()
