"""Does this domain actually authenticate its mail?

Until now `POST /domains/{id}/verify` answered yes. Not "checked and yes" —
it wrote `spf = 1, dkim = 1, dmarc = 1` and marked every DNS record `ok`
without resolving anything at all. The comment beside it said a real
deployment would resolve these over DNS, and then it did not.

That is the worst possible shape for this particular lie. A customer looks
at the deliverability screen to find out whether their mail is going to be
trusted, sees three green ticks, and sends twenty thousand messages from a
domain with no SPF record. The screen existed precisely to stop that.

THREE STATES, NOT TWO. A boolean cannot say "I could not find out", so it
said "no" — or, after `verify`, "yes". Both are wrong when the truth is
that the lookup failed. Everything here returns pass, fail or unknown, and
unknown is what you get whenever the answer is not certain.

WHY DNS-OVER-HTTPS. The standard library cannot query a TXT record —
`socket` resolves names to addresses and nothing more — and the
alternative is adding a resolver dependency to a requirements file whose
first line explains why it is deliberately short. DoH is a JSON GET, which
this codebase already knows how to do (see google.py), works from inside
the container, and needs nothing installed.

NOTHING HERE RAISES. A DNS check that throws would take out the
deliverability screen and, worse, the send path. Every failure becomes
`unknown`.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Literal

State = Literal["pass", "fail", "unknown"]

#: Resolvers, tried in order. Two of them because one being unreachable is
#: a network problem, not an answer about the customer's domain.
_RESOLVERS = (
    "https://dns.google/resolve",
    "https://cloudflare-dns.com/dns-query",
)

_TIMEOUT = 6.0


def _txt(name: str) -> list[str] | None:
    """Every TXT record at `name`, or None if we could not find out.

    None and [] mean different things and the difference is the whole point:
    [] is "the domain answered, and has no TXT record there" (a fail), None
    is "we never got an answer" (unknown).
    """
    for base in _RESOLVERS:
        url = f"{base}?{urllib.parse.urlencode({'name': name, 'type': 'TXT'})}"
        req = urllib.request.Request(url, headers={"accept": "application/dns-json"})
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as res:
                body = json.loads(res.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            continue

        # NXDOMAIN (3) is a real answer: there is nothing there.
        if body.get("Status") == 3:
            return []
        if body.get("Status") != 0:
            continue

        out = []
        for answer in body.get("Answer") or []:
            if answer.get("type") != 16:      # 16 = TXT
                continue
            value = str(answer.get("data") or "")
            # resolvers quote TXT data, and split long records into chunks
            out.append(value.replace('" "', "").strip('"'))
        return out
    return None


def spf(domain: str) -> State:
    """An SPF record says which servers may send as this domain."""
    records = _txt(domain)
    if records is None:
        return "unknown"
    return "pass" if any(r.lower().startswith("v=spf1") for r in records) else "fail"


def dmarc(domain: str) -> State:
    """DMARC tells receivers what to do when SPF and DKIM disagree."""
    records = _txt(f"_dmarc.{domain}")
    if records is None:
        return "unknown"
    return "pass" if any(r.lower().startswith("v=dmarc1") for r in records) else "fail"


def dkim(domain: str, selectors: tuple[str, ...] = ()) -> State:
    """DKIM signs the message itself, under a selector we have to guess.

    The selector is chosen by whoever sends the mail and is not discoverable
    from the domain, so this can only check the ones we know about. Finding
    none of them is NOT proof there is no DKIM — hence `unknown` rather than
    `fail` when every lookup answered and none matched.
    """
    # Google is the only sender this product supports today, and `google` is
    # the selector Workspace publishes. The rest are common defaults.
    guessing = not selectors
    candidates = selectors or ("google", "default", "selector1", "selector2", "k1", "mail")

    answered = False
    for selector in candidates:
        records = _txt(f"{selector}._domainkey.{domain}")
        if records is None:
            continue
        answered = True
        if any("v=dkim1" in r.lower() or "p=" in r for r in records):
            return "pass"

    if not answered:
        return "unknown"          # nothing resolved; we learned nothing
    if guessing:
        # Every lookup answered and none of OUR GUESSES matched. That is not
        # proof of absence — the domain may sign under a selector we have
        # never heard of — so it must not be reported as a failure.
        return "unknown"
    # A selector we were told to check, which answered and carries no key.
    return "fail"


def check(domain: str) -> dict[str, Any]:
    """All three, for one domain."""
    domain = (domain or "").strip().lower().rstrip(".")
    if not domain:
        return {"spf": "unknown", "dkim": "unknown", "dmarc": "unknown"}
    return {"spf": spf(domain), "dkim": dkim(domain), "dmarc": dmarc(domain)}


def worst(*states: str) -> State:
    """The state a group of checks should be reported as.

    A fail anywhere outranks an unknown, because a missing SPF record is a
    thing to fix and an unreadable one is a thing to retry.
    """
    if any(s == "fail" for s in states):
        return "fail"
    if any(s == "unknown" for s in states):
        return "unknown"
    return "pass"
