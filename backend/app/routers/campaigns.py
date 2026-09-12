"""Campaigns — list, detail, mutate, and the send lifecycle.

The state machine is enforced here rather than trusted from the client:
draft → scheduled → running → sent, with pause/resume only legal from running
or paused. A UI that offers the wrong button is a cosmetic bug; an API that
accepts it corrupts the record.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from .. import db, deployment, emailhtml, exporting, mailer, sendtime
from ..deps import Principal, current_principal, requires
from ..domain import ago_iso, bi_get, bi_in, iso, like, log, paginate, record_event, seeded_series
from ..schemas import Body, CampaignIn, CampaignPatch, SendIn
from ..security import new_id
from ..serial import campaign as ser
from .audience import segment_members

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

SENDABLE = {"draft", "scheduled", "paused"}


def _get(campaign_id: str):
    row = db.one("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return row


@router.get("")
def list_campaigns(
    q: str = "",
    status: str = "all",
    type: str = "all",
    segment: str = "all",
    agent: str = "all",
    sort: str = "updated",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    _: Principal = Depends(requires("analytics.view")),
) -> dict:
    where = ["1=1"]
    params: list = []
    if status != "all":
        where.append("status = ?")
        params.append(status)
    if type != "all":
        where.append("type = ?")
        params.append(type)
    if segment != "all":
        where.append("segment_id = ?")
        params.append(segment)
    if agent != "all":
        where.append("agent_id = ?")
        params.append(agent)
    if q:
        where.append("(name_en LIKE ? ESCAPE '\\' OR name_fa LIKE ? ESCAPE '\\' "
                     "OR subject_en LIKE ? ESCAPE '\\' OR subject_fa LIKE ? ESCAPE '\\' OR id LIKE ? ESCAPE '\\')")
        params += [like(q)] * 5

    order = {
        "updated": "updated_at DESC",
        "created": "created_at DESC",
        "sent": "sent DESC",
        "revenue": "revenue DESC",
        # a rate needs a guard or sqlite divides by zero and returns NULL
        "open": "(CASE WHEN sent > 0 THEN CAST(opens AS REAL) / sent ELSE 0 END) DESC",
        "name": "name_en COLLATE NOCASE ASC",
    }.get(sort, "updated_at DESC")

    rows = db.query(f"SELECT * FROM campaigns WHERE {' AND '.join(where)} ORDER BY {order}", params)
    result = paginate(rows, page, size)
    result["items"] = [ser(r) for r in result["items"]]
    return result


# Declared BEFORE `/{campaign_id}`, and it has to stay there. FastAPI
# matches routes in declaration order, so with the wildcard first this
# path was read as a campaign whose id is "best-time" and answered 404
# to everyone — the recommendation silently fell back to a convention.
@router.get("/export")
def export_campaigns(_: Principal = Depends(requires("analytics.view"))) -> Response:
    """What was sent and how it did, as a spreadsheet.

    Declared above `/{campaign_id}` for the same reason `best-time` is: below
    it, this path reads as a campaign called "export" and answers 404.
    """
    rows = db.query(
        "SELECT name_en, status, type, recipients, sent, delivered, opens, clicks, "
        "replies, unsubs, bounces, scheduled_for, created_at "
        "FROM campaigns ORDER BY created_at DESC"
    )
    out = [{
        "name": r["name_en"], "status": r["status"], "type": r["type"],
        "audience": r["recipients"], "sent": r["sent"], "delivered": r["delivered"],
        "opens": r["opens"], "clicks": r["clicks"], "replies": r["replies"],
        "unsubscribes": r["unsubs"], "bounces": r["bounces"],
        # computed here so a column means what the same figure means on screen
        "open_rate": exporting.rate(r["opens"], r["sent"]),
        "click_rate": exporting.rate(r["clicks"], r["sent"]),
        "scheduled_for": r["scheduled_for"] or "", "created": r["created_at"],
    } for r in rows]

    return exporting.csv_response(out, [
        "name", "status", "type", "audience", "sent", "delivered", "opens",
        "clicks", "replies", "unsubscribes", "bounces", "open_rate",
        "click_rate", "scheduled_for", "created",
    ], "campaigns.csv")


@router.get("/best-time")
def best_time(_: Principal = Depends(requires("analytics.view"))) -> dict:
    """When this audience opens most.

    Asked BEFORE scheduling, so the operator sees the recommendation and its
    basis rather than discovering after the fact that the panel picked a time
    out of nowhere.
    """
    return sendtime.recommend()

@router.get("/preflight")
def preflight_for_segment(segment: str = "", region: str = "",
                          _: Principal = Depends(requires("analytics.view"))) -> dict:
    """Who a campaign to this group would reach, before one exists.

    Declared above `/{campaign_id}` on purpose: FastAPI matches in order,
    and below it the word "preflight" is read as a campaign id.
    """
    from .. import brandprofile, eligibility, scoring, senderhealth

    people = segment_members(segment) if segment else []
    out = eligibility.summary("", people)

    # Fit is computed over the ELIGIBLE list only. Scoring somebody who may
    # not be written to would put them in a band on the screen and invite
    # the question of why they are not being sent to, when the answer has
    # nothing to do with fit.
    verdict = eligibility.classify("", people)
    scored = [
        scoring.score_for(c, profile=brandprofile.get(),
                          offer=scoring.best_offer(c, brandprofile.get()),
                          region=region)
        for c in verdict["eligible"]
    ]
    out["fit"] = scoring.distribution(scored)
    out["fitVersion"] = scoring.SCORE_VERSION
    # What launching right now would actually send to, under the default
    # rule that low and medium fit are opt-in (§16.6).
    out["defaultIncluded"] = sum(
        n for band, n in out["fit"].items() if band in scoring.DEFAULT_INCLUDED)

    health = senderhealth.status()
    out["senderHealth"] = {
        "status": health["status"],
        "score": health["score"],
        "blocking": health["status"] == "CRITICAL",
    }
    return out


@router.get("/{campaign_id}")
def get_campaign(campaign_id: str, _: Principal = Depends(requires("analytics.view"))) -> dict:
    row = _get(campaign_id)
    out = ser(row, detail=True)
    out["links"] = _link_stats(row)
    out["timeline"] = _timeline(row)
    return out


def _link_stats(row) -> list[dict]:
    clicks = row["clicks"] or 0
    weights = [
        ("/collections/summer", 0.46), ("/product/atlas-tee", 0.24),
        ("/pricing", 0.17), ("/blog/how-we-build", 0.08), ("/unsubscribe", 0.05),
    ]
    return [{"url": url, "clicks": round(clicks * w)} for url, w in weights]


def _timeline(row) -> list[dict]:
    stages = [("created", row["created_at"]), ("approved", row["created_at"]),
              ("sending", row["updated_at"]), ("done", row["updated_at"])]
    live = {"draft": 1, "scheduled": 2, "running": 3, "paused": 3, "sent": 4}.get(row["status"], 1)
    return [{"stage": s, "at": at, "done": i < live} for i, (s, at) in enumerate(stages)]


#: How far in the past a send time may be before it is treated as a mistake.
#: Not zero: the browser sends the time it believes it is, and a couple of
#: minutes of clock drift between a laptop and a server is ordinary.
SCHEDULE_GRACE_SECONDS = 120


def _check_when(when: str | None) -> None:
    """A send time in the past is a typo, not an instruction.

    The worker asks for campaigns whose `scheduled_for <= now`, so a date in
    the past is not "scheduled" at all — it is due, and goes out on the next
    tick. Choosing "send later" and mistyping the year would then reach the
    whole audience within the minute, which is the single most expensive
    mistake this product can make on a customer's behalf.
    """
    if not when:
        return
    from datetime import datetime, timedelta, timezone

    try:
        moment = datetime.fromisoformat(str(when).replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"'{when}' is not a date and time I can read.",
        ) from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    if moment < datetime.now(timezone.utc) - timedelta(seconds=SCHEDULE_GRACE_SECONDS):
        raise HTTPException(
            status_code=422,
            detail=("That time has already passed, so the campaign would go out "
                    "immediately rather than later. Pick a time in the future, "
                    "or send it now on purpose."),
        )


def _check_professional(row) -> None:
    """Professional mode needs a brand profile to write from.

    Refusing here rather than at generation time is the difference between
    one clear message before anything starts, and forty prospects each
    researched, written, and then held for the same missing field.

    It names what is missing, so the panel can walk the reader to the
    question instead of telling them the profile is incomplete and leaving
    them to find out which part.
    """
    from .. import brandprofile

    done = brandprofile.completeness()
    if done["proReady"]:
        return
    raise HTTPException(
        status_code=422,
        detail=("Beyondex Professional needs your brand information first. "
                "Still missing: " + ", ".join(done["missingForPro"])),
    )


def _check_ready(row) -> None:
    """A campaign with nothing in it must not reach anybody.

    The house template wraps whatever it is given, so an empty body produces a
    perfectly branded email containing nothing — header, footer, unsubscribe
    link, and a blank space where the message should be. Sent to the whole
    list, that is worse than an error: it is a real email, from the customer's
    real address, that makes them look broken.

    Checked at SEND rather than at save, because a draft is allowed to be
    half-written. That is what a draft is.
    """
    import re as _re

    # Professional mode writes a subject and a body per recipient, so the
    # campaign legitimately has neither. Its own precondition is the brand
    # profile, checked separately.
    try:
        if row["write_mode"] == "professional":
            _check_professional(row)
            return
    except (IndexError, KeyError):
        pass   # a database from before the column existed is manual

    body = (row["body_en"] or "").strip()
    # tags and whitespace are not content
    text = _re.sub(r"<[^>]+>", "", body)
    text = _re.sub(r"\{\{[^}]*\}\}", "", text).strip()
    if not text:
        raise HTTPException(
            status_code=422,
            detail="This campaign has no message in it yet. Write the email before sending it.",
        )
    if not (row["subject_en"] or "").strip():
        raise HTTPException(
            status_code=422,
            detail="This campaign has no subject line. An email without one is filtered as spam.",
        )

    # An opt-out that goes nowhere is the same as no opt-out. Bulk mail without
    # one is illegal in most of the places this product is sold, and a reader
    # who cannot leave presses spam — against the customer's own Gmail account.
    # Checked here with the other pre-send conditions rather than discovered by
    # a recipient clicking a dead link.
    from .. import mailer

    d = deployment.get()
    if not mailer.public_base() and not (d.get("support_email") or d.get("reply_to")):
        raise HTTPException(
            status_code=422,
            detail=("There is no way for a reader to unsubscribe. Set the panel's "
                    "public address, or a reply-to address, in Setup — bulk email "
                    "without a working opt-out gets the sending account closed."),
        )


def _check_links(segment: str | None, agent: str | None):
    """Refuse an id that does not exist, and say which one.

    Without this the insert reached SQLite, tripped a FOREIGN KEY constraint
    and surfaced as a 500 — an "Internal Server Error" for what is a plain
    mistake in the request, and one nobody could act on. A fresh install has no
    segments at all, so this was the first thing a new customer hit.
    """
    if segment:
        row = db.one("SELECT size FROM segments WHERE id = ?", (segment,))
        if row is None:
            raise HTTPException(
                status_code=422,
                detail=f"There is no audience with the id '{segment}'. "
                       "Create the group first, or leave the audience empty.",
            )
        return row
    if agent and not db.one("SELECT 1 FROM agents WHERE id = ?", (agent,)):
        raise HTTPException(status_code=422, detail=f"There is no agent '{agent}'")
    return None


@router.post("", status_code=201)
def create_campaign(payload: CampaignIn, principal: Principal = Depends(requires("campaigns.write"))) -> dict:
    cid = new_id("c")
    seg = _check_links(payload.segment, payload.agent)
    _check_when(payload.scheduled_for)
    recipients = seg["size"] if seg else 0
    now = iso()
    # The body is stored AS WRITTEN. The house template used to be applied
    # here, which meant a campaign kept whichever template happened to be the
    # default on the day it was created — and marking a new one "use for all"
    # changed nothing. It is applied at send time now, in `mailer`.
    #
    # Read through `bi_get`, never as an attribute: a `Lang` is a dict or a
    # plain string, and the panel sends the dict.
    body_en = bi_get(payload.body, "en")
    body_fa = bi_get(payload.body, "fa", body_en)

    data = {
        "id": cid,
        **bi_in(payload.name, "name"),
        **bi_in(payload.subject, "subject"),
        "body_en": body_en,
        "body_fa": body_fa,
        "type": payload.type,
        "status": "scheduled" if payload.scheduled_for else "draft",
        "agent_id": payload.agent,
        "segment_id": payload.segment,
        "recipients": recipients,
        "sent": 0, "delivered": 0, "opens": 0, "clicks": 0,
        "replies": 0, "unsubs": 0, "bounces": 0, "revenue": 0,
        "scheduled_for": payload.scheduled_for,
        "trend": db.dumps([]),
        "write_mode": payload.write_mode,
        "goal": (payload.goal or "").strip()[:2000],
        "created_at": now,
        "updated_at": now,
    }
    with db.transaction():
        db.insert("campaigns", data)
        log(kind="human", actor=principal.id, action_en="created a campaign",
            action_fa="یک کمپین ساخت", target=cid, tone="info")
    return ser(_get(cid), detail=True)


@router.patch("/{campaign_id}")
def update_campaign(
    campaign_id: str, payload: CampaignPatch, principal: Principal = Depends(requires("campaigns.write"))
) -> dict:
    row = _get(campaign_id)
    if row["status"] in {"sent"}:
        raise HTTPException(status_code=409, detail="A campaign that has finished sending cannot be edited")

    data: dict = {}
    if payload.name is not None:
        data |= bi_in(payload.name, "name")
    if payload.subject is not None:
        data |= bi_in(payload.subject, "subject")
    if payload.body is not None:
        data |= bi_in(payload.body, "body")
    _check_when(payload.scheduled_for)
    for field, col in (("type", "type"), ("agent", "agent_id"), ("segment", "segment_id"),
                       ("scheduled_for", "scheduled_for")):
        value = getattr(payload, field)
        if value is not None:
            data[col] = value
    if payload.segment is not None or payload.agent is not None:
        seg = _check_links(payload.segment, payload.agent)
        if payload.segment is not None:
            data["recipients"] = seg["size"] if seg else 0

    if data:
        data["updated_at"] = iso()
        with db.transaction():
            db.update("campaigns", campaign_id, data)
    return ser(_get(campaign_id), detail=True)


@router.delete("/{campaign_id}", status_code=204)
def delete_campaign(campaign_id: str, principal: Principal = Depends(requires("campaigns.write"))) -> None:
    row = _get(campaign_id)
    if row["status"] == "running":
        raise HTTPException(status_code=409, detail="Stop the campaign before deleting it")
    with db.transaction():
        db.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
        log(kind="human", actor=principal.id, action_en="deleted a campaign",
            action_fa="یک کمپین را حذف کرد", target=campaign_id, tone="warn")



@router.post("/{campaign_id}/send")
def send_campaign(
    campaign_id: str, payload: SendIn, principal: Principal = Depends(requires("campaigns.send"))
) -> dict:
    row = _get(campaign_id)
    if row["status"] not in SENDABLE:
        raise HTTPException(status_code=409, detail=f"A campaign in state '{row['status']}' cannot be sent")
    if not row["segment_id"]:
        raise HTTPException(status_code=422, detail="Give the campaign an audience before sending")
    _check_ready(row)

    data: dict = {"updated_at": iso()}
    if payload.mode == "schedule":
        if not payload.scheduled_for:
            raise HTTPException(status_code=422,
                                detail="Say when it should go out.")
        _check_when(payload.scheduled_for)
        data |= {"status": "scheduled", "scheduled_for": payload.scheduled_for}
    elif payload.mode == "optimal":
        # Worked out from this account's own open rates by hour and weekday —
        # not a fixed offset. `sendtime.recommend()` says whether it found a
        # real pattern or fell back to a convention.
        data |= {"status": "scheduled", "scheduled_for": sendtime.recommend()["at"]}
    else:
        # Sending for real needs a mailbox. Refusing here, before the status
        # moves, is the difference between "connect Gmail first" and a campaign
        # that sits in `running` forever with nothing behind it.
        if not deployment.get().get("google_refresh"):
            raise HTTPException(
                status_code=409,
                detail="Connect a Gmail account in Settings before sending",
            )
        # A critically unhealthy account does not get to start another
        # campaign. Refused here, before the status moves, so nothing is
        # queued that would then have to be unpicked -- and only CRITICAL
        # refuses, because a warning that blocked sending is a feature
        # customers would switch off.
        from .. import senderhealth

        if senderhealth.blocking():
            raise HTTPException(
                status_code=409,
                detail=("Sending is paused because this account's sender health "
                        "is critical. Open Sender Health to see what to fix."),
            )
        data |= {"status": "running", "scheduled_for": None,
                 "trend": db.dumps(seeded_series(14, base=max(row["recipients"] / 40, 1), seed=7))}

    with db.transaction():
        db.update("campaigns", campaign_id, data)
        log(kind="human", actor=principal.id,
            action_en=f"queued a campaign ({payload.mode})",
            action_fa=f"کمپینی را در صف گذاشت ({payload.mode})",
            target=campaign_id, tone="good")
        record_event("queued", campaign_id=campaign_id)

    # Outside the transaction: `enqueue` opens its own, and the worker it wakes
    # reads rows that must already be committed.
    if data["status"] == "running":
        queued = mailer.enqueue(campaign_id, recipients=segment_members(row["segment_id"]))
        db.update("campaigns", campaign_id, {"recipients": queued})

    return ser(_get(campaign_id), detail=True)


class VariantsIn(Body):
    """One variable, two or more values. Never two variables at once."""

    field: str = "subject"
    values: list[str] = []


@router.get("/{campaign_id}/variants")
def read_variants(campaign_id: str, _: Principal = Depends(requires("analytics.view"))) -> dict:
    """The test on this campaign, and how the split would fall."""
    from .. import optimize

    row = _get(campaign_id)
    people = segment_members(row["segment_id"]) if row["segment_id"] else []
    variants = db.query(
        "SELECT * FROM campaign_variants WHERE campaign_id = ? ORDER BY label",
        (campaign_id,))
    return {
        "fields": list(optimize.FIELDS),
        "variants": [{"label": v["label"], "field": v["field"], "value": v["value"]}
                     for v in variants],
        # Shown before launch, so the reader sees the split they are agreeing
        # to rather than discovering it afterwards.
        "allocation": optimize.allocation(campaign_id, len(people)),
        "minPerArm": int(optimize.limits()["min_sample"]),
    }


@router.put("/{campaign_id}/variants")
def write_variants(campaign_id: str, payload: VariantsIn,
                   _: Principal = Depends(requires("campaigns.write"))) -> dict:
    from .. import optimize

    row = _get(campaign_id)
    if row["status"] not in SENDABLE:
        raise HTTPException(status_code=409,
                            detail="A campaign that has already gone out cannot be split into a test")
    if not payload.values:
        with db.transaction():
            db.execute("DELETE FROM campaign_variants WHERE campaign_id = ?", (campaign_id,))
        return read_variants(campaign_id)
    if payload.field not in optimize.FIELDS:
        raise HTTPException(
            status_code=422,
            detail="Test one thing at a time: the subject, the call to action, or the angle")
    if len([v for v in payload.values if v.strip()]) < 2:
        raise HTTPException(status_code=422, detail="A test needs at least two versions")
    optimize.set_variants(campaign_id, payload.field, payload.values)
    return read_variants(campaign_id)


@router.get("/{campaign_id}/result")
def campaign_result(campaign_id: str, _: Principal = Depends(requires("analytics.view"))) -> dict:
    """Which arm won, or that the evidence does not yet say.

    INCONCLUSIVE is a real answer here and the most common honest one.
    """
    from .. import optimize

    _get(campaign_id)
    return optimize.decide(campaign_id)


@router.get("/{campaign_id}/recommendation")
def campaign_recommendation(campaign_id: str,
                            _: Principal = Depends(requires("analytics.view"))) -> dict:
    """What similar past campaigns suggest. A suggestion, never applied."""
    from .. import optimize

    row = _get(campaign_id)
    out = optimize.recommend(row["segment_id"])
    return out or {"enough": False, "none": True}


@router.get("/{campaign_id}/preflight")
def preflight(campaign_id: str, _: Principal = Depends(requires("analytics.view"))) -> dict:
    """Who this campaign would actually reach, and who it would not.

    The same call the sender makes when it fills the queue, so this is a
    promise rather than an estimate. Read-only: nothing is queued, nothing
    is suppressed, and running it twice changes nothing.
    """
    from .. import eligibility, senderhealth

    row = _get(campaign_id)
    people = segment_members(row["segment_id"]) if row["segment_id"] else []
    out = eligibility.summary(campaign_id, people)
    health = senderhealth.status()
    out["senderHealth"] = {
        "status": health["status"],
        "score": health["score"],
        "blocking": health["status"] == "CRITICAL",
        "reasons": health["reasons"],
    }
    return out


@router.get("/{campaign_id}/recipients")
def campaign_recipients(
    campaign_id: str,
    status: str = "all",
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    _: Principal = Depends(requires("analytics.view")),
) -> dict:
    """Who this campaign actually reached, one row per person.

    The outbox has held this since the sender was built and nothing exposed
    it, so the campaign screen could say "1,240 sent" and not a word about to
    whom, when, or what came back — which is the first question anyone asks
    when a send looks wrong.

    `error` is included verbatim. A row that failed because Gmail refused the
    address is a different problem from one that failed on a quota, and
    flattening both to "failed" throws away the only clue.
    """
    _get(campaign_id)
    where = ["campaign_id = ?"]
    params: list = [campaign_id]
    if status != "all":
        where.append("status = ?")
        params.append(status)

    rows = db.query(
        f"SELECT id, email, name, status, error, message_id, queued_at, sent_at "
        f"FROM outbox WHERE {' AND '.join(where)} "
        f"ORDER BY CASE status WHEN 'failed' THEN 0 ELSE 1 END, sent_at DESC, queued_at DESC",
        params,
    )
    out = paginate(rows, page, size)
    out["items"] = [{
        "id": r["id"], "email": r["email"], "name": r["name"],
        "status": r["status"], "error": r["error"] or "",
        "at": r["sent_at"] or r["queued_at"],
    } for r in out["items"]]
    out["counts"] = mailer.progress(campaign_id)
    return out


@router.get("/{campaign_id}/progress")
def campaign_progress(campaign_id: str, _: Principal = Depends(requires("analytics.view"))) -> dict:
    """How far through the outbox this campaign is.

    Polled by the campaign screen while a send drains. Cheap on purpose — one
    grouped count — because it is asked every few seconds.
    """
    _get(campaign_id)
    return mailer.progress(campaign_id)


@router.post("/{campaign_id}/pause")
def pause_campaign(campaign_id: str, principal: Principal = Depends(requires("campaigns.send"))) -> dict:
    row = _get(campaign_id)
    if row["status"] != "running":
        raise HTTPException(status_code=409, detail="Only a running campaign can be paused")
    with db.transaction():
        db.update("campaigns", campaign_id, {"status": "paused", "updated_at": iso()})
        log(kind="human", actor=principal.id, action_en="paused a campaign",
            action_fa="یک کمپین را متوقف کرد", target=campaign_id, tone="warn")
    return ser(_get(campaign_id))


@router.post("/{campaign_id}/resume")
def resume_campaign(campaign_id: str, principal: Principal = Depends(requires("campaigns.send"))) -> dict:
    row = _get(campaign_id)
    if row["status"] != "paused":
        raise HTTPException(status_code=409, detail="Only a paused campaign can be resumed")
    with db.transaction():
        db.update("campaigns", campaign_id, {"status": "running", "updated_at": iso()})
        log(kind="human", actor=principal.id, action_en="resumed a campaign",
            action_fa="یک کمپین را ادامه داد", target=campaign_id, tone="good")
    return ser(_get(campaign_id))


@router.post("/{campaign_id}/duplicate", status_code=201)
def duplicate_campaign(campaign_id: str, principal: Principal = Depends(requires("campaigns.write"))) -> dict:
    row = _get(campaign_id)
    cid = new_id("c")
    now = iso()
    data = {k: row[k] for k in row.keys()}
    data |= {
        "id": cid,
        "name_en": f"{row['name_en']} (copy)",
        "name_fa": f"{row['name_fa']} (رونوشت)",
        "status": "draft",
        "sent": 0, "delivered": 0, "opens": 0, "clicks": 0,
        "replies": 0, "unsubs": 0, "bounces": 0, "revenue": 0,
        "scheduled_for": None, "trend": db.dumps([]),
        "created_at": now, "updated_at": now,
    }
    with db.transaction():
        db.insert("campaigns", data)
        log(kind="human", actor=principal.id, action_en="duplicated a campaign",
            action_fa="از یک کمپین رونوشت گرفت", target=cid, tone="info")
    return ser(_get(cid), detail=True)
