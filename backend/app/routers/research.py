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
    added, skipped, blocked, noemail = 0, 0, 0, 0

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

    return {"added": added, "alreadyThere": skipped,
            "refusedAsUnsubscribed": blocked, "noAddress": noemail}


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
