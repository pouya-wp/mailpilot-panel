"""Drafting a reply for a human to approve.

This one is drafting, not sending. The route that actually sends already
exists, already requires a person to press the button, and already runs
suppression and sender-health checks at the moment of sending. Nothing
here may send anything, and nothing here shortens that path.

THE FAILURE MODE THIS IS BUILT AROUND. A prospect writes "sounds good,
what does it cost?" and a helpful model answers with a price. There is no
price in this system. The model would invent one, the customer would send
it, and a business would have quoted a number it never agreed to. The same
goes for a meeting time, a delivery date, an integration, a discount, or a
customer name.

So the generator is told what it may draw on, and anything it needs that
is not there comes back as a REQUEST TO THE USER rather than as prose. A
draft that says "we can do Tuesday at 3" is a failure even if it reads
beautifully; a draft that says "MailPilot needs your availability before
answering this" is the feature working.

INTENT DECIDES WHETHER TO DRAFT AT ALL. An unsubscribe never gets a
marketing reply — the suppression already happened and drafting a
persuasive answer to it would be the single worst thing this module could
do. An out-of-office is a mail server and gets nothing. A "not
interested" gets a short courteous close only if the operator asks for
one.
"""

from __future__ import annotations

from typing import Any

from . import brandprofile, brain, db, deployment
from .ai_provider import AIUnavailable, complete_json
from .domain import iso

#: Columns added to `threads` for the copilot. Same idempotent migration
#: the rest of the product uses; nothing existing is altered or dropped.
_ADDED_COLUMNS = {
    # The full incoming message. `preview_en` is capped at 400 characters
    # for the list, which is not enough to answer from.
    "body": "TEXT NOT NULL DEFAULT ''",
    "intent_confidence": "REAL NOT NULL DEFAULT 0",
    "campaign_id": "TEXT NOT NULL DEFAULT ''",
    "contact_id": "TEXT NOT NULL DEFAULT ''",
    "draft_status": "TEXT NOT NULL DEFAULT ''",
    "draft_missing": "TEXT NOT NULL DEFAULT '[]'",
    "draft_review": "TEXT NOT NULL DEFAULT '{}'",
    # When the draft was generated, against what the thread looked like
    # then. Both halves of the staleness check (§17.10).
    "draft_at": "TEXT NOT NULL DEFAULT ''",
    "draft_basis": "TEXT NOT NULL DEFAULT ''",
}

#: The states a draft can be in, from §17.5.
READY = "ready_for_review"
MISSING = "missing_information"
NEEDS_HUMAN = "needs_human_review"
EDITED = "edited_by_user"
APPROVED = "approved"
SENT = "sent"

#: What the copilot will and will not write for, by intent (§17.3).
#: `None` means no draft is produced at all, and the reason is not a
#: limitation — it is the correct behaviour.
NEVER_DRAFT = {
    "unsubscribe": "unsubscribe-never-answered",
    "ooo": "out-of-office-needs-no-reply",
}

#: Things a reply might need that this product has no source for. Asked of
#: the user by name rather than guessed (§17.7).
ASKABLE = (
    "price", "availability", "integration", "link", "terms", "discount",
)


def migrate() -> None:
    have = {r["name"] for r in db.query("PRAGMA table_info(threads)")}
    if not have:
        return
    for column, ddl in _ADDED_COLUMNS.items():
        if column not in have:
            db.execute(f"ALTER TABLE threads ADD COLUMN {column} {ddl}")


def _maybe(row, key: str, default: str = "") -> Any:
    try:
        value = row[key]
    except (IndexError, KeyError):
        return default
    return default if value is None else value


DRAFT_SHAPE = """{
  "can_answer": true,
  "missing": ["price"],
  "reply": ["paragraph 1", "paragraph 2"],
  "next_step": "the one thing you are asking them to do",
  "used_facts": ["the approved fact each claim rests on"],
  "notes": "one sentence for the operator, not for the recipient"
}"""


def _rules(intent: str, profile: dict, lang: str) -> list[str]:
    """What the drafter may and may not do.

    The prohibitions are stated as absolutes and repeated, because this is
    the one place in the product where a plausible sentence is more
    dangerous than a blank.
    """
    known = brandprofile.as_prompt(profile)
    return [
        "You are drafting a reply for a human to review. It will NOT be sent "
        "without their approval, and you must never write as though it will.",
        "",
        "== WHAT YOU MAY SAY ==",
        "Only what the business below has told us. That is the whole of your "
        "knowledge about the sender.",
        "",
        known or "(the sender has not filled in their brand information yet)",
        "",
        "== WHAT YOU MAY NEVER DO ==",
        "Never state a price, a discount, or any commercial term. There is no "
        "pricing in this system; any number you write would be invented.",
        "Never promise a meeting time, a call, a date, or availability. There "
        "is no calendar here.",
        "Never offer a link, a document, or a booking page that is not "
        "written above. Never construct a URL.",
        "Never claim an integration, a capability, a delivery time, a client "
        "name, or a case-study number that is not written above.",
        "",
        "If answering properly needs any of those and it is not above, set "
        "`can_answer` to false and list what is missing, using these words "
        "where they fit: " + ", ".join(ASKABLE) + ". Asking the operator is "
        "the correct outcome and is never a failure.",
        "",
        "== SHAPE ==",
        "Short. Two paragraphs at most. They have already had the first "
        "email; do not pitch it again.",
        "Answer the message they actually sent, then one clear next step.",
        _intent_rule(intent),
        brain._lang_rule(lang),
    ]


def _intent_rule(intent: str) -> str:
    return {
        "interested": "They are interested. Acknowledge it and propose one "
                      "concrete, small next step. Do not oversell a decision "
                      "they have already half made.",
        "question": "They asked something. Answer it from the knowledge above "
                    "or say what is missing. Do not pad the answer.",
        "objection": "They raised an objection. Take it seriously and answer "
                     "it plainly. Do not argue and do not dismiss it.",
    }.get(intent, "Answer what they actually wrote, briefly.")


def draft_for(thread: dict | Any, *, lang: str = "en") -> dict[str, Any]:
    """Write a reply draft for one incoming message.

    Returns the draft and the state it should be shown in. Never sends,
    never suppresses, never writes to the thread — the caller decides what
    to persist, so this stays safe to call twice.
    """
    intent = (_maybe(thread, "intent") or "question").strip()

    # Some messages must not be answered, and that is a result rather than
    # a failure to produce one.
    if intent in NEVER_DRAFT:
        return {
            "status": NEEDS_HUMAN,
            "drafted": False,
            "reason": NEVER_DRAFT[intent],
            "text": "",
            "missing": [],
        }

    profile = brandprofile.get()
    ready = brandprofile.completeness(profile)
    if not ready["proReady"]:
        # Writing on behalf of a business we cannot describe produces
        # generic copy with the customer's name on it.
        return {
            "status": MISSING,
            "drafted": False,
            "reason": "brand-profile-incomplete",
            "text": "",
            "missing": ready["missingForPro"],
        }

    incoming = (_maybe(thread, "body") or _maybe(thread, "preview_en") or "").strip()
    if not incoming:
        return {"status": NEEDS_HUMAN, "drafted": False,
                "reason": "nothing-to-answer", "text": "", "missing": []}

    try:
        out = complete_json(
            deployment.ai_settings(),
            system=brain._ground("\n".join(_rules(intent, profile, lang))),
            user=("The message to answer:\n"
                  f"{incoming[:4000]}\n\n"
                  f"Classified intent: {intent}"),
            shape=DRAFT_SHAPE,
            temperature=0.3,
        )
    except AIUnavailable:
        raise

    missing = [str(m).strip().lower() for m in (out.get("missing") or []) if str(m).strip()]
    body = [str(p).strip() for p in (out.get("reply") or []) if str(p).strip()]

    if not out.get("can_answer") or missing:
        # The valuable outcome. The operator is told exactly what to supply
        # rather than being handed a confident invention.
        return {
            "status": MISSING,
            "drafted": bool(body),
            "reason": "needs-approved-information",
            "text": "\n\n".join(body),
            "missing": missing or ["information"],
            "notes": str(out.get("notes") or ""),
        }

    if not body:
        return {"status": NEEDS_HUMAN, "drafted": False,
                "reason": "empty-draft", "text": "", "missing": []}

    return {
        "status": READY,
        "drafted": True,
        "text": "\n\n".join(body),
        "nextStep": str(out.get("next_step") or ""),
        "usedFacts": [str(f) for f in (out.get("used_facts") or [])],
        "missing": [],
        "notes": str(out.get("notes") or ""),
    }


def basis(thread: dict | Any) -> str:
    """A fingerprint of what the draft was written against.

    Staleness is not a timestamp comparison: the thread row is updated for
    reasons that do not change what needs answering. This is the content
    the draft actually responds to, so a NEW message invalidates it and a
    change of assignee does not.
    """
    import hashlib

    material = f"{_maybe(thread, 'body')}|{_maybe(thread, 'preview_en')}|{_maybe(thread, 'received_at')}"
    return hashlib.sha256(material.encode("utf-8", "replace")).hexdigest()[:16]


def is_stale(thread: dict | Any) -> bool:
    """Has the conversation moved since this draft was written?

    §17.10: a draft written before the prospect's next message answers a
    conversation that no longer exists, and sending it would read as not
    having been listening.
    """
    stored = _maybe(thread, "draft_basis")
    if not stored:
        return False
    return stored != basis(thread)


def save_draft(thread_id: str, result: dict[str, Any], thread: dict | Any) -> None:
    """Persist a generated draft and the state it is in."""
    from .domain import bi_in

    data = {
        "draft_status": result["status"],
        "draft_missing": db.dumps(result.get("missing") or []),
        "draft_review": db.dumps({k: result[k] for k in ("reason", "notes", "nextStep", "usedFacts")
                                  if k in result}),
        "draft_at": iso(),
        "draft_basis": basis(thread),
    }
    if result.get("text"):
        from .domain import MAX_BODY

        data |= bi_in({"en": result["text"], "fa": result["text"]}, "draft", limit=MAX_BODY)
    with db.transaction():
        db.update("threads", thread_id, data)
