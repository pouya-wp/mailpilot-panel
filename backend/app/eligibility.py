"""Who may actually be sent to, and why everyone else may not.

ONE FUNCTION, TWO CALLERS. The pre-flight summary a customer reads before
launching and the gate that fills the queue are the same code. If they were
two implementations they would drift, and the screen that says "912
eligible" would stop describing what the sender does — which is worse than
having no summary, because the customer would trust it.

IT RUNS AT QUEUE TIME AND AGAIN AT SEND TIME. Hours pass between approving
a campaign and the last message going out, and somebody who unsubscribes
inside that window must not receive the rest of it. The queue check is a
courtesy that keeps the outbox small; the send check is the one that
actually protects anybody.

WHY EXCLUSIONS ARE RECORDED RATHER THAN DROPPED. "We are sending to 912 of
your 1,000" invites the question "what happened to the other 88?", and the
only acceptable answer is a list. Each verdict carries its reason, and the
reason is stored on the outbox row so it survives the page being closed.

NOT OVERRIDABLE. Suppression and unsubscribe are refusals, not warnings.
There is deliberately no flag anywhere in this module that lets a caller
past them.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from . import db

#: Deliberately permissive. This is a last line of defence against obvious
#: rubbish — an address with a space in it, a missing @, a bare domain —
#: not an attempt to decide whether a well-formed address exists. RFC 5322
#: in a regex is famously a mistake, and rejecting a valid address is worse
#: than queueing one that bounces once.
_SHAPE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")

#: Every way a recipient can fail to be sendable. The order matters: it is
#: the order they are checked in, and the first match is the reason given.
BLOCKED = (
    "malformed",      # not an address at all
    "unsubscribed",   # asked us to stop
    "suppressed",     # on the do-not-contact list for any reason
    "hard_bounced",   # a previous send failed permanently
    "duplicate",      # already in this campaign
)


def _suppressed_set() -> set[str]:
    return {
        (r["email"] or "").strip().lower()
        for r in db.query("SELECT email FROM suppression")
    }


def _bounced_set() -> set[str]:
    """Addresses a permanent failure was recorded against.

    `bounces.record()` writes both a suppression row and a contact status,
    so this is belt and braces — but a contact deleted and re-imported
    keeps the suppression row and loses the status, and the suppression row
    is the one that must win.
    """
    return {
        (r["email"] or "").strip().lower()
        for r in db.query("SELECT email FROM suppression WHERE reason = 'bounce'")
    }


def _unsubscribed_set() -> set[str]:
    return {
        (r["email"] or "").strip().lower()
        for r in db.query(
            "SELECT email FROM contacts WHERE status IN ('unsubscribed', 'bounced')")
    }


def classify(campaign_id: str, recipients: Iterable[dict]) -> dict[str, Any]:
    """Sort recipients into those who may be sent to, and those who may not.

    Returns the eligible rows plus an itemised account of the rest. Nothing
    is written; this is safe to call to render a preview.
    """
    suppressed = _suppressed_set()
    bounced = _bounced_set()
    gone = _unsubscribed_set()
    already = {
        (r["email"] or "").strip().lower()
        for r in db.query("SELECT email FROM outbox WHERE campaign_id = ?", (campaign_id,))
    } if campaign_id else set()

    eligible: list[dict] = []
    excluded: list[dict] = []
    seen: set[str] = set()
    counts = dict.fromkeys(BLOCKED, 0)
    repeats = 0

    for person in recipients:
        email = (person.get("email") or "").strip().lower()
        reason = None

        # Already in this campaign's outbox from an earlier approval. That is
        # idempotency, not an exclusion: approving the same campaign twice
        # must be a no-op, and recording it as a blocked recipient would
        # invent a problem and inflate the count the customer reads.
        if email and email in already:
            repeats += 1
            continue

        if not email or not _SHAPE.match(email):
            reason = "malformed"
        elif email in gone:
            reason = "unsubscribed"
        elif email in bounced:
            # checked before the general suppression list so the reason given
            # is the specific one, which is the one a customer can act on
            reason = "hard_bounced"
        elif email in suppressed:
            reason = "suppressed"
        elif email in seen:
            # the same address twice in the list the customer selected
            reason = "duplicate"

        if reason:
            counts[reason] += 1
            excluded.append({
                "email": person.get("email") or "",
                "name": person.get("name") or "",
                "reason": reason,
            })
            continue

        seen.add(email)
        eligible.append(person)

    selected = len(eligible) + len(excluded) + repeats
    return {
        "selected": selected,
        # Already queued by an earlier approval of this same campaign, and
        # therefore neither sent again nor counted as a problem.
        "alreadyQueued": repeats,
        "eligible": eligible,
        "eligibleCount": len(eligible),
        "excluded": excluded,
        "counts": counts,
        # Nothing here checks an address against a validation service,
        # because this product has no such integration and inventing one
        # would be worse than saying so.
        "unknownValidity": len(eligible),
    }


def summary(campaign_id: str, recipients: Iterable[dict], *, limit: int = 200) -> dict[str, Any]:
    """The pre-flight figures, with a sample of who was excluded and why."""
    out = classify(campaign_id, recipients)
    return {
        "selected": out["selected"],
        "eligible": out["eligibleCount"],
        "counts": out["counts"],
        "excluded": out["excluded"][:limit],
        "excludedTotal": len(out["excluded"]),
    }


def may_send_now(email: str, campaign_id: str = "") -> str:
    """The last-second check, for one address, at the moment of sending.

    Returns "" when it may go, or the reason it may not. Deliberately
    queries rather than using a cached set: this runs once per message and
    the whole point is that it sees a suppression written thirty seconds
    ago by somebody clicking unsubscribe.
    """
    email = (email or "").strip().lower()
    if not email or not _SHAPE.match(email):
        return "malformed"
    if db.one("SELECT 1 FROM suppression WHERE lower(email) = ? AND reason = 'bounce'", (email,)):
        return "hard_bounced"
    if db.one("SELECT 1 FROM suppression WHERE lower(email) = ?", (email,)):
        return "suppressed"
    if db.one("SELECT 1 FROM contacts WHERE lower(email) = ? "
              "AND status IN ('unsubscribed', 'bounced')", (email,)):
        return "unsubscribed"
    return ""
