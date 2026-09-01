"""Researching who to reach, by region and by kind of business.

Two inputs, as asked for: a REGION and a CATEGORY. The agent searches the
open web and comes back with a targeting brief and a list of candidate
organisations.

WHY THIS IS A REVIEW QUEUE AND NOT AN IMPORT.

The obvious build is "type a region, get five hundred addresses, press send".
It is also the build that ends the product for whoever uses it, for three
reasons that are worth writing down because they are not obvious until the
damage is done.

  A model INVENTS addresses. Asked for contact details it does not have, it
  produces something shaped like an email address — plausible, well-formed,
  and belonging to nobody. Those bounce. A bounce rate above about 2% gets a
  sender filtered, and a list of invented addresses bounces at 60% or worse.
  Everything sent from that account afterwards, including to real customers
  who asked for it, lands in spam.

  A found address is not consent. Publishing `info@` on a shop's website is
  not permission to add that shop to a marketing list; under GDPR there is no
  lawful basis, and Gmail's own bulk-sender rules require the recipient to
  have opted in. The account that sends it is the customer's personal Gmail,
  and Google closes those.

  A bad list cannot be undone. Suppression fixes one address. Reputation is
  rebuilt over months, on a domain the customer probably also uses for their
  real business email.

So this module finds, cites and explains — and stops. Every lead carries the
URL it came from so a person can check it. Nothing reaches the sending list
without someone reading it and saying yes, and the accept step writes the
lead's source into the contact record so the origin survives the import.
"""

from __future__ import annotations

import re
from typing import Any

from . import db
from .domain import iso
from .security import new_id

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL DEFAULT '',
  kind       TEXT NOT NULL DEFAULT '',
  region     TEXT NOT NULL DEFAULT '',
  email      TEXT NOT NULL DEFAULT '',
  website    TEXT NOT NULL DEFAULT '',
  source     TEXT NOT NULL DEFAULT '',
  note       TEXT NOT NULL DEFAULT '',
  status     TEXT NOT NULL DEFAULT 'new',
  run_id     TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_leads_run ON leads(run_id);

CREATE TABLE IF NOT EXISTS lead_runs (
  id         TEXT PRIMARY KEY,
  region     TEXT NOT NULL DEFAULT '',
  category   TEXT NOT NULL DEFAULT '',
  brief      TEXT NOT NULL DEFAULT '',
  angles     TEXT NOT NULL DEFAULT '[]',
  found      INTEGER NOT NULL DEFAULT 0,
  with_email INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
"""

#: Deliberately small. This is research a person reads, not a scraper — and a
#: model asked for two hundred results starts inventing them around forty.
MAX_PER_RUN = 40

SHAPE = """{
  "brief": "2-4 sentences on who these people are and what they care about",
  "angles": ["a specific thing worth writing to them about", "another"],
  "leads": [
    {"name": "the organisation's name",
     "kind": "what it is, in three or four words",
     "region": "the town or area it is in",
     "website": "its own site, or empty",
     "email": "ONLY an address published on that site. Empty if you did not see one.",
     "source": "the URL you read this from. Required.",
     "note": "one line on why they fit"}
  ]
}"""


def rules(region: str, category: str, lang: str) -> list[str]:
    """What the agent is told before it goes looking."""
    return [
        f"Find organisations in {region} that match: {category}.",
        "",
        "== THE ONE RULE THAT MATTERS ==",
        "NEVER invent an email address. Not a plausible one, not a pattern like "
        "info@ or contact@ guessed from a domain, not a person's name at a "
        "company domain. If you did not READ the address on a page, leave "
        "`email` empty and still return the organisation — a lead with a "
        "website and no address is useful; a lead with a made-up address is a "
        "bounce, and enough bounces get the sender's account closed.",
        "",
        "Every lead must carry `source`: the URL of the page you read it on. A "
        "lead you cannot cite is a lead you made up, so drop it.",
        "Prefer a business address the organisation publishes for enquiries. Do "
        "not collect the personal address of a named individual.",
        f"Return at most {MAX_PER_RUN} leads. Fewer real ones beats more invented ones.",
        "",
        "`brief` is who these people are and what they actually care about — "
        "what a person writing to them would need to know, not a description of "
        "the search you ran.",
        "`angles` are things worth writing to them ABOUT: a season, a problem "
        "they have, a reason now is the moment. Not subject lines.",
        "",
        ("Write `brief`, `angles`, `kind` and `note` in Persian."
         if lang == "fa" else "Write everything in English."),
    ]


_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$")

#: Addresses a model reaches for when it has nothing. Seen in the wild from
#: every provider; none of them belong to anybody.
_INVENTED = {
    "example.com", "example.org", "example.net", "domain.com", "email.com",
    "company.com", "yourcompany.com", "business.com", "test.com", "sample.com",
    "acme.com", "mail.com", "website.com",
}


def clean_email(raw: Any, source: str) -> str:
    """Keep an address only if it could be real and was actually cited.

    An address without a source is an address the model produced from nothing,
    whatever it says. That is the single highest-value check here.
    """
    address = str(raw or "").strip().lower()
    if not address or not _EMAIL.match(address):
        return ""
    domain = address.rsplit("@", 1)[-1]
    if domain in _INVENTED or domain.endswith(".example"):
        return ""
    if not str(source or "").strip():
        return ""
    return address


def store(run_id: str, region: str, category: str, payload: dict) -> dict[str, Any]:
    """Write a run and its leads into the review queue."""
    leads_in = payload.get("leads")
    leads_in = leads_in if isinstance(leads_in, list) else []

    kept: list[dict] = []
    dropped_no_source = 0
    for item in leads_in[:MAX_PER_RUN]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()[:160]
        source = str(item.get("source") or "").strip()[:400]
        if not name:
            continue
        if not source:
            # no citation, no lead — see the module docstring
            dropped_no_source += 1
            continue
        kept.append({
            "id": new_id("lead"),
            "name": name,
            "kind": str(item.get("kind") or "").strip()[:80],
            "region": str(item.get("region") or region).strip()[:80],
            "email": clean_email(item.get("email"), source),
            "website": str(item.get("website") or "").strip()[:400],
            "source": source,
            "note": str(item.get("note") or "").strip()[:300],
            "status": "new",
            "run_id": run_id,
            "created_at": iso(),
        })

    with_email = sum(1 for lead in kept if lead["email"])
    with db.transaction():
        db.insert("lead_runs", {
            "id": run_id, "region": region[:120], "category": category[:160],
            "brief": str(payload.get("brief") or "").strip()[:1200],
            "angles": db.dumps([str(a).strip() for a in (payload.get("angles") or [])
                                if str(a).strip()][:6]),
            "found": len(kept), "with_email": with_email, "created_at": iso(),
        })
        for lead in kept:
            db.insert("leads", lead)

    return {
        "runId": run_id,
        "found": len(kept),
        "withEmail": with_email,
        # said out loud rather than silently discarded
        "droppedWithoutSource": dropped_no_source,
        "brief": str(payload.get("brief") or "").strip(),
        "angles": [str(a) for a in (payload.get("angles") or [])][:6],
    }


def ser(row) -> dict[str, Any]:
    return {
        "id": row["id"], "name": row["name"], "kind": row["kind"],
        "region": row["region"], "email": row["email"], "website": row["website"],
        "source": row["source"], "note": row["note"], "status": row["status"],
        "at": row["created_at"],
    }
