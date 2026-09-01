"""Contacts, segments and the suppression list.

Two rules are enforced server-side because they are the ones that get a sender
blocked, and no client should be trusted to remember them:

* an address on the suppression list can never be re-subscribed by an import;
* unsubscribing writes to BOTH the contact and the suppression list, in one
  transaction, so the two can never disagree about whether someone opted out.
"""

from __future__ import annotations

import base64
import binascii
import csv
import io
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from .. import db, exporting, tabular
from ..deps import Principal, requires
from ..domain import bi_in, iso, like, log, paginate
from ..schemas import (
    Body,
    ContactIn,
    ContactPatch,
    ImportAnalyseIn,
    ImportIn,
    SegmentIn,
    SegmentPatch,
    SuppressionIn,
)
from ..security import new_id
from ..serial import contact as ser_contact
from ..serial import segment as ser_segment
from ..serial import suppression as ser_supp

router = APIRouter(tags=["audience"])


# ================================================================ contacts


def _suppressed(email: str) -> bool:
    return db.one("SELECT 1 FROM suppression WHERE lower(email) = lower(?)", (email,)) is not None


@router.get("/contacts")
def list_contacts(
    q: str = "",
    status: str = "all",
    tag: str = "all",
    sort: str = "score",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=500),
    _: Principal = Depends(requires("contacts.read")),
) -> dict:
    where = ["1=1"]
    params: list = []
    if status != "all":
        where.append("status = ?")
        params.append(status)
    if tag != "all":
        # tags are a JSON array; match the quoted token so "vip" does not also
        # match "vip-2024"
        where.append("tags LIKE ? ESCAPE '\\'")
        params.append(f'%"{tag}"%')
    if q:
        where.append("(name_en LIKE ? ESCAPE '\\' OR name_fa LIKE ? ESCAPE '\\' OR email LIKE ? ESCAPE '\\')")
        params += [like(q)] * 3

    order = {
        "score": "score DESC", "ltv": "ltv DESC", "created": "created_at DESC",
        "lastOpen": "last_open_at DESC", "name": "name_en COLLATE NOCASE ASC",
    }.get(sort, "score DESC")

    rows = db.query(f"SELECT * FROM contacts WHERE {' AND '.join(where)} ORDER BY {order}", params)
    out = paginate(rows, page, size)
    out["items"] = [ser_contact(r) for r in out["items"]]
    return out


@router.get("/contacts/stats")
def contact_stats(_: Principal = Depends(requires("contacts.read"))) -> dict:
    row = db.one(
        """
        SELECT COUNT(*) total,
               SUM(CASE WHEN score >= 60 THEN 1 ELSE 0 END) engaged,
               SUM(CASE WHEN score < 25 THEN 1 ELSE 0 END) dormant,
               SUM(CASE WHEN status = 'subscribed' THEN 1 ELSE 0 END) subscribed,
               SUM(CASE WHEN status = 'unsubscribed' THEN 1 ELSE 0 END) unsubscribed,
               SUM(CASE WHEN status = 'bounced' THEN 1 ELSE 0 END) bounced
        FROM contacts
        """
    )
    return {k: (row[k] or 0) for k in row.keys()}


@router.get("/contacts/export")
def export_contacts(_: Principal = Depends(requires("contacts.export"))) -> Response:
    """Everything, as a spreadsheet.

    Behind `contacts.export` rather than `contacts.read`: reading one person on
    screen and walking out with the whole list are different acts, and the role
    matrix already said so — there was simply no endpoint enforcing it.
    """
    rows = db.query("SELECT name_en, email, status, score, ltv, orders, country, "
                    "tags, last_open_at, created_at FROM contacts ORDER BY created_at DESC")
    out = [{"name": r["name_en"], "email": r["email"], "status": r["status"],
            "score": r["score"], "ltv": r["ltv"], "orders": r["orders"],
            "country": r["country"], "tags": " ".join(db.loads(r["tags"], [])),
            "last_open": r["last_open_at"] or "", "added": r["created_at"]}
           for r in rows]
    return exporting.csv_response(out, ["name", "email", "status", "score", "ltv",
                                        "orders", "country", "tags", "last_open",
                                        "added"], "contacts.csv")


@router.get("/suppression/export")
def export_suppression(_: Principal = Depends(requires("contacts.export"))) -> Response:
    rows = db.query("SELECT email, reason, created_at FROM suppression ORDER BY created_at DESC")
    return exporting.csv_response(
        [{"email": r["email"], "reason": r["reason"], "added": r["created_at"]}
         for r in rows], ["email", "reason", "added"], "blocked.csv")


class BulkIn(Body):
    """Ids plus what to do to them. One shape for both actions."""
    ids: list[str] = []
    addTags: list[str] = []
    removeTags: list[str] = []


@router.post("/contacts/bulk/tag")
def bulk_tag(payload: BulkIn, principal: Principal = Depends(requires("contacts.write"))) -> dict:
    """Put a group of people in a group.

    This is what "add to a group" means in this product. A segment is a RULE,
    not a hand-kept list — it is re-evaluated every time anything reads it, so
    there is no membership table to append to. Tagging is the thing a person
    can do directly, and a segment whose rule is `tag has "vip"` then contains
    them from that moment on.

    The button that called this had no handler at all: selecting contacts and
    pressing it did nothing, silently, which is the worst way for a control to
    fail.
    """
    ids = [str(i) for i in payload.ids][:1000]
    if not ids:
        raise HTTPException(status_code=422, detail="No contacts were selected")

    add = [t.strip() for t in payload.addTags if t.strip()][:20]
    drop = {t.strip() for t in payload.removeTags if t.strip()}
    if not add and not drop:
        raise HTTPException(status_code=422, detail="Give a tag to add or remove")

    touched = 0
    with db.transaction():
        marks = ", ".join("?" for _ in ids)
        for row in db.query(f"SELECT id, tags FROM contacts WHERE id IN ({marks})", ids):
            tags = [str(t) for t in db.loads(row["tags"], [])]
            # order preserved, duplicates dropped: a tag list is read by people
            after = [t for t in tags if t not in drop]
            for tag in add:
                if tag not in after:
                    after.append(tag)
            if after != tags:
                db.update("contacts", row["id"], {"tags": db.dumps(after)})
                touched += 1
        if touched:
            log(kind="human", actor=principal.id,
                action_en=f"tagged {touched} contacts",
                action_fa=f"{touched} مخاطب برچسب خورد", target="contacts", tone="info")
    return {"updated": touched, "tags": add}


@router.post("/contacts/bulk/delete")
def bulk_delete(payload: BulkIn, principal: Principal = Depends(requires("contacts.write"))) -> dict:
    """Remove several people at once.

    Deleting a contact does NOT unsubscribe them: if they asked not to be
    mailed, that belongs on the suppression list, which outlives the row. This
    endpoint is for cleaning up a bad import, and says so.
    """
    ids = [str(i) for i in payload.ids][:1000]
    if not ids:
        raise HTTPException(status_code=422, detail="No contacts were selected")
    marks = ", ".join("?" for _ in ids)
    with db.transaction():
        gone = db.execute(f"DELETE FROM contacts WHERE id IN ({marks})", ids).rowcount
        log(kind="human", actor=principal.id, action_en=f"deleted {gone} contacts",
            action_fa=f"{gone} مخاطب حذف شد", target="contacts", tone="warn")
    return {"deleted": gone}


@router.get("/contacts/{contact_id}")
def get_contact(contact_id: str, _: Principal = Depends(requires("contacts.read"))) -> dict:
    row = db.one("SELECT * FROM contacts WHERE id = ?", (contact_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    out = ser_contact(row)
    out["activity"] = [
        {"type": e["type"], "at": e["created_at"], "campaign": e["campaign_id"]}
        for e in db.query(
            "SELECT * FROM events WHERE email = ? ORDER BY created_at DESC LIMIT 25", (row["email"],)
        )
    ]
    out["suppressed"] = _suppressed(row["email"])
    return out


@router.post("/contacts", status_code=201)
def create_contact(payload: ContactIn, principal: Principal = Depends(requires("contacts.write"))) -> dict:
    email = str(payload.email).lower()
    if db.one("SELECT 1 FROM contacts WHERE lower(email) = ?", (email,)):
        raise HTTPException(status_code=409, detail="A contact with that address already exists")
    if _suppressed(email) and payload.status == "subscribed":
        raise HTTPException(status_code=409, detail="That address is on the suppression list")

    cid = new_id("p")
    name = payload.name or email.split("@")[0]
    with db.transaction():
        db.insert("contacts", {
            "id": cid, **bi_in(name, "name"), "email": email, "status": payload.status,
            "score": 0, "ltv": 0, "orders": 0, "tags": db.dumps(payload.tags),
            "source_id": payload.source, "source_en": payload.source, "source_fa": payload.source,
            "country": payload.country, "device": "desktop",
            "last_open_at": None, "created_at": iso(),
        })
        log(kind="human", actor=principal.id, action_en="added a contact",
            action_fa="یک مخاطب افزود", target=cid, tone="info")
    return ser_contact(db.one("SELECT * FROM contacts WHERE id = ?", (cid,)))


@router.patch("/contacts/{contact_id}")
def update_contact(
    contact_id: str, payload: ContactPatch, principal: Principal = Depends(requires("contacts.write"))
) -> dict:
    row = db.one("SELECT * FROM contacts WHERE id = ?", (contact_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    data: dict = {}
    if payload.name is not None:
        data |= bi_in(payload.name, "name")
    if payload.tags is not None:
        data["tags"] = db.dumps(payload.tags)
    if payload.country is not None:
        data["country"] = payload.country
    if payload.score is not None:
        data["score"] = payload.score

    with db.transaction():
        if payload.status is not None and payload.status != row["status"]:
            data["status"] = payload.status
            # opting out must land in both places or the next import undoes it
            if payload.status == "unsubscribed" and not _suppressed(row["email"]):
                db.insert("suppression", {"id": new_id("s"), "email": row["email"],
                                          "reason": "unsub", "created_at": iso()})
            if payload.status == "subscribed":
                db.execute("DELETE FROM suppression WHERE lower(email) = lower(?)", (row["email"],))
        if data:
            db.update("contacts", contact_id, data)
    return ser_contact(db.one("SELECT * FROM contacts WHERE id = ?", (contact_id,)))


@router.delete("/contacts/{contact_id}", status_code=204)
def delete_contact(contact_id: str, principal: Principal = Depends(requires("contacts.write"))) -> None:
    if db.one("SELECT 1 FROM contacts WHERE id = ?", (contact_id,)) is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    with db.transaction():
        db.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        log(kind="human", actor=principal.id, action_en="deleted a contact",
            action_fa="یک مخاطب را حذف کرد", target=contact_id, tone="warn")


@router.post("/contacts/import")
def import_contacts(payload: ImportIn, principal: Principal = Depends(requires("contacts.write"))) -> dict:
    """Accepts a CSV with at least an `email` column.

    Reports per-row outcomes rather than failing the whole file on one bad
    address — an import of ten thousand rows that dies on row 4,000 with no
    detail is unusable.
    """
    # Two ways in: the original CSV paste, or an uploaded file with a mapping
    # that says which column is which.
    if payload.data:
        try:
            headers, rows = tabular.parse(_decode_upload(payload.data), filename=payload.filename)
        except tabular.UnreadableFile as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        mapping = {f: h for f, h in payload.mapping.items() if h in headers}
        if "email" not in mapping:
            raise HTTPException(status_code=422, detail="Say which column holds the email address")
        index = {f: headers.index(h) for f, h in mapping.items()}
        source = [
            {field: (row[i] if i < len(row) else "") for field, i in index.items()}
            for row in rows
        ]
    else:
        reader = csv.DictReader(io.StringIO(payload.csv.strip()))
        if not reader.fieldnames or not any(
            f and f.lower().strip() == "email" for f in reader.fieldnames
        ):
            raise HTTPException(status_code=422, detail="CSV must have an 'email' column")
        source = [
            {(k or "").lower().strip(): (v or "").strip() for k, v in raw.items()}
            for raw in reader
        ]

    created = updated = skipped = 0
    errors: list[dict] = []
    with db.transaction():
        for i, row in enumerate(source, start=2):
            row = {k: (v or "").strip() for k, v in row.items()}
            email = row.get("email", "").lower()
            if not email or "@" not in email:
                errors.append({"line": i, "error": "invalid email"})
                continue
            if _suppressed(email):
                skipped += 1
                continue
            raw_tags = row.get("tags", "")
            # split on whatever the export used, rather than insisting on a pipe
            tags = [t.strip() for t in re.split(r"[|,;/]", raw_tags) if t.strip()] if raw_tags else []
            if row.get("phone"):
                tags.append(f"phone:{row['phone']}")
            tags = list(dict.fromkeys(tags + payload.default_tags))
            existing = db.one("SELECT id FROM contacts WHERE lower(email) = ?", (email,))
            name = row.get("name") or email.split("@")[0]
            if existing:
                db.update("contacts", existing["id"], {**bi_in(name, "name"), "tags": db.dumps(tags)})
                updated += 1
            else:
                db.insert("contacts", {
                    "id": new_id("p"), **bi_in(name, "name"), "email": email,
                    "status": "subscribed", "score": 0, "ltv": 0, "orders": 0,
                    "tags": db.dumps(tags), "source_id": "import",
                    "source_en": "CSV import", "source_fa": "ورود از CSV",
                    "country": row.get("country", ""), "device": "desktop",
                    "last_open_at": None, "created_at": iso(),
                })
                created += 1
        log(kind="human", actor=principal.id,
            action_en=f"imported {created + updated} contacts",
            action_fa=f"{created + updated} مخاطب وارد کرد", target="contacts", tone="info")

    return {"created": created, "updated": updated, "skipped_suppressed": skipped,
            "errors": errors[:50], "error_count": len(errors)}



#: What a contact row can become. Anything else in the file is ignored rather
#: than guessed at — a column we cannot use is not a column worth inventing a
#: home for.
IMPORT_FIELDS = {
    "email": "the email address (required)",
    "name": "the person's name",
    "country": "country, ideally a two-letter code",
    "tags": "labels, however they are separated",
    "phone": "a phone number — stored as a tag, not a field",
}

MAPPING_SHAPE = """{
  "mapping": {"email": "the exact header holding emails", "name": "the exact header holding names"},
  "notes": "one sentence on anything you were unsure about"
}"""


@router.post("/contacts/import/analyse")
def analyse_import(payload: ImportAnalyseIn,
                   _: Principal = Depends(requires("contacts.write"))) -> dict:
    """Read the file, and work out which column is which.

    Returns the mapping as a SUGGESTION with the sample it was based on. The
    operator confirms it before a single row is written — the alternative is
    discovering that the phone column went into the email field after twenty
    thousand contacts already have it.
    """
    try:
        blob = _decode_upload(payload.data)
        headers, rows = tabular.parse(blob, filename=payload.filename)
    except tabular.UnreadableFile as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not headers:
        raise HTTPException(status_code=422, detail="No column headers found")

    sample = tabular.sample(headers, rows)
    mapping, notes, source = _suggest_mapping(headers, sample)

    return {
        "headers": headers,
        "sample": sample,
        "rowCount": len(rows),
        "mapping": mapping,
        "notes": notes,
        "source": source,
        "fields": IMPORT_FIELDS,
    }


def _decode_upload(data: str) -> bytes:
    raw = data
    if "," in raw and raw.strip().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="That file could not be decoded") from exc


def _suggest_mapping(headers: list[str], sample: list[dict]) -> tuple[dict, str, str]:
    """Ask the model; fall back to matching header names.

    The fallback is deliberately weak — it knows English and Persian and
    nothing else — because a weak fallback that the operator then CORRECTS is
    fine, while a clever one that is confidently wrong is not.
    """
    from .. import brain
    from ..ai_provider import AIUnavailable

    try:
        out = brain.complete_json_grounded(
            system_extra=(
                "You are mapping the columns of an uploaded contact list onto the "
                "fields below. Use the sample VALUES as well as the header names: "
                "the column whose values contain @ is the email column whatever it "
                "is called, in whatever language.\n"
                + "\n".join(f"  {k}: {v}" for k, v in IMPORT_FIELDS.items())
                + "\n\nUse the EXACT header strings as values. Omit any field the "
                "file does not have. Never invent a header."
            ),
            user=("Headers: " + ", ".join(headers)
                  + "\n\nFirst rows:\n" + json.dumps(sample, ensure_ascii=False)),
            shape=MAPPING_SHAPE,
            max_tokens=600,
            temperature=0.0,
        )
        mapping = {
            field: header
            for field, header in (out.get("mapping") or {}).items()
            if field in IMPORT_FIELDS and header in headers
        }
        if mapping:
            return mapping, str(out.get("notes") or ""), "ai"
    except (AIUnavailable, Exception):  # noqa: BLE001 - never block an import on the model
        pass

    return _guess_mapping(headers), "", "guess"


#: The fallback. English and Persian header words only.
_HEADER_HINTS = {
    "email": ("email", "e-mail", "mail", "ایمیل", "رایانامه", "پست الکترونیک"),
    "name": ("name", "fullname", "full name", "first", "نام", "اسم"),
    "country": ("country", "کشور"),
    "tags": ("tag", "tags", "label", "برچسب", "گروه"),
    "phone": ("phone", "mobile", "tel", "تلفن", "موبایل", "همراه"),
}


def _guess_mapping(headers: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for field, hints in _HEADER_HINTS.items():
        for header in headers:
            low = header.lower().strip()
            if any(h in low for h in hints):
                out[field] = header
                break
    return out


# ================================================================ segments


@router.get("/segments")
def list_segments(_: Principal = Depends(requires("contacts.read"))) -> list[dict]:
    return [ser_segment(r) for r in db.query("SELECT * FROM segments ORDER BY size DESC")]


@router.get("/segments/{segment_id}")
def get_segment(segment_id: str, _: Principal = Depends(requires("contacts.read"))) -> dict:
    row = db.one("SELECT * FROM segments WHERE id = ?", (segment_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    return ser_segment(row)


@router.get("/segments/{segment_id}/preview")
def preview_segment(
    segment_id: str, limit: int = Query(10, ge=1, le=100), _: Principal = Depends(requires("contacts.read"))
) -> dict:
    """Runs the segment's rules against the real contact table."""
    row = db.one("SELECT * FROM segments WHERE id = ?", (segment_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    try:
        where, params = _compile_rules(db.loads(row["rules"]), row["match_mode"])
    except UnknownField as exc:
        # A segment saved before unknown fields were refused. Reporting zero and
        # saying why beats both a 500 and the old behaviour, which was to widen
        # it to every contact.
        return {"total": 0, "items": [], "broken": str(exc)}
    total = db.scalar(f"SELECT COUNT(*) FROM contacts WHERE {where}", params, default=0)
    rows = db.query(f"SELECT * FROM contacts WHERE {where} ORDER BY score DESC LIMIT ?", [*params, limit])
    return {"total": total, "items": [ser_contact(r) for r in rows]}


# The only place a rule's field name is allowed to reach SQL. Anything not in
# this map is rejected, so a rule can never name an arbitrary column.
_FIELDS = {
    "orders": "orders", "ltv": "ltv", "score": "score", "country": "country",
    "status": "status", "device": "device", "tag": "tags", "lastOpen": "last_open_at",
}
_OPS = {"eq": "=", "neq": "!=", "gte": ">=", "lte": "<=", "gt": ">", "lt": "<"}


class UnknownField(ValueError):
    """A rule named a column the compiler does not accept."""


def validate_rules(rules: list[dict], match: str = "all") -> None:
    """Refuse unknown fields BEFORE anything is saved.

    Silently dropping them is what made a mistyped rule compile to `1=1`, i.e.
    to everyone. Whoever wrote the rule meant something by it; the one thing we
    must not do is quietly decide they meant "the whole list".
    """
    # An empty rule list compiles to `1=1` — every contact there is. The
    # unknown-field check below exists because silently widening a segment is
    # dangerous, and this was the same danger through a different door: a group
    # nobody got round to describing quietly meant everybody.
    #
    # Targeting everyone is still allowed. It just has to be said.
    if not rules and match != "everyone":
        raise UnknownField(
            "This group has no rules, so it would match every contact you have. "
            "Add a rule to say who belongs — or choose 'everyone' if that is "
            "really what you mean."
        )

    unknown = sorted({
        str(r.get("field", "")) for r in rules
        if str(r.get("field", "")) not in _FIELDS
    })
    if unknown:
        raise UnknownField(
            "These are not fields you can filter on: " + ", ".join(unknown)
            + ". Allowed: " + ", ".join(sorted(_FIELDS))
        )


def _compile_rules(rules: list[dict], match: str) -> tuple[str, list]:
    if match == "everyone":
        return "1=1", []
    if not rules:
        # Only reachable for a segment saved before `everyone` existed. It
        # keeps working rather than breaking, because changing what an existing
        # group means without being asked is its own kind of damage.
        return "1=1", []
    clauses: list[str] = []
    params: list = []
    for rule in rules:
        col = _FIELDS.get(str(rule.get("field", "")))
        if not col:
            continue
        op = str(rule.get("op", "eq"))
        value = str(rule.get("value", ""))
        if col == "tags" and op == "has":
            clauses.append("tags LIKE ?")
            params.append(f'%"{value}"%')
        elif col == "last_open_at" and op in {"before", "after"}:
            from ..domain import ago_iso
            days = int("".join(ch for ch in value if ch.isdigit()) or 0)
            clauses.append(f"last_open_at {'<' if op == 'before' else '>'} ?")
            params.append(ago_iso(days=days))
        elif op in _OPS:
            clauses.append(f"{col} {_OPS[op]} ?")
            params.append(value)
    if not clauses:
        return "1=1", []
    return "(" + (" AND " if match == "all" else " OR ").join(clauses) + ")", params


def segment_members(segment_id: str) -> list[dict]:
    """Everyone a segment matches right now, for the sender to queue.

    Resolved at SEND time rather than being stored on the campaign. A segment
    is a rule, not a list: someone who unsubscribed or stopped matching between
    the campaign being written and it being sent should not receive it, and the
    only way to honour that is to ask the question late.

    Unsubscribed and bounced contacts are excluded here as well as by the
    suppression check in the sender, because a rule that does not mention
    `status` would otherwise happily match them.
    """
    row = db.one("SELECT * FROM segments WHERE id = ?", (segment_id,))
    if row is None:
        return []
    try:
        where, params = _compile_rules(db.loads(row["rules"]), row["match_mode"])
    except UnknownField:
        return []
    rows = db.query(
        f"SELECT id, name_en, name_fa, email FROM contacts "
        f"WHERE {where} AND status = 'subscribed'",
        params,
    )
    return [{"id": r["id"], "email": r["email"], "name": r["name_en"] or r["name_fa"]}
            for r in rows]


@router.post("/segments", status_code=201)
def create_segment(payload: SegmentIn, principal: Principal = Depends(requires("contacts.write"))) -> dict:
    sid = new_id("seg")
    rules = [r.model_dump() for r in payload.rules]
    try:
        validate_rules(rules, payload.match)
        where, params = _compile_rules(rules, payload.match)
    except UnknownField as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    size = db.scalar(f"SELECT COUNT(*) FROM contacts WHERE {where}", params, default=0)
    with db.transaction():
        db.insert("segments", {
            "id": sid, **bi_in(payload.name, "name"), "emoji": payload.emoji,
            "tint": "linear-gradient(140deg,#5b8cff,#1b3fae)", "size": size,
            "growth": 0, "open_rate": 0, "live": 1, "match_mode": payload.match,
            "rules": db.dumps(rules), "created_at": iso(),
        })
        log(kind="human", actor=principal.id, action_en="created a segment",
            action_fa="یک بخش‌بندی ساخت", target=sid, tone="info")
    return ser_segment(db.one("SELECT * FROM segments WHERE id = ?", (sid,)))


@router.patch("/segments/{segment_id}")
def update_segment(
    segment_id: str, payload: SegmentPatch, principal: Principal = Depends(requires("contacts.write"))
) -> dict:
    row = db.one("SELECT * FROM segments WHERE id = ?", (segment_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    data: dict = {}
    if payload.name is not None:
        data |= bi_in(payload.name, "name")
    if payload.emoji is not None:
        data["emoji"] = payload.emoji
    if payload.live is not None:
        data["live"] = int(payload.live)
    if payload.rules is not None or payload.match is not None:
        rules = [r.model_dump() for r in payload.rules] if payload.rules is not None else db.loads(row["rules"])
        match = payload.match or row["match_mode"]
        try:
            validate_rules(rules, payload.match or row["match_mode"])
            where, params = _compile_rules(rules, match)
        except UnknownField as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        data |= {"rules": db.dumps(rules), "match_mode": match,
                 "size": db.scalar(f"SELECT COUNT(*) FROM contacts WHERE {where}", params, default=0)}
    if data:
        with db.transaction():
            db.update("segments", segment_id, data)
    return ser_segment(db.one("SELECT * FROM segments WHERE id = ?", (segment_id,)))


@router.delete("/segments/{segment_id}", status_code=204)
def delete_segment(segment_id: str, principal: Principal = Depends(requires("contacts.write"))) -> None:
    if db.one("SELECT 1 FROM segments WHERE id = ?", (segment_id,)) is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    used = db.scalar("SELECT COUNT(*) FROM campaigns WHERE segment_id = ?", (segment_id,), default=0)
    if used:
        raise HTTPException(status_code=409, detail=f"{used} campaign(s) still use this segment")
    with db.transaction():
        db.execute("DELETE FROM segments WHERE id = ?", (segment_id,))


# ================================================================ suppression


@router.get("/suppression")
def list_suppression(
    q: str = "",
    reason: str = "all",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=500),
    _: Principal = Depends(requires("contacts.read")),
) -> dict:
    where = ["1=1"]
    params: list = []
    if reason != "all":
        where.append("reason = ?")
        params.append(reason)
    if q:
        where.append("email LIKE ? ESCAPE '\\'")
        params.append(like(q))
    rows = db.query(f"SELECT * FROM suppression WHERE {' AND '.join(where)} ORDER BY created_at DESC", params)
    out = paginate(rows, page, size)
    out["items"] = [ser_supp(r) for r in out["items"]]
    counts = db.query("SELECT reason, COUNT(*) n FROM suppression GROUP BY reason")
    out["counts"] = {r["reason"]: r["n"] for r in counts}
    return out


@router.post("/suppression", status_code=201)
def add_suppression(payload: SuppressionIn, principal: Principal = Depends(requires("contacts.write"))) -> dict:
    email = str(payload.email).lower()
    if _suppressed(email):
        raise HTTPException(status_code=409, detail="Already suppressed")
    sid = new_id("s")
    with db.transaction():
        db.insert("suppression", {"id": sid, "email": email, "reason": payload.reason, "created_at": iso()})
        # keep the contact record consistent with the suppression list
        db.execute("UPDATE contacts SET status = 'unsubscribed' WHERE lower(email) = ?", (email,))
        log(kind="human", actor=principal.id, action_en="suppressed an address",
            action_fa="یک آدرس را به لیست سیاه افزود", target=email, tone="warn")
    return ser_supp(db.one("SELECT * FROM suppression WHERE id = ?", (sid,)))


@router.delete("/suppression/{entry_id}", status_code=204)
def remove_suppression(entry_id: str, principal: Principal = Depends(requires("contacts.write"))) -> None:
    row = db.one("SELECT * FROM suppression WHERE id = ?", (entry_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    with db.transaction():
        db.execute("DELETE FROM suppression WHERE id = ?", (entry_id,))
        log(kind="human", actor=principal.id, action_en="removed a suppression",
            action_fa="یک آدرس را از لیست سیاه درآورد", target=row["email"], tone="info")
