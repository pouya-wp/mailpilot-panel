"""Whether this account is safe to send from, and why.

Three things this has to get right, and the third is the one that makes it
worth building.

IT MUST NOT FABRICATE. `verify_domain` used to write `spf = 1, dkim = 1,
dmarc = 1` without resolving anything, so the screen a customer checks
before sending twenty thousand messages showed three green ticks for a
domain with no SPF record at all. Every state here is pass, fail or
UNKNOWN, and unknown is what you get whenever the answer is not certain.

IT MUST BE EXPLAINABLE. A single number is not actionable: "74" tells a
customer nothing they can do. The status always travels with the reasons
that produced it and the actions that would fix them.

IT MUST BE HONEST ABOUT THIN EVIDENCE. Two bounces out of three sends is
not a 67% bounce rate worth pausing an account over, it is three sends.
Every rate carries the sample it came from, and below the floor the answer
is "not enough data" rather than a confident number.

THE THRESHOLDS ARE CONFIGURABLE. Hard-coding "4% is critical" invents a
universal truth that does not exist — a warm domain mailing opted-in
customers and a cold domain mailing found addresses do not share a safe
bounce rate. Defaults live here; a deployment may override them.
"""

from __future__ import annotations

from typing import Any

from . import db, dnscheck
from .domain import ago_iso, iso

#: Columns added to `domains` so authentication can say "unknown". The old
#: 0/1 columns are KEPT and kept in step — anything still reading them sees
#: what it always saw — but they are no longer the source of truth.
_DOMAIN_COLUMNS = {
    "spf_state": "TEXT NOT NULL DEFAULT 'unknown'",
    "dkim_state": "TEXT NOT NULL DEFAULT 'unknown'",
    "dmarc_state": "TEXT NOT NULL DEFAULT 'unknown'",
    "checked_at": "TEXT NOT NULL DEFAULT ''",
}

#: Defaults. Deliberately not presented as universal truth — see the module
#: docstring. A deployment overrides any of these through `thresholds()`.
DEFAULTS: dict[str, float] = {
    # rates, as fractions of what was sent
    "bounce_warn": 0.02,
    "bounce_critical": 0.05,
    "unsub_warn": 0.005,
    "unsub_critical": 0.02,
    # below this many sends, a rate is noise and is reported as such
    "min_sample": 50,
    # a day's volume this many times the recent baseline is a spike
    "spike_multiple": 4.0,
}


def migrate() -> None:
    """Add the three-state columns, and seed them from the old booleans."""
    have = {r["name"] for r in db.query("PRAGMA table_info(domains)")}
    if not have:
        return
    added = False
    for column, ddl in _DOMAIN_COLUMNS.items():
        if column not in have:
            db.execute(f"ALTER TABLE domains ADD COLUMN {column} {ddl}")
            added = True
    if not added:
        return

    # Carry the old data across rather than resetting every domain to
    # unknown: a deployment that had verified a domain keeps saying so until
    # the next real check corrects it. A 0 becomes `unknown`, not `fail` —
    # the old default meant "not checked", and calling that a failure would
    # invent a problem on every existing install.
    for row in db.query("SELECT id, spf, dkim, dmarc FROM domains"):
        db.update("domains", row["id"], {
            "spf_state": "pass" if row["spf"] else "unknown",
            "dkim_state": "pass" if row["dkim"] else "unknown",
            "dmarc_state": "pass" if row["dmarc"] else "unknown",
        })


def thresholds() -> dict[str, float]:
    """The defaults, with any deployment override applied."""
    from . import deployment

    out = dict(DEFAULTS)
    try:
        raw = deployment.get().get("health_thresholds") or "{}"
        for key, value in (db.loads(raw, {}) or {}).items():
            if key in out:
                out[key] = float(value)
    except (ValueError, TypeError, AttributeError):
        pass
    return out


# ============================================================ authentication


def refresh_auth(domain_id: str) -> dict[str, str]:
    """Actually look the records up, and record what was found.

    The legacy booleans are written too, so anything still reading them
    keeps working — but only a `pass` sets one, so an unknown can never
    again look like a verified domain.
    """
    row = db.one("SELECT * FROM domains WHERE id = ?", (domain_id,))
    if row is None:
        return {"spf": "unknown", "dkim": "unknown", "dmarc": "unknown"}

    found = dnscheck.check(row["domain"])
    with db.transaction():
        db.update("domains", domain_id, {
            "spf_state": found["spf"],
            "dkim_state": found["dkim"],
            "dmarc_state": found["dmarc"],
            "checked_at": iso(),
            "spf": 1 if found["spf"] == "pass" else 0,
            "dkim": 1 if found["dkim"] == "pass" else 0,
            "dmarc": 1 if found["dmarc"] == "pass" else 0,
            # A domain is only verified when all three actually pass.
            "status": "verified" if all(
                found[k] == "pass" for k in ("spf", "dkim", "dmarc")) else "unverified",
        })
    return found


def authentication() -> dict[str, str]:
    """The account's authentication, across every domain it sends from.

    The worst state wins: one unauthenticated domain is enough to cost the
    account its reputation, so an average would hide exactly the thing this
    is for.
    """
    rows = db.query("SELECT * FROM domains")
    if not rows:
        # No domain configured at all. Mail goes out through the connected
        # Gmail account under its own domain, which we cannot check from
        # here — so unknown, which is the truth.
        return {"spf": "unknown", "dkim": "unknown", "dmarc": "unknown"}
    return {
        key: dnscheck.worst(*[_state(r, key) for r in rows])
        for key in ("spf", "dkim", "dmarc")
    }


def _state(row, key: str) -> str:
    """Read a three-state column, falling back for a pre-migration row."""
    try:
        value = row[f"{key}_state"]
    except (IndexError, KeyError):
        value = None
    if value in ("pass", "fail", "unknown"):
        return value
    return "pass" if row[key] else "unknown"


# ================================================================= signals


def signals(days: int = 7) -> dict[str, Any]:
    """The measurable risks, each with the sample it came from.

    Counted off the outbox, which has a row and a timestamp per message,
    rather than the campaign counters, which are running totals that cannot
    answer "in the last seven days".
    """
    since = ago_iso(days=days)
    sent = db.scalar(
        "SELECT COUNT(*) FROM outbox WHERE status = 'sent' AND sent_at >= ?",
        (since,), default=0) or 0
    failed = db.scalar(
        "SELECT COUNT(*) FROM outbox WHERE status = 'failed' AND sent_at >= ?",
        (since,), default=0) or 0

    # Hard and soft are already separated by bounces.py at the moment a
    # bounce arrives: a permanent one suppresses, a temporary one does not.
    hard = db.scalar(
        "SELECT COUNT(*) FROM suppression WHERE reason = 'bounce' AND created_at >= ?",
        (since,), default=0) or 0
    unsubs = db.scalar(
        "SELECT COUNT(*) FROM suppression WHERE reason = 'unsub' AND created_at >= ?",
        (since,), default=0) or 0

    def rate(n: int) -> float | None:
        # None, not 0.0: "no sends" and "no bounces" are different answers
        # and a caller that cannot tell them apart will draw a 0% bar.
        return round(n / sent, 4) if sent else None

    return {
        "windowDays": days,
        "sent": sent,
        "sendFailures": failed,
        "hardBounces": hard,
        "unsubscribes": unsubs,
        "hardBounceRate": rate(hard),
        "unsubscribeRate": rate(unsubs),
        "suppressed": db.scalar("SELECT COUNT(*) FROM suppression", default=0) or 0,
        "sentToday": db.scalar(
            "SELECT COUNT(*) FROM outbox WHERE status = 'sent' AND substr(sent_at,1,10) = ?",
            (iso()[:10],), default=0) or 0,
    }


def _spike(limits: dict[str, float]) -> dict[str, Any] | None:
    """Today's volume against the fortnight behind it.

    Only meaningful with a baseline: a first campaign is not a spike, it is
    a first campaign, and calling it one would pause every new account.
    """
    rows = db.query(
        "SELECT substr(sent_at,1,10) d, COUNT(*) n FROM outbox "
        "WHERE status = 'sent' AND sent_at >= ? GROUP BY d ORDER BY d",
        (ago_iso(days=14),))
    today = iso()[:10]
    history = [r["n"] for r in rows if r["d"] != today]
    if len(history) < 3:
        return None
    baseline = sum(history) / len(history)
    now = next((r["n"] for r in rows if r["d"] == today), 0)
    if baseline > 0 and now > baseline * limits["spike_multiple"]:
        return {"today": now, "baseline": round(baseline, 1)}
    return None


# ================================================================== status


def status() -> dict[str, Any]:
    """Healthy, Warning or Critical — with the reasons that decided it.

    Never a bare score. The number is there because people expect one, but
    the reasons are the part that can be acted on, and a status without
    them is a shrug with a colour.
    """
    limits = thresholds()
    auth = authentication()
    sig = signals()

    reasons: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    level = "healthy"

    def escalate(to: str) -> None:
        nonlocal level
        order = {"healthy": 0, "warning": 1, "critical": 2}
        if order[to] > order[level]:
            level = to

    # ---- authentication
    for key in ("spf", "dkim", "dmarc"):
        if auth[key] == "fail":
            escalate("critical" if key == "spf" else "warning")
            reasons.append({"id": f"auth-{key}-fail", "tone": "bad", "key": key})
            actions.append({"id": "verify-domain", "to": "domains"})
        elif auth[key] == "unknown":
            escalate("warning")
            reasons.append({"id": f"auth-{key}-unknown", "tone": "warn", "key": key})
            actions.append({"id": "verify-domain", "to": "domains"})

    # ---- rates, but only where there is enough behind them to mean anything
    enough = sig["sent"] >= limits["min_sample"]
    if enough:
        if sig["hardBounceRate"] is not None:
            if sig["hardBounceRate"] >= limits["bounce_critical"]:
                escalate("critical")
                reasons.append({"id": "bounce-critical", "tone": "bad",
                                "value": sig["hardBounceRate"], "sample": sig["sent"]})
                actions.append({"id": "clean-list", "to": "audience"})
            elif sig["hardBounceRate"] >= limits["bounce_warn"]:
                escalate("warning")
                reasons.append({"id": "bounce-warn", "tone": "warn",
                                "value": sig["hardBounceRate"], "sample": sig["sent"]})
                actions.append({"id": "clean-list", "to": "audience"})
        if sig["unsubscribeRate"] is not None:
            if sig["unsubscribeRate"] >= limits["unsub_critical"]:
                escalate("critical")
                reasons.append({"id": "unsub-critical", "tone": "bad",
                                "value": sig["unsubscribeRate"], "sample": sig["sent"]})
                actions.append({"id": "review-targeting", "to": "audience"})
            elif sig["unsubscribeRate"] >= limits["unsub_warn"]:
                escalate("warning")
                reasons.append({"id": "unsub-warn", "tone": "warn",
                                "value": sig["unsubscribeRate"], "sample": sig["sent"]})

    spike = _spike(limits)
    if spike:
        escalate("warning")
        reasons.append({"id": "volume-spike", "tone": "warn", **spike})
        actions.append({"id": "slow-down", "to": "settings"})

    # A score, because people look for one — but derived from the same
    # reasons, so it can never disagree with them.
    score = 100
    for r in reasons:
        score -= 25 if r["tone"] == "bad" else 10
    score = max(0, min(100, score))

    return {
        "status": level.upper(),
        "score": score,
        "authentication": auth,
        "signals": sig,
        "thresholds": limits,
        "enoughData": enough,
        "reasons": reasons,
        # de-duplicated, keeping order: the same fix suggested three times
        # reads as three problems
        "recommendedActions": list({a["id"]: a for a in actions}.values()),
    }


def blocking() -> bool:
    """Is the account too unhealthy to start another send?

    Only CRITICAL blocks, and only that. A warning that stopped sending
    would make the whole feature something customers switch off.
    """
    return status()["status"] == "CRITICAL"
