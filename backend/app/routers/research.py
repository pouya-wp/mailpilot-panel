"""The research agent: find who to reach, by region and by kind.

Two inputs and a review queue. The reasoning for the queue is in
`app/prospect.py` and is the whole design — nothing found here can reach the
sending list without a person reading it and saying yes.

`accept` is the only route that writes a contact, and it does two things the
ordinary contact route also does, for the same reasons: it refuses an address
on the suppression list, and it refuses one already on the list. A researched
lead is not special.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import brain, budget, db, deployment, prospect
from ..ai_provider import AIUnavailable
from ..deps import Principal, requires
from ..domain import bi_in, iso, log, paginate
from ..schemas import Body
from ..security import new_id

router = APIRouter(prefix="/research", tags=["research"])


def _needs_module() -> None:
    if not deployment.enabled("audience"):
        raise HTTPException(status_code=404, detail="Not found")


class ResearchIn(Body):
    region: str = ""
    category: str = ""
    lang: str = "en"


class AcceptIn(Body):
    ids: list[str] = []
    tags: list[str] = []
    #: Make (or reuse) a group holding exactly what this search found.
    #: On by default: a batch of leads with nothing to select them by is
    #: the thing that made them hard to use.
    group: bool = True


def run_label(run: dict | None) -> str:
    """What the search was, as a person would say it: "gold shops Dubai".

    Built from the run rather than asked for, because the operator already
    said both halves when they started the search and should not have to
    invent a name for the result.
    """
    if not run:
        return ""
    category = (run["category"] or "").strip()
    region = (run["region"] or "").strip()
    return " ".join(part for part in (category, region) if part)[:60]


@router.post("/run")
def run_research(payload: ResearchIn,
                 principal: Principal = Depends(requires("contacts.write"))) -> dict:
    """Go and look. Returns a brief and a queue of candidates.

    Search is required, not optional: this is a question about the world, and
    answering it from the model's memory would produce a confident list of
    businesses that may have closed years ago — or never existed.
    """
    _needs_module()
    region = payload.region.strip()
    category = payload.category.strip()
    if not region or not category:
        raise HTTPException(status_code=422,
                            detail="Give a place to look and a kind of business to look for.")
    if not deployment.get().get("ai_key"):
        raise HTTPException(status_code=400, detail="This installation has no AI key yet")

    settings = deployment.ai_settings()
    if not settings.search_enabled:
        raise HTTPException(
            status_code=400,
            detail=("Research needs web search, which is switched off for this "
                    "installation. Turn it on in Setup — without it the agent "
                    "would be answering from memory, which for a question about "
                    "real businesses means inventing them."),
        )

    try:
        daily, monthly = deployment.caps()
        budget.check(daily, monthly)
    except budget.BudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    try:
        out = brain.research_leads(
            region=region, category=category, lang=payload.lang,
        )
    except AIUnavailable as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    budget.record(out.get("_usage") or 0)

    result = prospect.store(new_id("run"), region, category, out)
    log(kind="agent", actor=deployment.get()["agent_name"],
        action_en=f"researched {category} in {region} — {result['found']} found",
        action_fa=f"دربارهٔ {category} در {region} تحقیق کرد — {result['found']} مورد",
        target="research", tone="info")
    result["citations"] = out.get("_citations") or []
    return result


@router.get("/leads")
def list_leads(status: str = "new", withEmail: str = "all",
               page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
               _: Principal = Depends(requires("contacts.read"))) -> dict:
    _needs_module()
    where, params = ["1=1"], []
    if status != "all":
        where.append("status = ?")
        params.append(status)
    if withEmail == "yes":
        where.append("email != ''")
    elif withEmail == "no":
        where.append("email = ''")

    rows = db.query(
        f"SELECT * FROM leads WHERE {' AND '.join(where)} ORDER BY created_at DESC", params)
    out = paginate(rows, page, size)
    out["items"] = [prospect.ser(r) for r in out["items"]]
    out["counts"] = {
        "new": db.scalar("SELECT COUNT(*) FROM leads WHERE status = 'new'", default=0),
        "accepted": db.scalar("SELECT COUNT(*) FROM leads WHERE status = 'accepted'", default=0),
        "dismissed": db.scalar("SELECT COUNT(*) FROM leads WHERE status = 'dismissed'", default=0),
        "withEmail": db.scalar("SELECT COUNT(*) FROM leads WHERE status = 'new' AND email != ''",
                               default=0),
    }
    return out


@router.get("/runs")
def list_runs(_: Principal = Depends(requires("contacts.read"))) -> list[dict]:
    _needs_module()
    return [{
        "id": r["id"], "region": r["region"], "category": r["category"],
        "brief": r["brief"], "angles": db.loads(r["angles"], []),
        "found": r["found"], "withEmail": r["with_email"], "at": r["created_at"],
    } for r in db.query("SELECT * FROM lead_runs ORDER BY created_at DESC LIMIT 20")]


@router.post("/leads/accept")
def accept(payload: AcceptIn,
           principal: Principal = Depends(requires("contacts.write"))) -> dict:
    """Move chosen leads onto the contact list.

    The only route here that writes a contact, and it is deliberately explicit
    — ids, chosen one at a time by a person who has read them. It enforces the
    same two refusals the ordinary contact route does, because a researched
    lead has earned no exemption: an address on the suppression list stays off,
    and one already on the list is not duplicated.

    The lead's source URL is written into the contact's `source` field, so six
    months from now the answer to "where did this person come from?" is still
    in the record.
    """
    _needs_module()
    ids = [str(i) for i in payload.ids][:500]
    if not ids:
        raise HTTPException(status_code=422, detail="No leads were chosen")

    tags = [t.strip() for t in payload.tags if t.strip()][:10]

    # The search these leads came from, so they can be tagged with it. All
    # the chosen ids normally share one run; if they somehow do not, the
    # most common one names the batch.
    marks_for_run = ", ".join("?" for _ in ids)
    runs = [r["run_id"] for r in
            db.query(f"SELECT run_id FROM leads WHERE id IN ({marks_for_run})", ids)
            if r["run_id"]]
    run = None
    if runs:
        top = max(set(runs), key=runs.count)
        run = db.one("SELECT * FROM lead_runs WHERE id = ?", (top,))
    label = run_label(run)
    if label and label not in tags:
        tags = (tags + [label])[:10]

    added, skipped, blocked, noemail = 0, 0, 0, 0
    group_id, group_name = "", ""

    with db.transaction():
        marks = ", ".join("?" for _ in ids)
        for row in db.query(f"SELECT * FROM leads WHERE id IN ({marks})", ids):
            email = (row["email"] or "").strip().lower()
            if not email:
                noemail += 1
                continue
            if db.one("SELECT 1 FROM suppression WHERE lower(email) = ?", (email,)):
                blocked += 1
                db.update("leads", row["id"], {"status": "dismissed"})
                continue
            if db.one("SELECT 1 FROM contacts WHERE lower(email) = ?", (email,)):
                skipped += 1
                db.update("leads", row["id"], {"status": "accepted"})
                continue

            db.insert("contacts", {
                "id": new_id("p"),
                **bi_in(row["name"] or email.split("@")[0], "name"),
                "email": email, "status": "subscribed",
                "score": 0, "ltv": 0, "orders": 0,
                "tags": db.dumps(tags),
                "source_id": "research",
                # where it came from, kept with the person
                "source_en": f"Research: {row['source']}"[:200],
                "source_fa": f"تحقیق: {row['source']}"[:200],
                "country": "", "device": "desktop",
                "last_open_at": None, "created_at": iso(),
            })
            db.update("leads", row["id"], {"status": "accepted"})
            added += 1

        if added:
            log(kind="human", actor=principal.id,
                action_en=f"accepted {added} researched leads onto the contact list",
                action_fa=f"{added} سرنخ تحقیق‌شده به فهرست مخاطبان افزوده شد",
                target="contacts", tone="info")

        # The group, made from the tag every one of them now carries. Reused
        # if it already exists, so running the same search twice widens the
        # group instead of making a second one beside it.
        if payload.group and label and (added or skipped):
            existing = db.one(
                "SELECT id FROM segments WHERE name_en = ? OR name_fa = ?", (label, label))
            if existing is None:
                group_id = new_id("seg")
                db.insert("segments", {
                    "id": group_id,
                    "name_en": label, "name_fa": label,
                    "emoji": "", "tint": "", "size": added,
                    "growth": 0, "open_rate": 0, "live": 1,
                    "match_mode": "all",
                    "rules": db.dumps([{"field": "tag", "op": "has", "value": label}]),
                    "created_at": iso(),
                })
                log(kind="human", actor=principal.id,
                    action_en=f"created the group '{label}' from the email finder",
                    action_fa=f"گروه «{label}» از ایمیل‌یاب ساخته شد",
                    target=group_id, tone="good")
            else:
                group_id = existing["id"]
            group_name = label

    return {"added": added, "alreadyThere": skipped,
            "refusedAsUnsubscribed": blocked, "noAddress": noemail,
            "tag": label, "group": group_name, "groupId": group_id}


@router.post("/leads/dismiss")
def dismiss(payload: AcceptIn,
            _: Principal = Depends(requires("contacts.write"))) -> dict:
    _needs_module()
    ids = [str(i) for i in payload.ids][:500]
    if not ids:
        raise HTTPException(status_code=422, detail="No leads were chosen")
    marks = ", ".join("?" for _ in ids)
    with db.transaction():
        db.execute(f"UPDATE leads SET status = 'dismissed' WHERE id IN ({marks})", ids)
    return {"dismissed": len(ids)}
