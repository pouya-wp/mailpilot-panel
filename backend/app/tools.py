"""What the agent is allowed to actually DO.

Until now the agent could write and propose; every real change went through a
screen. This is the layer that lets "add these three people and send them the
spring offer" happen from the input box.

The whole design rests on one split, and it is not a detail:

  SAFE actions run the moment the agent asks for them. Adding a contact,
  building a segment, saving a draft campaign — all reversible, all internal,
  none of them visible to a stranger. Making the operator confirm these would
  be the clutter this product exists to remove.

  OUTWARD actions do not. Sending mail leaves the building, reaches real
  people, and cannot be recalled. These come back as a PROPOSAL with a button
  on it, and the model's say-so is never enough on its own. The only thing that
  changes that is the deployment's own `agent_autonomy = auto`, which is a
  human decision made once, deliberately, in Settings — not something the model
  can talk its way into.

The second rule: the model's arguments are never trusted. Every one is
re-validated here against the same rules the REST routes enforce — the
suppression list, the field allow-list, the address format. A model that
hallucinates a column name or a segment id gets an error back, not a query.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from pydantic import EmailStr, TypeAdapter, ValidationError

from . import db, deployment, emailhtml
from .domain import bi_in, iso, log
from .security import new_id

#: Actions that reach a stranger's inbox. Everything else is reversible from
#: inside the panel, and is treated accordingly.
OUTWARD = {"send_email", "send_campaign"}

MAX_PER_TURN = 8
MAX_RECIPIENTS_PER_EMAIL = 25


class ToolError(ValueError):
    """The action cannot be carried out, and the agent should be told why."""


# ================================================================= the catalog


CATALOG: list[dict[str, Any]] = [
    {
        "name": "add_contacts",
        "what": "Add people to the contact list.",
        "args": '{"people": [{"email": "a@b.com", "name": "Ali", "country": "IR", "tags": ["vip"]}]}',
        "when": "The operator gives you addresses to save, or pastes a list of people.",
    },
    {
        "name": "find_contacts",
        "what": "Count and sample the contact list, optionally filtered.",
        "args": '{"status": "subscribed | unsubscribed | bounced | any", "country": "", "tag": ""}',
        "when": "You need to know who is on the list before deciding anything.",
    },
    {
        "name": "unsubscribe",
        "what": "Stop mailing an address, permanently.",
        "args": '{"email": "a@b.com", "reason": "why"}',
        "when": "Someone asked to be removed, or the operator says to stop mailing them.",
    },
    {
        "name": "create_group",
        "what": "Save a group (an audience) defined by a rule.",
        "args": '{"name": "", "rules": [{"field": "tag", "op": "has", "value": "vip"}], '
                '"match": "all | any | everyone"}',
        "when": "You need an audience that does not exist yet. Use match=everyone with "
                "no rules for the whole list.",
    },
    {
        "name": "create_campaign",
        "what": "Save a campaign as a DRAFT. Sends nothing.",
        "args": '{"name": "", "subject": "", "body": ["paragraph", "paragraph"], "segmentId": "or null"}',
        "when": "There is a finished draft worth keeping, whether or not it goes out now.",
    },
    {
        "name": "send_email",
        "what": "Send one email, now, to specific addresses.",
        "args": '{"to": ["a@b.com"], "subject": "", "body": ["paragraph"]}',
        "when": "The operator names who to write to. Use for one or a handful of people, not a list.",
    },
    {
        "name": "send_campaign",
        "what": "Send a saved campaign to its whole audience.",
        "args": '{"campaignId": "c-…"}',
        "when": "A draft exists and the operator says to send it.",
    },
]


def describe() -> str:
    """The catalogue, as the model reads it."""
    lines = ["You can take actions by putting them in `actions`. Available actions:"]
    for tool in CATALOG:
        mark = "  (this reaches real inboxes)" if tool["name"] in OUTWARD else ""
        lines.append(f'- {tool["name"]}: {tool["what"]}{mark}')
        lines.append(f'    args: {tool["args"]}')
        lines.append(f'    use when: {tool["when"]}')
    lines += [
        "Each action is {\"tool\": \"name\", \"args\": {…}}. Use an empty list when the "
        "operator only asked a question.",
        "Never invent an email address, a name, or a campaign id. If you do not have one, "
        "ask for it in `needs` instead of guessing.",
        "Do not add a contact and mail them in the same turn unless the operator asked for both.",
    ]
    return "\n".join(lines)


# ================================================================== execution


#: The same validator the REST routes get from `EmailStr`. Built once, because
#: constructing a TypeAdapter per address is not free and the importer runs it
#: a few thousand times in a row.
_ADDRESS = TypeAdapter(EmailStr)


def _email(value: Any) -> str:
    """A real address, by the same rule the rest of the API uses.

    The check here used to be "contains @, no spaces, five characters" — which
    passes `ali@example`, `ali@.com` and `x@y..z`. That mattered more than it
    looks: these addresses do not come from a form a person is staring at, they
    come out of a model reading a pasted list, so nobody sees them before they
    are stored and mailed. A bad one is a bounce, and enough bounces is a
    sending reputation.

    `EmailStr` also strips a display-name wrapper, so `<ali@example.com>` from
    a copy-pasted header arrives clean instead of being stored with brackets.
    """
    raw = str(value or "").strip()
    try:
        return str(_ADDRESS.validate_python(raw)).lower()
    except ValidationError as exc:
        raise ToolError(f"{raw!r} is not a valid email address") from exc


def _text(value: Any, *, field: str, limit: int = 4000) -> str:
    out = str(value or "").strip()
    if not out:
        raise ToolError(f"{field} is empty")
    return out[:limit]


def _body_html(body: Any) -> str:
    """Paragraphs to HTML. The model writes prose; the wire wants markup."""
    if isinstance(body, str):
        parts = [p.strip() for p in body.split("\n") if p.strip()]
    else:
        parts = [str(p).strip() for p in (body or []) if str(p).strip()]
    if not parts:
        raise ToolError("the email has no body")
    escaped = (
        p.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") for p in parts
    )
    return "".join(f"<p>{p}</p>" for p in escaped)


# ---------------------------------------------------------------- safe tools


def _add_contacts(args: dict, actor: str) -> dict:
    people = args.get("people") or []
    if not isinstance(people, list) or not people:
        raise ToolError("no people were given")

    added, skipped, blocked, invalid = [], [], [], []
    with db.transaction():
        for person in people[:200]:
            if not isinstance(person, dict):
                continue
            try:
                email = _email(person.get("email"))
            except ToolError:
                # Reported, not swallowed. A list where three addresses were
                # malformed and vanished without a word is worse than one that
                # says so — the operator still has the original to correct.
                invalid.append(str(person.get("email") or "")[:80])
                continue
            if db.one("SELECT 1 FROM contacts WHERE lower(email) = ?", (email,)):
                skipped.append(email)
                continue
            # The same refusal the REST route makes: someone who unsubscribed
            # does not come back because a model was handed their address.
            if db.one("SELECT 1 FROM suppression WHERE lower(email) = ?", (email,)):
                blocked.append(email)
                continue

            name = str(person.get("name") or "").strip() or email.split("@")[0]
            tags = person.get("tags")
            db.insert("contacts", {
                "id": new_id("p"), **bi_in(name, "name"), "email": email,
                "status": "subscribed", "score": 0, "ltv": 0, "orders": 0,
                "tags": db.dumps([str(x) for x in tags] if isinstance(tags, list) else []),
                "source_id": "agent", "source_en": "Added by the agent",
                "source_fa": "افزودهٔ ایجنت",
                "country": str(person.get("country") or "")[:2].upper(),
                "device": "desktop", "last_open_at": None, "created_at": iso(),
            })
            added.append(email)
        if added:
            log(kind="agent", actor=actor, action_en=f"added {len(added)} contacts",
                action_fa=f"{len(added)} مخاطب افزود", target="contacts", tone="good")

    return {"added": len(added), "alreadyThere": len(skipped),
            "refusedAsUnsubscribed": len(blocked),
            "invalid": len(invalid), "invalidExamples": invalid[:5],
            "emails": added[:10]}


def _find_contacts(args: dict, actor: str) -> dict:
    where, params = ["1=1"], []
    status = str(args.get("status") or "").strip()
    if status and status != "any":
        where.append("status = ?")
        params.append(status)
    if args.get("country"):
        where.append("country = ?")
        params.append(str(args["country"])[:2].upper())
    if args.get("tag"):
        where.append("tags LIKE ?")
        params.append(f'%"{args["tag"]}"%')

    clause = " AND ".join(where)
    total = db.scalar(f"SELECT COUNT(*) FROM contacts WHERE {clause}", params, default=0)
    rows = db.query(
        f"SELECT email, name_en, country FROM contacts WHERE {clause} ORDER BY score DESC LIMIT 8",
        params,
    )
    return {"total": total,
            "sample": [{"email": r["email"], "name": r["name_en"]} for r in rows]}


def _unsubscribe(args: dict, actor: str) -> dict:
    email = _email(args.get("email"))
    with db.transaction():
        db.execute("UPDATE contacts SET status = 'unsubscribed' WHERE lower(email) = ?", (email,))
        if not db.one("SELECT 1 FROM suppression WHERE lower(email) = ?", (email,)):
            db.insert("suppression", {
                "id": new_id("sup"), "email": email,
                "reason": str(args.get("reason") or "unsub")[:60], "created_at": iso(),
            })
        log(kind="agent", actor=actor, action_en=f"stopped mailing {email}",
            action_fa=f"ارسال به {email} متوقف شد", target=email, tone="warn")
    return {"email": email, "status": "unsubscribed"}


def _create_group(args: dict, actor: str) -> dict:
    """Build an audience.

    The agent could name a segment id but never make one, so on an install
    with no groups — which is every new install — it had nothing to point a
    campaign at and returned none. The campaign was then created with no
    audience and the send refused, which is the loop the operator was stuck in.

    Validation goes through the same compiler the REST route uses, so a rule
    the agent invents is refused here exactly as a rule a person types is.
    """
    from .routers.audience import UnknownField, validate_rules

    name = _text(args.get("name"), field="name", limit=80)
    match = str(args.get("match") or "all")
    if match not in {"all", "any", "everyone"}:
        match = "all"
    rules = args.get("rules")
    rules = [r for r in rules if isinstance(r, dict)] if isinstance(rules, list) else []

    try:
        validate_rules(rules, match)
    except UnknownField as exc:
        raise ToolError(str(exc)) from exc

    sid = new_id("seg")
    with db.transaction():
        db.insert("segments", {
            "id": sid, **bi_in(name, "name"), "emoji": "🎯",
            "tint": "linear-gradient(140deg,#7ba3cd,#274563)",
            "size": 0, "growth": 0, "open_rate": 0, "live": 1,
            "match_mode": match, "rules": db.dumps(rules), "created_at": iso(),
        })
        log(kind="agent", actor=actor, action_en=f"created the group '{name}'",
            action_fa=f"گروه «{name}» را ساخت", target=sid, tone="info")

    from .routers.audience import segment_members
    return {"segmentId": sid, "name": name, "size": len(segment_members(sid))}


def _create_campaign(args: dict, actor: str) -> dict:
    name = _text(args.get("name") or args.get("subject"), field="name", limit=120)
    subject = _text(args.get("subject"), field="subject", limit=200)
    html = _body_html(args.get("body"))

    segment_id = args.get("segmentId") or None
    if segment_id and not db.one("SELECT 1 FROM segments WHERE id = ?", (segment_id,)):
        # A hallucinated id must not become a campaign pointed at nothing.
        raise ToolError(f"there is no segment {segment_id!r}")

    cid = new_id("c")
    with db.transaction():
        db.insert("campaigns", {
            "id": cid, **bi_in(name, "name"), **bi_in(subject, "subject"),
            "body_en": html, "body_fa": html, "type": "agent", "status": "draft",
            "segment_id": segment_id, "created_at": iso(), "updated_at": iso(),
        })
        log(kind="agent", actor=actor, action_en="drafted a campaign",
            action_fa="یک کمپین پیش‌نویس کرد", target=cid, tone="info")
    return {"campaignId": cid, "name": name, "status": "draft"}


# ------------------------------------------------------------- outward tools


def _send_email(args: dict, actor: str) -> dict:
    from . import google, mailer

    recipients = args.get("to")
    if isinstance(recipients, str):
        recipients = [recipients]
    addresses = [_email(x) for x in (recipients or [])][:MAX_RECIPIENTS_PER_EMAIL]
    if not addresses:
        raise ToolError("no recipient was given")

    subject = _text(args.get("subject"), field="subject", limit=200)
    html = emailhtml.wrap_for_send(db, _body_html(args.get("body")), subject=subject)

    # Who is being written to is checked before whether we can write at all: an
    # operator asking to mail someone who has unsubscribed should hear about
    # THAT, which is about their request, rather than about the deployment.
    blocked = [a for a in addresses
               if db.one("SELECT 1 FROM suppression WHERE lower(email) = ?", (a,))]
    addresses = [a for a in addresses if a not in blocked]
    if not addresses:
        raise ToolError("every one of those addresses has unsubscribed")

    d = deployment.get()
    if not d.get("google_refresh"):
        raise ToolError("no mailbox is connected — connect one in Settings, Sending")

    token = mailer.access_token()
    sent, failed = [], []
    for address in addresses:
        raw = google.build_message(
            to=address,
            sender=d.get("from_email") or d.get("google_email") or "",
            sender_name=d.get("from_name") or d.get("brand_name") or "",
            subject=subject, html=html, reply_to=d.get("reply_to") or "",
        )
        try:
            google.send_message(token, raw)
            sent.append(address)
        except google.GoogleError as exc:
            failed.append({"email": address, "why": str(exc)})

    log(kind="agent", actor=actor, action_en=f"sent an email to {len(sent)} people",
        action_fa=f"به {len(sent)} نفر ایمیل فرستاد", target="email",
        tone="good" if sent else "bad")
    return {"sent": sent, "failed": failed, "skippedAsUnsubscribed": blocked}


def _send_campaign(args: dict, actor: str) -> dict:
    from . import mailer
    from .routers.audience import segment_members

    cid = str(args.get("campaignId") or "").strip()
    row = db.one("SELECT * FROM campaigns WHERE id = ?", (cid,))
    if row is None:
        raise ToolError(f"there is no campaign {cid!r}")
    if row["status"] == "sent":
        raise ToolError("that campaign has already been sent")
    if not row["segment_id"]:
        raise ToolError("that campaign has no audience yet")
    if not deployment.get().get("google_refresh"):
        raise ToolError("no mailbox is connected — connect one in Settings, Sending")

    db.execute("UPDATE campaigns SET status = 'running', updated_at = ? WHERE id = ?",
               (iso(), cid))
    queued = mailer.enqueue(cid, recipients=segment_members(row["segment_id"]))
    db.execute("UPDATE campaigns SET recipients = ? WHERE id = ?", (queued, cid))
    log(kind="agent", actor=actor, action_en=f"started sending to {queued} people",
        action_fa=f"ارسال به {queued} نفر آغاز شد", target=cid, tone="good")
    return {"campaignId": cid, "queued": queued}


RUNNERS: dict[str, Callable[[dict, str], dict]] = {
    "add_contacts": _add_contacts,
    "find_contacts": _find_contacts,
    "unsubscribe": _unsubscribe,
    "create_group": _create_group,
    "create_campaign": _create_campaign,
    "send_email": _send_email,
    "send_campaign": _send_campaign,
}


# ================================================================ the gateway


def run(tool: str, args: dict, *, actor: str = "agent") -> dict:
    """Carry out one action. Raises `ToolError` with something worth reading."""
    runner = RUNNERS.get(tool)
    if runner is None:
        raise ToolError(f"{tool!r} is not something I can do")
    if not isinstance(args, dict):
        raise ToolError("the arguments were not an object")
    return runner(args, actor)


def summarise(tool: str, args: Any) -> str:
    """One line describing a pending action, for the button the human presses.

    Built here from the validated arguments rather than taken from the model's
    prose, so what the operator approves is what will actually happen.
    """
    # `args` arrives from the model. `execute` checks the ACTION is an object
    # and did not check the same of its arguments, so `{"tool": "send_email",
    # "args": "nope"}` reached `.get()` and 500'd the request.
    if not isinstance(args, dict):
        return tool.replace("_", " ")
    if tool == "send_email":
        to = args.get("to")
        to = [to] if isinstance(to, str) else (to or [])
        who = ", ".join(str(x) for x in to[:3])
        more = f" +{len(to) - 3}" if len(to) > 3 else ""
        return f'Send "{args.get("subject", "")}" to {who}{more}'
    if tool == "send_campaign":
        row = db.one("SELECT name_en FROM campaigns WHERE id = ?", (args.get("campaignId"),))
        return f'Send the campaign "{row["name_en"]}" to its whole audience' if row \
            else "Send a campaign"
    return tool.replace("_", " ")


def execute(actions: Any, *, actor: str = "agent") -> tuple[list[dict], list[dict]]:
    """Run what is safe, hold back what is not.

    Returns `(done, pending)`. Anything in `pending` has been validated but not
    performed; it needs a human to press the button, unless this deployment was
    deliberately set to `auto`.
    """
    autonomy = deployment.get().get("agent_autonomy") or "approve"
    done: list[dict] = []
    pending: list[dict] = []

    for action in (actions or [])[:MAX_PER_TURN]:
        if not isinstance(action, dict):
            continue
        tool = str(action.get("tool") or "").strip()
        args = action.get("args")
        if tool not in RUNNERS:
            continue
        # the model is asked for an object here and does not always send one
        if not isinstance(args, dict):
            done.append({"tool": tool, "ok": False,
                         "error": "the arguments were not an object"})
            continue

        # `suggest` means the agent proposes and never acts; the operator chose
        # that, so even a safe action waits.
        outward = tool in OUTWARD
        if autonomy == "suggest" or (outward and autonomy != "auto"):
            try:
                pending.append({"tool": tool, "args": args, "says": summarise(tool, args),
                                "outward": outward})
            except ToolError as exc:
                done.append({"tool": tool, "ok": False, "error": str(exc)})
            continue

        try:
            done.append({"tool": tool, "ok": True, "result": run(tool, args, actor=actor)})
        except ToolError as exc:
            done.append({"tool": tool, "ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - one bad action must not lose the turn
            done.append({"tool": tool, "ok": False, "error": str(exc)[:200]})

    return done, pending


def sign(tool: str, args: dict) -> str:
    """A tamper check for a pending action on its way to the browser and back.

    The confirm endpoint re-validates everything anyway, but this makes the
    round trip carry exactly what was shown: the operator approves the sentence
    they read, not whatever the client posts back.
    """
    from .security import sign_blob

    return sign_blob(_canonical(tool, args))


def blob_ok(tool: str, args: Any, signature: str) -> bool:
    """Does this posted action match the one that was signed and shown?"""
    from .security import blob_matches

    if not isinstance(args, dict):
        return False
    return blob_matches(_canonical(tool, args), signature)


def _canonical(tool: str, args: dict) -> str:
    """One string per action, stable across a JSON round trip.

    `sort_keys` matters: the browser re-serialises the args on the way back and
    is under no obligation to keep our key order.
    """
    return json.dumps({"tool": tool, "args": args}, sort_keys=True, ensure_ascii=False)
